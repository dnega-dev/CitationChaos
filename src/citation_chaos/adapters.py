"""Pipeline adapter contract and the deterministic reference adapter."""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import importlib.util
import inspect
from pathlib import Path
import sys
from types import ModuleType
from typing import Any, Callable, Mapping, Optional, Protocol, Union, runtime_checkable

from .schemas import Answer, Claim, Corpus, SchemaError, Source


@runtime_checkable
class PipelineAdapter(Protocol):
    """Minimal contract implemented by object-based pipeline adapters."""

    def run(self, question: str, corpus: Corpus) -> Union[Answer, Mapping[str, Any]]:
        """Produce a structured answer from a question and mutated corpus."""


@dataclass(frozen=True)
class LoadedAdapter:
    """A normalized callable plus a stable display name."""

    name: str
    invoke: Callable[[str, Corpus], Answer]


_OPERATOR_REASONS = {
    "delete-cited-span": "missing cited span",
    "alter-number": "number changed in cited evidence",
    "alter-date": "date changed in cited evidence",
    "swap-source-ids": "source identity changed",
    "corrupt-anchor": "citation anchor is unresolvable",
    "supersede-source": "cited source was superseded",
    "introduce-conflicting-current-source": "conflicting current source",
    "replace-primary-with-secondary": "primary source was replaced by a secondary source",
    "zero-result-retrieval": "no sources returned",
    "stale-cache-text": "source hash mismatch for stale cache text",
}


class ReferenceAdapter:
    """Deterministic structural baseline for examples and smoke tests.

    The reference adapter reads a ``reference_answer`` annotation placed in the
    corpus metadata, then retains only claims whose original citations still
    resolve, match their recorded quotes, and satisfy simple integrity/current/
    primary-source checks.  It is deliberately mechanical: it is not a semantic
    evaluator and does not prove that retained claims are true.
    """

    name = "reference"

    def run(self, question: str, corpus: Corpus) -> Answer:
        del question  # The annotated baseline is intentionally question-specific.
        raw_answer = corpus.metadata.get("reference_answer")
        if not isinstance(raw_answer, Mapping):
            raise SchemaError(
                "reference adapter requires corpus.metadata.reference_answer; use your own adapter for unannotated corpora"
            )
        baseline = Answer.from_dict(raw_answer)
        operator = ""
        chaos = corpus.metadata.get("citation_chaos")
        if isinstance(chaos, Mapping):
            value = chaos.get("operator")
            operator = value if isinstance(value, str) else ""

        retained = []
        removed_reasons = []
        for claim in baseline.claims:
            reason = self._claim_failure(claim, corpus)
            if reason is None:
                retained.append(claim)
            else:
                removed_reasons.append("%s: %s" % (claim.id, reason))

        if removed_reasons:
            operator_reason = _OPERATOR_REASONS.get(operator)
            reason_parts = [operator_reason] if operator_reason else []
            reason_parts.extend(removed_reasons)
            reason_text: Optional[str] = "; ".join(reason_parts)
        else:
            reason_text = None

        if not retained:
            return Answer(
                status="abstained",
                claims=(),
                reason=reason_text or "no resolvable grounded claims",
                text=None,
                metadata={"adapter": self.name},
            )
        return Answer(
            status="answered",
            claims=tuple(retained),
            reason=reason_text,
            text=" ".join(claim.text for claim in retained),
            metadata={"adapter": self.name},
        )

    @staticmethod
    def _claim_failure(claim: Claim, corpus: Corpus) -> Optional[str]:
        if not claim.citations:
            return "claim has no citation"
        for citation in claim.citations:
            source = corpus.source(citation.source_id)
            if source is None:
                return "missing source %s" % citation.source_id
            span = source.span(citation.span_id)
            if span is None:
                return "missing span %s/%s" % (citation.source_id, citation.span_id)
            if citation.quote is not None and citation.quote != span.text:
                return "cited text changed"
            if source.sha256 != Source.hash_spans(source.spans):
                return "hash mismatch"
            if not source.current:
                return "source superseded"
            if source.kind != "primary":
                return "primary source unavailable"
            for candidate in corpus.sources:
                marker = candidate.metadata.get("citation_chaos")
                if not isinstance(marker, Mapping):
                    continue
                if marker.get("operator") != "introduce-conflicting-current-source":
                    continue
                if marker.get("conflicts_with") == source.id and marker.get("span_id") == span.id:
                    return "conflicting current source"
        return None


def _module_from_path(path: Path) -> ModuleType:
    resolved = path.resolve()
    if not resolved.is_file():
        raise ValueError("adapter path does not exist: %s" % path)
    module_name = "citation_chaos_user_adapter_%s" % abs(hash(str(resolved)))
    spec = importlib.util.spec_from_file_location(module_name, str(resolved))
    if spec is None or spec.loader is None:
        raise ValueError("could not import adapter file: %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def _resolve_spec(specification: str) -> Any:
    if specification == "reference":
        return ReferenceAdapter()
    module_part, separator, object_part = specification.partition(":")
    if not separator or not module_part or not object_part:
        raise ValueError("adapter must be 'reference' or MODULE:OBJECT / PATH.py:OBJECT")
    if module_part.endswith(".py") or "/" in module_part or "\\" in module_part:
        module = _module_from_path(Path(module_part))
    else:
        module = importlib.import_module(module_part)
    target: Any = module
    for component in object_part.split("."):
        if not component:
            raise ValueError("adapter object path must not contain empty components")
        try:
            target = getattr(target, component)
        except AttributeError as exc:
            raise ValueError("adapter object %r was not found" % object_part) from exc
    return target


def load_adapter(specification: str) -> LoadedAdapter:
    """Load and normalize an adapter specification.

    Importing an adapter executes user-supplied Python.  Callers should only load
    trusted adapter modules.
    """

    target = _resolve_spec(specification)
    if inspect.isclass(target):
        target = target()
    candidate: Any
    if hasattr(target, "run") and callable(target.run):
        candidate = target.run
    elif callable(target):
        candidate = target
    else:
        raise ValueError("adapter object must be callable or expose run(question, corpus)")

    name = getattr(target, "name", None)
    if not isinstance(name, str) or not name.strip():
        name = specification

    def invoke(question: str, corpus: Corpus) -> Answer:
        result = candidate(question, corpus)
        if isinstance(result, Answer):
            return result
        if isinstance(result, Mapping):
            return Answer.from_dict(result)
        raise TypeError("adapter returned %s; expected Answer or mapping" % type(result).__name__)

    return LoadedAdapter(name=name, invoke=invoke)
