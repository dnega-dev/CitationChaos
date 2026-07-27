# Mutation model

Citation Chaos tests a grounded pipeline by changing the evidence bundle while
holding the question and baseline claim identities fixed. A mutation is a known,
controlled perturbation with an explicit expected response. The runner compares
the adapter's structured answer to that expectation.

This model tests **metamorphic behavior**. It does not establish semantic truth,
entailment, source reliability, completeness, or real-world correctness.

## Schema semantics

### Corpus

A corpus has a stable `id`, a `version`, zero or more sources, and JSON metadata.
An empty source list is valid because it represents zero-result retrieval.
Source IDs are unique within a corpus.

### Source

A source has:

- stable `id` and retrieval `uri`;
- human-readable `title`;
- `sha256`, defined by this MVP as SHA-256 of span texts joined by `"\n"` in
  stored order;
- provenance `kind`: `primary` or `secondary`;
- optional ISO date `published_at`;
- `current` and `supersedes` currency fields;
- one or more uniquely identified spans.

The schema validates digest syntax but intentionally does not require the digest
to match current text. That mismatch is necessary to represent stale-cache
mutations. Integrity-aware adapters should compare `source.sha256` with
`Source.hash_spans(source.spans)`.

### Span

A span is a directly citable unit with stable `id`, non-empty `text`, optional
paired logical offsets, optional page label, and metadata. Offset bounds are
structural anchors; Citation Chaos does not reconstruct a parent document.

### Answer, claim, and citation

An answered `Answer` has at least one uniquely identified claim. An abstained
answer has no claims and a non-empty reason. Claims have stable IDs, text, and
citations. A citation points to `source_id` and `span_id`; `anchor` is a display
label and `quote` is an optional exact baseline snapshot.

Stable claim IDs are required for impact localization. If a production pipeline
regenerates IDs, normalize them in the adapter.

### Mutation and expected response

A mutation embeds:

- deterministic ID, operator name, and seed;
- original question and baseline corpus digest;
- mutated corpus and baseline answer;
- expected claim IDs to remove, preserve, treat as impacted, and require as
  resolvable;
- reason substrings required in the observed answer.

The expected response is generated mechanically from baseline citation links and
operator policy. It is not discovered from a model output.

### Run result

A run result has `passed`, `failed`, or `error` status, adapter identity, optional
structured answer, and named score checks. Adapter exceptions are isolated to a
single mutation and become `error` results so the remainder of a suite runs.

## Determinism

Operators enumerate claims, citations, and sources in stable order and use a
local `random.Random(seed)` only to select among eligible targets. They do not
use wall-clock time, global random state, network I/O, or process-dependent IDs.
Mutation IDs hash the operator, seed, baseline digest, mutated digest, and target
metadata. Repeating generation with identical validated inputs and arguments
produces identical manifest content.

The CLI assigns `seed + operator_index` to each selected operator. Selecting a
different subset can therefore change per-operator effective seeds; record the
manifest as the executable test artifact.

## Operator definitions

### Delete cited span

Select an eligible cited span whose source has another span and remove it. Claims
citing that span are impacted. Other claims should remain byte-for-byte equal.
The one-span guard preserves the source schema invariant.

### Alter number

Select a numeric token in a cited span and increment it by one, preserving decimal
precision, comma grouping, and `%` suffix. ISO date components are excluded. The
source digest is recomputed. Claims citing that span are impacted.

### Alter date

Select a valid `YYYY-MM-DD` token in a cited span and add one calendar day. The
source digest is recomputed. Claims citing that span are impacted.

### Swap source IDs

Select a cited source and a distinct source and swap record IDs without changing
their contents. Baseline citations continue to name the old IDs and may resolve
to the wrong record or to missing spans. Claims citing either swapped identity
are impacted.

### Corrupt page/span anchor

Rename a cited span to a deterministic corrupt ID and prefix its page label with
`corrupt:`. Baseline citations no longer resolve. Claims using the original span
are impacted.

### Supersede source

Mark a cited source non-current, add a current revision with `supersedes` pointing
to the original, and make a deterministic content revision. Claims citing the
non-current source are impacted until re-grounded in the revision.

### Move source URI while retaining hash

Change only a cited source URI and retain source ID, span content, and hash. No
claim is expected to change. This negative-control operator catches systems that
incorrectly bind evidence identity only to location.

### Introduce conflicting current source

Add a second current source tagged as conflicting with one cited source/span. Its
text changes a number or date when possible, otherwise uses an explicit
contradictory sentence. Claims using the disputed span are impacted; other claims
should survive.

### Replace primary source with secondary

Change a cited primary source's kind to `secondary` and annotate its replacement,
while retaining text and source ID. This operator encodes a primary-source policy.
Projects that permit secondary evidence should omit this operator or customize
expectations rather than treating the default as universal truth.

### Zero-result retrieval

Replace the source collection with an empty tuple. Every baseline claim is
impacted. The expected output is an explicit empty abstention.

### Stale-cache text

Change one cited span but retain the original source hash. Since the hash covers
the document's complete span sequence, every claim citing that source is
impacted, not only claims citing the visibly changed span.

## Six scoring checks

1. **Abstention** — requires an empty abstention when all claims are impacted;
   otherwise requires answered status.
2. **Unsupported-claim removal** — every expected removed claim ID is absent.
3. **Unaffected-claim preservation** — every preserved claim ID remains with
   exactly the baseline text.
4. **Impact localization** — the set of missing or text-changed baseline claims
   equals the expected impacted set, and no new claim IDs appear.
5. **Explicit reason** — when impact exists, a reason is present and contains all
   operator-specific substrings, case-insensitively.
6. **Citation resolvability** — every emitted claim has citations; every cited
   source/span exists; expected resolvable claims are present.

Checks are intentionally strict and explainable. A paraphrase of an unaffected
claim fails exact preservation. A valid redesign can normalize output in its
adapter or build a domain-specific scorer on top of the serialized run results.

## Reference adapter

Generated mutation corpora include `metadata.reference_answer` solely for the
included reference adapter. It retains baseline claims only when all citations
resolve, exact quotes match, the source digest matches, the source is current,
the source is primary, and no tagged conflict targets the cited span. It then
adds deterministic reasons.

This is controlled fixture logic, not an AI pipeline, oracle, semantic judge, or
truth-proving system. Do not use its pass rate as a product quality claim.

## Threats to validity

- Baseline claims or citations can themselves be wrong.
- Exact quote and text equality miss semantically equivalent paraphrases.
- The synthetic conflict marker is harness metadata; real conflict detection is
  a retrieval and reasoning problem.
- SHA-256 checks integrity, not authority or truth.
- Source currency and primary/secondary labels depend on supplied metadata.
- A finite mutation suite cannot cover all failure modes.
- An adapter can overfit to mutation metadata. Production evaluation should
  ensure the tested pipeline cannot inspect harness-only fields.

Use Citation Chaos as one reproducible layer in a broader evaluation program.
