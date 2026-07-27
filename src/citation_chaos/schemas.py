"""Validated, JSON-serializable data models for Citation Chaos.

The models intentionally use only the Python standard library.  Every schema has
``to_dict`` and ``from_dict`` methods so adapters can cross process boundaries
without depending on a serialization framework.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import hashlib
import json
import re
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple


class SchemaError(ValueError):
    """Raised when a Citation Chaos schema is invalid."""


def _require_string(value: Any, path: str, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise SchemaError("%s must be a string" % path)
    if not allow_empty and not value.strip():
        raise SchemaError("%s must not be empty" % path)
    return value


def _optional_string(value: Any, path: str) -> Optional[str]:
    if value is None:
        return None
    return _require_string(value, path)


def _mapping(value: Any, path: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaError("%s must be an object" % path)
    return value


def _string_tuple(value: Any, path: str) -> Tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise SchemaError("%s must be an array" % path)
    return tuple(_require_string(item, "%s[%d]" % (path, index)) for index, item in enumerate(value))


def _json_safe_mapping(value: Any, path: str) -> Dict[str, Any]:
    mapping = dict(_mapping(value, path))
    try:
        json.dumps(mapping, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise SchemaError("%s must contain JSON-serializable values: %s" % (path, exc))
    return mapping


def canonical_json(value: Any) -> str:
    """Return stable compact JSON for hashing and reproducible fixtures."""

    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def stable_hash(value: Any) -> str:
    """Return a SHA-256 hash of a JSON-compatible value."""

    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Span:
    """A directly citable text range in a source.

    ``start`` and ``end`` are offsets into the source's logical text when known.
    They are anchors, not proof that the text is semantically correct.
    """

    id: str
    text: str
    start: Optional[int] = None
    end: Optional[int] = None
    page: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_string(self.id, "span.id")
        _require_string(self.text, "span.text")
        if (self.start is None) != (self.end is None):
            raise SchemaError("span.start and span.end must either both be set or both be null")
        if self.start is not None:
            if isinstance(self.start, bool) or not isinstance(self.start, int) or self.start < 0:
                raise SchemaError("span.start must be a non-negative integer")
            if isinstance(self.end, bool) or not isinstance(self.end, int) or self.end < self.start:
                raise SchemaError("span.end must be an integer greater than or equal to span.start")
        _optional_string(self.page, "span.page")
        object.__setattr__(self, "metadata", _json_safe_mapping(self.metadata, "span.metadata"))

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"id": self.id, "text": self.text}
        if self.start is not None:
            result["start"] = self.start
            result["end"] = self.end
        if self.page is not None:
            result["page"] = self.page
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Span":
        data = _mapping(value, "span")
        return cls(
            id=data.get("id"),
            text=data.get("text"),
            start=data.get("start"),
            end=data.get("end"),
            page=data.get("page"),
            metadata=data.get("metadata", {}),
        )


_SOURCE_KINDS = {"primary", "secondary"}


@dataclass(frozen=True)
class Source:
    """A retrievable source document and its citable spans."""

    id: str
    uri: str
    title: str
    spans: Tuple[Span, ...]
    sha256: str
    kind: str = "primary"
    published_at: Optional[str] = None
    supersedes: Tuple[str, ...] = ()
    current: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_string(self.id, "source.id")
        _require_string(self.uri, "source.uri")
        _require_string(self.title, "source.title")
        spans = tuple(self.spans)
        if not spans:
            raise SchemaError("source.spans must not be empty")
        if not all(isinstance(span, Span) for span in spans):
            raise SchemaError("source.spans must contain Span objects")
        span_ids = [span.id for span in spans]
        if len(span_ids) != len(set(span_ids)):
            raise SchemaError("source span IDs must be unique")
        object.__setattr__(self, "spans", spans)
        digest = _require_string(self.sha256, "source.sha256").lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise SchemaError("source.sha256 must be a 64-character hexadecimal digest")
        object.__setattr__(self, "sha256", digest)
        if self.kind not in _SOURCE_KINDS:
            raise SchemaError("source.kind must be one of: %s" % ", ".join(sorted(_SOURCE_KINDS)))
        if self.published_at is not None:
            published = _require_string(self.published_at, "source.published_at")
            try:
                date.fromisoformat(published)
            except ValueError as exc:
                raise SchemaError("source.published_at must be an ISO-8601 date") from exc
        supersedes = tuple(self.supersedes)
        for index, source_id in enumerate(supersedes):
            _require_string(source_id, "source.supersedes[%d]" % index)
        object.__setattr__(self, "supersedes", supersedes)
        if not isinstance(self.current, bool):
            raise SchemaError("source.current must be a boolean")
        object.__setattr__(self, "metadata", _json_safe_mapping(self.metadata, "source.metadata"))

    @staticmethod
    def hash_spans(spans: Sequence[Span]) -> str:
        text = "\n".join(span.text for span in spans)
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    def span(self, span_id: str) -> Optional[Span]:
        return next((item for item in self.spans if item.id == span_id), None)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "uri": self.uri,
            "title": self.title,
            "sha256": self.sha256,
            "kind": self.kind,
            "current": self.current,
            "spans": [span.to_dict() for span in self.spans],
        }
        if self.published_at is not None:
            result["published_at"] = self.published_at
        if self.supersedes:
            result["supersedes"] = list(self.supersedes)
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Source":
        data = _mapping(value, "source")
        spans = data.get("spans")
        if not isinstance(spans, (list, tuple)):
            raise SchemaError("source.spans must be an array")
        return cls(
            id=data.get("id"),
            uri=data.get("uri"),
            title=data.get("title"),
            sha256=data.get("sha256"),
            kind=data.get("kind", "primary"),
            published_at=data.get("published_at"),
            supersedes=_string_tuple(data.get("supersedes", []), "source.supersedes"),
            current=data.get("current", True),
            spans=tuple(Span.from_dict(item) for item in spans),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class Corpus:
    """A versioned collection of sources supplied to a grounded pipeline."""

    id: str
    sources: Tuple[Source, ...]
    version: str = "1"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_string(self.id, "corpus.id")
        _require_string(self.version, "corpus.version")
        sources = tuple(self.sources)
        if not all(isinstance(source, Source) for source in sources):
            raise SchemaError("corpus.sources must contain Source objects")
        source_ids = [source.id for source in sources]
        if len(source_ids) != len(set(source_ids)):
            raise SchemaError("corpus source IDs must be unique")
        object.__setattr__(self, "sources", sources)
        object.__setattr__(self, "metadata", _json_safe_mapping(self.metadata, "corpus.metadata"))

    def source(self, source_id: str) -> Optional[Source]:
        return next((item for item in self.sources if item.id == source_id), None)

    @property
    def digest(self) -> str:
        return stable_hash(self.to_dict())

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "version": self.version,
            "sources": [source.to_dict() for source in self.sources],
        }
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Corpus":
        data = _mapping(value, "corpus")
        sources = data.get("sources")
        if not isinstance(sources, (list, tuple)):
            raise SchemaError("corpus.sources must be an array")
        return cls(
            id=data.get("id"),
            version=data.get("version", "1"),
            sources=tuple(Source.from_dict(item) for item in sources),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class Citation:
    """A claim-level pointer to a source span and optional display anchor."""

    source_id: str
    span_id: str
    anchor: Optional[str] = None
    quote: Optional[str] = None

    def __post_init__(self) -> None:
        _require_string(self.source_id, "citation.source_id")
        _require_string(self.span_id, "citation.span_id")
        _optional_string(self.anchor, "citation.anchor")
        _optional_string(self.quote, "citation.quote")

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {"source_id": self.source_id, "span_id": self.span_id}
        if self.anchor is not None:
            result["anchor"] = self.anchor
        if self.quote is not None:
            result["quote"] = self.quote
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Citation":
        data = _mapping(value, "citation")
        return cls(
            source_id=data.get("source_id"),
            span_id=data.get("span_id"),
            anchor=data.get("anchor"),
            quote=data.get("quote"),
        )


@dataclass(frozen=True)
class Claim:
    """An atomic answer assertion and the citations offered for it."""

    id: str
    text: str
    citations: Tuple[Citation, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_string(self.id, "claim.id")
        _require_string(self.text, "claim.text")
        citations = tuple(self.citations)
        if not all(isinstance(citation, Citation) for citation in citations):
            raise SchemaError("claim.citations must contain Citation objects")
        object.__setattr__(self, "citations", citations)
        object.__setattr__(self, "metadata", _json_safe_mapping(self.metadata, "claim.metadata"))

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "text": self.text,
            "citations": [citation.to_dict() for citation in self.citations],
        }
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Claim":
        data = _mapping(value, "claim")
        citations = data.get("citations", [])
        if not isinstance(citations, (list, tuple)):
            raise SchemaError("claim.citations must be an array")
        return cls(
            id=data.get("id"),
            text=data.get("text"),
            citations=tuple(Citation.from_dict(item) for item in citations),
            metadata=data.get("metadata", {}),
        )


_ANSWER_STATUSES = {"answered", "abstained"}


@dataclass(frozen=True)
class Answer:
    """Structured pipeline output used for mutation scoring."""

    status: str
    claims: Tuple[Claim, ...] = ()
    reason: Optional[str] = None
    text: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.status not in _ANSWER_STATUSES:
            raise SchemaError("answer.status must be one of: answered, abstained")
        claims = tuple(self.claims)
        if not all(isinstance(claim, Claim) for claim in claims):
            raise SchemaError("answer.claims must contain Claim objects")
        claim_ids = [claim.id for claim in claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise SchemaError("answer claim IDs must be unique")
        if self.status == "abstained" and claims:
            raise SchemaError("an abstained answer must not contain claims")
        if self.status == "answered" and not claims:
            raise SchemaError("an answered answer must contain at least one claim")
        if self.status == "abstained" and not self.reason:
            raise SchemaError("an abstained answer must include a reason")
        object.__setattr__(self, "claims", claims)
        _optional_string(self.reason, "answer.reason")
        _optional_string(self.text, "answer.text")
        object.__setattr__(self, "metadata", _json_safe_mapping(self.metadata, "answer.metadata"))

    def claim(self, claim_id: str) -> Optional[Claim]:
        return next((item for item in self.claims if item.id == claim_id), None)

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "status": self.status,
            "claims": [claim.to_dict() for claim in self.claims],
        }
        if self.reason is not None:
            result["reason"] = self.reason
        if self.text is not None:
            result["text"] = self.text
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Answer":
        data = _mapping(value, "answer")
        claims = data.get("claims", [])
        if not isinstance(claims, (list, tuple)):
            raise SchemaError("answer.claims must be an array")
        return cls(
            status=data.get("status"),
            claims=tuple(Claim.from_dict(item) for item in claims),
            reason=data.get("reason"),
            text=data.get("text"),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class ExpectedResponse:
    """Machine-checkable behavioral expectations for one mutation."""

    must_abstain: bool = False
    remove_claim_ids: Tuple[str, ...] = ()
    preserve_claim_ids: Tuple[str, ...] = ()
    impact_claim_ids: Tuple[str, ...] = ()
    reason_contains: Tuple[str, ...] = ()
    resolvable_claim_ids: Tuple[str, ...] = ()
    notes: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.must_abstain, bool):
            raise SchemaError("expected_response.must_abstain must be a boolean")
        for name in (
            "remove_claim_ids",
            "preserve_claim_ids",
            "impact_claim_ids",
            "reason_contains",
            "resolvable_claim_ids",
        ):
            values = tuple(getattr(self, name))
            for index, item in enumerate(values):
                _require_string(item, "expected_response.%s[%d]" % (name, index))
            object.__setattr__(self, name, values)
        overlap = set(self.remove_claim_ids) & set(self.preserve_claim_ids)
        if overlap:
            raise SchemaError("expected response cannot both remove and preserve: %s" % ", ".join(sorted(overlap)))
        _optional_string(self.notes, "expected_response.notes")

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "must_abstain": self.must_abstain,
            "remove_claim_ids": list(self.remove_claim_ids),
            "preserve_claim_ids": list(self.preserve_claim_ids),
            "impact_claim_ids": list(self.impact_claim_ids),
            "reason_contains": list(self.reason_contains),
            "resolvable_claim_ids": list(self.resolvable_claim_ids),
        }
        if self.notes is not None:
            result["notes"] = self.notes
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ExpectedResponse":
        data = _mapping(value, "expected_response")
        return cls(
            must_abstain=data.get("must_abstain", False),
            remove_claim_ids=_string_tuple(data.get("remove_claim_ids", []), "expected_response.remove_claim_ids"),
            preserve_claim_ids=_string_tuple(data.get("preserve_claim_ids", []), "expected_response.preserve_claim_ids"),
            impact_claim_ids=_string_tuple(data.get("impact_claim_ids", []), "expected_response.impact_claim_ids"),
            reason_contains=_string_tuple(data.get("reason_contains", []), "expected_response.reason_contains"),
            resolvable_claim_ids=_string_tuple(
                data.get("resolvable_claim_ids", []), "expected_response.resolvable_claim_ids"
            ),
            notes=data.get("notes"),
        )


@dataclass(frozen=True)
class Mutation:
    """A deterministic corpus perturbation and its expected pipeline response."""

    id: str
    operator: str
    seed: int
    question: str
    baseline_corpus_hash: str
    corpus: Corpus
    baseline_answer: Answer
    expected_response: ExpectedResponse
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_string(self.id, "mutation.id")
        _require_string(self.operator, "mutation.operator")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise SchemaError("mutation.seed must be a non-negative integer")
        _require_string(self.question, "mutation.question")
        digest = _require_string(self.baseline_corpus_hash, "mutation.baseline_corpus_hash").lower()
        if not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise SchemaError("mutation.baseline_corpus_hash must be a SHA-256 digest")
        object.__setattr__(self, "baseline_corpus_hash", digest)
        if not isinstance(self.corpus, Corpus):
            raise SchemaError("mutation.corpus must be a Corpus")
        if not isinstance(self.baseline_answer, Answer):
            raise SchemaError("mutation.baseline_answer must be an Answer")
        if not isinstance(self.expected_response, ExpectedResponse):
            raise SchemaError("mutation.expected_response must be an ExpectedResponse")
        object.__setattr__(self, "metadata", _json_safe_mapping(self.metadata, "mutation.metadata"))

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "id": self.id,
            "operator": self.operator,
            "seed": self.seed,
            "question": self.question,
            "baseline_corpus_hash": self.baseline_corpus_hash,
            "corpus": self.corpus.to_dict(),
            "baseline_answer": self.baseline_answer.to_dict(),
            "expected_response": self.expected_response.to_dict(),
        }
        if self.metadata:
            result["metadata"] = dict(self.metadata)
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "Mutation":
        data = _mapping(value, "mutation")
        return cls(
            id=data.get("id"),
            operator=data.get("operator"),
            seed=data.get("seed"),
            question=data.get("question"),
            baseline_corpus_hash=data.get("baseline_corpus_hash"),
            corpus=Corpus.from_dict(data.get("corpus")),
            baseline_answer=Answer.from_dict(data.get("baseline_answer")),
            expected_response=ExpectedResponse.from_dict(data.get("expected_response")),
            metadata=data.get("metadata", {}),
        )


@dataclass(frozen=True)
class MutationSuite:
    """Portable manifest consumed by ``citation-chaos run``."""

    schema_version: str
    corpus_id: str
    mutations: Tuple[Mutation, ...]

    def __post_init__(self) -> None:
        _require_string(self.schema_version, "mutation_suite.schema_version")
        _require_string(self.corpus_id, "mutation_suite.corpus_id")
        mutations = tuple(self.mutations)
        if not all(isinstance(mutation, Mutation) for mutation in mutations):
            raise SchemaError("mutation_suite.mutations must contain Mutation objects")
        ids = [mutation.id for mutation in mutations]
        if len(ids) != len(set(ids)):
            raise SchemaError("mutation IDs must be unique")
        object.__setattr__(self, "mutations", mutations)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "corpus_id": self.corpus_id,
            "mutations": [mutation.to_dict() for mutation in self.mutations],
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "MutationSuite":
        data = _mapping(value, "mutation_suite")
        mutations = data.get("mutations")
        if not isinstance(mutations, (list, tuple)):
            raise SchemaError("mutation_suite.mutations must be an array")
        return cls(
            schema_version=data.get("schema_version", "1.0"),
            corpus_id=data.get("corpus_id"),
            mutations=tuple(Mutation.from_dict(item) for item in mutations),
        )


@dataclass(frozen=True)
class ScoreCheck:
    """Result of one named behavioral check."""

    name: str
    passed: bool
    details: str
    expected: Any = None
    observed: Any = None

    def __post_init__(self) -> None:
        _require_string(self.name, "score_check.name")
        if not isinstance(self.passed, bool):
            raise SchemaError("score_check.passed must be a boolean")
        _require_string(self.details, "score_check.details", allow_empty=True)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "details": self.details,
            "expected": self.expected,
            "observed": self.observed,
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "ScoreCheck":
        data = _mapping(value, "score_check")
        return cls(
            name=data.get("name"),
            passed=data.get("passed"),
            details=data.get("details", ""),
            expected=data.get("expected"),
            observed=data.get("observed"),
        )


_RUN_STATUSES = {"passed", "failed", "error"}


@dataclass(frozen=True)
class RunResult:
    """Adapter output plus all mutation scoring checks."""

    mutation_id: str
    operator: str
    adapter: str
    status: str
    checks: Tuple[ScoreCheck, ...]
    answer: Optional[Answer] = None
    error: Optional[str] = None

    def __post_init__(self) -> None:
        _require_string(self.mutation_id, "run_result.mutation_id")
        _require_string(self.operator, "run_result.operator")
        _require_string(self.adapter, "run_result.adapter")
        if self.status not in _RUN_STATUSES:
            raise SchemaError("run_result.status must be one of: passed, failed, error")
        checks = tuple(self.checks)
        if not all(isinstance(check, ScoreCheck) for check in checks):
            raise SchemaError("run_result.checks must contain ScoreCheck objects")
        object.__setattr__(self, "checks", checks)
        if self.answer is not None and not isinstance(self.answer, Answer):
            raise SchemaError("run_result.answer must be an Answer or null")
        _optional_string(self.error, "run_result.error")
        if self.status == "error" and not self.error:
            raise SchemaError("an error run result must include an error message")

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def to_dict(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "mutation_id": self.mutation_id,
            "operator": self.operator,
            "adapter": self.adapter,
            "status": self.status,
            "checks": [check.to_dict() for check in self.checks],
        }
        if self.answer is not None:
            result["answer"] = self.answer.to_dict()
        if self.error is not None:
            result["error"] = self.error
        return result

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RunResult":
        data = _mapping(value, "run_result")
        checks = data.get("checks", [])
        if not isinstance(checks, (list, tuple)):
            raise SchemaError("run_result.checks must be an array")
        answer = data.get("answer")
        return cls(
            mutation_id=data.get("mutation_id"),
            operator=data.get("operator"),
            adapter=data.get("adapter"),
            status=data.get("status"),
            checks=tuple(ScoreCheck.from_dict(item) for item in checks),
            answer=Answer.from_dict(answer) if answer is not None else None,
            error=data.get("error"),
        )


def assert_answer_references(answer: Answer, corpus: Corpus) -> None:
    """Validate every answer citation against source/span IDs in ``corpus``.

    This is structural resolvability only.  It does not establish semantic truth.
    """

    for claim in answer.claims:
        for citation in claim.citations:
            source = corpus.source(citation.source_id)
            if source is None:
                raise SchemaError(
                    "claim %s citation references missing source %s" % (claim.id, citation.source_id)
                )
            if source.span(citation.span_id) is None:
                raise SchemaError(
                    "claim %s citation references missing span %s/%s"
                    % (claim.id, citation.source_id, citation.span_id)
                )
