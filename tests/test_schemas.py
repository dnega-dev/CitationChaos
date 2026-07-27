import json
import unittest
from dataclasses import replace

from citation_chaos import (
    Answer,
    Citation,
    Claim,
    Corpus,
    MutationSuite,
    SchemaError,
    Source,
    Span,
    generate_suite,
)
from citation_chaos.schemas import assert_answer_references
from citation_chaos.seeds import starter_project


class SchemaTests(unittest.TestCase):
    def test_corpus_and_answer_round_trip(self):
        corpus, answer, _ = starter_project()
        self.assertEqual(corpus, Corpus.from_dict(json.loads(json.dumps(corpus.to_dict()))))
        self.assertEqual(answer, Answer.from_dict(json.loads(json.dumps(answer.to_dict()))))

    def test_mutation_suite_round_trip(self):
        corpus, answer, question = starter_project()
        suite, _ = generate_suite(corpus, answer, question, ["alter-number"], strict=True)
        restored = MutationSuite.from_dict(json.loads(json.dumps(suite.to_dict())))
        self.assertEqual(suite, restored)

    def test_duplicate_source_ids_are_rejected(self):
        corpus, _, _ = starter_project()
        with self.assertRaisesRegex(SchemaError, "source IDs must be unique"):
            Corpus(id="bad", sources=(corpus.sources[0], corpus.sources[0]))

    def test_duplicate_span_ids_are_rejected(self):
        span = Span(id="x", text="text")
        with self.assertRaisesRegex(SchemaError, "span IDs must be unique"):
            Source(
                id="s",
                uri="urn:s",
                title="source",
                spans=(span, span),
                sha256=Source.hash_spans((span, span)),
            )

    def test_invalid_sha_is_rejected(self):
        span = Span(id="x", text="text")
        with self.assertRaisesRegex(SchemaError, "64-character"):
            Source(id="s", uri="urn:s", title="source", spans=(span,), sha256="nope")

    def test_answer_status_invariants(self):
        claim = Claim(id="c", text="claim")
        with self.assertRaisesRegex(SchemaError, "abstained answer"):
            Answer(status="abstained", claims=(claim,), reason="because")
        with self.assertRaisesRegex(SchemaError, "answered answer"):
            Answer(status="answered", claims=())

    def test_missing_reference_is_rejected(self):
        corpus, _, _ = starter_project()
        bad = Answer(
            status="answered",
            claims=(
                Claim(
                    id="bad",
                    text="bad",
                    citations=(Citation(source_id="missing", span_id="missing"),),
                ),
            ),
        )
        with self.assertRaisesRegex(SchemaError, "missing source"):
            assert_answer_references(bad, corpus)

    def test_span_offsets_must_be_paired(self):
        with self.assertRaisesRegex(SchemaError, "both be set"):
            Span(id="x", text="text", start=0)


if __name__ == "__main__":
    unittest.main()
