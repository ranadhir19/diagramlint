"""Bidirectional conformance check: diagram edges vs. truth edges.

diagramlint's own verdict taxonomy and rule codes (authored for this
tool; no other tool's schema, codes or text are used):

  DL100 supported            direct import evidence for the diagram edge
  DL101 transitive           a code path exists, no direct edge
  DL200 reversed             evidence runs in the opposite direction
  DL300 no-evidence          no code evidence in either direction
  DL400 missing-from-diagram a code edge between mapped components that
                             the diagram does not show (report-only)
  DL500 waived               matched by an auditable waiver in config
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .graph import Diagram, TruthEdge

CODES = {
    "supported": "DL100",
    "transitive": "DL101",
    "reversed": "DL200",
    "no-evidence": "DL300",
    "missing-from-diagram": "DL400",
    "waived": "DL500",
}


@dataclass
class Finding:
    code: str
    verdict: str
    source: str
    target: str
    evidence: list[dict] = field(default_factory=list)
    note: str = ""


@dataclass
class Waiver:
    source: str
    target: str
    reason: str


def _reachable(truth: dict[tuple[str, str], list[TruthEdge]], start: str) -> set[str]:
    seen: set[str] = set()
    stack = [start]
    adjacency: dict[str, set[str]] = {}
    for (a, _b) in truth:
        adjacency.setdefault(a, set()).add(_b)
    while stack:
        cur = stack.pop()
        for nxt in adjacency.get(cur, set()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def check(diagram: Diagram, truth_edges: list[TruthEdge],
          waivers: list[Waiver] | None = None,
          mapping: dict[str, str] | None = None) -> dict:
    mapping = mapping or {}
    waivers = waivers or []

    def node(name: str) -> str:
        return mapping.get(name, name)

    truth: dict[tuple[str, str], list[TruthEdge]] = {}
    for edge in truth_edges:
        truth.setdefault((edge.source, edge.target), []).append(edge)

    def waived(src: str, dst: str) -> Waiver | None:
        for w in waivers:
            if w.source == src and w.target == dst:
                return w
        return None

    findings: list[Finding] = []
    diagram_pairs: set[tuple[str, str]] = set()
    for edge in diagram.edges:
        src, dst = node(edge.source), node(edge.target)
        diagram_pairs.add((src, dst))
        w = waived(src, dst)
        if w:
            findings.append(Finding(CODES["waived"], "waived", src, dst,
                                    note=w.reason))
        elif (src, dst) in truth:
            ev = [{"file": e.evidence.file, "line": e.evidence.line,
                   "detail": e.evidence.detail} for e in truth[(src, dst)]]
            findings.append(Finding(CODES["supported"], "supported", src, dst, ev))
        elif (dst, src) in truth:
            ev = [{"file": e.evidence.file, "line": e.evidence.line,
                   "detail": e.evidence.detail} for e in truth[(dst, src)]]
            findings.append(Finding(CODES["reversed"], "reversed", src, dst, ev,
                                    "code evidence runs the other way"))
        elif dst in _reachable(truth, src):
            findings.append(Finding(CODES["transitive"], "transitive", src, dst,
                                    note="code path exists; no direct edge"))
        else:
            findings.append(Finding(CODES["no-evidence"], "no-evidence", src, dst,
                                    note="no code evidence in either direction"))

    mapped = {node(n) for n in diagram.nodes}
    for (src, dst), edges in sorted(truth.items()):
        if src in mapped and dst in mapped and src != dst:
            if (src, dst) not in diagram_pairs and (dst, src) not in diagram_pairs:
                ev = [{"file": e.evidence.file, "line": e.evidence.line,
                       "detail": e.evidence.detail} for e in edges]
                findings.append(Finding(CODES["missing-from-diagram"],
                                        "missing-from-diagram", src, dst, ev,
                                        "report-only: a curated diagram may omit edges"))

    counts: dict[str, int] = {}
    for f in findings:
        counts[f.verdict] = counts.get(f.verdict, 0) + 1
    return {
        "tool": "diagramlint",
        "receipt_version": 1,
        "counts": counts,
        "findings": [
            {"code": f.code, "verdict": f.verdict, "source": f.source,
             "target": f.target, "evidence": f.evidence, "note": f.note}
            for f in findings
        ],
    }


def finding_key(f: dict) -> tuple[str, str, str]:
    """Stable identity of a finding for baseline comparison."""
    return (f["verdict"], f["source"], f["target"])


def apply_baseline(receipt: dict, baseline: dict) -> dict:
    """Annotate a receipt against a saved baseline receipt.

    Findings whose (verdict, source, target) key already appears in the
    baseline are marked ``baseline: true`` — known drift, reported but
    not new. Baseline keys absent from the current receipt are
    ``resolved``. The receipt gains a ``drift`` section; the input
    receipt is annotated in place and returned.
    """
    base_keys = {finding_key(f) for f in baseline.get("findings", [])}
    new_keys: list[list[str]] = []
    known = 0
    for f in receipt["findings"]:
        if finding_key(f) in base_keys:
            f["baseline"] = True
            known += 1
        else:
            f["baseline"] = False
            new_keys.append(list(finding_key(f)))
    current_keys = {finding_key(f) for f in receipt["findings"]}
    receipt["drift"] = {
        "known_count": known,
        "new": sorted(new_keys),
        "resolved": sorted(list(k) for k in base_keys - current_keys),
    }
    return receipt


def exit_code(receipt: dict, strict: bool = False) -> int:
    # With a baseline applied, only NEW findings can fail the build:
    # known drift is reported, not re-litigated on every run.
    findings = receipt["findings"]
    if "drift" in receipt:
        findings = [f for f in findings if not f.get("baseline")]
    verdicts = {f["verdict"] for f in findings}
    if "reversed" in verdicts:
        return 1
    if strict and "no-evidence" in verdicts:
        return 1
    return 0
