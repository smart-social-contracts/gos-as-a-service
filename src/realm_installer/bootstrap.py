"""Post-install bootstrap helpers for the in-realm setup wizard.

A Realms GOS backend takes every operation by name: ``run(name, json_args)``,
or ``read(name, json_args)`` for a query, and answers ``{"ok": true, ...}`` or
``{"ok": false, "error": ...}``. The installer sets a new realm up with
``setup_step``, one ``step`` at a time; the founder finishes in the wizard and
launches the realm (``setup_launch``) themselves.
"""

from deploy_resume import coerce_realm_json
from installer_config import (
    configured_file_registry_id,
    configured_marketplace_id,
)

ANONYMOUS_PRINCIPAL = "2vxsx-fae"

# The fields of setup_step "infrastructure" (realm_backend api/setup.py FIELDS).
INFRASTRUCTURE_FIELDS = (
    "frontend_canister_id",
    "file_registry_canister_id",
    "marketplace_canister_id",
    "installer_canister_id",
    "baton_canister_id",
)

# GOS packages carry no marketplace approval the realm could check, so a
# founding install that kept the realm's default policy would refuse them all.
RELAX_TRUST_POLICY_STEP = {"step": "trust_policy", "require_marketplace_approval": False}

# Package step kind -> (realm operation, argument naming the package).
PACKAGE_INSTALL_OPS = {
    "extension": ("extension_install", "extension"),
    "codex": ("codex_install", "codex"),
}


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


def realm_reply(raw) -> tuple[dict, str]:
    """``(reply, error)`` for a realm ``run``/``read`` answer; ``error`` is "" only when the realm did it.

    A governed operation the realm turned into a proposal answers ok with
    ``requires_vote``: nothing ran, so that is an error here too.
    """
    parsed = coerce_realm_json(raw)
    if not isinstance(parsed, dict):
        return {}, f"unreadable realm reply: {str(raw)[:200]}"
    if parsed.get("ok") is not True:
        return parsed, str(parsed.get("error") or "the realm refused the call")
    if parsed.get("requires_vote"):
        return parsed, (
            f"the realm filed this as proposal {parsed.get('proposal') or '?'} "
            "instead of running it: its root department's policy needs a vote"
        )
    return parsed, ""


def setup_install_args(manifest: dict, backend_id: str) -> dict:
    """Args for the setup_install deploy step: the facts the realm takes once, from the installer."""
    return {
        "backend_canister_id": backend_id,
        "founder": resolve_founder(manifest),
        "network": (manifest.get("network") or "").strip(),
        "can_test_mode": bool(manifest.get("can_test_mode")),
    }


def founder_error(founder: str) -> str:
    """Why ``founder`` cannot be the realm's founder, or ""."""
    founder = (founder or "").strip()
    if not founder:
        return "no founder: the manifest has neither founder nor requesting_principal"
    if founder == ANONYMOUS_PRINCIPAL:
        return "the anonymous principal cannot found a realm"
    return ""


def setup_install_payload(args: dict) -> dict:
    """``setup_step`` install: network, can_test_mode and the founder, who gets the founder profile."""
    return {
        "step": "install",
        "network": (args.get("network") or "").strip(),
        "can_test_mode": bool(args.get("can_test_mode")),
        "founder": (args.get("founder") or "").strip(),
    }


def setup_infrastructure_args(manifest: dict, backend_id: str, frontend_id: str) -> dict:
    """Args for the setup_infrastructure deploy step."""
    return {
        "backend_canister_id": backend_id,
        "frontend_canister_id": frontend_id,
        "file_registry_canister_id": _resolve_file_registry_canister_id(manifest),
        "marketplace_canister_id": _resolve_marketplace_canister_id(manifest),
        "installer_canister_id": (manifest.get("installer_canister_id") or "").strip(),
        "baton_canister_id": (manifest.get("baton_canister_id") or "").strip(),
        "test_flags": manifest.get("test_flags") or {},
    }


def setup_infrastructure_payload(args: dict) -> dict:
    """``setup_step`` infrastructure with the canister ids that are known.

    An id nobody supplied is left out rather than sent empty, so the realm is
    never pointed at nothing (or at a stale default).
    """
    payload = {"step": "infrastructure"}
    for field in INFRASTRUCTURE_FIELDS:
        value = (args.get(field) or "").strip()
        if value:
            payload[field] = value
    return payload


def realm_test_mode_payload(test_flags) -> dict:
    """``setup_step`` realm with the manifest's test flags, or {} when there are none.

    The manifest says ``{"test_mode": true, "ii_bypass": true, ...}``; the realm
    keeps ``test_mode`` apart and the other switches as ``test_mode_<name>``.
    """
    if not isinstance(test_flags, dict) or not test_flags:
        return {}
    switches = {}
    for name, on in test_flags.items():
        if name == "test_mode":
            continue
        key = name if name.startswith("test_mode_") else f"test_mode_{name}"
        switches[key] = bool(on)
    return {"step": "realm", "test_mode": bool(test_flags.get("test_mode")), "test_flags": switches}


def realm_identity_payload(realm_info: dict) -> dict:
    """``setup_step`` realm with the realm's name, manifesto and welcome message.

    The name is the installer's to set: the wizard never asks for it and the
    realm will not launch without one. ``open_registration`` is left to the
    codex when there is one, which decides its onboarding itself.
    """
    payload = {
        "step": "realm",
        "name": realm_info.get("display_name") or realm_info.get("name", ""),
        "manifesto": realm_info.get("manifesto", ""),
        "welcome_message": realm_info.get("welcome_message", ""),
    }
    if not realm_info.get("codex"):
        payload["open_registration"] = bool(realm_info.get("open_registration", False))
    return payload


def tokens_payload(nft_canister_id: str, shared_tokens: dict) -> dict:
    """``setup_step`` tokens with the environment's land-NFT canister and shared ledgers, or {}."""
    payload = {"step": "tokens"}
    if (nft_canister_id or "").strip():
        payload["nft_canister_id"] = nft_canister_id.strip()
    if isinstance(shared_tokens, dict) and shared_tokens:
        payload["shared_tokens_json"] = shared_tokens
    return payload if len(payload) > 1 else {}


# manifest.branding.files keys (the portal's upload) -> realm branding fields.
_BRANDING_FIELDS = {
    "/custom/logo.png": "logo_url",
    "/custom/background.png": "background_image_url",
}


def branding_payload(branding: dict, default_registry_id: str = "") -> dict:
    """``setup_step`` branding pointing at the images the user uploaded to the file registry, or {}.

    ``branding`` is ``{file_registry_canister_id, namespace, files}`` with
    ``files`` mapping ``/custom/logo.png`` / ``/custom/background.png`` to a
    path in ``namespace``; the registry serves each at
    ``https://<registry>.icp0.io/<namespace>/<path>``.
    """
    branding = branding or {}
    files = branding.get("files") or {}
    namespace = (branding.get("namespace") or "").strip().strip("/")
    registry = (branding.get("file_registry_canister_id") or default_registry_id or "").strip()
    if not (files and namespace and registry):
        return {}
    payload = {"step": "branding"}
    for asset_key, field in _BRANDING_FIELDS.items():
        path = str(files.get(asset_key) or "").strip().lstrip("/")
        if path:
            payload[field] = f"https://{registry}.icp0.io/{namespace}/{path}"
    return payload if len(payload) > 1 else {}


def package_needs_version(version) -> bool:
    """True when a package step names no version, which the realm needs: resolve the latest first."""
    v = str(version or "").strip().lower()
    return v in ("", "latest", "none")


def package_install_call(kind: str, package_id: str, version: str) -> tuple[str, dict]:
    """The realm operation and arguments that install ``package_id`` at ``version`` from the file registry."""
    op, key = PACKAGE_INSTALL_OPS[kind]
    return op, {key: package_id, "version": version}


def gos_implementation(manifest: dict) -> str:
    gos = manifest.get("gos") or {}
    if isinstance(gos, dict):
        return (gos.get("implementation") or "").strip()
    return ""


def uses_realms_bootstrap(manifest: dict) -> bool:
    """Realms GOS post-install (setup_step / grant_frontend_access).

    Missing/blank implementation stays Realms so existing jobs keep working.
    """
    impl = gos_implementation(manifest)
    return impl in ("", "realms-gos")


def uses_monad_gos_bootstrap(manifest: dict) -> bool:
    return gos_implementation(manifest) == "monad-gos"


def enter_setup_args(manifest: dict, backend_id: str) -> dict:
    """Build args for the Monad GOS enter_setup deploy step."""
    return {
        "backend_canister_id": backend_id,
        "creator_principal": resolve_founder(manifest),
        "realm_registry_canister_id": _resolve_realm_registry_canister_id(manifest),
        "environment": (manifest.get("network") or "").strip(),
    }


def build_enter_setup_candid(creator: str, registry_id: str, environment: str) -> str:
    """Candid for Monad GOS ``enter_setup(principal, text, text)``."""
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


def setup_entry_kind(manifest: dict) -> str:
    """The first bootstrap step: ``setup_install`` on Realms GOS, ``enter_setup`` on Monad GOS."""
    return "setup_install" if uses_realms_bootstrap(manifest) else "enter_setup"


def deploy_step_kinds(manifest: dict) -> list[str]:
    """Return ordered deploy step kinds matching ``_build_steps``."""
    kinds = []
    frontend_id = manifest.get("frontend_canister_id", "")
    backend_id = manifest.get("target_canister_id", "")
    if needs_enter_setup_step(manifest, backend_id):
        kinds.append(setup_entry_kind(manifest))
    if uses_realms_bootstrap(manifest) and frontend_id and backend_id:
        kinds.extend(["setup_infrastructure", "grant_frontend_access"])

    for ext in manifest.get("extensions") or []:
        ext_id = ext.get("id") if isinstance(ext, dict) else None
        if ext_id:
            kinds.append("extension")

    for cdx in manifest.get("codices") or []:
        cdx_id = cdx.get("id") if isinstance(cdx, dict) else None
        if cdx_id:
            kinds.append("codex")

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
            codex_list.append({"id": pkg, "version": codex.get("version")})
        elif isinstance(pkg, dict):
            codex_list.append({"id": pkg.get("name", ""), "version": pkg.get("version")})

    return ext_list, codex_list
