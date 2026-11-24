# diagramlint — agent skill

Use diagramlint after drawing or editing an architecture diagram,
before committing it. A well-formed diagram can still be untrue:
edges can be invented, reversed, or silently omit a dependency the
code has.

## When to run it

- You generated or edited a Mermaid or JSON architecture diagram.
- A refactor moved imports between components shown in a diagram.
- A reviewer asks whether the diagram matches the code.

## How

Preferred, when the MCP server is available: call the
`check_diagram` tool with `diagram_path` and `code_path` (optional:
`config_path`, `baseline_path`, `strict`, `lang`, `granularity`).
It returns the receipt described below.

From a shell:

```bash
diagramlint check docs/architecture.mmd --code src --format json
# single-package Python trees:
diagramlint check docs/architecture.mmd --code src --granularity module
# record known drift, then fail only on new findings:
diagramlint baseline docs/architecture.mmd --code src --out base.json
diagramlint check docs/architecture.mmd --code src --baseline base.json
```

## Reading the receipt

- `DL100 supported` / `DL101 transitive` — the edge is true.
- `DL200 reversed` — the code evidence runs the other way; fix the
  arrow direction. This fails the check.
- `DL300 no-evidence` — no code evidence either way; remove the
  edge, or record a waiver in `diagramcheck.toml` with a reason if
  the dependency is real but invisible to static analysis (for
  example dependency injection). Fails only under `--strict`.
- `DL400 missing-from-diagram` — a real edge between diagrammed
  components the diagram omits; report-only, add it if the diagram
  aims to be complete.
- `DL500 waived` — matched by a recorded waiver.

Every verdict carries file:line evidence. Repair the diagram (or
the code) until reversed and unwaived no-evidence findings are
gone; do not waive a finding just to make the check pass.
