# Contributing to zarrcurator

Thanks for contributing to zarrcurator.

## Development Setup

1. Clone the repository.
2. Install the package in editable mode.
3. Install development and documentation extras.

```bash
python -m pip install -e .[dev,docs]
```

## Coding Rules

1. Target Python 3.12+.
2. Keep changes focused and minimal. Avoid unrelated refactors in feature or fix PRs.
3. Prefer explicit error handling with clear user-facing messages.
4. Preserve backward compatibility for public APIs unless a breaking change is intentional and documented.
5. Add or update docstrings for new public functions, classes, and methods.
6. Use logging for diagnostics, and avoid noisy logging at INFO level.
7. Keep naming descriptive and consistent with existing modules.
8. Avoid hardcoded secrets, keys, endpoints, and local machine paths.

## Formatting, Linting, and Type Checks

Pre-commit hooks are required before opening a PR.

```bash
pre-commit install
pre-commit run --all-files
```

Current enforced checks include:

- Ruff linting
- Mypy type checks
- Codespell spelling checks
- YAML and TOML validation
- Merge-conflict markers, trailing whitespace, and EOF hygiene

## Testing Rules

Run tests locally before pushing:

```bash
python -m pytest
python -m tests.test_all_modules
python -m tests.regression_test
python -m unittest tests.test_all_modules.TestConfigAndSubgroup
```

When adding or changing behavior:

1. Add a test that fails before your change and passes after your change.
2. Include edge cases for object-store access paths where relevant.
3. Keep tests deterministic (no external network dependencies unless explicitly intended).
4. For changes to how stores are read or archived, cover the store layouts: zarr v2 and v3,
   `.` and `/` chunk key separators, nested groups and sharding (see `docs/store_layouts.md`).
   `zarrcurator.synthetic_store` generates all of them (`--separators .,/ --shards 4,4,8
   --layouts flat,tree`); `TestSyntheticStoreVariants` runs each through the Kerchunk step.
5. If a store variant is added to the generator, regenerate the fixture in
   `tests/data/synthetic_experiment` with the command in the README.
6. Give each test class a docstring whose first line says what it covers: it is shown in the
   summary table printed at the end of `python -m pytest` (see `tests/conftest.py`).

## Documentation Rules

If behavior or interfaces change, update docs in the same PR.

1. Update user-facing docs in README.md as needed.
2. Update API docstrings in source.
3. Update `docs/known_issues.md` (and its summary in the README) when a known issue is fixed or found.
4. Regenerate API docs from docstrings:

```bash
python scripts/generate_api_docstrings.py
```

5. Rebuild Sphinx docs and ensure both targets succeed:

```bash
python -m sphinx -b html docs docs/_build/html
python -m sphinx -b pdf docs docs/_build/pdf
```

## Pull Request Guidelines

1. Use a clear title describing the user-visible impact.
2. Describe what changed, why, and how it was tested.
3. Link related issues when available.
4. Keep PR scope small and reviewable.

## Commit Guidelines

Use concise, imperative commit messages, for example:

- fix: handle anonymous S3 fallback failure cleanly
- test: add regression for credential fallback path
- docs: update release and contribution guide

## Release Notes and Versioning

Release process is documented in RELEASE.md.

For release-impacting changes:

1. Update CHANGELOG.md.
2. Ensure package metadata in pyproject.toml is correct.
3. Follow version bump and tagging guidance in RELEASE.md.

## Security and Credentials

1. Never commit credentials or tokens.
2. Use environment variables for secrets.
3. Redact sensitive URLs, access keys, and secret keys from logs and issue reports.
