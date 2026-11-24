"""Statically extract JavaScript/TypeScript import edges with evidence.

Walks a source root, scans each ``.js``/``.jsx``/``.mjs``/``.cjs``/
``.ts``/``.tsx`` file line by line, and records every relative import
of a module that lives inside the scanned tree as a TruthEdge.

Components are file modules: the path relative to the scanned root,
without its extension, in POSIX form, with a trailing ``/index``
collapsed to the containing folder (``src/util/index.ts`` is the
module ``src/util``). Diagram node names then name modules; a
``[mapping]`` entry can roll modules up if wanted.

Recognised import forms (all with the specifier in single or double
quotes): static ``import ... from '...'``, bare ``import '...'``,
``export ... from '...'``, CommonJS ``require('...')`` and dynamic
``import('...')``. Bare specifiers (packages, ``node:`` builtins) are
ignored: diagramlint judges a diagram against the repository's own
dependency graph, not the ecosystem's. Resolution tries the specifier
as written, then with each known extension, then as a folder with an
``index`` file, and maps a ``.js`` specifier onto a ``.ts`` source
(the standard TypeScript ESM convention).

This is a line scanner, not a full parser: an import-shaped string
inside a comment or a string literal can be recorded. That limitation
is deliberate for a dependency-free scaffold and is recorded in the
README; evidence lines let a reader audit every edge.
"""

from __future__ import annotations

import re
from pathlib import Path

from .graph import Evidence, TruthEdge

EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
SKIP_DIRS = {"node_modules", "dist", "build", ".git", "coverage"}

_PATTERNS = [
    re.compile(r"""^\s*import\s+(?:[^'"]*?\s+from\s+)?['"]([^'"]+)['"]"""),
    re.compile(r"""^\s*export\s+[^'"]*?\s+from\s+['"]([^'"]+)['"]"""),
    re.compile(r"""\brequire\(\s*['"]([^'"]+)['"]\s*\)"""),
    re.compile(r"""\bimport\(\s*['"]([^'"]+)['"]\s*\)"""),
]


def _module_name(rel: Path) -> str:
    stem = rel.with_suffix("").as_posix()
    if stem.endswith("/index"):
        stem = stem[: -len("/index")]
    return stem


def _modules(root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix not in EXTENSIONS:
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        found[_module_name(path.relative_to(root))] = path
    return found


def _resolve(spec: str, importer: Path, root: Path,
             modules: dict[str, Path]) -> str | None:
    if not (spec.startswith("./") or spec.startswith("../")):
        return None
    base = (importer.parent / spec).resolve()
    try:
        rel = base.relative_to(root.resolve())
    except ValueError:
        return None
    stem = rel.as_posix()
    candidates = [stem]
    for ext in (".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"):
        if stem.endswith(ext):
            candidates.append(stem[: -len(ext)])
            break
    for cand in candidates:
        # A folder with an index file is keyed by the folder name
        # itself (see _module_name), so this also covers index files.
        if cand in modules:
            return cand
    return None


def extract_javascript(root: Path) -> list[TruthEdge]:
    root = Path(root)
    modules = _modules(root)
    edges: list[TruthEdge] = []
    for module, path in sorted(modules.items()):
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(lines, start=1):
            for pat in _PATTERNS:
                m = pat.search(line)
                if not m:
                    continue
                spec = m.group(1)
                dst = _resolve(spec, path, root, modules)
                if dst is not None and dst != module:
                    ev_file = (str(path.relative_to(root.parent))
                               if path.is_relative_to(root.parent) else str(path))
                    edges.append(TruthEdge(module, dst, Evidence(
                        ev_file, lineno, f"import {spec}")))
                break
    return edges
