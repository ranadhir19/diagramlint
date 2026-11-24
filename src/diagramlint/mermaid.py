"""Parse Mermaid flowchart/graph text into a normalised Diagram.

Supports the common agent-generated shapes: a ``flowchart`` or ``graph``
header, node declarations with optional [label] / (label) / {label}
wrappers, directed edges (--> , --- >, ==>) with optional |label| or
-- label --> forms, and subgraph blocks (their membership is flattened;
component mapping is handled by the checker, not the parser).
Original parser written for diagramlint; no third-party code is used.
"""

from __future__ import annotations

import re

from .graph import Diagram, Edge

_NODE = r"[A-Za-z0-9_][A-Za-z0-9_.\-]*"
_EDGE_RE = re.compile(
    rf"^\s*({_NODE})(?:\s*\[[^\]]*\]|\s*\([^)]*\)|\s*\{{[^}}]*\}})?"
    rf"\s*(?:-->|==>|-\.->|---)\s*"
    rf"(?:\|[^|]*\||--\s*[^-]+?-->)?\s*"
    rf"({_NODE})(?:\s*\[[^\]]*\]|\s*\([^)]*\)|\s*\{{[^}}]*\}})?\s*$"
)
_NODE_RE = re.compile(rf"^\s*({_NODE})(?:\s*[\[({{].*)?$")


def parse_mermaid(text: str) -> Diagram:
    diagram = Diagram()
    seen: set[str] = set()

    def add_node(name: str) -> None:
        if name and name not in seen and name not in ("flowchart", "graph", "subgraph", "end"):
            seen.add(name)
            diagram.nodes.append(name)

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("%%"):
            continue
        if line.startswith(("flowchart", "graph ")) or line == "graph":
            continue
        m = _EDGE_RE.match(line)
        if m:
            src, dst = m.group(1), m.group(2)
            add_node(src)
            add_node(dst)
            diagram.edges.append(Edge(src, dst))
            continue
        if line.startswith("subgraph") or line == "end":
            continue
        m = _NODE_RE.match(line)
        if m:
            add_node(m.group(1))
    return diagram
