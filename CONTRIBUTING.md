# Contributing

Thank you for improving Citation Chaos.

## Development setup

Citation Chaos supports Python 3.9+ and has no runtime dependencies. From the
repository root:

```sh
export PYTHONPATH="$PWD/src"
./ci/check.sh
```

The checks use only the standard library: `unittest` and `compileall`.

## Change guidelines

1. Keep runtime code zero-dependency and compatible with Python 3.9.
2. Keep operators deterministic: no network, wall-clock, global random state, or
   unordered target selection.
3. Add schema validation for new fields and round-trip tests for JSON changes.
4. Add at least one full operator-to-adapter-to-runner test for each new operator.
5. Preserve the distinction between structural mutation behavior and semantic
   truth. Documentation and reports must not claim truth proof.
6. Treat adapter imports as trusted-code execution and avoid silently importing
   project files.
7. Update `CHANGELOG.md` for user-visible changes.

## Tests

Run:

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q src tests examples
```

Tests that write files must place temporary data under this repository and clean
it up. Tests must not require network access, credentials, third-party services,
or non-standard packages.

## Operator checklist

A new operator should document:

- eligibility and deterministic target selection;
- exact corpus fields changed and fields intentionally retained;
- impacted and preserved claim calculation;
- required explicit-reason tokens;
- limitations and policy assumptions;
- serialized fixture stability.

## Compatibility

Schema additions should be backward-compatible when practical. A breaking JSON
change requires a schema-version change and migration notes. Public Python names
exported from `citation_chaos.__init__` are part of the supported API.
