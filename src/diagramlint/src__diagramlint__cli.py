"""diagramlint command line (scaffold surface).

Usage:
  diagramlint check DIAGRAM --code PATH [--config diagramcheck.toml]
                    [--strict] [--format text|json]

The diagram may be Mermaid text (.mmd / .md) or a JSON diagram (.json).
Python code under --code is scanned with the built-in AST extractor.
An optional TOML config may carry a [mapping] table (diagram node ->
component name) and [[waivers]] entries with source, target and reason.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

from .check import Waiver, apply_baseline, check, exit_code
from .jsextract import extract_javascript
from .jsondiagram import parse_json_diagram
from .mermaid import parse_mermaid
from .pyextract import extract_python


def _load_diagram(path: Path):
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return parse_json_diagram(text)
    return parse_mermaid(text)


def _load_config(path: Path | None):
    mapping: dict[str, str] = {}
    waivers: list[Waiver] = []
    if path is not None:
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        mapping = {str(k): str(v) for k, v in data.get("mapping", {}).items()}
        for w in data.get("waivers", []):
            waivers.append(Waiver(str(w["source"]), str(w["target"]),
                                  str(w.get("reason", ""))))
    return mapping, waivers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="diagramlint")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check", help="check a diagram against code")
    p.add_argument("diagram")
    p.add_argument("--code", required=True, help="root of the Python code to scan")
    p.add_argument("--config", default=None)
    p.add_argument("--granularity", choices=["package","module"], default="package",
                   help="component granularity for the Python extractor")
    p.add_argument("--lang", choices=["auto", "python", "javascript"], default="auto",
                   help="which extractor to run (auto: Python + JavaScript/TypeScript)")
    p.add_argument("--strict", action="store_true",
                   help="treat no-evidence edges as errors")
    p.add_argument("--baseline", default=None,
                   help="baseline receipt JSON: known findings are reported "
                        "as known drift; only new reversed (or, with "
                        "--strict, new no-evidence) findings fail")
    p.add_argument("--format", choices=["text", "json"], default="text")
    b = sub.add_parser("baseline", help="write the current receipt as a baseline file")
    b.add_argument("diagram")
    b.add_argument("--code", required=True, help="root of the code to scan")
    b.add_argument("--config", default=None)
    b.add_argument("--granularity", choices=["package", "module"], default="package")
    b.add_argument("--lang", choices=["auto", "python", "javascript"], default="auto")
    b.add_argument("--out", required=True, help="baseline JSON file to write")
    args = parser.parse_args(argv)

    diagram = _load_diagram(Path(args.diagram))
    mapping, waivers = _load_config(Path(args.config) if args.config else None)
    truth = []
    if args.lang in ("auto", "python"):
        truth += extract_python(Path(args.code), granularity=args.granularity)
    if args.lang in ("auto", "javascript"):
        truth += extract_javascript(Path(args.code))
    receipt = check(diagram, truth, waivers=waivers, mapping=mapping)

    if args.command == "baseline":
        Path(args.out).write_text(json.dumps(receipt, indent=2) + "\n",
                                  encoding="utf-8")
        print(f"baseline written: {args.out} "
              f"({len(receipt['findings'])} findings recorded)")
        return 0

    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        receipt = apply_baseline(receipt, baseline)
    code = exit_code(receipt, strict=args.strict)

    if args.format == "json":
        print(json.dumps(receipt, indent=2))
    else:
        for f in receipt["findings"]:
            line = f"{f['code']} {f['verdict']}: {f['source']} -> {f['target']}"
            if f["evidence"]:
                ev = f["evidence"][0]
                line += f"  ({ev['file']}:{ev['line']})"
            if f.get("baseline"):
                line += "  [known drift]"
            print(line)
        print(f"counts: {receipt['counts']}; exit {code}")
        if "drift" in receipt:
            d = receipt["drift"]
            print(f"drift: {d['known_count']} known, "
                  f"{len(d['new'])} new, {len(d['resolved'])} resolved")
    return code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
