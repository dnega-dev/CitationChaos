import unittest

from citation_chaos import OPERATORS, generate_suite, get_operator
from citation_chaos.schemas import Source
from citation_chaos.seeds import starter_project


EXPECTED_OPERATORS = (
    "delete-cited-span",
    "alter-number",
    "alter-date",
    "swap-source-ids",
    "corrupt-anchor",
    "supersede-source",
    "move-source-uri",
    "introduce-conflicting-current-source",
    "replace-primary-with-secondary",
    "zero-result-retrieval",
    "stale-cache-text",
)


class OperatorTests(unittest.TestCase):
    def setUp(self):
        self.corpus, self.answer, self.question = starter_project()

    def test_registry_has_all_required_operators_in_stable_order(self):
        self.assertEqual(EXPECTED_OPERATORS, tuple(OPERATORS))

    def test_move_uri_retains_hash_and_content(self):
        mutation = get_operator("move-source-uri").apply(
            self.corpus, self.answer, self.question, seed=0
        )
        source_id = mutation.metadata["source_id"]
        before = self.corpus.source(source_id)
        after = mutation.corpus.source(source_id)
        self.assertNotEqual(before.uri, after.uri)
        self.assertEqual(before.sha256, after.sha256)
        self.assertEqual(before.spans, after.spans)

    def test_stale_cache_retains_wrong_hash(self):
        mutation = get_operator("stale-cache-text").apply(
            self.corpus, self.answer, self.question, seed=0
        )
        source = mutation.corpus.source(mutation.metadata["source_id"])
        self.assertNotEqual(source.sha256, Source.hash_spans(source.spans))

    def test_superseding_source_links_to_old_source(self):
        mutation = get_operator("supersede-source").apply(
            self.corpus, self.answer, self.question, seed=0
        )
        old = mutation.corpus.source(mutation.metadata["source_id"])
        new = mutation.corpus.source(mutation.metadata["superseding_source_id"])
        self.assertFalse(old.current)
        self.assertIn(old.id, new.supersedes)
        self.assertTrue(new.current)

    def test_conflicting_source_is_current_and_tagged(self):
        mutation = get_operator("introduce-conflicting-current-source").apply(
            self.corpus, self.answer, self.question, seed=0
        )
        conflicting = mutation.corpus.source(mutation.metadata["conflicting_source_id"])
        self.assertTrue(conflicting.current)
        self.assertEqual(
            mutation.metadata["source_id"],
            conflicting.metadata["citation_chaos"]["conflicts_with"],
        )

    def test_non_strict_generation_skips_inapplicable_operator(self):
        # Remove all ISO dates while retaining valid citations.
        schedule_source = self.corpus.sources[0]
        schedule = schedule_source.spans[1]
        replacement_text = "The storage pilot begins during the next cycle."
        replacement = type(schedule)(
            id=schedule.id,
            text=replacement_text,
            start=schedule.start,
            end=schedule.end,
            page=schedule.page,
        )
        spans = (schedule_source.spans[0], replacement, schedule_source.spans[2])
        updated_source = type(schedule_source)(
            id=schedule_source.id,
            uri=schedule_source.uri,
            title=schedule_source.title,
            spans=spans,
            sha256=Source.hash_spans(spans),
            kind=schedule_source.kind,
            published_at=schedule_source.published_at,
        )
        updated = type(self.corpus)(
            id=self.corpus.id,
            version=self.corpus.version,
            sources=(updated_source, self.corpus.sources[1]),
            metadata=self.corpus.metadata,
        )
        suite, skipped = generate_suite(
            updated,
            self.answer,
            self.question,
            ["alter-date"],
            strict=False,
        )
        self.assertFalse(suite.mutations)
        self.assertEqual(1, len(skipped))


if __name__ == "__main__":
    unittest.main()
