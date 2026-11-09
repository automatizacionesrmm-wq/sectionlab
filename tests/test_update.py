"""In-app update logic, offline and without Qt (specs S4, S7-S9)."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from sectionlab.core.update import (
    API_LATEST,
    Asset,
    UpdateError,
    download,
    fetch_latest,
    install_code,
    is_newer,
    parse_release,
    verify_digest,
    version_tuple,
)

RELEASE_BODY = {
    "tag_name": "v0.2.1",
    "body": "notas de la versión",
    "assets": [
        {
            "name": "SectionLab-0.2.1-code.zip",
            "browser_download_url": "https://example.test/code.zip",
            "size": 50_000,
            "digest": "sha256:abc",
        },
        {
            "name": "SectionLab-0.2.1-setup.exe",
            "browser_download_url": "https://example.test/setup.exe",
            "size": 75_000_000,
        },
    ],
}


def test_versions_are_compared_as_numbers_not_text() -> None:
    assert version_tuple("v0.2.1") == (0, 2, 1)
    assert is_newer("0.2.0", "0.10.0") is True
    assert is_newer("0.9.9", "0.10.0") is True
    assert is_newer("0.2.1", "0.2.1") is False
    assert is_newer("0.2.2", "0.2.1") is False
    assert is_newer("1.0", "1.0.0") is False


def test_a_version_that_cannot_be_read_offers_nothing() -> None:
    assert version_tuple("nightly") is None
    assert version_tuple("") is None
    assert is_newer("0.2.0", "nightly") is False


def test_a_release_body_gives_its_version_notes_and_assets() -> None:
    release = parse_release(RELEASE_BODY)
    assert release.version == "0.2.1"
    assert release.tag == "v0.2.1"
    assert release.notes == "notas de la versión"
    assert release.code() is not None
    assert release.code().name.endswith("-code.zip")
    assert release.installer() is not None
    assert release.code().digest == "sha256:abc"


def test_a_release_without_a_usable_tag_is_refused() -> None:
    with pytest.raises(UpdateError) as refused:
        parse_release({"tag_name": "sin-numero"})
    assert refused.value.code == "malformed_release"
    with pytest.raises(UpdateError):
        parse_release({"assets": []})


def test_a_release_without_assets_offers_no_update_path() -> None:
    release = parse_release({"tag_name": "v0.3.0"})
    assert release.code() is None
    assert release.installer() is None


class FakeResponse(io.BytesIO):
    """Minimal stand-in for the HTTP response the real opener returns."""


def opener_for(body: bytes, seen: list[dict[str, object]] | None = None):
    def opener(url: str, headers) -> FakeResponse:
        if seen is not None:
            seen.append({"url": url, "headers": dict(headers)})
        return FakeResponse(body)

    return opener


def test_fetching_the_newest_release_reads_github(  ) -> None:
    seen: list[dict[str, object]] = []
    release = fetch_latest(opener_for(json.dumps(RELEASE_BODY).encode(), seen))
    assert release.version == "0.2.1"
    assert seen[0]["url"] == API_LATEST
    assert "SectionLab/" in str(seen[0]["headers"]["User-Agent"])


def test_a_broken_check_speaks_one_language() -> None:
    def offline(url: str, headers):
        raise OSError("no route to host")

    with pytest.raises(UpdateError) as failed:
        fetch_latest(offline)
    assert failed.value.code == "check_failed"

    with pytest.raises(UpdateError) as junk:
        fetch_latest(opener_for(b"no es json"))
    assert junk.value.code == "check_failed"


def test_a_download_is_written_and_checked_against_its_digest(tmp_path: Path) -> None:
    payload = b"contenido del parche"
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    asset = Asset(name="code.zip", url="https://example.test/code.zip", digest=digest)
    target = download(asset, tmp_path / "code.zip", opener_for(payload))
    assert target.read_bytes() == payload
    assert verify_digest(target, digest) is True
    assert verify_digest(target, "sha256:" + "0" * 64) is False
    assert verify_digest(target, "") is True


def test_a_download_that_does_not_match_leaves_nothing_behind(tmp_path: Path) -> None:
    asset = Asset(name="code.zip", url="https://example.test/code.zip", digest="sha256:" + "1" * 64)
    with pytest.raises(UpdateError) as refused:
        download(asset, tmp_path / "code.zip", opener_for(b"otra cosa"))
    assert refused.value.code == "digest_mismatch"
    assert list(tmp_path.iterdir()) == []


def test_a_failed_download_keeps_the_installation_untouched(tmp_path: Path) -> None:
    def broken(url: str, headers):
        raise OSError("connection reset")

    asset = Asset(name="code.zip", url="https://example.test/code.zip")
    with pytest.raises(UpdateError) as failed:
        download(asset, tmp_path / "code.zip", broken)
    assert failed.value.code == "download_failed"
    assert list(tmp_path.iterdir()) == []


def make_archive(path: Path, files: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
    return path


@pytest.fixture()
def installation(tmp_path: Path) -> Path:
    app_dir = tmp_path / "SectionLab" / "app"
    (app_dir / "sectionlab").mkdir(parents=True)
    (app_dir / "sectionlab" / "__init__.py").write_text('__version__ = "0.1.0"\n', encoding="utf-8")
    (app_dir / "sectionlab" / "old.py").write_text("viejo\n", encoding="utf-8")
    return app_dir


def test_installing_the_code_keeps_the_previous_folder(installation: Path, tmp_path: Path) -> None:
    archive = make_archive(
        tmp_path / "code.zip",
        {"sectionlab/__init__.py": '__version__ = "0.2.1"\n', "sectionlab/new.py": "nuevo\n"},
    )
    backup = install_code(archive, installation)
    assert (installation / "sectionlab" / "__init__.py").read_text(encoding="utf-8") == '__version__ = "0.2.1"\n'
    assert (installation / "sectionlab" / "new.py").is_file()
    assert not (installation / "sectionlab" / "old.py").exists()
    assert backup == installation / "sectionlab.bak"
    assert (backup / "old.py").is_file()


def test_an_archive_without_the_package_is_refused(installation: Path, tmp_path: Path) -> None:
    archive = make_archive(tmp_path / "code.zip", {"otra/__init__.py": ""})
    with pytest.raises(UpdateError) as refused:
        install_code(archive, installation)
    assert refused.value.code == "invalid_archive"
    assert (installation / "sectionlab" / "old.py").is_file()


def test_a_corrupt_archive_is_refused(installation: Path, tmp_path: Path) -> None:
    archive = tmp_path / "code.zip"
    archive.write_bytes(b"esto no es un zip")
    with pytest.raises(UpdateError) as refused:
        install_code(archive, installation)
    assert refused.value.code == "invalid_archive"
    assert (installation / "sectionlab" / "old.py").is_file()
    assert not (installation / "sectionlab.bak").exists()


def test_an_archive_without_the_package_entry_point_is_refused(
    installation: Path, tmp_path: Path
) -> None:
    archive = make_archive(tmp_path / "code.zip", {"sectionlab/readme.txt": "sin init\n"})
    with pytest.raises(UpdateError) as refused:
        install_code(archive, installation)
    assert refused.value.code == "invalid_archive"
    assert (installation / "sectionlab" / "old.py").is_file()


def test_installing_somewhere_that_is_not_an_installation_is_refused(tmp_path: Path) -> None:
    archive = make_archive(tmp_path / "code.zip", {"sectionlab/__init__.py": ""})
    with pytest.raises(UpdateError) as refused:
        install_code(archive, tmp_path / "no-existe")
    assert refused.value.code == "not_installed"
