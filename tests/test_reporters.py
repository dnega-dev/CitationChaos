import json
import unittest
from xml.etree import ElementTree as ET

from citation_chaos import LoadedAdapter, generate_suite, load_adapter, run_suite
from citation_chaos.reporters import render_json, render_junit, render_sarif, render_text
from citation_chaos.seeds import starter_project


class ReporterTests(unittest.TestCase):
    def report(self, adapter=None):
        corpus, answer, question = starter_project()
        suite, _ = generate_suite(corpus, answer, question, ["alter-number"], strict=True)
        return run_suite(suite, adapter or load_adapter("reference"))

    def test_text_has_summary_and_disclaimer(self):
        text = render_text(self.report())
        self.assertIn("Summary: 1 total, 1 passed", text)
        self.assertIn("not proof of semantic truth", text)

    def test_json_has_stable_schema(self):
        document = json.loads(render_json(self.report()))
        self.assertEqual("1.0", document["schema_version"])
        self.assertEqual(1, document["summary"]["total"])
        self.assertEqual(6, len(document["results"][0]["checks"]))

    def test_junit_is_well_formed(self):
        root = ET.fromstring(render_junit(self.report()))
        self.assertEqual("testsuite", root.tag)
        self.assertEqual("1", root.attrib["tests"])
        self.assertEqual(1, len(root.findall("testcase")))

    def test_sarif_has_results_for_failed_checks(self):
        corpus, answer, question = starter_project()
        suite, _ = generate_suite(corpus, answer, question, ["alter-number"], strict=True)
        naive = LoadedAdapter(name="naive", invoke=lambda q, c: answer)
        document = json.loads(render_sarif(run_suite(suite, naive)))
        self.assertEqual("2.1.0", document["version"])
        self.assertTrue(document["runs"][0]["results"])
        self.assertIn(
            "unsupported-claim-removal",
            {item["ruleId"] for item in document["runs"][0]["results"]},
        )


if __name__ == "__main__":
    unittest.main()
