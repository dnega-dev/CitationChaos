# Citation Chaos

**Mutation testing for grounded AI output pipelines.**

Citation Chaos (CLI: `citation-chaos`) is a zero-runtime-dependency Python 3.9+
toolkit for checking how a grounded answer pipeline reacts when its evidence is
deleted, altered, moved, superseded, conflicted, or made unresolvable. It treats
claims and citations as structured data, runs deterministic corpus mutations,
and scores exact behavioral expectations.

> Citation Chaos does **not** prove semantic truth, factual correctness, or the
> quality of retrieval. Passing means the pipeline responded as expected to the
> mutations in the suite. Human review and domain-specific evaluation remain
> necessary.

## What the MVP includes

- Validated JSON schemas for corpus, source, span, claim, citation, answer,
  mutation, expected response, and run result.
- Eleven seeded, deterministic mutation operators.
- A small adapter contract for user-supplied Python pipelines.
- A deterministic, mechanical reference adapter for smoke tests.
- Six explainable checks per mutation: abstention, unsupported-claim removal,
  unaffected-claim preservation, impact localization, explicit reason, and
  citation resolvability.
- Text, JSON, JUnit XML, and SARIF 2.1.0 reports.
- Two synthetic seeded corpora and an end-to-end `unittest` suite.
- No runtime dependencies beyond the Python standard library.

## Quick start

From a source checkout:

```sh
export PYTHONPATH="$PWD/src"
python3 -m citation_chaos operators list
python3 -m citation_chaos init .demo
python3 -m citation_chaos mutate .demo/corpus.json \
  --answer .demo/answer.json \
  --output .demo/mutations.json
python3 -m citation_chaos run .demo/mutations.json --adapter reference
```

After installation, replace `python3 -m citation_chaos` with `citation-chaos`.
The starter corpus stores its question in `corpus.metadata.question`; otherwise
pass `--question` to `mutate`.

A successful text summary looks like:

```text
Summary: 11 total, 11 passed, 0 failed, 0 errors
Note: these are mutation-response checks, not proof of semantic truth.
```

## CLI

### `init`

```sh
citation-chaos init DIRECTORY [--force]
```

Creates `corpus.json`, `answer.json`, `question.txt`, and a safe adapter stub.
Existing generated files are never overwritten unless `--force` is supplied.
The synthetic starter must not be interpreted as real-world data.

### `mutate`

```sh
citation-chaos mutate CORPUS.json --answer ANSWER.json \
  [--question TEXT] [--operator NAME ...] [--seed N] [--strict] \
  --output mutations.json
```

With no `--operator`, all registered operators are attempted in stable registry
order. Inapplicable operators are reported and skipped; `--strict` instead fails
immediately. The same validated inputs, selected operators, and seed produce the
same serialized mutation content and mutation IDs.

### `run`

```sh
citation-chaos run mutations.json \
  --adapter reference \
  --format text \
  --output -
```

Adapters can also be trusted local imports:

```sh
citation-chaos run mutations.json \
  --adapter examples/pipeline_adapter.py:run_pipeline \
  --format junit --output report.xml
```

Supported formats are `text`, `json`, `junit`, and `sarif`. Exit status is `0`
when every mutation passes, `1` for scored failures or adapter errors, and `2`
for invalid CLI input. Use `--traceback` only when diagnostic stack traces are
appropriate for the report.

### `operators list`

```sh
citation-chaos operators list
citation-chaos operators list --format json
```

## Operators

| Operator | Perturbation | Expected behavioral pressure |
|---|---|---|
| `delete-cited-span` | Removes one cited span | Remove only dependent claims |
| `alter-number` | Increments a numeric token | Do not repeat the old numeric claim |
| `alter-date` | Moves an ISO date by one day | Do not repeat the old dated claim |
| `swap-source-ids` | Swaps two source identifiers | Detect provenance/identity drift |
| `corrupt-anchor` | Changes span ID and page anchor | Reject unresolvable citations |
| `supersede-source` | Adds a revision and marks cited source non-current | Reject stale provenance |
| `move-source-uri` | Changes URI, retaining ID, text, and hash | Preserve unaffected claims |
| `introduce-conflicting-current-source` | Adds current contradictory evidence | Localize uncertainty to disputed claims |
| `replace-primary-with-secondary` | Downgrades primary provenance to secondary | Enforce primary-source policy |
| `zero-result-retrieval` | Supplies an empty corpus | Explicitly abstain |
| `stale-cache-text` | Changes text while retaining recorded hash | Detect integrity mismatch |

See [docs/mutation-model.md](docs/mutation-model.md) for exact assumptions and
limitations.

## Adapter contract

An adapter is a callable or object with `run(question, corpus)`. It returns an
`Answer` or an `Answer`-compatible mapping:

```python
from citation_chaos import Answer, Claim, Citation


def run_pipeline(question, corpus):
    raw = your_pipeline(question, corpus.to_dict())
    return Answer(
        status="answered",
        claims=(
            Claim(
                id="stable-claim-id",
                text=raw["claim"],
                citations=(
                    Citation(
                        source_id=raw["source_id"],
                        span_id=raw["span_id"],
                        quote=raw.get("quote"),
                    ),
                ),
            ),
        ),
        reason=raw.get("reason"),
    )
```

Claim IDs must be stable across the baseline and mutated runs. Use `status`
`"abstained"`, no claims, and a non-empty `reason` for abstention. The adapter
runs in-process; importing an adapter executes Python code, so load only trusted
modules.

The included `reference` adapter consumes a harness annotation, compares cited
quotes and hashes, and applies simple current/primary-source rules. It exists to
verify fixtures, operators, scoring, and reporters. It is **not** an evaluator of
model intelligence or semantic truth and must not be used as benchmark evidence.

## Data model at a glance

- A **corpus** contains uniquely identified **sources**.
- A source has a URI, SHA-256 content fingerprint, provenance kind, currency
  fields, and uniquely identified **spans**.
- An **answer** contains atomic, stable-ID **claims**.
- Each claim has zero or more **citations**, each pointing to a source ID and
  span ID and optionally recording an anchor and exact quote.
- A **mutation** embeds the mutated corpus, baseline answer, operator metadata,
  and an **expected response**.
- A **run result** contains the adapter answer and one result for each of the six
  structural checks.

All schema classes implement `to_dict()` and `from_dict()` and reject malformed
invariants with `SchemaError`.

## Reports and CI

JSON is the lossless native report. JUnit emits one test case per mutation.
SARIF emits one result per failed check and can be ingested by tools that support
SARIF 2.1.0. Text is intended for local diagnosis.

Run the repository checks:

```sh
./ci/check.sh
```

That command runs all `unittest` cases and `compileall` over source, tests, and
examples. No network access is required.

## Seeded examples

- `examples/corpora/energy/`: the same synthetic corpus produced by `init`.
- `examples/corpora/transit/`: an independent synthetic transit corpus.
- `examples/pipeline_adapter.py`: trusted file-adapter shape.

Both corpora include multiple claims, citations, numeric values, ISO dates, and
at least two sources so the full operator set is applicable.

## Scope and limitations

Citation Chaos observes structured output behavior. Exact text comparisons make
preservation checks deterministic; they do not recognize paraphrase. Structural
citation resolvability confirms that IDs point to present records; it does not
show that a citation entails a claim. Operator expectations encode testing
policy (for example, requiring a primary source), not universal epistemic rules.
See the mutation model before treating a failure as a product defect.

## Assurance toolkit

This repository is part of a set of small, deterministic tools for testing AI-agent and retrieval-system failure boundaries:

- [SourceAdapter-Fuzz](https://github.com/dnega-dev/SourceAdapter-Fuzz) — fault injection for public-data acquisition strategies.
- [SourceContract](https://github.com/dnega-dev/SourceContract) — conformance testing for official-source ingestion adapters.
- [ClaimSpec](https://github.com/dnega-dev/ClaimSpec) — executable grounding contracts for research-agent traces.
- [CitationChaos](https://github.com/dnega-dev/CitationChaos) — citation mutation testing for grounded-answer pipelines.
- [AsOfGuard](https://github.com/dnega-dev/AsOfGuard) — temporal-contamination detection for RAG and agent memory.
- [Legal-MCP-Assurance](https://github.com/dnega-dev/Legal-MCP-Assurance) — black-box assurance for legal and retrieval tool servers.
- [JurisdictionLeakBench](https://github.com/dnega-dev/JurisdictionLeakBench) — retrieval-scope isolation security benchmark.
- [MemoryLitmus](https://github.com/dnega-dev/MemoryLitmus) — conformance testing for agent-memory semantics.
- [FailureKata](https://github.com/dnega-dev/FailureKata) — executable practice from coding-agent transcript failures.
- [FieldQuarantine](https://github.com/dnega-dev/FieldQuarantine) — safe migration of offline submissions across schema changes.

Each project is independently installable and reports deterministic outcomes suitable for local development and CI.

## License

Apache License 2.0. See [LICENSE](LICENSE).
