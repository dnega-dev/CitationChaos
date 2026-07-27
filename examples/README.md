# Examples

The `energy` and `transit` directories are synthetic seeded corpora. Run either
with the deterministic reference adapter:

```sh
export PYTHONPATH="$PWD/src"
python3 -m citation_chaos mutate examples/corpora/energy/corpus.json \
  --answer examples/corpora/energy/answer.json \
  --strict --output examples/corpora/energy/mutations.json
python3 -m citation_chaos run examples/corpora/energy/mutations.json \
  --adapter reference
```

To exercise file-based adapter loading:

```sh
python3 -m citation_chaos run examples/corpora/energy/mutations.json \
  --adapter examples/pipeline_adapter.py:run_pipeline
```

Adapter files are executable Python. Load only trusted local code. The reference
adapter is fixture plumbing and does not prove the semantic truth of any claim.
