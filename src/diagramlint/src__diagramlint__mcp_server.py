"""diagramlint MCP server (stdlib-only, JSON-RPC over stdio).

Exposes one tool, ``check_diagram``, so an agent that drew or edited
an architecture diagram can verify it against the code before
committing it and receive the same receipt the CLI and the GitHub
Action produce. No language model is consulted; the check is the
deterministic checker core.

Protocol surface implemented (Model Context Protocol, stdio
transport): ``initialize``, ``ping``, ``tools/list`` and
``tools/call``. Notifications (messages without an id) are accepted
and produce no response. Each message is one JSON object per line.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from .check import apply_baseline, check, exit_code
from .cli import _load_config, _load_diagram
from .jsextract import extract_javascript
from .pyextract import extract_python

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "diagramlint", "version": "0.0.1"}

TOOL = {
    "name": "check_diagram",
    "description": (
        "Check a committed architecture diagram (Mermaid .mmd/.md or "
        "JSON) against the code it claims to describe. Returns the "
        "diagramlint receipt: every diagram edge classified as "
        "supported, transitive, reversed, no-evidence, missing-from-"
        "diagram or waived, with file:line evidence, plus the CI "
        "exit code the same check would produce."
    ),
    "inputSchema": {
        "type": "object",
        "properties": {
            "diagram_path": {"type": "string",
                             "description": "Path to the diagram file."},
            "code_path": {"type": "string",
                          "description": "Root of the code tree to scan."},
            "config_path": {"type": "string",
                            "description": "Optional diagramcheck.toml."},
            "baseline_path": {"type": "string",
                              "description": "Optional baseline receipt JSON."},
            "strict": {"type": "boolean", "default": False,
                       "description": "Fail also on no-evidence edges."},
            "lang": {"type": "string", "enum": ["auto", "python", "javascript"],
                     "default": "auto"},
            "granularity": {"type": "string", "enum": ["package", "module"],
                            "default": "package"},
        },
        "required": ["diagram_path", "code_path"],
    },
}


def run_check(arguments: dict) -> dict:
    diagram = _load_diagram(Path(arguments["diagram_path"]))
    config = arguments.get("config_path")
    mapping, waivers = _load_config(Path(config) if config else None)
    code_root = Path(arguments["code_path"])
    lang = arguments.get("lang", "auto")
    truth = []
    if lang in ("auto", "python"):
        truth += extract_python(
            code_root, granularity=arguments.get("granularity", "package"))
    if lang in ("auto", "javascript"):
        truth += extract_javascript(code_root)
    receipt = check(diagram, truth, waivers=waivers, mapping=mapping)
    if arguments.get("baseline_path"):
        baseline = json.loads(
            Path(arguments["baseline_path"]).read_text(encoding="utf-8"))
        receipt = apply_baseline(receipt, baseline)
    receipt = dict(receipt)
    receipt["exit_code"] = exit_code(receipt, strict=bool(arguments.get("strict")))
    return receipt


def _result(req_id, result: dict) -> dict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _error(req_id, code: int, message: str) -> dict:
    return {"jsonrpc": "2.0", "id": req_id,
            "error": {"code": code, "message": message}}


def handle(message: dict) -> dict | None:
    """Handle one JSON-RPC message; None means no response is owed."""
    method = message.get("method", "")
    req_id = message.get("id")
    if req_id is None:
        return None  # notification
    if method == "initialize":
        return _result(req_id, {
            "protocolVersion": PROTOCOL_VERSION,
            "capabilities": {"tools": {}},
            "serverInfo": SERVER_INFO,
        })
    if method == "ping":
        return _result(req_id, {})
    if method == "tools/list":
        return _result(req_id, {"tools": [TOOL]})
    if method == "tools/call":
        params = message.get("params") or {}
        if params.get("name") != TOOL["name"]:
            return _error(req_id, -32602,
                          f"unknown tool: {params.get('name')!r}")
        try:
            receipt = run_check(params.get("arguments") or {})
        except Exception as exc:  # noqa: BLE001 - reported to the caller
            return _result(req_id, {
                "content": [{"type": "text", "text": f"check failed: {exc}"}],
                "isError": True,
            })
        return _result(req_id, {
            "content": [{"type": "text",
                         "text": json.dumps(receipt, indent=2)}],
            "structuredContent": receipt,
            "isError": False,
        })
    return _error(req_id, -32601, f"method not found: {method}")


def main(argv: list[str] | None = None) -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        response = handle(message)
        if response is not None:
            print(json.dumps(response), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
