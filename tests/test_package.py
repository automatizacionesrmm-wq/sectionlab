"""Package smoke test: the distribution installs and exposes its version."""

from __future__ import annotations

import sectionlab


def test_package_exposes_version() -> None:
    assert sectionlab.__version__ == "0.1.0"
