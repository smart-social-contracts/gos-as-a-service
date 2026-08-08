"""GitHub release artifact fetcher with caching and checksum verification."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import requests

DEFAULT_CACHE_ROOT = Path.home() / ".cache" / "gaas"


class ArtifactError(RuntimeError):
    pass


def release_asset_url(repo: str, tag: str, name: str) -> str:
    return f"https://github.com/{repo}/releases/download/{tag}/{name}"


def cache_dir(repo: str, tag: str, cache_root: Path | None = None) -> Path:
    root = cache_root or DEFAULT_CACHE_ROOT
    return root / repo.replace("/", "_") / tag


def _parse_checksums(text: str) -> dict[str, str]:
    checksums: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            digest, filename = parts[0], parts[-1]
            checksums[filename] = digest.lower()
    return checksums


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download(url: str, dest: Path, session: requests.Session) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    response = session.get(url, stream=True, timeout=120)
    if response.status_code != 200:
        raise ArtifactError(
            f"failed to download {url}: HTTP {response.status_code} {response.reason}"
        )
    with dest.open("wb") as handle:
        for chunk in response.iter_content(chunk_size=1024 * 1024):
            if chunk:
                handle.write(chunk)


def fetch_release_assets(
    repo: str,
    tag: str,
    names: list[str],
    dest_dir: Path,
    *,
    cache_root: Path | None = None,
    session: requests.Session | None = None,
) -> list[Path]:
    """Download release assets, using cache and optional checksum verification."""
    if not names:
        return []

    http = session or requests.Session()
    store = cache_dir(repo, tag, cache_root)
    store.mkdir(parents=True, exist_ok=True)
    dest_dir.mkdir(parents=True, exist_ok=True)

    checksums: dict[str, str] = {}
    if "checksums.txt" in names:
        checksum_url = release_asset_url(repo, tag, "checksums.txt")
        checksum_path = store / "checksums.txt"
        if not checksum_path.is_file():
            _download(checksum_url, checksum_path, http)
        checksums = _parse_checksums(checksum_path.read_text(encoding="utf-8"))

    downloaded: list[Path] = []
    for name in names:
        if name == "checksums.txt":
            continue
        url = release_asset_url(repo, tag, name)
        cached = store / name
        output = dest_dir / name

        if not cached.is_file():
            _download(url, cached, http)

        if name in checksums:
            actual = _sha256_file(cached)
            expected = checksums[name].lower()
            if not re.fullmatch(r"[a-f0-9]{64}", expected):
                raise ArtifactError(
                    f"unsupported checksum format for {name}: {expected!r}"
                )
            if actual != expected:
                cached.unlink(missing_ok=True)
                raise ArtifactError(
                    f"checksum mismatch for {name}: expected {expected}, got {actual}"
                )

        if not output.is_file() or output.stat().st_size != cached.stat().st_size:
            output.write_bytes(cached.read_bytes())
        downloaded.append(output)

    return downloaded
