"""Package smoke test: the distribution installs and exposes its version."""

from __future__ import annotations

import re
from pathlib import Path

import sectionlab

ROOT = Path(__file__).resolve().parents[1]


def test_package_exposes_version() -> None:
    assert re.fullmatch(r"\d+\.\d+\.\d+", sectionlab.__version__), sectionlab.__version__


def test_the_package_version_matches_the_project_metadata() -> None:
    """One version, so a release tag, the setup file and `--version` can never disagree."""
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    declared = re.search(r'^version = "([^"]+)"', pyproject, re.MULTILINE)
    assert declared is not None
    assert declared.group(1) == sectionlab.__version__
