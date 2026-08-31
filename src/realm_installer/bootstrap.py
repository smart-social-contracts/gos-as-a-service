"""Post-install bootstrap helpers for the in-realm setup wizard."""

from installer_config import (
    configured_file_registry_id,
    configured_marketplace_id,
    configured_portal_base,
)


def _resolve_file_registry_canister_id(manifest: dict) -> str:
    """Resolve the file registry from manifest infra, not the realm registry."""
    infra = manifest.get("infra") or {}
    return (
        (manifest.get("file_registry_canister_id") or "").strip()
        or (infra.get("file_registry_canister_id") or "").strip()
        or configured_file_registry_id(manifest.get("network", ""))
        or ""
    )


def _resolve_marketplace_canister_id(manifest: dict) -> str:
    """Resolve marketplace from manifest or infra."""
    infra = manifest.get("infra") or {}
    return (
        (manifest.get("marketplace_canister_id") or "").strip()
        or (infra.get("marketplace_canister_id") or "").strip()
        or configured_marketplace_id(manifest.get("network", ""))
        or ""
    )


def _resolve_realm_registry_canister_id(manifest: dict) -> str:
    """Resolve the realm registry id (registry backend), when present."""
    return (
        (manifest.get("realm_registry_canister_id") or "").strip()
        or (manifest.get("registry_canister_id") or "").strip()
    )


def resolve_founder(manifest: dict) -> str:
    founder = (manifest.get("founder") or "").strip()
    if founder:
        return founder
    return (manifest.get("requesting_principal") or "").strip()


def manifest_has_codex_block(manifest: dict) -> bool:
    """True when the manifest carries a legacy realm.codex package block."""
    realm_info = manifest.get("realm") or {}
    codex = realm_info.get("codex")
    if not codex or not isinstance(codex, dict):
        return False
    return bool(codex.get("package"))


def configure_canister_ids_args(manifest: dict, backend_id: str, frontend_id: str) -> dict:
    """Build args for the configure_canister_ids deploy step."""
    return {
        "backend_canister_id": backend_id,
        "frontend_canister_id": frontend_id,
        "realm_registry_canister_id": _resolve_realm_registry_canister_id(manifest),
        "file_registry_canister_id": _resolve_file_registry_canister_id(manifest),
        "marketplace_canister_id": _resolve_marketplace_canister_id(manifest),
        "test_flags": manifest.get("test_flags") or {},
        "can_test_mode": bool(manifest.get("can_test_mode")),
        "requesting_principal": resolve_founder(manifest),
        "portal_origin": configured_portal_base(manifest),
    }


def configure_canister_ids_payload(args: dict) -> tuple[dict, list[str]]:
    """Build set_canister_config_json payload. Returns (payload, warnings)."""
    warnings = []
    frontend_id = args.get("frontend_canister_id", "")
    payload = {"frontend_canister_id": frontend_id}

    realm_registry_id = (args.get("realm_registry_canister_id") or "").strip()
    if realm_registry_id:
        payload["realm_registry_canister_id"] = realm_registry_id

    file_registry_id = (args.get("file_registry_canister_id") or "").strip()
    if file_registry_id:
        payload["file_registry_canister_id"] = file_registry_id

    marketplace_id = (args.get("marketplace_canister_id") or "").strip()
    if marketplace_id:
        payload["marketplace_canister_id"] = marketplace_id

    test_flags = args.get("test_flags")
    if isinstance(test_flags, dict) and test_flags:
        payload["test_flags"] = test_flags
    if "can_test_mode" in args:
        payload["can_test_mode"] = bool(args["can_test_mode"])

    creator = (args.get("requesting_principal") or "").strip()
    if creator:
        payload["creator_principal"] = creator
    else:
        warnings.append(
            "requesting_principal missing from manifest; creator_principal not set"
        )

    portal_origin = (args.get("portal_origin") or "").strip()
    if portal_origin:
        payload["portal_origin"] = portal_origin

    return payload, warnings


def resync_extension_frontends_args(manifest: dict) -> dict:
    """Build args for the resync_extension_frontends post-provision step."""
    return {
        "frontend_canister_id": (manifest.get("frontend_canister_id") or "").strip(),
    }


def gos_implementation(manifest: dict) -> str:
    gos = manifest.get("gos") or {}
    if isinstance(gos, dict):
        return (gos.get("implementation") or "").strip()
    return ""


def uses_realms_bootstrap(manifest: dict) -> bool:
    """Realms-only post-install (set_canister_config_json / grant_frontend_access).

    Missing/blank implementation stays Realms so existing jobs keep working.
    """
    impl = gos_implementation(manifest)
    return impl in ("", "realms-gos")


def uses_monad_gos_bootstrap(manifest: dict) -> bool:
    return gos_implementation(manifest) == "monad-gos"


def enter_setup_args(manifest: dict, backend_id: str) -> dict:
    """Build args for the enter_setup deploy step."""
    return {
        "backend_canister_id": backend_id,
        "creator_principal": resolve_founder(manifest),
        "realm_registry_canister_id": _resolve_realm_registry_canister_id(manifest),
        "environment": (manifest.get("network") or "").strip(),
    }


def bootstrap_json_error(raw) -> str:
    """Return an error string when a (text) bootstrap call encoded failure.

    Inter-canister ``call_raw`` success is not enough: Realms ``enter_setup``
    and ``set_canister_config_json`` reply with JSON ``{"ok": false}`` /
    ``{"success": false}`` instead of trapping. Treating that as completed
    left a virgin realm (no creator) and then failed ``configure_canister_ids``.
    """
    payload = raw
    if isinstance(payload, (bytes, bytearray)):
        try:
            payload = payload.decode("utf-8")
        except UnicodeDecodeError:
            return ""
    if isinstance(payload, str):
        text = payload.strip()
        if text.startswith("(") and text.endswith(")"):
            text = text[1:-1].strip().rstrip(",")
        if text.startswith('"') and text.endswith('"'):
            try:
                import json as _json

                text = _json.loads(text)
            except Exception:
                text = text[1:-1]
        payload = text
    if isinstance(payload, str):
        try:
            import json as _json

            payload = _json.loads(payload)
        except Exception:
            return ""
    if not isinstance(payload, dict):
        return ""
    if payload.get("ok") is False or payload.get("success") is False:
        return str(payload.get("error") or payload.get("err") or payload)
    return ""


def build_enter_setup_candid(creator: str, registry_id: str, environment: str) -> str:
    """Candid for Realms/Chora ``enter_setup(principal, text, text)``."""
    def _text(value: str) -> str:
        return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'

    return f'(principal "{creator}", {_text(registry_id)}, {_text(environment)})'


def needs_enter_setup_step(manifest: dict, backend_id: str = "") -> bool:
    """True when the deploy includes a backend (or will deploy both canisters)."""
    backend = (backend_id or manifest.get("target_canister_id") or "").strip()
    if backend:
        return True
    deploy_scope = (manifest.get("deploy_scope") or "both").strip()
    return deploy_scope == "both"


def has_extension_installs(manifest: dict) -> bool:
    for ext in manifest.get("extensions") or []:
        if isinstance(ext, str) and ext.strip():
            return True
        if isinstance(ext, dict) and (ext.get("id") or "").strip():
            return True
    return False


def deploy_step_kinds(manifest: dict) -> list[str]:
    """Return ordered deploy step kinds matching ``_build_steps``."""
    kinds = []
    frontend_id = manifest.get("frontend_canister_id", "")
    backend_id = manifest.get("target_canister_id", "")
    if needs_enter_setup_step(manifest, backend_id):
        kinds.append("enter_setup")
    if uses_realms_bootstrap(manifest) and frontend_id and backend_id:
        kinds.extend(["configure_canister_ids", "grant_frontend_access"])

    for ext in manifest.get("extensions") or []:
        ext_id = ext.get("id") if isinstance(ext, dict) else None
        if ext_id:
            kinds.append("extension")

    for cdx in manifest.get("codices") or []:
        cdx_id = cdx.get("id") if isinstance(cdx, dict) else None
        if cdx_id:
            kinds.append("codex")

    if has_extension_installs(manifest):
        kinds.append("resync_extension_frontends")

    return kinds


def resolve_legacy_install_lists(realm_info: dict) -> tuple[list, list]:
    """Resolve extension and codex install lists from a legacy manifest."""
    ext_list = []
    for ext in realm_info.get("extensions") or []:
        if isinstance(ext, str):
            ext_list.append({"id": ext})
        elif isinstance(ext, dict):
            ext_list.append(ext)

    codex_list = []
    codex = realm_info.get("codex")
    if codex and isinstance(codex, dict):
        pkg = codex.get("package")
        if isinstance(pkg, str):
            codex_list.append({"id": pkg, "version": codex.get("version"), "run_init": True})
        elif isinstance(pkg, dict):
            codex_list.append(
                {"id": pkg.get("name", ""), "version": pkg.get("version"), "run_init": True}
            )

    return ext_list, codex_list
