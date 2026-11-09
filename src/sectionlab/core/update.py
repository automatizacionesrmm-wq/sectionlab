"""In-app updates: which release is newer, which file to fetch, and how to swap the code.

Pure logic plus the two operations that touch the outside world (an HTTPS fetch and a ZIP that
is unpacked beside the frozen executable). Both are behind a seam the interface replaces in
tests, so the suite never opens a socket or rewrites an installation (spec S9).
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from sectionlab import __version__

REPOSITORY = "https://github.com/automatizacionesrmm-wq/sectionlab"
API_LATEST = f"{REPOSITORY.replace('https://github.com', 'https://api.github.com/repos')}/releases/latest"
CODE_SUFFIX = "-code.zip"
INSTALLER_SUFFIX = "-setup.exe"
APP_FOLDER = "app"
PACKAGE_NAME = "sectionlab"
BACKUP_NAME = "sectionlab.bak"
# GitHub rejects requests without a User-Agent, and asks for this Accept header.
_USER_AGENT = f"SectionLab/{__version__}"
_ACCEPT = "application/vnd.github+json"
_TIMEOUT_S = 10.0
_CHUNK = 65536

Opener = Callable[[str, Mapping[str, str]], object]


class UpdateError(RuntimeError):
    """A refused or failed update step; ``code`` lets the interface answer in Spanish (D6)."""

    def __init__(self, code: str, message: str = "") -> None:
        super().__init__(message or code)
        self.code = code


@dataclass(frozen=True)
class Asset:
    """One file attached to a release."""

    name: str
    url: str
    size: int = 0
    digest: str = ""


@dataclass(frozen=True)
class Release:
    """A published release, as much of it as the application needs."""

    version: str
    tag: str
    notes: str = ""
    assets: tuple[Asset, ...] = field(default_factory=tuple)

    def code(self) -> Asset | None:
        return _with_suffix(self.assets, CODE_SUFFIX)

    def installer(self) -> Asset | None:
        return _with_suffix(self.assets, INSTALLER_SUFFIX)


def _with_suffix(assets: tuple[Asset, ...], suffix: str) -> Asset | None:
    for asset in assets:
        if asset.name.endswith(suffix):
            return asset
    return None


def version_tuple(text: str) -> tuple[int, ...] | None:
    """``v0.2.1`` → ``(0, 2, 1)``; anything that is not dotted numbers → None (spec S8)."""
    cleaned = str(text).strip()
    if cleaned[:1] in ("v", "V"):
        cleaned = cleaned[1:]
    if not cleaned:
        return None
    parts = cleaned.split(".")
    numbers: list[int] = []
    for part in parts:
        if not part.isdigit():
            return None
        numbers.append(int(part))
    return tuple(numbers)


def is_newer(current: str, candidate: str) -> bool:
    """True only when ``candidate`` is a strictly newer release than ``current``."""
    have = version_tuple(current)
    offered = version_tuple(candidate)
    if have is None or offered is None:
        return False
    width = max(len(have), len(offered))
    padded = have + (0,) * (width - len(have))
    other = offered + (0,) * (width - len(offered))
    return other > padded


def parse_release(payload: Mapping[str, object]) -> Release:
    """Turn the GitHub ``/releases/latest`` body into a Release, or refuse it."""
    if not isinstance(payload, Mapping):
        raise UpdateError("malformed_release", "the release body is not an object")
    tag = payload.get("tag_name")
    numbers = version_tuple(tag) if isinstance(tag, str) else None
    if not isinstance(tag, str) or numbers is None:
        raise UpdateError("malformed_release", "the release has no usable tag")
    notes = payload.get("body")
    raw_assets = payload.get("assets")
    assets: list[Asset] = []
    if isinstance(raw_assets, list):
        for raw in raw_assets:
            if not isinstance(raw, Mapping):
                continue
            name = raw.get("name")
            url = raw.get("browser_download_url") or raw.get("url")
            if not isinstance(name, str) or not isinstance(url, str):
                continue
            assets.append(
                Asset(
                    name=name,
                    url=url,
                    size=int(raw.get("size") or 0),
                    digest=str(raw.get("digest") or ""),
                )
            )
    return Release(
        version=".".join(str(number) for number in numbers),
        tag=tag,
        notes=notes if isinstance(notes, str) else "",
        assets=tuple(assets),
    )


def _open(url: str, headers: Mapping[str, str]):
    request = urllib.request.Request(url, headers=dict(headers))
    return urllib.request.urlopen(request, timeout=_TIMEOUT_S)  # noqa: S310 - fixed https host


def fetch_latest(opener: Opener | None = None) -> Release:
    """Read the newest published release. Raises UpdateError on any failure (spec S7)."""
    open_url = opener or _open
    try:
        response = open_url(API_LATEST, {"User-Agent": _USER_AGENT, "Accept": _ACCEPT})
        try:
            raw = response.read()
        finally:
            close = getattr(response, "close", None)
            if close is not None:
                close()
        payload = json.loads(raw.decode("utf-8"))
    except UpdateError:
        raise
    except Exception as error:  # network, DNS, TLS, JSON: all the same to the interface
        raise UpdateError("check_failed", str(error)) from error
    return parse_release(payload)


def verify_digest(path: Path, digest: str) -> bool:
    """True when the file matches ``sha256:…``; an empty digest means there is nothing to check."""
    expected = digest.strip().lower()
    if not expected:
        return True
    if expected.startswith("sha256:"):
        expected = expected[len("sha256:") :]
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(_CHUNK), b""):
            hasher.update(block)
    return hasher.hexdigest() == expected


def download(asset: Asset, target: Path, opener: Opener | None = None) -> Path:
    """Fetch one asset to ``target``, half-written files never left behind (spec S4)."""
    open_url = opener or _open
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    try:
        response = open_url(asset.url, {"User-Agent": _USER_AGENT, "Accept": "application/octet-stream"})
        try:
            with partial.open("wb") as handle:
                while True:
                    block = response.read(_CHUNK)
                    if not block:
                        break
                    handle.write(block)
        finally:
            close = getattr(response, "close", None)
            if close is not None:
                close()
    except UpdateError:
        partial.unlink(missing_ok=True)
        raise
    except Exception as error:
        partial.unlink(missing_ok=True)
        raise UpdateError("download_failed", str(error)) from error
    if not verify_digest(partial, asset.digest):
        partial.unlink(missing_ok=True)
        raise UpdateError("digest_mismatch", "the downloaded archive does not match its checksum")
    partial.replace(target)
    return target


def install_code(archive: Path, app_dir: Path) -> Path:
    """Replace ``app_dir/sectionlab`` with the package inside ``archive``.

    The previous folder is kept as ``sectionlab.bak`` so a bad release can be walked back by
    hand; if anything fails, the backup is restored and the installation is left as it was.
    """
    app_dir = Path(app_dir)
    if not app_dir.is_dir():
        raise UpdateError("not_installed", f"{app_dir} is not an installation folder")
    with tempfile.TemporaryDirectory(dir=app_dir) as staging_name:
        staging = Path(staging_name)
        try:
            with zipfile.ZipFile(archive) as bundle:
                names = bundle.namelist()
                if not any(name.split("/")[0] == PACKAGE_NAME for name in names):
                    raise UpdateError("invalid_archive", "the archive holds no sectionlab package")
                bundle.extractall(staging)
        except zipfile.BadZipFile as error:
            raise UpdateError("invalid_archive", str(error)) from error

        incoming = staging / PACKAGE_NAME
        if not (incoming / "__init__.py").is_file():
            raise UpdateError("invalid_archive", "the archive holds no sectionlab/__init__.py")

        target = app_dir / PACKAGE_NAME
        backup = app_dir / BACKUP_NAME
        if backup.exists():
            shutil.rmtree(backup)
        if target.exists():
            target.rename(backup)
        try:
            shutil.move(str(incoming), str(target))
        except Exception as error:
            if backup.exists() and not target.exists():
                backup.rename(target)
            raise UpdateError("install_failed", str(error)) from error
    return backup
