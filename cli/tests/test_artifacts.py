"""Tests for release artifact URL construction and fetching."""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gaas.artifacts import (
    ArtifactError,
    cache_dir,
    fetch_release_assets,
    release_asset_url,
)


def test_release_asset_url() -> None:
    url = release_asset_url("smart-social-contracts/realms", "v0.3.1", "realm-backend.wasm.gz")
    assert url == (
        "https://github.com/smart-social-contracts/realms/releases/download/"
        "v0.3.1/realm-backend.wasm.gz"
    )


def test_cache_dir_normalizes_repo() -> None:
    path = cache_dir("smart-social-contracts/realms", "v0.3.1", Path("/tmp/cache"))
    assert path == Path("/tmp/cache/smart-social-contracts_realms/v0.3.1")


def test_fetch_release_assets_uses_cache(tmp_path: Path) -> None:
    session = MagicMock()
    wasm_bytes = b"wasm-content"
    checksum = hashlib.sha256(wasm_bytes).hexdigest()

    def fake_get(url: str, stream: bool = True, timeout: int = 120) -> MagicMock:
        response = MagicMock()
        response.status_code = 200
        if url.endswith("checksums.txt"):
            body = f"{checksum}  artifact.wasm.gz\n".encode()
        else:
            body = wasm_bytes
        response.iter_content = lambda chunk_size: iter([body])
        return response

    session.get.side_effect = fake_get

    dest = tmp_path / "out"
    paths = fetch_release_assets(
        "org/repo",
        "v1.0.0",
        ["checksums.txt", "artifact.wasm.gz"],
        dest,
        cache_root=tmp_path / "cache",
        session=session,
    )

    assert len(paths) == 1
    assert paths[0].read_bytes() == wasm_bytes
    assert session.get.call_count == 2


def test_fetch_release_assets_checksum_mismatch(tmp_path: Path) -> None:
    session = MagicMock()

    def fake_get(url: str, stream: bool = True, timeout: int = 120) -> MagicMock:
        response = MagicMock()
        response.status_code = 200
        if url.endswith("checksums.txt"):
            body = b"deadbeef" * 8 + b"  artifact.wasm.gz\n"
        else:
            body = b"other-content"
        response.iter_content = lambda chunk_size: iter([body])
        return response

    session.get.side_effect = fake_get

    with pytest.raises(ArtifactError, match="checksum mismatch"):
        fetch_release_assets(
            "org/repo",
            "v1.0.0",
            ["checksums.txt", "artifact.wasm.gz"],
            tmp_path / "out",
            cache_root=tmp_path / "cache",
            session=session,
        )
