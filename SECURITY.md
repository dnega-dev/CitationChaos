# Security policy

## Supported versions

Until the first stable release, security fixes are applied to the latest `0.x`
release only.

## Reporting a vulnerability

Do not publish credentials, private corpora, exploitable adapter code, or other
sensitive details in a public issue. Contact the maintainers through the private
security-reporting channel provided by the package distributor. Include affected
version, reproduction steps, impact, and suggested mitigation when available.

Maintainers should acknowledge a report promptly, reproduce it in an isolated
environment, coordinate a fix and disclosure window, and credit the reporter if
requested.

## Security model

- A `MODULE:OBJECT` or `PATH.py:OBJECT` adapter is imported and executed in the
  Citation Chaos process. **Only run trusted adapters.** There is no sandbox.
- Corpora and manifests are untrusted data. Schema validation limits shape and
  types but does not make text safe for downstream HTML, shell, SQL, or prompt
  interpolation.
- JSON parsing can consume memory proportional to input size; this MVP does not
  enforce file-size limits.
- Report paths can overwrite files selected by the invoking user. `init` is the
  exception: it refuses generated-file overwrites unless `--force` is set.
- SARIF and JUnit reports may include adapter error text and answer content. Treat
  reports as potentially sensitive and avoid `--traceback` in public artifacts.
- SHA-256 fields support integrity checks. They do not prove authorship,
  authority, safety, or semantic truth.

Citation Chaos performs no network calls. A user-supplied adapter may do so and
is responsible for its own transport, credential, data-retention, and prompt-
injection controls.
