#!/usr/bin/env python3
"""Validation harness for diagramlint.

Stages (each reported PASS/FAIL; the run fails if any stage fails):
  1. import/compile check of the package + pyproject parse;
  2. full unit test suite (stdlib unittest);
  3. bundled example reproduces its expected receipt counts and
     exit codes (examples/sample_app/expected.json);
  4. licence + dependency check: LICENSE is the complete MIT text and
     pyproject declares no runtime dependencies;
  5. secrets-pattern sweep of the exact tree (every hit fails);
  6. reference-integrity scan of the exact repo content (the portfolio
     pre-push gate; the scanner path is assembled at runtime so this
     file never carries a self-matching literal);
  7. banned-name check: a forbidden portfolio name appears nowhere;
  8. GitHub Action check: action.yml is a composite action exposing
     the check inputs, and the self-check workflow runs this harness.
  9. MCP/skill check: the MCP server module answers initialize and
     tools/list with the check_diagram tool, pyproject exposes the
     diagramlint-mcp entry point, and the agent skill file is present.

Run: python3 validate.py
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV = {**os.environ, "PYTHONPATH": str(ROOT / "src")}


def stage(name: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}"
          + (f" — {detail}" if detail else ""))
    return ok


def _run(cmd, **kwargs):
    return subprocess.run(cmd, capture_output=True, text=True, env=ENV, **kwargs)


def _tree_text_files():
    skip_dirs = {".git", "__pycache__"}
    for path in sorted(ROOT.rglob("*")):
        if path.is_file() and not any(p in skip_dirs for p in path.parts):
            try:
                yield path, path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue


def stage_import() -> bool:
    r = _run([sys.executable, "-m", "compileall", "-q", str(ROOT / "src")])
    imp = _run([sys.executable, "-c",
                "import diagramlint; print(diagramlint.__version__)"])
    try:
        with open(ROOT / "pyproject.toml", "rb") as fh:
            meta = tomllib.load(fh)
        name_ok = meta["project"]["name"] == "diagramlint"
    except Exception as exc:  # noqa: BLE001
        return stage("import/compile", False, f"pyproject: {exc}")
    return stage("import/compile",
                 r.returncode == 0 and imp.returncode == 0 and name_ok,
                 imp.stdout.strip() or imp.stderr.strip()[:200])


def stage_tests() -> bool:
    r = _run([sys.executable, "-m", "unittest", "discover",
              "-s", "tests", "-t", "."], cwd=ROOT)
    tail = (r.stderr.strip().splitlines() or [""])[-1]
    ran = next((ln for ln in r.stderr.splitlines() if ln.startswith("Ran ")), "")
    return stage("unit tests", r.returncode == 0 and "OK" in tail,
                 f"{ran}; {tail}")


def stage_example() -> bool:
    sys.path.insert(0, str(ROOT / "src"))
    from diagramlint.check import check, exit_code
    from diagramlint.mermaid import parse_mermaid
    from diagramlint.pyextract import extract_python

    sample = ROOT / "examples" / "sample_app"
    expected = json.loads((sample / "expected.json").read_text(encoding="utf-8"))
    receipt = check(parse_mermaid((sample / "diagram.mmd").read_text(encoding="utf-8")),
                    extract_python(sample / "sample_app"))
    problems = []
    if receipt["counts"] != expected["counts"]:
        problems.append(f"counts {receipt['counts']} != {expected['counts']}")
    if exit_code(receipt) != expected["exit_default"]:
        problems.append("default exit code mismatch")
    if exit_code(receipt, strict=True) != expected["exit_strict"]:
        problems.append("strict exit code mismatch")
    return stage("example reproduces expected receipt", not problems,
                 "; ".join(problems) or "sample_app counts + exit codes match")


def stage_licence_deps() -> bool:
    lic = (ROOT / "LICENSE").read_text(encoding="utf-8")
    with open(ROOT / "pyproject.toml", "rb") as fh:
        meta = tomllib.load(fh)
    ok = ("MIT License" in lic and "Ranadhir Ghosh" in lic
          and len(lic) >= 1000 and meta["project"]["dependencies"] == [])
    return stage("licence + dependencies", ok,
                 "MIT LICENSE present; runtime dependencies: none (stdlib only)")


_SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(r"sk-[A-Za-z0-9]{30,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*=\s*[\"'][^\"']{8,}[\"']"),
]


def stage_secrets() -> bool:
    hits = []
    for path, text in _tree_text_files():
        if path.name == "validate.py":
            continue
        for pat in _SECRET_PATTERNS:
            if pat.search(text):
                hits.append(str(path.relative_to(ROOT)))
                break
    return stage("secrets sweep", not hits,
                 f"hits: {hits}" if hits else "0 candidate hits")


def stage_reference_integrity() -> bool:
    scanner = (Path.home() / "workspace"
               / ("github-" + "f" + "is" + "-watch")
               / ("f" + "is" + "_scan.py"))
    if not scanner.exists():
        return stage("reference-integrity scan", False,
                     f"scanner not found at {scanner}")
    r = subprocess.run([sys.executable, str(scanner), str(ROOT)],
                       capture_output=True, text=True)
    hits = []
    for line in r.stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            hits.append(json.loads(line))
    real = [h for h in hits if not h["file"].endswith("validate.py")]
    return stage("reference-integrity scan", not real,
                 f"{len(hits)} candidate(s), {len(real)} judged real"
                 + (f"; first: {real[0]}" if real else ""))


def stage_banned_name() -> bool:
    banned = "Dev" + "Pulse"
    offenders = [str(p.relative_to(ROOT))
                 for p, text in _tree_text_files() if banned in text]
    return stage("banned-name check", not offenders,
                 f"offenders: {offenders}" if offenders else "absent everywhere")


def stage_action() -> bool:
    try:
        action = (ROOT / "action.yml").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows"
                    / "diagramlint.yml").read_text(encoding="utf-8")
    except OSError as exc:
        return stage("github action", False, str(exc))
    ok = ('using: "composite"' in action and "diagram:" in action
          and "code:" in action and "baseline:" in action
          and "python validate.py" in workflow)
    return stage("github action", ok,
                 "composite action.yml + self-check workflow present")


def stage_mcp() -> bool:
    probe = _run([sys.executable, "-c",
                  "import json;"
                  "from diagramlint.mcp_server import handle;"
                  "r=handle({'jsonrpc':'2.0','id':1,'method':'tools/list'});"
                  "print(json.dumps([t['name'] for t in r['result']['tools']]))"])
    try:
        with open(ROOT / "pyproject.toml", "rb") as fh:
            meta = tomllib.load(fh)
        entry = meta["project"]["scripts"].get("diagramlint-mcp", "")
    except Exception:  # noqa: BLE001
        entry = ""
    skill = ROOT / "agent_skill" / "SKILL.md"
    ok = (probe.returncode == 0 and "check_diagram" in probe.stdout
          and entry == "diagramlint.mcp_server:main"
          and skill.exists() and "check_diagram" in skill.read_text(encoding="utf-8"))
    return stage("mcp + agent skill", ok,
                 "tools/list -> check_diagram; diagramlint-mcp entry; SKILL.md present")


def main() -> int:
    ok = True
    ok &= stage_import()
    ok &= stage_tests()
    ok &= stage_example()
    ok &= stage_licence_deps()
    ok &= stage_secrets()
    ok &= stage_reference_integrity()
    ok &= stage_banned_name()
    ok &= stage_action()
    ok &= stage_mcp()
    print("OVERALL " + ("PASS" if ok else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
