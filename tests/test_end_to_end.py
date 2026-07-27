"""End-to-end mutation tests: operator -> adapter -> runner -> checks."""

import json
import unittest

from citation_chaos import (
    LoadedAdapter,
    MutationSuite,
    generate_suite,
    get_operator,
    load_adapter,
    run_mutation,
    run_suite,
)
from citation_chaos.seeds import starter_project


class EndToEndMutationTests(unittest.TestCase):
    """Each named operator test executes the complete in-process harness."""

    def setUp(self):
        self.corpus, self.answer, self.question = starter_project()
        self.adapter = load_adapter("reference")

    def assert_operator_passes(self, name, seed=7):
        mutation = get_operator(name).apply(self.corpus, self.answer, self.question, seed)
        result = run_mutation(mutation, self.adapter)
        self.assertEqual("passed", result.status, result.to_dict())
        self.assertEqual(6, len(result.checks))
        self.assertTrue(all(check.passed for check in result.checks))
        self.assertEqual(name, result.operator)
        return mutation, result

    def test_01_delete_cited_span(self):
        self.assert_operator_passes("delete-cited-span")

    def test_02_alter_number(self):
        self.assert_operator_passes("alter-number")

    def test_03_alter_date(self):
        self.assert_operator_passes("alter-date")

    def test_04_swap_source_ids(self):
        self.assert_operator_passes("swap-source-ids")

    def test_05_corrupt_anchor(self):
        self.assert_operator_passes("corrupt-anchor")

    def test_06_supersede_source(self):
        self.assert_operator_passes("supersede-source")

    def test_07_move_source_uri(self):
        mutation, result = self.assert_operator_passes("move-source-uri")
        self.assertEqual(2, len(result.answer.claims))
        self.assertFalse(mutation.expected_response.impact_claim_ids)

    def test_08_introduce_conflicting_current_source(self):
        self.assert_operator_passes("introduce-conflicting-current-source")

    def test_09_replace_primary_with_secondary(self):
        self.assert_operator_passes("replace-primary-with-secondary")

    def test_10_zero_result_retrieval(self):
        mutation, result = self.assert_operator_passes("zero-result-retrieval")
        self.assertFalse(mutation.corpus.sources)
        self.assertEqual("abstained", result.answer.status)

    def test_11_stale_cache_text(self):
        self.assert_operator_passes("stale-cache-text")

    def test_12_partial_impact_preserves_unaffected_claim(self):
        mutation, result = self.assert_operator_passes("alter-number", seed=0)
        self.assertEqual(("pilot-date",), mutation.expected_response.preserve_claim_ids)
        self.assertEqual(["pilot-date"], [claim.id for claim in result.answer.claims])

    def test_13_full_suite_generation_is_byte_deterministic(self):
        first, first_skipped = generate_suite(self.corpus, self.answer, self.question, seed=19, strict=True)
        second, second_skipped = generate_suite(self.corpus, self.answer, self.question, seed=19, strict=True)
        first_json = json.dumps(first.to_dict(), sort_keys=True, separators=(",", ":"))
        second_json = json.dumps(second.to_dict(), sort_keys=True, separators=(",", ":"))
        self.assertEqual(first_json, second_json)
        self.assertEqual(first_skipped, second_skipped)

    def test_14_round_tripped_manifest_runs_all_mutations(self):
        suite, _ = generate_suite(self.corpus, self.answer, self.question, seed=23, strict=True)
        suite = MutationSuite.from_dict(json.loads(json.dumps(suite.to_dict())))
        report = run_suite(suite, self.adapter)
        self.assertEqual(11, report.total)
        self.assertTrue(report.successful, report.to_dict())

    def test_15_naive_unchanged_answer_is_rejected(self):
        mutation = get_operator("delete-cited-span").apply(
            self.corpus, self.answer, self.question, seed=2
        )
        naive = LoadedAdapter(name="naive", invoke=lambda question, corpus: self.answer)
        result = run_mutation(mutation, naive)
        self.assertEqual("failed", result.status)
        failed = {check.name for check in result.checks if not check.passed}
        self.assertIn("unsupported-claim-removal", failed)
        self.assertIn("citation-resolvability", failed)

    def test_16_adapter_exception_becomes_error_result(self):
        mutation = get_operator("alter-date").apply(
            self.corpus, self.answer, self.question, seed=0
        )

        def explode(question, corpus):
            raise RuntimeError("pipeline unavailable")

        result = run_mutation(mutation, LoadedAdapter(name="broken", invoke=explode))
        self.assertEqual("error", result.status)
        self.assertIn("pipeline unavailable", result.error)


if __name__ == "__main__":
    unittest.main()
