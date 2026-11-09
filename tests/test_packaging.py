"""Entry point and packaging artifacts (spec S17)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from sectionlab import __version__
from sectionlab.__main__ import main

ROOT = Path(__file__).resolve().parents[1]


def test_version_flag_reports_the_package_version(capsys) -> None:
    assert main(["--version"]) == 0
    assert capsys.readouterr().out.strip() == f"SectionLab {__version__}"


def test_self_test_uses_a_dialog_when_there_is_no_console(monkeypatch) -> None:
    from sectionlab import __main__ as entry

    captured: list[tuple[str, bool]] = []
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(entry, "_report_without_console", lambda report, ok: captured.append((report, ok)))
    assert entry.main(["--self-test"]) == 0
    assert captured and captured[0][1] is True
    assert "area=20000.000000" in captured[0][0]


def test_self_test_runs_the_solver(capsys) -> None:
    assert main(["--self-test"]) == 0
    output = capsys.readouterr().out
    assert "area=20000.000000" in output


def test_help_flag_explains_the_application(capsys) -> None:
    assert main(["--help"]) == 0
    assert "propiedades geométricas" in capsys.readouterr().out


def test_module_entry_point_runs() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "sectionlab", "--version"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0
    assert __version__ in result.stdout


def test_spec_builds_a_windowed_onedir_bundle() -> None:
    spec = (ROOT / "packaging" / "sectionlab.spec").read_text(encoding="utf-8")
    assert 'src" / "sectionlab" / "__main__.py"' in spec
    assert 'name="SectionLab"' in spec
    assert "COLLECT(" in spec
    assert "console=False" in spec
    assert '"matplotlib"' in spec


def test_windows_build_script_produces_a_zip() -> None:
    script = (ROOT / "tools" / "build_windows.ps1").read_text(encoding="utf-8")
    assert "packaging/sectionlab.spec" in script
    assert "Compress-Archive" in script
    assert "windows.zip" in script


def test_build_extra_installs_pyinstaller() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"build = \[(.*?)\]", pyproject, re.DOTALL)
    assert block is not None
    assert "pyinstaller" in block.group(1).lower()


@pytest.mark.parametrize("name", ["packaging/sectionlab.spec", "tools/build_windows.ps1"])
def test_packaging_files_are_tracked(name: str) -> None:
    assert (ROOT / name).is_file()
