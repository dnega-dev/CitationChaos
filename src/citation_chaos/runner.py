"""Mutation execution and structural behavioral scoring."""

from __future__ import annotations

from dataclasses import dataclass
import traceback
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Set, Tuple

from .adapters import LoadedAdapter
from .schemas import Answer, Claim, Corpus, Mutation, MutationSuite, RunResult, ScoreCheck, stable_hash


CHECK_NAMES = (
    "abstention",
    "unsupported-claim-removal",
    "unaffected-claim-preservation",
    "impact-localization",
    "explicit-reason",
    "citation-resolvability",
)


@dataclass(frozen=True)
class RunReport:
    """Aggregate result for a mutation suite."""

    run_id: str
    adapter: str
    results: Tuple[RunResult, ...]

    @property
    def passed(self) -> int:
        return sum(result.status == "passed" for result in self.results)

    @property
    def failed(self) -> int:
        return sum(result.status == "failed" for result in self.results)

    @property
    def errors(self) -> int:
        return sum(result.status == "error" for result in self.results)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def successful(self) -> bool:
        return self.failed == 0 and self.errors == 0

    def to_dict(self) -> Dict[str, object]:
        return {
            "schema_version": "1.0",
            "run_id": self.run_id,
            "adapter": self.adapter,
            "summary": {
                "total": self.total,
                "passed": self.passed,
                "failed": self.failed,
                "errors": self.errors,
                "successful": self.successful,
            },
            "results": [result.to_dict() for result in self.results],
        }


def _ids(answer: Answer) -> Set[str]:
    return {claim.id for claim in answer.claims}


def _claim_texts(answer: Answer) -> Dict[str, str]:
    return {claim.id: claim.text for claim in answer.claims}


def _citation_errors(answer: Answer, corpus: Corpus) -> Tuple[str, ...]:
    errors: List[str] = []
    for claim in answer.claims:
        if not claim.citations:
            errors.append("%s has no citations" % claim.id)
            continue
        for citation in claim.citations:
            source = corpus.source(citation.source_id)
            if source is None:
                errors.append("%s references missing source %s" % (claim.id, citation.source_id))
            elif source.span(citation.span_id) is None:
                errors.append(
                    "%s references missing span %s/%s"
                    % (claim.id, citation.source_id, citation.span_id)
                )
    return tuple(errors)


def score_answer(mutation: Mutation, answer: Answer) -> Tuple[ScoreCheck, ...]:
    """Score an answer using six exact, explainable structural checks.

    These checks measure response behavior under a known perturbation.  They do
    not judge open-ended semantic truth.
    """

    expected = mutation.expected_response
    observed_ids = _ids(answer)
    baseline_ids = _ids(mutation.baseline_answer)
    baseline_text = _claim_texts(mutation.baseline_answer)
    observed_text = _claim_texts(answer)

    if expected.must_abstain:
        abstention_passed = answer.status == "abstained" and not answer.claims
        abstention_details = "expected an empty abstention"
    else:
        abstention_passed = answer.status == "answered"
        abstention_details = "expected a non-abstaining answer"
    checks: List[ScoreCheck] = [
        ScoreCheck(
            name="abstention",
            passed=abstention_passed,
            details=abstention_details,
            expected="abstained" if expected.must_abstain else "answered",
            observed=answer.status,
        )
    ]

    remove_ids = set(expected.remove_claim_ids)
    lingering = sorted(remove_ids & observed_ids)
    checks.append(
        ScoreCheck(
            name="unsupported-claim-removal",
            passed=not lingering,
            details=(
                "all expected unsupported claims were removed"
                if not lingering
                else "unsupported claims remain: %s" % ", ".join(lingering)
            ),
            expected=sorted(remove_ids),
            observed=lingering,
        )
    )

    preserve_ids = set(expected.preserve_claim_ids)
    missing_preserved = sorted(preserve_ids - observed_ids)
    changed_preserved = sorted(
        claim_id
        for claim_id in preserve_ids & observed_ids
        if observed_text.get(claim_id) != baseline_text.get(claim_id)
    )
    preservation_passed = not missing_preserved and not changed_preserved
    preservation_problems = []
    if missing_preserved:
        preservation_problems.append("missing: %s" % ", ".join(missing_preserved))
    if changed_preserved:
        preservation_problems.append("text changed: %s" % ", ".join(changed_preserved))
    checks.append(
        ScoreCheck(
            name="unaffected-claim-preservation",
            passed=preservation_passed,
            details="preserved exactly" if preservation_passed else "; ".join(preservation_problems),
            expected=sorted(preserve_ids),
            observed=sorted(preserve_ids & observed_ids),
        )
    )

    changed_ids = {
        claim_id
        for claim_id in baseline_ids
        if claim_id not in observed_ids or baseline_text.get(claim_id) != observed_text.get(claim_id)
    }
    added_ids = observed_ids - baseline_ids
    expected_impact = set(expected.impact_claim_ids)
    localization_passed = changed_ids == expected_impact and not added_ids
    localization_details = "impact matched expected claim set"
    if not localization_passed:
        localization_details = "changed=%s added=%s expected=%s" % (
            sorted(changed_ids),
            sorted(added_ids),
            sorted(expected_impact),
        )
    checks.append(
        ScoreCheck(
            name="impact-localization",
            passed=localization_passed,
            details=localization_details,
            expected=sorted(expected_impact),
            observed={"changed": sorted(changed_ids), "added": sorted(added_ids)},
        )
    )

    reason_text = (answer.reason or "").casefold()
    reason_tokens = tuple(token.casefold() for token in expected.reason_contains)
    missing_tokens = sorted(token for token in reason_tokens if token not in reason_text)
    reason_required = bool(reason_tokens or expected.must_abstain or expected.remove_claim_ids)
    reason_passed = (not reason_required) or (bool(answer.reason) and not missing_tokens)
    checks.append(
        ScoreCheck(
            name="explicit-reason",
            passed=reason_passed,
            details=(
                "reason supplied with required terms"
                if reason_passed and reason_required
                else "no reason required"
                if reason_passed
                else "reason missing terms: %s" % ", ".join(missing_tokens)
            ),
            expected=list(expected.reason_contains),
            observed=answer.reason,
        )
    )

    citation_errors = list(_citation_errors(answer, mutation.corpus))
    expected_resolvable = set(expected.resolvable_claim_ids)
    missing_resolvable = sorted(expected_resolvable - observed_ids)
    if missing_resolvable:
        citation_errors.append("expected resolvable claims missing: %s" % ", ".join(missing_resolvable))
    resolvability_passed = not citation_errors
    checks.append(
        ScoreCheck(
            name="citation-resolvability",
            passed=resolvability_passed,
            details=(
                "all emitted citations resolve"
                if resolvability_passed
                else "; ".join(citation_errors)
            ),
            expected=sorted(expected_resolvable),
            observed=sorted(observed_ids),
        )
    )

    return tuple(checks)


def run_mutation(mutation: Mutation, adapter: LoadedAdapter, include_traceback: bool = False) -> RunResult:
    """Execute and score one mutation, converting adapter failures to error results."""

    try:
        answer = adapter.invoke(mutation.question, mutation.corpus)
        checks = score_answer(mutation, answer)
        status = "passed" if all(check.passed for check in checks) else "failed"
        return RunResult(
            mutation_id=mutation.id,
            operator=mutation.operator,
            adapter=adapter.name,
            status=status,
            checks=checks,
            answer=answer,
        )
    except Exception as exc:  # Adapter isolation boundary: record, then continue the suite.
        if include_traceback:
            message = traceback.format_exc()
        else:
            message = "%s: %s" % (type(exc).__name__, exc)
        return RunResult(
            mutation_id=mutation.id,
            operator=mutation.operator,
            adapter=adapter.name,
            status="error",
            checks=(),
            error=message,
        )


def run_suite(
    suite: MutationSuite,
    adapter: LoadedAdapter,
    include_traceback: bool = False,
) -> RunReport:
    """Run a suite sequentially in manifest order for deterministic reporting."""

    results = tuple(
        run_mutation(mutation, adapter, include_traceback=include_traceback)
        for mutation in suite.mutations
    )
    run_id = "run-%s" % stable_hash(
        {"adapter": adapter.name, "mutations": [mutation.id for mutation in suite.mutations]}
    )[:12]
    return RunReport(run_id=run_id, adapter=adapter.name, results=results)
