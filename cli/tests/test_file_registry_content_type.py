"""MIME type mapping for file_registry uploads (realms#292)."""

from pathlib import Path

from gaas.file_registry_client import _content_type, upload_file


def test_svg_content_type() -> None:
    assert _content_type("frontend/dist/images/internet-computer-icp-logo.svg") == "image/svg+xml"


def test_ic_assets_json5_content_type() -> None:
    assert _content_type("frontend/dist/.ic-assets.json5") == "application/json"


def test_upload_file_uploads_zero_byte_file(tmp_path: Path, monkeypatch) -> None:
    from gaas import dfx
    from gaas import file_registry_client as client

    client._oneshot_finalize_ids.clear()
    empty = tmp_path / "empty.js"
    empty.write_bytes(b"")
    calls: list[str] = []

    def fake_call(canister_id, method, *args, **kwargs):
        del canister_id, args, kwargs
        calls.append(method)
        if method == "finalize_chunked_file_step":
            raise dfx.DfxError(
                "The replica returned a rejection error: reject message "
                "Canister has no update method 'finalize_chunked_file_step'.",
                command=["dfx", "canister", "call"],
                stderr="has no update method 'finalize_chunked_file_step'",
            )
        return '{"ok": true}'

    monkeypatch.setattr(dfx, "canister_call", fake_call)
    monkeypatch.setattr(dfx, "candid_text_arg", lambda payload: payload)
    assert (
        upload_file(
            "registry-id",
            "ns",
            "empty.js",
            empty,
            "ic",
        )
        == "uploaded"
    )
    assert "store_file_chunk" in calls
    assert "finalize_chunked_file" in calls


def test_common_frontend_assets() -> None:
    assert _content_type("index.html") == "text/html"
    assert _content_type("app.js") == "application/javascript"
    assert _content_type("style.css") == "text/css"
    assert _content_type("logo.png") == "image/png"
    assert _content_type("font.woff2") == "font/woff2"


def test_finalize_falls_back_to_casals_oneshot(monkeypatch) -> None:
    from gaas import dfx
    from gaas import file_registry_client as client

    client._oneshot_finalize_ids.clear()
    calls: list[str] = []

    def fake_call(canister_id, method, *args, **kwargs):
        del canister_id, args, kwargs
        calls.append(method)
        if method == "finalize_chunked_file_step":
            raise dfx.DfxError(
                "The replica returned a rejection error: reject message "
                "Canister has no update method 'finalize_chunked_file_step'.",
                command=["dfx", "canister", "call"],
                stderr="has no update method 'finalize_chunked_file_step'",
            )
        return '{"ok": true}'

    monkeypatch.setattr(dfx, "canister_call", fake_call)
    monkeypatch.setattr(dfx, "candid_text_arg", lambda payload: payload)
    assert (
        client._finalize_chunked_upload("reg", "ns", "file.wasm.gz", "abc", "ic")
        == "uploaded"
    )
    assert calls == ["finalize_chunked_file_step", "finalize_chunked_file"]


def test_finalize_oneshot_is_cached_per_registry(monkeypatch) -> None:
    from gaas import dfx
    from gaas import file_registry_client as client

    client._oneshot_finalize_ids.clear()
    calls: list[str] = []

    def fake_call(canister_id, method, *args, **kwargs):
        del canister_id, args, kwargs
        calls.append(method)
        if method == "finalize_chunked_file_step":
            raise dfx.DfxError(
                "Canister has no update method 'finalize_chunked_file_step'.",
                command=["dfx", "canister", "call"],
                stderr="has no update method 'finalize_chunked_file_step'",
            )
        return '{"ok": true}'

    monkeypatch.setattr(dfx, "canister_call", fake_call)
    monkeypatch.setattr(dfx, "candid_text_arg", lambda payload: payload)
    assert client._finalize_chunked_upload("reg", "ns", "a.js", "aa", "ic") == "uploaded"
    calls.clear()
    assert client._finalize_chunked_upload("reg", "ns", "b.js", "bb", "ic") == "uploaded"
    assert calls == ["finalize_chunked_file"]


def test_upload_directory_includes_failed_paths(tmp_path: Path, monkeypatch) -> None:
    from gaas import dfx
    from gaas import file_registry_client as client

    client._oneshot_finalize_ids.clear()
    good = tmp_path / "ok.js"
    good.write_text("ok")
    bad = tmp_path / "bad.js"
    bad.write_text("bad")

    def fake_call(canister_id, method, *args, **kwargs):
        del canister_id, kwargs
        payload = args[0] if args else ""
        if method == "store_file_chunk" and "bad.js" in str(payload):
            return '{"ok": false}'
        if method == "finalize_chunked_file_step":
            raise dfx.DfxError(
                "Canister has no update method 'finalize_chunked_file_step'.",
                command=["dfx", "canister", "call"],
                stderr="has no update method 'finalize_chunked_file_step'",
            )
        return '{"ok": true}'

    monkeypatch.setattr(dfx, "canister_call", fake_call)
    monkeypatch.setattr(dfx, "candid_text_arg", lambda payload: payload)
    uploaded, failed, failed_paths = client.upload_directory(
        "reg", "ns", tmp_path, "ic"
    )
    assert uploaded == 1
    assert failed == 1
    assert failed_paths == ["bad.js"]
