"""Citation Chaos: mutation testing for grounded AI output pipelines.

Citation Chaos measures deterministic response behavior under controlled corpus
perturbations.  It does not prove the semantic truth of an answer.
"""

from .adapters import LoadedAdapter, PipelineAdapter, ReferenceAdapter, load_adapter
from .operators import (
    OPERATORS,
    MutationNotApplicable,
    generate_suite,
    get_operator,
    operator_infos,
)
from .runner import CHECK_NAMES, RunReport, run_mutation, run_suite, score_answer
from .schemas import (
    Answer,
    Citation,
    Claim,
    Corpus,
    ExpectedResponse,
    Mutation,
    MutationSuite,
    RunResult,
    SchemaError,
    ScoreCheck,
    Source,
    Span,
)

__version__ = "0.1.0"

__all__ = [
    "Answer",
    "CHECK_NAMES",
    "Citation",
    "Claim",
    "Corpus",
    "ExpectedResponse",
    "LoadedAdapter",
    "Mutation",
    "MutationNotApplicable",
    "MutationSuite",
    "OPERATORS",
    "PipelineAdapter",
    "ReferenceAdapter",
    "RunReport",
    "RunResult",
    "SchemaError",
    "ScoreCheck",
    "Source",
    "Span",
    "generate_suite",
    "get_operator",
    "load_adapter",
    "operator_infos",
    "run_mutation",
    "run_suite",
    "score_answer",
]
