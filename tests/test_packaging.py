"""Entry point, packaging artifacts and update delivery (spec S17, S20)."""

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


def test_self_test_can_write_its_report_to_a_file(monkeypatch, tmp_path) -> None:
    from sectionlab import __main__ as entry

    report = tmp_path / "selftest.txt"
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setenv("SECTIONLAB_SELFTEST_FILE", str(report))
    assert entry.main(["--self-test"]) == 0
    text = report.read_text(encoding="utf-8")
    assert "area=20000.000000" in text
    assert text.strip().endswith("ok")


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
    assert 'name="SectionLab"' in spec
    assert "COLLECT(" in spec
    assert "console=False" in spec
    assert '"matplotlib"' in spec


def test_spec_freezes_the_runtime_but_not_the_application() -> None:
    spec = (ROOT / "packaging" / "sectionlab.spec").read_text(encoding="utf-8")
    analysis = spec.split("excludes=[", 1)[1].split("]", 1)[0]
    assert '"sectionlab"' in analysis
    assert 'LAUNCHER' in spec.split("Analysis(", 1)[1]


def test_launcher_runs_the_code_beside_the_executable(tmp_path, monkeypatch) -> None:
    from importlib import util

    spec = util.spec_from_file_location("sectionlab_launcher", ROOT / "packaging" / "launcher.py")
    launcher = util.module_from_spec(spec)
    spec.loader.exec_module(launcher)

    executable = tmp_path / "SectionLab.exe"
    executable.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))

    assert launcher.code_root() == tmp_path / "app"


def test_the_launcher_names_every_third_party_module_the_application_imports() -> None:
    """Drift guard: a new import in `src/` must reach the frozen runtime, not just `app/`."""
    launcher = (ROOT / "packaging" / "launcher.py").read_text(encoding="utf-8")
    pattern = re.compile(
        r"^\s*(?:from|import)\s+(PySide6|shapely|sectionproperties|scipy|numpy|matplotlib)[\w.]*",
        re.MULTILINE,
    )
    imported: set[str] = set()
    for path in (ROOT / "src" / "sectionlab").rglob("*.py"):
        for match in pattern.finditer(path.read_text(encoding="utf-8")):
            module = match.group(0).split()[-1] if " import " not in match.group(0) else match.group(0).split()[1]
            imported.add(module.split(" as ")[0])

    missing = sorted(module for module in imported if f"import {module}" not in launcher)
    assert missing == []


def test_the_launcher_names_the_standard_modules_the_frozen_app_cannot_analyse() -> None:
    """The updater talks HTTPS and unpacks a ZIP; neither is visible to the analyser."""
    launcher = (ROOT / "packaging" / "launcher.py").read_text(encoding="utf-8")
    for module in ("ssl", "urllib.request", "hashlib", "zipfile", "zlib", "tempfile"):
        assert f"import {module}" in launcher, module


def test_the_updater_imports_what_the_launcher_promises() -> None:
    """If the updater starts using something else from the network stack, this fails."""
    update = (ROOT / "src" / "sectionlab" / "core" / "update.py").read_text(encoding="utf-8")
    launcher = (ROOT / "packaging" / "launcher.py").read_text(encoding="utf-8")
    for module in ("urllib.request", "hashlib", "zipfile", "tempfile"):
        if f"import {module}" in update or f"from {module}" in update:
            assert f"import {module}" in launcher, module


def test_launcher_points_at_the_source_tree_when_not_frozen() -> None:
    from importlib import util

    spec = util.spec_from_file_location("sectionlab_launcher", ROOT / "packaging" / "launcher.py")
    launcher = util.module_from_spec(spec)
    spec.loader.exec_module(launcher)

    assert launcher.code_root() == ROOT / "src"


def test_the_code_archive_ships_the_package_alone(tmp_path) -> None:
    from importlib import util

    spec = util.spec_from_file_location("sectionlab_assemble", ROOT / "tools" / "assemble_app.py")
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assemble, PACKAGE = module.assemble, module.PACKAGE

    bundle = tmp_path / "dist" / "SectionLab"
    bundle.mkdir(parents=True)
    (bundle / "SectionLab.exe").write_text("", encoding="utf-8")

    target, archive = assemble(bundle, PACKAGE, "9.9.9")

    assert target == bundle / "app" / "sectionlab"
    assert (target / "__main__.py").is_file()
    assert not list(target.rglob("__pycache__"))
    assert archive.name == "SectionLab-9.9.9-code.zip"

    import zipfile

    with zipfile.ZipFile(archive) as code:
        names = code.namelist()
    assert "sectionlab/__main__.py" in names
    assert all(name.startswith("sectionlab/") for name in names)
    assert not any(name.endswith(".pyc") for name in names)


def test_the_installer_upgrades_in_place_under_the_user_profile() -> None:
    script = (ROOT / "packaging" / "sectionlab.iss").read_text(encoding="utf-8")
    assert "AppId={{7C4B2F19" in script
    assert "PrivilegesRequired=lowest" in script
    assert 'Source: "{#AppSourceDir}\\*"; DestDir: "{app}"' in script
    assert 'Filename: "{app}\\{#AppExeName}"' in script


def test_windows_build_script_produces_a_zip() -> None:
    script = (ROOT / "tools" / "build_windows.ps1").read_text(encoding="utf-8")
    assert "packaging/sectionlab.spec" in script
    assert "Compress-Archive" in script
    assert "windows.zip" in script


def test_windows_build_script_ships_the_code_and_the_installer() -> None:
    script = (ROOT / "tools" / "build_windows.ps1").read_text(encoding="utf-8")
    pyinstaller = script.index("packaging/sectionlab.spec")
    assert script.index("tools/assemble_app.py") > pyinstaller
    assert "sectionlab.iss" in script


def test_the_workflow_publishes_the_code_archive_and_the_installer() -> None:
    workflow = (ROOT / ".github" / "workflows" / "windows-build.yml").read_text(encoding="utf-8")
    steps = workflow.split("jobs:", 1)[1]
    assert steps.index("packaging/sectionlab.spec") < steps.index("tools/assemble_app.py")
    # The bundle cannot start without its code, so the self-test runs after assembling it.
    assert steps.index("tools/assemble_app.py") < steps.index("--self-test")
    assert "code.zip" in workflow
    assert "setup.exe" in workflow


def test_build_extra_installs_pyinstaller() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"build = \[(.*?)\]", pyproject, re.DOTALL)
    assert block is not None
    assert "pyinstaller" in block.group(1).lower()


@pytest.mark.parametrize(
    "name",
    ["packaging/sectionlab.spec", "packaging/sectionlab.iss", "packaging/launcher.py", "tools/assemble_app.py", "tools/build_windows.ps1"],
)
def test_packaging_files_are_tracked(name: str) -> None:
    assert (ROOT / name).is_file()
