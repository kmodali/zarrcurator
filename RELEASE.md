# Release Process

This project follows a tag-based release flow with Trusted Publishing.

## Versioning Policy

- Use semantic versioning (`MAJOR.MINOR.PATCH`).
- Single source of truth: update version only in `pyproject.toml`.
- Never reuse a released version number.

## Version Bump Helper

Use the helper script to update `pyproject.toml`:

```bash
python scripts/release.py --bump patch
python scripts/release.py --bump minor
python scripts/release.py --version 1.2.0
```

Create a tag in the same step (optional):

```bash
python scripts/release.py --bump patch --tag
```

## Release Checklist

1. Update release notes in `CHANGELOG.md`.
2. Ensure package metadata is accurate in `pyproject.toml`.
3. Run quality checks:

```bash
python -m tests.test_all_modules
python -m tests.regression_test
pre-commit run --all-files
```

4. Build and validate artifacts locally:

```bash
python -m pip install -U build twine
python -m build
python -m twine check dist/*
```

5. (Recommended) Publish to TestPyPI from GitHub Actions using `workflow_dispatch` with target `testpypi`.
6. Validate install from TestPyPI in a clean environment.
7. Create and push a version tag to publish to PyPI:

```bash
git tag vX.Y.Z
git push origin vX.Y.Z
```

8. Confirm package appears on PyPI and install it in a clean environment.

## GitHub Actions Publishing

Workflow file: `.github/workflows/publish-pypi.yml`

- Push tags matching `v*` to publish to PyPI.
- Manual dispatch supports publishing to TestPyPI or PyPI.

Version consistency check workflow:

- `.github/workflows/version-consistency.yml`
- Verifies that:
   - package version in `pyproject.toml`
   - runtime `zarrcurator.__version__`
   - installed distribution metadata version
   are all identical.

## Required One-Time Setup

1. Configure Trusted Publishing on PyPI and TestPyPI for this repository.
2. In GitHub, create protected environments:
   - `pypi`
   - `testpypi`
3. Add approval rules to environment deployments if needed.
