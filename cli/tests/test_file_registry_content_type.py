"""MIME type mapping for file_registry uploads (realms#292)."""

from gaas.file_registry_client import _content_type


def test_svg_content_type() -> None:
    assert _content_type("frontend/dist/images/logo_sphere_only.svg") == "image/svg+xml"


def test_ic_assets_json5_content_type() -> None:
    assert _content_type("frontend/dist/.ic-assets.json5") == "application/json"


def test_common_frontend_assets() -> None:
    assert _content_type("index.html") == "text/html"
    assert _content_type("app.js") == "application/javascript"
    assert _content_type("style.css") == "text/css"
    assert _content_type("logo.png") == "image/png"
    assert _content_type("font.woff2") == "font/woff2"
