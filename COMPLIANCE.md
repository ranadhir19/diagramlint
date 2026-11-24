# Compliance record — diagramlint (scaffold)

Recorded 2026-11-23 at the scaffold step. The authoritative record is
the 2026-11-22 addendum in the brand goal's IP/legal compliance ledger
(IP_LEGAL_COMPLIANCE_LEDGER_2026-11-10.md); this file is the in-tree
summary.

- Name: `diagramlint` — collision-checked 2026-11-22 (GitHub search
  total 0, PyPI 404, npm 404, absent from the ranadhir19 namespace)
  and re-verified the same evening.
- Originality: the subject (diagram-to-code conformance) was taken as
  an idea only, under the reference rule. No reference product's name,
  code, copy, structure or text is used. The verdict taxonomy, rule
  codes (DL100–DL500), receipt fields and all code and copy in this
  tree were authored for this deliverable. In particular, the receipt
  uses diagramlint's own field names and codes.
- Licence: MIT, complete standard text at repo root (LICENSE),
  consistent with pyproject.toml.
- Dependencies: none. The package, tests and harness are Python
  standard library only. The compliance ledger's planned-extractor
  sweep (dependency-cruiser MIT, Madge MIT, pydeps BSD-2-Clause,
  tree-sitter MIT — all permissive) stands for the future
  JavaScript/TypeScript step; no such dependency is locked in this
  scaffold, and any adoption must be recorded in the ledger first.
- Assets: none vendored. All fixtures are the bundled sample app,
  authored in-tree.
- MCP/skill surface (added 2026-11-24): the MCP server is authored
  in-tree on the Python standard library only (JSON-RPC over stdio);
  the protocol method and message names are the public MCP spec's
  interface vocabulary, and all tool naming, descriptions and the
  agent skill text are diagramlint's own. No new dependency, asset
  or vendored code was introduced.
- Scans: secrets-pattern sweep and the reference-integrity scan are
  stages of validate.py and must pass on the exact tree before any
  publication. Publication has NOT happened: this scaffold is local
  only, and read-back verification will be required after any push.
