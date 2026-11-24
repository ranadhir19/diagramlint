"""Statically extract Python import edges with file:line evidence.

Walks a source root, parses each ``.py`` file with the standard-library
``ast`` module, and records every import of a module that lives inside
the scanned tree as a TruthEdge. Two granularities are supported:

- ``package`` (default): components are top-level package names. This
  suits multi-package trees but collapses a single-package src-layout
  repo to zero intra-package edges (measured 2026-11-23 on pairseal
  and runreckon).
- ``module``: components are full dotted module names, so imports
  between modules of one package are visible. Diagram node names then
  name modules (a ``[mapping]`` entry can roll modules up if wanted).

External (installed) imports are ignored: diagramlint judges a diagram
against the repository's own dependency graph, not the ecosystem's.
"""

from __future__ import annotations

import ast
from pathlib import Path

from .graph import Evidence, TruthEdge


def _modules(root: Path) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        parts = list(rel.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            found[".".join(parts)] = path
    return found


def component_of(module: str, granularity: str = "package") -> str:
    if granularity == "module":
        return module
    if granularity != "package":
        raise ValueError(f"unknown granularity: {granularity!r}")
    return module.split(".")[0]


def extract_python(root: Path, granularity: str = "package") -> list[TruthEdge]:
    modules = _modules(root)
    by_component = {component_of(m, granularity) for m in modules}
    edges: list[TruthEdge] = []
    for module, path in sorted(modules.items()):
        src_component = component_of(module, granularity)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            imported: str | None = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported = alias.name
                    _maybe_add(edges, modules, by_component, src_component,
                               imported, path, root, node.lineno, granularity)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0:
                    base_mod = node.module or ""
                else:
                    base = module.rsplit(".", node.level)[0] if "." in module else ""
                    base_mod = ".".join(p for p in [base, node.module or ""] if p)
                if base_mod:
                    # `from pkg import sub` may import the submodule
                    # pkg.sub; try that first, fall back to pkg itself.
                    added = False
                    for alias in node.names:
                        before = len(edges)
                        _maybe_add(edges, modules, by_component, src_component,
                                   f"{base_mod}.{alias.name}", path, root,
                                   node.lineno, granularity)
                        added = added or len(edges) > before
                    if not added:
                        _maybe_add(edges, modules, by_component, src_component,
                                   base_mod, path, root, node.lineno, granularity)
    return edges


def _maybe_add(edges, modules, by_component, src_component, imported,
               path, root, lineno, granularity="package") -> None:
    if not imported:
        return
    dst = component_of(imported, granularity)
    if dst in by_component and dst != src_component:
        edges.append(TruthEdge(src_component, dst, Evidence(
            str(path.relative_to(root.parent)) if path.is_relative_to(root.parent) else str(path),
            lineno, f"import {imported}")))
