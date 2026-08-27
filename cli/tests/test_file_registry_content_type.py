"""MIME type mapping for file_registry uploads (realms#292)."""

from pathlib import Path

from gaas.file_registry_client import _content_type, upload_file


def test_svg_content_type() -> None:
    assert _content_type("frontend/dist/images/internet-computer-icp-logo.svg") == "image/svg+xml"


def test_ic_assets_json5_content_type() -> None:
    assert _content_type("frontend/dist/.ic-assets.json5") == "application/json"


def test_upload_file_skips_zero_byte_file(tmp_path: Path) -> None:
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
        == "skipped"
    )


def test_common_frontend_assets() -> None:
    assert _content_type("index.html") == "text/html"
    assert _content_type("app.js") == "application/javascript"
    assert _content_type("style.css") == "text/css"
    assert _content_type("logo.png") == "image/png"
    assert _content_type("font.woff2") == "font/woff2"
