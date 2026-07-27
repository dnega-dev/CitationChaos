import contextlib
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from xml.etree import ElementTree as ET

from citation_chaos.cli import main


ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def setUp(self):
        self.temp = Path(tempfile.mkdtemp(prefix="citation-chaos-test-", dir=str(ROOT / "tests")))

    def tearDown(self):
        shutil.rmtree(self.temp)

    def call(self, argv):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_init_mutate_run_reference_workflow(self):
        project = self.temp / "starter"
        code, stdout, stderr = self.call(["init", str(project)])
        self.assertEqual(0, code, stderr)
        self.assertTrue((project / "corpus.json").is_file())
        self.assertTrue((project / "answer.json").is_file())
        self.assertTrue((project / "adapter.py").is_file())

        manifest = self.temp / "mutations.json"
        code, stdout, stderr = self.call(
            [
                "mutate",
                str(project / "corpus.json"),
                "--answer",
                str(project / "answer.json"),
                "--seed",
                "41",
                "--strict",
                "--output",
                str(manifest),
            ]
        )
        self.assertEqual(0, code, stderr)
        self.assertEqual(11, len(json.loads(manifest.read_text(encoding="utf-8"))["mutations"]))

        code, stdout, stderr = self.call(["run", str(manifest), "--adapter", "reference"])
        self.assertEqual(0, code, stderr)
        self.assertIn("11 passed", stdout)
        self.assertIn("not proof of semantic truth", stdout)

    def test_all_machine_readable_formats(self):
        project = self.temp / "starter"
        self.assertEqual(0, self.call(["init", str(project)])[0])
        manifest = self.temp / "mutations.json"
        self.assertEqual(
            0,
            self.call(
                [
                    "mutate",
                    str(project / "corpus.json"),
                    "--answer",
                    str(project / "answer.json"),
                    "--operator",
                    "alter-number",
                    "--output",
                    str(manifest),
                ]
            )[0],
        )
        for output_format in ("json", "junit", "sarif"):
            with self.subTest(output_format=output_format):
                code, stdout, stderr = self.call(
                    ["run", str(manifest), "--format", output_format]
                )
                self.assertEqual(0, code, stderr)
                if output_format == "json":
                    self.assertTrue(json.loads(stdout)["summary"]["successful"])
                elif output_format == "junit":
                    self.assertEqual("testsuite", ET.fromstring(stdout).tag)
                else:
                    self.assertEqual("2.1.0", json.loads(stdout)["version"])

    def test_operator_list_text_and_json(self):
        code, stdout, stderr = self.call(["operators", "list"])
        self.assertEqual(0, code, stderr)
        self.assertIn("delete-cited-span", stdout)
        code, stdout, stderr = self.call(["operators", "list", "--format", "json"])
        self.assertEqual(0, code, stderr)
        self.assertEqual(11, len(json.loads(stdout)["operators"]))

    def test_init_refuses_overwrite_without_force(self):
        project = self.temp / "starter"
        self.assertEqual(0, self.call(["init", str(project)])[0])
        code, stdout, stderr = self.call(["init", str(project)])
        self.assertEqual(2, code)
        self.assertIn("refusing to overwrite", stderr)
        self.assertEqual(0, self.call(["init", str(project), "--force"])[0])

    def test_user_adapter_file_is_loaded(self):
        project = self.temp / "starter"
        self.assertEqual(0, self.call(["init", str(project)])[0])
        manifest = self.temp / "mutations.json"
        self.assertEqual(
            0,
            self.call(
                [
                    "mutate",
                    str(project / "corpus.json"),
                    "--answer",
                    str(project / "answer.json"),
                    "--operator",
                    "move-source-uri",
                    "--output",
                    str(manifest),
                ]
            )[0],
        )
        adapter = self.temp / "trusted_adapter.py"
        adapter.write_text(
            "from citation_chaos.adapters import ReferenceAdapter\n"
            "def pipeline(question, corpus):\n"
            "    return ReferenceAdapter().run(question, corpus).to_dict()\n",
            encoding="utf-8",
        )
        code, stdout, stderr = self.call(
            ["run", str(manifest), "--adapter", "%s:pipeline" % adapter]
        )
        self.assertEqual(0, code, stderr)
        self.assertIn("1 passed", stdout)


if __name__ == "__main__":
    unittest.main()
