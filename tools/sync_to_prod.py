#!/usr/bin/env python3
"""Sync tested mud_utility_test integration code into production mud_utility."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

TEST_DOMAIN = "mud_utility_test"
PROD_DOMAIN = "mud_utility"

TEST_NAME = "MUD Utilities Test"
PROD_NAME = "MUD Utilities"

TEST_REPO_URL = "https://github.com/DuckCowMooQuack/mud_utility_test"
PROD_REPO_URL = "https://github.com/DuckCowMooQuack/mud_utility"

SOURCE_FILES = (
    "__init__.py",
    "api.py",
    "config_flow.py",
    "const.py",
    "coordinator.py",
    "sensor.py",
    "translations/en.json",
)

BINARY_FILES = (
    "brand/icon.png",
)


def run_git(args: list[str], cwd: Path) -> str:
    """Run git and return stripped stdout."""
    return subprocess.check_output(
        ["git", *args],
        cwd=cwd,
        text=True,
    ).strip()


def transform_text(text: str) -> str:
    """Convert test integration identifiers to production identifiers."""
    text = text.replace(TEST_DOMAIN, PROD_DOMAIN)
    text = text.replace(TEST_NAME, PROD_NAME)
    text = text.replace("MudUtilityTestConfigEntry", "MudUtilityConfigEntry")
    text = text.replace(TEST_REPO_URL, PROD_REPO_URL)

    # Production uses a shorter device name while keeping entity/stat names descriptive.
    text = text.replace(
        'name="MUD Utilities",',
        'name="MUD",',
    )

    return text


def sync_text_file(source: Path, destination: Path) -> None:
    """Copy and transform one text file."""
    text = source.read_text(encoding="utf-8")
    text = transform_text(text)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(text, encoding="utf-8")


def sync_manifest(source: Path, destination: Path, version: str) -> None:
    """Copy manifest with production metadata and requested version."""
    manifest = json.loads(source.read_text(encoding="utf-8"))

    manifest["domain"] = PROD_DOMAIN
    manifest["name"] = PROD_NAME
    manifest["documentation"] = PROD_REPO_URL
    manifest["issue_tracker"] = f"{PROD_REPO_URL}/issues"
    manifest["version"] = version

    destination.write_text(
        json.dumps(manifest, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--version",
        required=True,
        help="Production manifest version, for example 0.0.3-rc.1",
    )
    parser.add_argument(
        "--prod-repo",
        default="~/mud_utility",
        help="Path to production repository.",
    )
    args = parser.parse_args()

    test_repo = Path(__file__).resolve().parents[1]
    prod_repo = Path(args.prod_repo).expanduser().resolve()

    source_dir = test_repo / "custom_components" / TEST_DOMAIN
    destination_dir = prod_repo / "custom_components" / PROD_DOMAIN

    branch = run_git(["branch", "--show-current"], prod_repo)
    if not branch.startswith("release/"):
        raise SystemExit(
            f"Production repo is on {branch!r}; expected a release/* branch."
        )

    for file_name in SOURCE_FILES:
        sync_text_file(
            source_dir / file_name,
            destination_dir / file_name,
        )

    for file_name in BINARY_FILES:
        destination = destination_dir / file_name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_dir / file_name, destination)

    sync_manifest(
        source_dir / "manifest.json",
        destination_dir / "manifest.json",
        args.version,
    )

    leftovers = subprocess.run(
        ["rg", TEST_DOMAIN, str(destination_dir)],
        text=True,
        capture_output=True,
        check=False,
    )

    if leftovers.returncode == 0:
        raise SystemExit(
            f"Test domain remains in production files:\n{leftovers}"
        )

    if leftovers.returncode not in (0, 1):
        raise SystemExit(leftovers.stderr)


if __name__ == "__main__":
    main()
