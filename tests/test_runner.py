import unittest

from citation_chaos import Answer, LoadedAdapter, generate_suite, load_adapter, run_mutation, score_answer
from citation_chaos.runner import CHECK_NAMES
from citation_chaos.seeds import starter_project


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.corpus, self.answer, self.question = starter_project()

    def mutation(self, name):
        suite, _ = generate_suite(
            self.corpus, self.answer, self.question, [name], strict=True
        )
        return suite.mutations[0]

    def test_exact_six_check_names(self):
        mutation = self.mutation("alter-number")
        answer = load_adapter("reference").invoke(self.question, mutation.corpus)
        checks = score_answer(mutation, answer)
        self.assertEqual(CHECK_NAMES, tuple(check.name for check in checks))

    def test_overbroad_abstention_fails_preservation_and_localization(self):
        mutation = self.mutation("alter-number")
        overbroad = Answer(status="abstained", claims=(), reason="number changed")
        checks = {check.name: check for check in score_answer(mutation, overbroad)}
        self.assertFalse(checks["abstention"].passed)
        self.assertFalse(checks["unaffected-claim-preservation"].passed)
        self.assertFalse(checks["impact-localization"].passed)

    def test_reason_must_contain_expected_terms(self):
        mutation = self.mutation("alter-number")
        reference = load_adapter("reference").invoke(self.question, mutation.corpus)
        bad_reason = Answer(
            status=reference.status,
            claims=reference.claims,
            reason="evidence was different",
            text=reference.text,
        )
        checks = {check.name: check for check in score_answer(mutation, bad_reason)}
        self.assertFalse(checks["explicit-reason"].passed)

    def test_adapter_can_return_mapping(self):
        mutation = self.mutation("move-source-uri")
        reference = load_adapter("reference")
        mapping_adapter = LoadedAdapter(
            name="mapping",
            invoke=lambda question, corpus: reference.invoke(question, corpus),
        )
        result = run_mutation(mutation, mapping_adapter)
        self.assertEqual("passed", result.status)


if __name__ == "__main__":
    unittest.main()
