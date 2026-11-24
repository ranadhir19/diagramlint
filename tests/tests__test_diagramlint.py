import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diagramlint.check import Waiver, apply_baseline, check, exit_code
from diagramlint.jsextract import extract_javascript
from diagramlint.mermaid import parse_mermaid
from diagramlint.pyextract import extract_python

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "sample_app"


class MermaidTests(unittest.TestCase):
    def test_edges_and_nodes(self):
        d = parse_mermaid("flowchart LR\n    a --> b\n    b --> c\n")
        self.assertEqual([(e.source, e.target) for e in d.edges],
                         [("a", "b"), ("b", "c")])
        self.assertEqual(d.nodes, ["a", "b", "c"])

    def test_labelled_node_wrappers(self):
        d = parse_mermaid("graph TD\n    api[API] --> store[(Store)]\n")
        self.assertEqual([(e.source, e.target) for e in d.edges],
                         [("api", "store")])


class SampleAppTests(unittest.TestCase):
    def setUp(self):
        diagram = parse_mermaid((SAMPLE / "diagram.mmd").read_text())
        truth = extract_python(SAMPLE / "sample_app")
        self.receipt = check(diagram, truth)

    def test_counts(self):
        self.assertEqual(self.receipt["counts"].get("supported"), 2)
        self.assertEqual(self.receipt["counts"].get("reversed"), 1)
        self.assertEqual(self.receipt["counts"].get("no-evidence"), 1)
        self.assertEqual(self.receipt["counts"].get("missing-from-diagram"), 1)

    def test_reversed_carries_evidence(self):
        rev = [f for f in self.receipt["findings"] if f["verdict"] == "reversed"]
        self.assertEqual(len(rev), 1)
        self.assertTrue(rev[0]["evidence"])
        self.assertGreaterEqual(rev[0]["evidence"][0]["line"], 1)

    def test_exit_code(self):
        self.assertEqual(exit_code(self.receipt), 1)

    def test_waiver(self):
        diagram = parse_mermaid((SAMPLE / "diagram.mmd").read_text())
        truth = extract_python(SAMPLE / "sample_app")
        receipt = check(diagram, truth,
                        waivers=[Waiver("api", "cache", "planned, not built")])
        self.assertEqual(receipt["counts"].get("waived"), 1)
        self.assertNotIn("no-evidence", receipt["counts"])


class ModuleGranularityTests(unittest.TestCase):
    def _tree(self, tmp):
        pkg = Path(tmp) / "pkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("")
        (pkg / "a.py").write_text("from pkg import b\nimport pkg.c\n")
        (pkg / "b.py").write_text("")
        (pkg / "c.py").write_text("from . import b\n")
        return Path(tmp)

    def test_package_mode_collapses_single_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._tree(tmp)
            pairs = {(e.source, e.target) for e in extract_python(root)}
            self.assertEqual(pairs, set())

    def test_module_mode_sees_intra_package_edges(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._tree(tmp)
            pairs = {(e.source, e.target) for e in extract_python(root, granularity="module")}
            self.assertIn(("pkg.a", "pkg.b"), pairs)
            self.assertIn(("pkg.a", "pkg.c"), pairs)
            self.assertIn(("pkg.c", "pkg.b"), pairs)

    def test_unknown_granularity_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._tree(tmp)
            with self.assertRaises(ValueError):
                extract_python(root, granularity="file")


class JavaScriptExtractTests(unittest.TestCase):
    def _tree(self, tmp):
        root = Path(tmp)
        (root / "src").mkdir()
        (root / "src" / "util").mkdir()
        (root / "src" / "a.ts").write_text(
            "import { b } from './b';\n"
            "import './c.js';\n"
            "import React from 'react';\n"
            "export { u } from './util';\n"
            "const d = require('./d');\n")
        (root / "src" / "b.ts").write_text("export const b = 1;\n")
        (root / "src" / "c.ts").write_text("export {};\n")
        (root / "src" / "d.js").write_text("module.exports = {};\n")
        (root / "src" / "util" / "index.ts").write_text("export const u = 1;\n")
        (root / "src" / "e.tsx").write_text(
            "export async function load() { return import('./b'); }\n")
        return root

    def test_relative_forms_resolve(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._tree(tmp)
            pairs = {(e.source, e.target) for e in extract_javascript(root / "src")}
            self.assertIn(("a", "b"), pairs)
            self.assertIn(("a", "c"), pairs)  # .js specifier maps to .ts source
            self.assertIn(("a", "util"), pairs)  # folder index resolution
            self.assertIn(("a", "d"), pairs)  # require()
            self.assertIn(("e", "b"), pairs)  # dynamic import()

    def test_external_imports_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._tree(tmp)
            pairs = {(e.source, e.target) for e in extract_javascript(root / "src")}
            self.assertFalse(any(t == "react" for _, t in pairs))

    def test_evidence_lines_point_at_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self._tree(tmp)
            edges = [e for e in extract_javascript(root / "src")
                     if (e.source, e.target) == ("a", "b")]
            self.assertEqual(len(edges), 1)
            self.assertEqual(edges[0].evidence.line, 1)


class BaselineDriftTests(unittest.TestCase):
    def _receipt(self, diagram_text):
        diagram = parse_mermaid(diagram_text)
        truth = extract_python(SAMPLE / "sample_app")
        return check(diagram, truth)

    def test_unchanged_against_own_baseline_passes(self):
        base = self._receipt((SAMPLE / "diagram.mmd").read_text())
        cur = apply_baseline(
            self._receipt((SAMPLE / "diagram.mmd").read_text()), base)
        self.assertEqual(cur["drift"]["new"], [])
        self.assertEqual(cur["drift"]["resolved"], [])
        self.assertEqual(cur["drift"]["known_count"],
                         len(cur["findings"]))
        # the sample's reversed edge is known drift: no failure
        self.assertEqual(exit_code(cur), 0)

    def test_new_finding_is_drift_and_fails(self):
        base = self._receipt((SAMPLE / "diagram.mmd").read_text())
        # add a diagram edge whose code evidence runs the other way
        # (code: store imports util, so util --> store is reversed)
        text = (SAMPLE / "diagram.mmd").read_text()
        cur = apply_baseline(self._receipt(text + "\n    util --> store\n"),
                             base)
        new = [tuple(k) for k in cur["drift"]["new"]]
        self.assertIn(("reversed", "util", "store"), new)
        self.assertEqual(exit_code(cur), 1)

    def test_resolved_finding_reported(self):
        base = self._receipt((SAMPLE / "diagram.mmd").read_text())
        cur = apply_baseline(self._receipt("flowchart LR\n    api --> store\n"),
                             base)
        self.assertTrue(cur["drift"]["resolved"])


class McpServerTests(unittest.TestCase):
    def test_initialize_and_tools_list(self):
        from diagramlint.mcp_server import handle
        init = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
        self.assertEqual(init["result"]["serverInfo"]["name"], "diagramlint")
        listed = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = [t["name"] for t in listed["result"]["tools"]]
        self.assertEqual(names, ["check_diagram"])

    def test_tools_call_returns_sample_receipt(self):
        from diagramlint.mcp_server import handle
        resp = handle({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                       "params": {"name": "check_diagram",
                                  "arguments": {
                                      "diagram_path": str(SAMPLE / "diagram.mmd"),
                                      "code_path": str(SAMPLE / "sample_app")}}})
        self.assertFalse(resp["result"]["isError"])
        receipt = resp["result"]["structuredContent"]
        self.assertEqual(receipt["counts"].get("supported"), 2)
        self.assertEqual(receipt["counts"].get("reversed"), 1)
        self.assertEqual(receipt["exit_code"], 1)

    def test_unknown_tool_and_notification(self):
        from diagramlint.mcp_server import handle
        resp = handle({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                       "params": {"name": "nope", "arguments": {}}})
        self.assertIn("error", resp)
        self.assertIsNone(handle({"jsonrpc": "2.0",
                                  "method": "notifications/initialized"}))

    def test_agent_skill_file_present(self):
        root = SAMPLE.parent.parent
        text = (root / "agent_skill" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("check_diagram", text)
        self.assertIn("DL200", text)


class GitHubActionTests(unittest.TestCase):
    def test_action_definition_present_and_composite(self):
        root = SAMPLE.parent.parent
        text = (root / "action.yml").read_text(encoding="utf-8")
        self.assertIn('using: "composite"', text)
        self.assertIn("diagramlint", text)
        for inp in ("diagram:", "code:", "baseline:", "strict:"):
            self.assertIn(inp, text)
        workflow = (root / ".github" / "workflows"
                    / "diagramlint.yml").read_text(encoding="utf-8")
        self.assertIn("python validate.py", workflow)


if __name__ == "__main__":
    unittest.main()
