"""Release helper for zarrcurator.

Usage examples:
    python scripts/release.py --bump patch
    python scripts/release.py --bump minor --tag
    python scripts/release.py --version 1.2.0 --tag
"""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT_PATH = REPO_ROOT / "pyproject.toml"

VERSION_PATTERN = re.compile(r'(?m)^(version\s*=\s*")(\d+\.\d+\.\d+)("\s*)$')


def read_pyproject() -> str:
    return PYPROJECT_PATH.read_text(encoding="utf-8")


def get_current_version(content: str) -> str:
    match = VERSION_PATTERN.search(content)
    if not match:
        raise ValueError("Unable to find project.version in pyproject.toml")
    return match.group(2)


def bump_version(version: str, part: str) -> str:
    major, minor, patch = [int(v) for v in version.split(".")]
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Unsupported bump part: {part}")


def set_version(content: str, new_version: str) -> str:
    return VERSION_PATTERN.sub(rf'\g<1>{new_version}\g<3>', content, count=1)


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bump release version and optionally create a git tag")
    parser.add_argument("--bump", choices=["patch", "minor", "major"], help="Version part to bump")
    parser.add_argument("--version", help="Set an explicit semantic version (X.Y.Z)")
    parser.add_argument("--tag", action="store_true", help="Create git tag v<version> after updating")
    args = parser.parse_args()

    if bool(args.bump) == bool(args.version):
        raise SystemExit("Use exactly one of --bump or --version")

    content = read_pyproject()
    current = get_current_version(content)

    if args.version:
        if not re.fullmatch(r"\d+\.\d+\.\d+", args.version):
            raise SystemExit("--version must be in semantic version format X.Y.Z")
        new_version = args.version
    else:
        new_version = bump_version(current, args.bump)

    if new_version == current:
        print(f"Version unchanged: {current}")
        return

    updated = set_version(content, new_version)
    PYPROJECT_PATH.write_text(updated, encoding="utf-8")

    print(f"Updated version: {current} -> {new_version}")
    print("Next steps:")
    print("  1. Update CHANGELOG.md")
    print("  2. Run tests/build checks")
    print("  3. Commit changes")

    if args.tag:
        tag = f"v{new_version}"
        run(["git", "tag", tag])
        print(f"Created tag: {tag}")
        print(f"Push with: git push origin {tag}")


if __name__ == "__main__":
    main()
