"""Normalised graph types shared by diagram parsers and code extractors."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    label: str = ""


@dataclass
class Diagram:
    nodes: list[str] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)


@dataclass(frozen=True)
class Evidence:
    file: str
    line: int
    detail: str


@dataclass(frozen=True)
class TruthEdge:
    source: str
    target: str
    evidence: Evidence
