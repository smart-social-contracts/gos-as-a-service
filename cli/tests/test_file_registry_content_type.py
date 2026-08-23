"""MIME type mapping for file_registry uploads (realms#292)."""

from pathlib import Path
from unittest.mock import patch

from gaas.file_registry_client import _content_type, upload_directory, upload_file


def test_svg_content_type() -> None:
    assert _content_type("frontend/dist/images/logo_sphere_only.svg") == "image/svg+xml"


def test_ic_assets_json5_content_type() -> None:
    assert _content_type("frontend/dist/.ic-assets.json5") == "application/json"


def test_upload_file_rejects_zero_byte_file(tmp_path: Path) -> None:
    empty = tmp_path / "empty.wasm"
    empty.write_bytes(b"")
    assert (
        upload_file(
            "registry-id",
            "ns",
            "empty.wasm",
            empty,
            "ic",
        )
        == "failed"
    )


def test_upload_directory_skips_empty_placeholders(tmp_path: Path) -> None:
    (tmp_path / "images").mkdir()
    empty = tmp_path / "images" / "error.svg"
    empty.write_bytes(b"")
    real = tmp_path / "index.html"
    real.write_text("<html></html>")
    calls: list[str] = []

    def fake_upload(_registry, _ns, path, _local, _network, **_kwargs):
        calls.append(path)
        return "uploaded"

    with patch("gaas.file_registry_client.upload_file", side_effect=fake_upload):
        uploaded, failed = upload_directory("reg", "frontend/ns", tmp_path, "ic")

    assert failed == 0
    assert uploaded == 1
    assert calls == ["index.html"]


def test_common_frontend_assets() -> None:
    assert _content_type("index.html") == "text/html"
    assert _content_type("app.js") == "application/javascript"
    assert _content_type("style.css") == "text/css"
    assert _content_type("logo.png") == "image/png"
    assert _content_type("font.woff2") == "font/woff2"
