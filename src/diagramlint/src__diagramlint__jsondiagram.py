"""Parse a JSON architecture diagram into a normalised Diagram.

The input is any JSON object carrying a ``nodes`` list and an ``edges``
list. Node entries may be strings or objects with an ``id`` (or ``name``)
field; edge entries are objects with ``from``/``source`` and
``to``/``target`` fields. This is diagramlint's own tolerant reader for
a generic data shape — it implements no other tool's schema, rule codes
or receipt format.
"""

from __future__ import annotations

import json

from .graph import Diagram, Edge


def parse_json_diagram(text: str) -> Diagram:
    data = json.loads(text)
    diagram = Diagram()
    for node in data.get("nodes", []):
        if isinstance(node, str):
            diagram.nodes.append(node)
        elif isinstance(node, dict):
            name = node.get("id") or node.get("name")
            if name:
                diagram.nodes.append(str(name))
    for edge in data.get("edges", []):
        if not isinstance(edge, dict):
            continue
        src = edge.get("from") or edge.get("source")
        dst = edge.get("to") or edge.get("target")
        if src and dst:
            diagram.edges.append(Edge(str(src), str(dst), str(edge.get("label", ""))))
    return diagram
