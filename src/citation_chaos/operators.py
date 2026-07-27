"""Deterministic corpus mutation operators.

Operators mutate evidence or provenance, never the baseline answer.  The expected
response records which baseline claims should be removed or preserved.  Mutation
metadata is descriptive and must not be treated as a substitute for exercising a
real pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, timedelta
import hashlib
import random
import re
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from .schemas import (
    Answer,
    Citation,
    Claim,
    Corpus,
    ExpectedResponse,
    Mutation,
    MutationSuite,
    Source,
    Span,
    assert_answer_references,
    stable_hash,
)


class MutationNotApplicable(ValueError):
    """Raised when an operator cannot find a valid deterministic target."""


@dataclass(frozen=True)
class OperatorInfo:
    name: str
    summary: str
    category: str

    def to_dict(self) -> Dict[str, str]:
        return {"name": self.name, "summary": self.summary, "category": self.category}


@dataclass(frozen=True)
class _Target:
    claim_id: str
    citation: Citation
    source: Source
    span: Span


_NUMBER_RE = re.compile(r"(?<![\w-])(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?(?![\w-])")
_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")


def _rng_choice(items: Sequence[object], seed: int) -> object:
    if not items:
        raise MutationNotApplicable("no eligible mutation target")
    return items[random.Random(seed).randrange(len(items))]


def _targets(corpus: Corpus, answer: Answer) -> Tuple[_Target, ...]:
    targets: List[_Target] = []
    for claim in sorted(answer.claims, key=lambda item: item.id):
        for citation in sorted(claim.citations, key=lambda item: (item.source_id, item.span_id)):
            source = corpus.source(citation.source_id)
            if source is None:
                continue
            span = source.span(citation.span_id)
            if span is not None:
                targets.append(_Target(claim.id, citation, source, span))
    return tuple(targets)


def _claims_for(answer: Answer, source_ids: Iterable[str], span_ids: Optional[Iterable[str]] = None) -> Tuple[str, ...]:
    source_set = set(source_ids)
    span_set = set(span_ids) if span_ids is not None else None
    matches: List[str] = []
    for claim in answer.claims:
        if any(
            citation.source_id in source_set and (span_set is None or citation.span_id in span_set)
            for citation in claim.citations
        ):
            matches.append(claim.id)
    return tuple(matches)


def _expected(
    answer: Answer,
    affected: Iterable[str],
    reason_contains: Iterable[str],
    notes: str,
) -> ExpectedResponse:
    affected_set = set(affected)
    ordered_affected = tuple(claim.id for claim in answer.claims if claim.id in affected_set)
    preserved = tuple(claim.id for claim in answer.claims if claim.id not in affected_set)
    return ExpectedResponse(
        must_abstain=bool(answer.claims) and not preserved,
        remove_claim_ids=ordered_affected,
        preserve_claim_ids=preserved,
        impact_claim_ids=ordered_affected,
        reason_contains=tuple(reason_contains),
        resolvable_claim_ids=preserved,
        notes=notes,
    )


def _expected_preserve(answer: Answer, notes: str) -> ExpectedResponse:
    claim_ids = tuple(claim.id for claim in answer.claims)
    return ExpectedResponse(
        must_abstain=False,
        preserve_claim_ids=claim_ids,
        resolvable_claim_ids=claim_ids,
        notes=notes,
    )


def _tag_metadata(metadata: Mapping[str, object], operator: str, **details: object) -> Dict[str, object]:
    result = dict(metadata)
    result["citation_chaos"] = {"operator": operator, **details}
    return result


def _rebuild_source(source: Source, spans: Sequence[Span], retain_hash: bool = False, **changes: object) -> Source:
    digest = source.sha256 if retain_hash else Source.hash_spans(spans)
    return replace(source, spans=tuple(spans), sha256=digest, **changes)


def _replace_source(corpus: Corpus, source_id: str, replacement: Optional[Source]) -> Corpus:
    sources: List[Source] = []
    for source in corpus.sources:
        if source.id == source_id:
            if replacement is not None:
                sources.append(replacement)
        else:
            sources.append(source)
    return replace(corpus, sources=tuple(sources))


def _mutation(
    operator: str,
    seed: int,
    question: str,
    baseline: Corpus,
    mutated: Corpus,
    answer: Answer,
    expected: ExpectedResponse,
    metadata: Mapping[str, object],
) -> Mutation:
    payload = {
        "operator": operator,
        "seed": seed,
        "baseline": baseline.digest,
        "mutated": mutated.digest,
        "metadata": dict(metadata),
    }
    mutation_id = "%s-%s" % (operator, stable_hash(payload)[:12])
    tagged_metadata = _tag_metadata(mutated.metadata, operator, mutation_id=mutation_id)
    # This annotation powers only the included deterministic reference adapter.
    # User adapters should ignore it and exercise their own retrieval/generation path.
    tagged_metadata["reference_answer"] = answer.to_dict()
    tagged_corpus = replace(
        mutated,
        version="%s+%s" % (baseline.version, mutation_id),
        metadata=tagged_metadata,
    )
    return Mutation(
        id=mutation_id,
        operator=operator,
        seed=seed,
        question=question,
        baseline_corpus_hash=baseline.digest,
        corpus=tagged_corpus,
        baseline_answer=answer,
        expected_response=expected,
        metadata=dict(metadata),
    )


def _replace_span(source: Source, span_id: str, replacement: Optional[Span], retain_hash: bool = False) -> Source:
    spans: List[Span] = []
    for span in source.spans:
        if span.id == span_id:
            if replacement is not None:
                spans.append(replacement)
        else:
            spans.append(span)
    if not spans:
        raise MutationNotApplicable("deleting the span would leave an empty source")
    return _rebuild_source(source, spans, retain_hash=retain_hash)


def _change_number(text: str) -> Optional[Tuple[str, str, str]]:
    for match in _NUMBER_RE.finditer(text):
        token = match.group(0)
        # Dates are handled by the date operator, not accidentally as numbers.
        context = text[max(0, match.start() - 5) : min(len(text), match.end() + 5)]
        if _DATE_RE.search(context):
            continue
        suffix = "%" if token.endswith("%") else ""
        numeric = token[:-1] if suffix else token
        commas = "," in numeric
        if "." in numeric:
            decimals = len(numeric.rsplit(".", 1)[1])
            altered_value = float(numeric.replace(",", "")) + 1.0
            altered = ("%%.%df" % decimals) % altered_value
        else:
            altered_value = int(numeric.replace(",", "")) + 1
            altered = format(altered_value, ",d") if commas else str(altered_value)
        altered += suffix
        return text[: match.start()] + altered + text[match.end() :], token, altered
    return None


def _change_date(text: str) -> Optional[Tuple[str, str, str]]:
    for match in _DATE_RE.finditer(text):
        token = match.group(0)
        try:
            altered = (date.fromisoformat(token) + timedelta(days=1)).isoformat()
        except ValueError:
            continue
        return text[: match.start()] + altered + text[match.end() :], token, altered
    return None


def _conflicting_text(text: str) -> Tuple[str, str, str]:
    changed = _change_number(text) or _change_date(text)
    if changed is not None:
        return changed
    altered = "Contradictory revision: the prior statement is not accepted."
    return altered, text, altered


class MutationOperator:
    info: OperatorInfo

    def apply(self, corpus: Corpus, answer: Answer, question: str, seed: int = 0) -> Mutation:
        raise NotImplementedError


class DeleteCitedSpan(MutationOperator):
    info = OperatorInfo("delete-cited-span", "Delete a span referenced by a baseline claim.", "availability")

    def apply(self, corpus: Corpus, answer: Answer, question: str, seed: int = 0) -> Mutation:
        eligible = [target for target in _targets(corpus, answer) if len(target.source.spans) > 1]
        target = _rng_choice(eligible, seed)
        assert isinstance(target, _Target)
        replacement = _replace_span(target.source, target.span.id, None)
        replacement = replace(
            replacement,
            metadata=_tag_metadata(
                replacement.metadata, self.info.name, deleted_span_id=target.span.id
            ),
        )
        mutated = _replace_source(corpus, target.source.id, replacement)
        affected = _claims_for(answer, [target.source.id], [target.span.id])
        expected = _expected(
            answer,
            affected,
            ("missing", "span"),
            "Claims relying on the deleted span should be removed; unrelated claims should survive.",
        )
        return _mutation(
            self.info.name,
            seed,
            question,
            corpus,
            mutated,
            answer,
            expected,
            {"source_id": target.source.id, "span_id": target.span.id},
        )


class AlterNumber(MutationOperator):
    info = OperatorInfo("alter-number", "Alter a numeric value inside a cited span.", "content")

    def apply(self, corpus: Corpus, answer: Answer, question: str, seed: int = 0) -> Mutation:
        eligible: List[Tuple[_Target, Tuple[str, str, str]]] = []
        for target in _targets(corpus, answer):
            changed = _change_number(target.span.text)
            if changed is not None:
                eligible.append((target, changed))
        target, changed = _rng_choice(eligible, seed)  # type: ignore[misc]
        new_text, old_value, new_value = changed
        new_span = replace(target.span, text=new_text)
        new_source = _replace_span(target.source, target.span.id, new_span)
        new_source = replace(
            new_source,
            metadata=_tag_metadata(
                new_source.metadata,
                self.info.name,
                span_id=target.span.id,
                old_value=old_value,
                new_value=new_value,
            ),
        )
        mutated = _replace_source(corpus, target.source.id, new_source)
        affected = _claims_for(answer, [target.source.id], [target.span.id])
        expected = _expected(
            answer,
            affected,
            ("changed", "number"),
            "A claim whose quoted numeric evidence changed should not be repeated unchanged.",
        )
        return _mutation(
            self.info.name,
            seed,
            question,
            corpus,
            mutated,
            answer,
            expected,
            {
                "source_id": target.source.id,
                "span_id": target.span.id,
                "old_value": old_value,
                "new_value": new_value,
            },
        )


class AlterDate(MutationOperator):
    info = OperatorInfo("alter-date", "Move an ISO-8601 date in a cited span by one day.", "content")

    def apply(self, corpus: Corpus, answer: Answer, question: str, seed: int = 0) -> Mutation:
        eligible: List[Tuple[_Target, Tuple[str, str, str]]] = []
        for target in _targets(corpus, answer):
            changed = _change_date(target.span.text)
            if changed is not None:
                eligible.append((target, changed))
        target, changed = _rng_choice(eligible, seed)  # type: ignore[misc]
        new_text, old_value, new_value = changed
        new_span = replace(target.span, text=new_text)
        new_source = _replace_span(target.source, target.span.id, new_span)
        new_source = replace(
            new_source,
            metadata=_tag_metadata(
                new_source.metadata,
                self.info.name,
                span_id=target.span.id,
                old_value=old_value,
                new_value=new_value,
            ),
        )
        mutated = _replace_source(corpus, target.source.id, new_source)
        affected = _claims_for(answer, [target.source.id], [target.span.id])
        expected = _expected(
            answer,
            affected,
            ("changed", "date"),
            "A claim whose quoted date changed should not be repeated unchanged.",
        )
        return _mutation(
            self.info.name,
            seed,
            question,
            corpus,
            mutated,
            answer,
            expected,
            {
                "source_id": target.source.id,
                "span_id": target.span.id,
                "old_value": old_value,
                "new_value": new_value,
            },
        )


class SwapSourceIds(MutationOperator):
    info = OperatorInfo("swap-source-ids", "Swap the identifiers of two source records.", "identity")

    def apply(self, corpus: Corpus, answer: Answer, question: str, seed: int = 0) -> Mutation:
        cited_ids = sorted({target.source.id for target in _targets(corpus, answer)})
        if not cited_ids or len(corpus.sources) < 2:
            raise MutationNotApplicable("swap-source-ids requires a cited source and at least two sources")
        first_id = _rng_choice(cited_ids, seed)
        assert isinstance(first_id, str)
        alternatives = sorted(source.id for source in corpus.sources if source.id != first_id)
        second_id = _rng_choice(alternatives, seed + 1)
        assert isinstance(second_id, str)
        swapped: List[Source] = []
        for source in corpus.sources:
            if source.id == first_id:
                swapped.append(
                    replace(
                        source,
                        id=second_id,
                        metadata=_tag_metadata(source.metadata, self.info.name, original_id=first_id),
                    )
                )
            elif source.id == second_id:
                swapped.append(
                    replace(
                        source,
                        id=first_id,
                        metadata=_tag_metadata(source.metadata, self.info.name, original_id=second_id),
                    )
                )
            else:
                swapped.append(source)
        mutated = replace(corpus, sources=tuple(swapped))
        affected = _claims_for(answer, [first_id, second_id])
        expected = _expected(
            answer,
            affected,
            ("source", "identity"),
            "Claims tied to swapped source identities should be withheld unless re-grounded.",
        )
        return _mutation(
            self.info.name,
            seed,
            question,
            corpus,
            mutated,
            answer,
            expected,
            {"first_source_id": first_id, "second_source_id": second_id},
        )


class CorruptAnchor(MutationOperator):
    info = OperatorInfo(
        "corrupt-anchor",
        "Corrupt a cited span ID and its page anchor.",
        "resolvability",
    )

    def apply(self, corpus: Corpus, answer: Answer, question: str, seed: int = 0) -> Mutation:
        target = _rng_choice(_targets(corpus, answer), seed)
        assert isinstance(target, _Target)
        corrupt_id = "%s-corrupt-%s" % (target.span.id, hashlib.sha256(target.span.id.encode()).hexdigest()[:6])
        new_span = replace(
            target.span,
            id=corrupt_id,
            page="corrupt:%s" % (target.span.page or "unknown"),
            metadata=_tag_metadata(target.span.metadata, self.info.name, original_span_id=target.span.id),
        )
        new_source = _replace_span(target.source, target.span.id, new_span)
        mutated = _replace_source(corpus, target.source.id, new_source)
        affected = _claims_for(answer, [target.source.id], [target.span.id])
        expected = _expected(
            answer,
            affected,
            ("unresolvable", "anchor"),
            "An unresolvable page/span anchor must not support the original claim.",
        )
        return _mutation(
            self.info.name,
            seed,
            question,
            corpus,
            mutated,
            answer,
            expected,
            {
                "source_id": target.source.id,
                "original_span_id": target.span.id,
                "corrupt_span_id": corrupt_id,
            },
        )


class SupersedeSource(MutationOperator):
    info = OperatorInfo("supersede-source", "Add a newer source that supersedes a cited source.", "currency")

    def apply(self, corpus: Corpus, answer: Answer, question: str, seed: int = 0) -> Mutation:
        target = _rng_choice(_targets(corpus, answer), seed)
        assert isinstance(target, _Target)
        old_source = replace(
            target.source,
            current=False,
            metadata=_tag_metadata(target.source.metadata, self.info.name, superseded=True),
        )
        revised_spans: List[Span] = []
        changed_any = False
        for span in target.source.spans:
            changed = _change_number(span.text) or _change_date(span.text)
            if not changed_any and changed is not None:
                revised_spans.append(replace(span, text=changed[0]))
                changed_any = True
            else:
                revised_spans.append(span)
        if not changed_any:
            revised_spans[0] = replace(
                revised_spans[0], text=revised_spans[0].text + " This statement is revised."
            )
        suffix = stable_hash({"source": target.source.id, "seed": seed})[:8]
        new_id = "%s-revision-%s" % (target.source.id, suffix)
        new_source = replace(
            target.source,
            id=new_id,
            uri=target.source.uri + "?revision=" + suffix,
            title=target.source.title + " (superseding revision)",
            spans=tuple(revised_spans),
            sha256=Source.hash_spans(revised_spans),
            current=True,
            supersedes=(target.source.id,),
            metadata=_tag_metadata({}, self.info.name, supersedes=target.source.id),
        )
        sources = tuple(old_source if source.id == target.source.id else source for source in corpus.sources) + (
            new_source,
        )
        mutated = replace(corpus, sources=sources)
        affected = _claims_for(answer, [target.source.id])
        expected = _expected(
            answer,
            affected,
            ("superseded", "source"),
            "Claims citing a superseded source should be withheld until grounded in the current revision.",
        )
        return _mutation(
            self.info.name,
            seed,
            question,
            corpus,
            mutated,
            answer,
            expected,
            {"source_id": target.source.id, "superseding_source_id": new_id},
        )


class MoveSourceUri(MutationOperator):
    info = OperatorInfo(
        "move-source-uri",
        "Move a source URI while retaining its content hash.",
        "location",
    )

    def apply(self, corpus: Corpus, answer: Answer, question: str, seed: int = 0) -> Mutation:
        target = _rng_choice(_targets(corpus, answer), seed)
        assert isinstance(target, _Target)
        new_uri = "urn:citation-chaos:moved:%s:%s" % (target.source.sha256, seed)
        moved = replace(
            target.source,
            uri=new_uri,
            metadata=_tag_metadata(
                target.source.metadata,
                self.info.name,
                moved_from=target.source.uri,
                retained_hash=target.source.sha256,
            ),
        )
        mutated = _replace_source(corpus, target.source.id, moved)
        expected = _expected_preserve(
            answer,
            "A pure location change with the same identity and hash should not invalidate grounded claims.",
        )
        return _mutation(
            self.info.name,
            seed,
            question,
            corpus,
            mutated,
            answer,
            expected,
            {
                "source_id": target.source.id,
                "old_uri": target.source.uri,
                "new_uri": new_uri,
                "retained_hash": target.source.sha256,
            },
        )


class IntroduceConflictingCurrentSource(MutationOperator):
    info = OperatorInfo(
        "introduce-conflicting-current-source",
        "Add a second current source that conflicts with cited evidence.",
        "conflict",
    )

    def apply(self, corpus: Corpus, answer: Answer, question: str, seed: int = 0) -> Mutation:
        target = _rng_choice(_targets(corpus, answer), seed)
        assert isinstance(target, _Target)
        changed_text, old_value, new_value = _conflicting_text(target.span.text)
        conflicting_spans = tuple(
            replace(span, text=changed_text) if span.id == target.span.id else span
            for span in target.source.spans
        )
        suffix = stable_hash({"conflict": target.source.id, "seed": seed})[:8]
        conflicting = replace(
            target.source,
            id="%s-conflict-%s" % (target.source.id, suffix),
            uri="urn:citation-chaos:conflict:%s" % suffix,
            title=target.source.title + " (conflicting current source)",
            spans=conflicting_spans,
            sha256=Source.hash_spans(conflicting_spans),
            current=True,
            metadata=_tag_metadata(
                {}, self.info.name, conflicts_with=target.source.id, span_id=target.span.id
            ),
        )
        mutated = replace(corpus, sources=corpus.sources + (conflicting,))
        affected = _claims_for(answer, [target.source.id], [target.span.id])
        expected = _expected(
            answer,
            affected,
            ("conflicting", "source"),
            "A current unresolved conflict should localize impact to claims using the disputed evidence.",
        )
        return _mutation(
            self.info.name,
            seed,
            question,
            corpus,
            mutated,
            answer,
            expected,
            {
                "source_id": target.source.id,
                "conflicting_source_id": conflicting.id,
                "span_id": target.span.id,
                "old_value": old_value,
                "new_value": new_value,
            },
        )


class ReplacePrimaryWithSecondary(MutationOperator):
    info = OperatorInfo(
        "replace-primary-with-secondary",
        "Replace cited primary-source provenance with secondary-source provenance.",
        "provenance",
    )

    def apply(self, corpus: Corpus, answer: Answer, question: str, seed: int = 0) -> Mutation:
        eligible = [target for target in _targets(corpus, answer) if target.source.kind == "primary"]
        target = _rng_choice(eligible, seed)
        assert isinstance(target, _Target)
        secondary = replace(
            target.source,
            kind="secondary",
            uri="urn:citation-chaos:secondary:%s" % target.source.sha256,
            title="Secondary summary of " + target.source.title,
            metadata=_tag_metadata(
                target.source.metadata, self.info.name, replaced_primary=True
            ),
        )
        mutated = _replace_source(corpus, target.source.id, secondary)
        affected = _claims_for(answer, [target.source.id])
        expected = _expected(
            answer,
            affected,
            ("primary", "source"),
            "A policy requiring primary evidence should reject a secondary-only replacement.",
        )
        return _mutation(
            self.info.name,
            seed,
            question,
            corpus,
            mutated,
            answer,
            expected,
            {"source_id": target.source.id, "original_kind": "primary", "new_kind": "secondary"},
        )


class ZeroResultRetrieval(MutationOperator):
    info = OperatorInfo("zero-result-retrieval", "Return an empty retrieval corpus.", "availability")

    def apply(self, corpus: Corpus, answer: Answer, question: str, seed: int = 0) -> Mutation:
        if not answer.claims:
            raise MutationNotApplicable("zero-result-retrieval requires baseline claims")
        mutated = replace(
            corpus,
            sources=(),
            metadata=_tag_metadata(corpus.metadata, self.info.name, original_source_count=len(corpus.sources)),
        )
        affected = tuple(claim.id for claim in answer.claims)
        expected = _expected(
            answer,
            affected,
            ("no", "sources"),
            "No retrieval results should produce an explicit abstention, not uncited claims.",
        )
        return _mutation(
            self.info.name,
            seed,
            question,
            corpus,
            mutated,
            answer,
            expected,
            {"original_source_count": len(corpus.sources)},
        )


class StaleCacheText(MutationOperator):
    info = OperatorInfo(
        "stale-cache-text",
        "Change cached span text while retaining the recorded source hash.",
        "integrity",
    )

    def apply(self, corpus: Corpus, answer: Answer, question: str, seed: int = 0) -> Mutation:
        target = _rng_choice(_targets(corpus, answer), seed)
        assert isinstance(target, _Target)
        changed = _change_number(target.span.text) or _change_date(target.span.text)
        changed_text = changed[0] if changed is not None else target.span.text + " [stale cached copy]"
        stale_span = replace(target.span, text=changed_text)
        stale_source = _replace_span(target.source, target.span.id, stale_span, retain_hash=True)
        stale_source = replace(
            stale_source,
            metadata=_tag_metadata(
                stale_source.metadata,
                self.info.name,
                stale_cache=True,
                recorded_hash=target.source.sha256,
            ),
        )
        mutated = _replace_source(corpus, target.source.id, stale_source)
        # A document-level hash mismatch invalidates every claim using that source,
        # not only the span whose cached bytes exposed the mismatch.
        affected = _claims_for(answer, [target.source.id])
        expected = _expected(
            answer,
            affected,
            ("hash", "mismatch"),
            "Cached text that no longer matches its recorded hash should not support claims.",
        )
        return _mutation(
            self.info.name,
            seed,
            question,
            corpus,
            mutated,
            answer,
            expected,
            {"source_id": target.source.id, "span_id": target.span.id, "retained_hash": target.source.sha256},
        )


_OPERATOR_CLASSES = (
    DeleteCitedSpan,
    AlterNumber,
    AlterDate,
    SwapSourceIds,
    CorruptAnchor,
    SupersedeSource,
    MoveSourceUri,
    IntroduceConflictingCurrentSource,
    ReplacePrimaryWithSecondary,
    ZeroResultRetrieval,
    StaleCacheText,
)

OPERATORS: Mapping[str, MutationOperator] = {
    operator.info.name: operator for operator in (operator_class() for operator_class in _OPERATOR_CLASSES)
}


def operator_infos() -> Tuple[OperatorInfo, ...]:
    """Return operator metadata in stable registry order."""

    return tuple(operator.info for operator in OPERATORS.values())


def get_operator(name: str) -> MutationOperator:
    try:
        return OPERATORS[name]
    except KeyError as exc:
        raise KeyError("unknown operator %r; choose from %s" % (name, ", ".join(OPERATORS))) from exc


def generate_suite(
    corpus: Corpus,
    answer: Answer,
    question: str,
    operator_names: Optional[Sequence[str]] = None,
    seed: int = 0,
    strict: bool = False,
) -> Tuple[MutationSuite, Tuple[str, ...]]:
    """Generate mutations and return ``(suite, skipped_messages)``.

    Each operator receives ``seed + registry_index`` so target choices are stable
    even when generation is repeated.  In non-strict mode, inapplicable operators
    are reported and skipped.  Unknown names always fail.
    """

    assert_answer_references(answer, corpus)
    names = tuple(operator_names) if operator_names else tuple(OPERATORS)
    mutations: List[Mutation] = []
    skipped: List[str] = []
    for index, name in enumerate(names):
        operator = get_operator(name)
        try:
            mutations.append(operator.apply(corpus, answer, question, seed + index))
        except MutationNotApplicable as exc:
            message = "%s: %s" % (name, exc)
            if strict:
                raise MutationNotApplicable(message) from exc
            skipped.append(message)
    suite = MutationSuite(schema_version="1.0", corpus_id=corpus.id, mutations=tuple(mutations))
    return suite, tuple(skipped)
