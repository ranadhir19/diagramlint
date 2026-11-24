# diagramlint

Check a committed architecture diagram against the code it claims to
describe.

Generators produce diagrams that are well-formed. Well-formed is not
the same as true: a diagram edge can be invented, drawn in the wrong
direction, or quietly omit a dependency the code actually has.
diagramlint compares a committed diagram's edges, in both directions,
against a statically extracted dependency graph, and reports every
disagreement with file:line evidence, a machine-readable receipt, and
a CI exit code — so a person, or the agent that drew the diagram, can
repair it before it ships.

## Status

Scaffold (v0.0.1). The checker core, the Mermaid and JSON diagram
readers, the Python import extractor, the JavaScript/TypeScript
extractor, the receipt format and the validation harness are in place
and tested on a bundled sample app.
Python extraction supports package granularity (default) and
module granularity (`--granularity module`), which exposes imports
between modules of a single package — package mode alone collapses a
single-package src-layout repo to zero checkable edges.
JavaScript/TypeScript extraction (`--lang javascript`, or `auto`)
resolves relative static, re-export, `require` and dynamic imports
between files in the tree, with folder-index and `.js`-to-`.ts`
resolution; it is a line scanner, not a full parser, so an
import-shaped string in a comment can be recorded — every edge
carries its file:line evidence for audit.
Baseline/drift mode is built: `diagramlint baseline … --out
base.json` records the current receipt, and `check --baseline
base.json` marks findings already in the baseline as known drift
(they are reported, but only NEW reversed — or, with `--strict`,
new no-evidence — findings fail the build) and reports resolved
findings in the receipt's `drift` section. A GitHub Action is built:
`action.yml` at the repo root is a composite action taking diagram,
code, optional config/baseline, strict, language and granularity
inputs, installing the package and running the check so its exit code
gates the workflow; the receipt path is exposed as an output. The
repo's own workflow runs validate.py and exercises the baseline flow
on the sample app. The agent skill/MCP surface is built: a
stdlib-only MCP server (`diagramlint-mcp`, JSON-RPC over stdio)
exposes one tool, `check_diagram`, returning the same receipt as
the CLI, and `agent_skill/SKILL.md` tells an agent when and how to
run the check and how to read each verdict. Nothing here is a
finished product claim.

## Verdicts

diagramlint's own rule codes:

| Code | Verdict | Meaning |
|---|---|---|
| DL100 | supported | direct code evidence for the diagram edge |
| DL101 | transitive | a code path exists, but no direct edge |
| DL200 | reversed | code evidence runs in the opposite direction |
| DL300 | no-evidence | no code evidence in either direction |
| DL400 | missing-from-diagram | a code edge between diagrammed components the diagram omits (report-only) |
| DL500 | waived | matched by a waiver recorded in the config, with its reason |

Exit code is 1 when a reversed edge is present, and also for
no-evidence edges under `--strict`. Missing edges never fail a build
on their own: a curated summary diagram is allowed to omit detail.

## Use

In CI, use the GitHub Action:

```yaml
- uses: ranadhir19/diagramlint@v0
  with:
    diagram: docs/architecture.mmd
    code: src
    # baseline: docs/diagramlint-baseline.json  # optional drift mode
    # strict: "true"                            # optional
```

```bash
diagramlint check diagram.mmd --code path/to/python/package --format json
# single-package trees: diagramlint check diagram.mmd --code path/to/src --granularity module
# drift mode: diagramlint baseline diagram.mmd --code path/to/package --out base.json
#             diagramlint check diagram.mmd --code path/to/package --baseline base.json
```

For agents: run `diagramlint-mcp` as an MCP stdio server and call
`check_diagram` with `diagram_path` and `code_path`, or follow
`agent_skill/SKILL.md` from a shell.

An optional `diagramcheck.toml` can map diagram node names to code
components (`[mapping]`) and record auditable waivers for edges static
analysis cannot see, such as dependency-injection or runtime wiring
(`[[waivers]]` with `source`, `target` and `reason`).

## Design rules

- Generator-neutral: the diagram is an input, whoever or whatever
  produced it. Mermaid text and JSON diagrams are read today.
- Deterministic: no language model is consulted. The same diagram and
  the same code always produce the same receipt.
- Evidence first: every supported, reversed and missing verdict
  carries the file and line of the import that proves it.

## Licence

MIT — see LICENSE.
