"""Deployment phase runner."""

from __future__ import annotations

import json
import os
import shutil
import sys
import tarfile
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol
from urllib.parse import urlparse, urlunparse

import requests
import typer
from rich.console import Console
from rich.table import Table

from gaas import dfx
from gaas.artifacts import fetch_release_assets
from gaas.casals_cli import CASALS_BOOTSTRAP_NAMES, run_casals_new
from gaas.descriptor import CANISTER_ID_RE, Descriptor
from gaas.destroy import destroy_except_frontend
from gaas.dns import render_dns_records, wait_for_dns
from gaas.domain_reg import attempt_domain_registration
from gaas.codex_seed import seed_codex_catalog
from gaas.cycles_plan import apply_headroom_topups, canister_headroom
from gaas.conductor_seed import (
    authorize_gos_entry,
    casals_orchestra_name,
    configure_multisig_signers,
    ensure_deployments_commander,
    ensure_platform_stand,
    ensure_section_commanders,
    ensure_sheet_and_deploy_multisig,
    get_tree,
    seed_orchestration_templates,
    _find_canister_id,
    _section_names,
)
from gaas.file_registry_client import (
    ensure_version_catalog_entry,
    fetch_namespace_hashes,
    namespace_published,
    seed_gos_entry,
    sha256_file,
)
from gaas.gaas_env import frontend_ic_origin, remove_gaas_env, write_gaas_env
from gaas.known import (
    DEFAULT_CANISTER_COUNT,
    DEFAULT_CASALS_SECTION,
    DEFAULT_CYCLES_PER_CANISTER,
    DEFAULT_PLATFORM_RELEASE_REPO,
    DFX_CANISTER_NAMES,
    KNOWN_CANISTER_NAMES,
)
from gaas.namespace_approval_seed import seed_namespace_approvals
from gaas.platform import (
    PlatformError,
    fetch_platform_frontend_archive,
    find_gos_repo_root,
    frontend_dist_dir,
    inject_portal_ic_env_assets,
    require_casals_checkout,
    resolve_casals_file_registry_wasm,
    resolve_casals_frontend_dist,
    resolve_casals_wasm,
    resolve_platform_backend_wasm,
)
from gaas.canister_ids_sync import align_ic_alias, persist_descriptor_canister_ids
from gaas.canister_liveness import (
    CanisterNotFoundError,
    assert_casals_frontend_live,
    assert_installer_live_for_network,
)
from gaas.preflight import PreflightReport, run_preflight
from gaas.runlog import format_duration, get_run_log, print_log_path
from gaas.source_build import resolve_gos_artifacts
from gaas.versions import normalize_catalog_version, resolve_deploy_version

console = Console()


@dataclass
class SeedArtifactSummary:
    key: str
    wasm_hash: str
    status: str


@dataclass
class SeedAuthSummary:
    key: str
    wasm_hash: str
    status: str


SEED_PHASE_CANISTERS: tuple[str, ...] = (
    "realm_registry_backend",
    "casals_backend",
    "realm_registry_frontend",
    "realm_installer",
)


@dataclass
class DeployContext:
    identity: str
    network: str
    required_cycles: int | None = None
    preflight: PreflightReport | None = None
    stopped: bool = False
    completed_phases: list[str] = field(default_factory=list)
    current_phase: str | None = None
    from_phase: str | None = None
    descriptor_path: Path | None = None
    yes: bool = False
    casals_src: Path | None = None
    dns_timeout_min: int = 20
    skip_dns_wait: bool = False
    keep_env_file: bool = False
    reinstall_backends: bool = False
    destroy_except_frontend: bool = False
    cycles_evacuated: int = 0
    work_dir: Path | None = None
    http: requests.Session | None = None
    seed_artifacts: list[SeedArtifactSummary] = field(default_factory=list)
    seed_authorizations: list[SeedAuthSummary] = field(default_factory=list)


class PhaseFunc(Protocol):
    def __call__(self, descriptor: Descriptor, ctx: DeployContext) -> None: ...


def _work_dir(ctx: DeployContext) -> Path:
    if ctx.work_dir is None:
        ctx.work_dir = Path(tempfile.mkdtemp(prefix="gaas-deploy-"))
    return ctx.work_dir


def _save_descriptor(descriptor: Descriptor, ctx: DeployContext) -> None:
    if ctx.descriptor_path:
        descriptor.save(ctx.descriptor_path)


def _create_and_register_canister(
    name: str,
    descriptor: Descriptor,
    ctx: DeployContext,
    principal: str,
) -> str:
    """Mint a platform canister, persist its id, and verify it exists on the replica."""
    fund = canister_headroom(name, descriptor) if ctx.network == "ic" else None
    dfx_name = DFX_CANISTER_NAMES.get(name)
    if dfx_name:
        canister_id = dfx.create_canister(
            dfx_name,
            ctx.network,
            identity=ctx.identity,
            with_cycles=fund,
        )
    else:
        canister_id = dfx.create_canister_via_ledger(
            ctx.network,
            identity=ctx.identity,
            controller=principal,
        )
        if fund and ctx.network == "ic":
            dfx.top_up_canister(
                canister_id,
                fund,
                ctx.network,
                identity=ctx.identity,
            )

    descriptor.set_canister_id(name, canister_id)
    try:
        created = dfx.canister_status(
            canister_id, ctx.network, identity=ctx.identity
        )
    except dfx.DfxError as exc:
        if not dfx.is_canister_not_found_error(exc):
            raise RuntimeError(
                f"refusing to use {name} {canister_id}: create did not leave a "
                f"live canister on {ctx.network} ({exc})"
            ) from exc
        # Named ``dfx canister create`` reused a dead canister_ids.json row.
        dead_id = canister_id
        console.print(
            f"  {name}: named create reused dead {dead_id}; minting via ledger"
        )
        if dfx_name:
            dfx.forget_dead_named_canister_mappings(
                dfx_name,
                ctx.network,
                identity=ctx.identity,
                is_dead=lambda cid, _dead=dead_id: cid == _dead,
            )
        canister_id = dfx.create_canister_via_ledger(
            ctx.network,
            identity=ctx.identity,
            controller=principal,
        )
        if fund and ctx.network == "ic":
            dfx.top_up_canister(
                canister_id,
                fund,
                ctx.network,
                identity=ctx.identity,
            )
        descriptor.set_canister_id(name, canister_id)
        created = dfx.canister_status(
            canister_id, ctx.network, identity=ctx.identity
        )
    _save_descriptor(descriptor, ctx)
    console.print(f"  {name}: created {canister_id} ({created.status})")
    return canister_id


def _try_adopt_pinned_canister(
    name: str,
    existing_id: str,
    descriptor: Descriptor,
    ctx: DeployContext,
    principal: str,
) -> bool:
    """Adopt a live pin when deployer is a controller. Return False when the pin is dead."""
    try:
        status = dfx.canister_status(existing_id, ctx.network, identity=ctx.identity)
    except dfx.DfxError as exc:
        if dfx.is_canister_not_found_error(exc):
            console.print(
                f"  {name}: stale pin {existing_id} not on IC; creating fresh canister"
            )
            descriptor.canisters.pop(name, None)
            return False
        raise

    controllers = status.controllers
    if controllers and principal not in controllers:
        raise RuntimeError(
            f"identity {principal!r} is not a controller of adopted canister "
            f"{name} ({existing_id}); controllers: {', '.join(controllers)}"
        )

    if name == "realm_installer" and (
        descriptor.name == "staging"
        or ctx.network in ("staging", "local", "localhost")
    ):
        assert_installer_live_for_network(existing_id, ctx.network)

    console.print(f"  {name}: adopt {existing_id} ({status.status})")
    return True


def _normalize_version(version: str) -> str:
    return normalize_catalog_version(version)


def _gos_catalog_version(entry, session=None) -> str:
    return resolve_deploy_version(
        entry.version, entry.release_repo, session=session
    ).catalog_version


def _gos_version_label(entry, session=None) -> str:
    resolved = resolve_deploy_version(
        entry.version, entry.release_repo, session=session
    )
    if resolved.descriptor_version == "latest" and resolved.fetch_tag:
        return f"latest→{resolved.fetch_tag}"
    return entry.version


def _portal_url(descriptor: Descriptor) -> str:
    return f"https://{descriptor.domain}"


# descriptor test_flags name -> key in the registry's get_runtime_flags reply.
# Mirrors _FLAG_MAP in src/realm_registry_backend/core/runtime_flags.py; keep in
# step with it when a flag is added.
_RUNTIME_FLAG_KEYS = {
    "test_mode": "test_mode",
    "ii_bypass": "test_mode_ii_bypass",
    "user_self_registration": "test_mode_user_self_registration",
    "demo_data": "test_mode_demo_data",
    "skip_terms": "test_mode_skip_terms",
    "skip_passport_zkproof": "test_mode_skip_passport_zkproof",
    "skip_authentication": "test_mode_skip_authentication",
    "disable_card_billing": "test_mode_disable_card_billing",
    "assistant_experimental_notice": "test_mode_assistant_experimental_notice",
}


def _resolve_can_test_mode(descriptor: Descriptor) -> bool:
    """Precedence: explicit flags.can_test_mode > deprecated flags.open_mode >
    deprecated services.open_mode > derived (true when no billing_url)."""
    if "can_test_mode" in descriptor.flags:
        return descriptor.flags["can_test_mode"]
    if "open_mode" in descriptor.flags:
        return descriptor.flags["open_mode"]
    if descriptor.services.open_mode is not None:
        return descriptor.services.open_mode
    return descriptor.services.billing_url is None


def _registry_config_json(descriptor: Descriptor) -> str:
    payload: dict = {
        "portal_url": _portal_url(descriptor),
        "can_test_mode": _resolve_can_test_mode(descriptor),
    }
    if descriptor.services.billing_url:
        payload["billing_url"] = descriptor.services.billing_url
    if descriptor.services.billing_service_principal:
        payload["billing_service_principal"] = descriptor.services.billing_service_principal
    installer_id = descriptor.canisters.get("realm_installer", "")
    if installer_id:
        payload["installer_id"] = installer_id
    casals_frontend = descriptor.canisters.get("casals_frontend", "")
    if casals_frontend:
        payload["casals_frontend_canister_id"] = casals_frontend
    for key, value in descriptor.flags.items():
        if key not in ("open_mode", "can_test_mode"):
            payload[key] = value
    return json.dumps(payload)


def _registry_runtime_config_json(descriptor: Descriptor, network: str) -> str | None:
    """Runtime config for the portal (test flags + live Casals frontend principal).

    ``casals_frontend_canister_id`` is always included when present so
    ``realms seed`` can refresh the Infrastructure link without a portal
    rebuild. Test flags are omitted when can_test_mode is false.
    """
    payload: dict = {}
    casals_frontend = (descriptor.canisters.get("casals_frontend") or "").strip()
    if casals_frontend:
        payload["casals_frontend_canister_id"] = casals_frontend

    if _resolve_can_test_mode(descriptor):
        # No test_mode/ii_bypass base: can_test_mode means test mode is permitted
        # here, not that it is on. Inferring them turned staging — which runs with
        # every test flag false — into an environment that auto-logs-in every
        # visitor as the deterministic test identity. The descriptor decides.
        test_flags: dict = {}
        if (network or "").strip().lower() in ("staging", "demo"):
            test_flags["disable_card_billing"] = True
            test_flags["assistant_experimental_notice"] = True
        if descriptor.test_flags:
            test_flags.update(descriptor.test_flags)
        payload["test_flags"] = test_flags
        # Registry runtime_flags rejects test flags when network=ic; omit on mainnet.
        if network != "ic":
            payload["network"] = network

    if not payload:
        return None
    return json.dumps(payload)


def _installer_config_json(descriptor: Descriptor) -> str:
    canisters = descriptor.canisters
    payload = {
        "registry_backend_id": canisters.get("realm_registry_backend", ""),
        "casals_canister_id": canisters.get("casals_backend", ""),
        "casals_section": DEFAULT_CASALS_SECTION,
        "portal_url": _portal_url(descriptor),
        "provision_via_casals": True,
        "create_stand_baton": True,
        "baton_wasm_key": "orchestration-baton@1.3.0",
        "cycle_threshold_cycles": descriptor.threshold_cycles(),
    }
    # file_registry / marketplace_backend belong to the Realms product stack, which
    # `realms seed` mints after this phase has already run. They are absent from the
    # GaaS descriptor, so sending them here would send "" — and a re-run of this
    # phase would erase the pointers seed configured, leaving the installer to fall
    # back to whatever id its build has baked in.
    for key, name in (
        ("file_registry_id", "file_registry"),
        ("marketplace_id", "marketplace_backend"),
    ):
        value = (canisters.get(name) or "").strip()
        if value:
            payload[key] = value
    return json.dumps(payload)


def _resolve_monitor_service_url(descriptor: Descriptor) -> str | None:
    """Derive ``monitor_service_url`` from descriptor host + Casals backend id.

    ``services.monitor_url`` may be a bare origin (``https://casals.realmsgos.dev``)
    or a legacy slug path (``…/v1/realms-test``). When ``casals_backend`` is known,
    the path is always ``/v1/<casals_backend>``.
    """
    base = descriptor.services.monitor_url
    if not base:
        return None
    casals_backend = descriptor.canisters.get("casals_backend", "")
    if not casals_backend:
        return base.rstrip("/")
    parsed = urlparse(base.rstrip("/"))
    origin = urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))
    return f"{origin}/v1/{casals_backend}"


def _casals_settings_json(descriptor: Descriptor, deployer_principal: str) -> str:
    canisters = descriptor.canisters
    threshold = descriptor.threshold_cycles()
    file_registry_id = (
        canisters.get("casals_file_registry") or canisters.get("file_registry", "")
    )
    payload: dict = {
        "file_registry_canister_id": file_registry_id,
        "casals_frontend_canister_id": canisters.get("casals_frontend", ""),
        "realm_installer_canister_id": canisters.get("realm_installer", ""),
        "orchestra_name": casals_orchestra_name(descriptor),
        "default_min_cycles": threshold,
        "default_topup_cycles": threshold,
        "treasury_reserve": threshold,
        "create_cycles": threshold,
        "monitor_enabled": False,
    }
    file_registry_frontend_id = (
        canisters.get("casals_file_registry_frontend")
        or canisters.get("file_registry_frontend")
    )
    if file_registry_frontend_id:
        payload["file_registry_frontend_canister_id"] = file_registry_frontend_id
    if descriptor.services.monitor_url:
        payload["monitor_enabled"] = True
        payload["monitor_service_url"] = _resolve_monitor_service_url(descriptor)
    if descriptor.services.monitor_principal:
        payload["monitor_principal"] = descriptor.services.monitor_principal
    extras: list[str] = []
    # The installer finalizes every realm Casals provisions (config, codex,
    # extensions), and the realm backend only grants realm.admin to its IC
    # controllers, so it has to be a controller of each new realm canister.
    installer_id = (canisters.get("realm_installer") or "").strip()
    if installer_id:
        extras.append(installer_id)
    if _resolve_can_test_mode(descriptor) and deployer_principal:
        extras.append(deployer_principal)
    if extras:
        payload["extra_controller_principals"] = extras
    return json.dumps(payload)


def _parse_casals_settings_response(raw: str) -> dict:
    return json.loads(raw)


def _infra_canister_names() -> tuple[str, ...]:
    return (
        "realm_registry_backend",
        "realm_registry_frontend",
        "realm_installer",
    )


def _gos_binary_registry_id(descriptor: Descriptor) -> str:
    return (
        descriptor.canisters.get("casals_file_registry")
        or descriptor.canisters.get("file_registry", "")
    )


def _opt_text_init_arg(config_json: str) -> str:
    if not config_json:
        return "(null)"
    escaped = config_json.replace("\\", "\\\\").replace('"', '\\"')
    return f'(opt "{escaped}")'


@contextmanager
def _injected_file_registry_id(index_html: Path, canister_id: str) -> Iterator[None]:
    """Temporarily stamp the live file_registry ID into a frontend index.html."""
    if not canister_id or not index_html.is_file():
        yield
        return
    original = index_html.read_text(encoding="utf-8")
    snippet = (
        f"<script>window.__FILE_REGISTRY_CANISTER_ID__={json.dumps(canister_id)};</script>\n"
    )
    if "</head>" in original:
        updated = original.replace("</head>", snippet + "</head>", 1)
    else:
        updated = snippet + original
    index_html.write_text(updated, encoding="utf-8")
    try:
        yield
    finally:
        index_html.write_text(original, encoding="utf-8")


def phase_destroy_except_frontend(descriptor: Descriptor, ctx: DeployContext) -> None:
    if not ctx.destroy_except_frontend:
        return

    if not ctx.yes:
        confirmed = typer.confirm(
            "Destroy ALL GaaS platform canisters except DNS-mapped "
            f"realm_registry_frontend {descriptor.canisters.get('realm_registry_frontend', '?')}? "
            "Other GaaS frontends are destroyed. Cycles go to your cycles wallet; "
            "the portal DNS frontend ID is kept. This cannot be undone.",
            default=False,
        )
        if not confirmed:
            raise RuntimeError("destroy-except-realm-registry-frontend aborted")

    result = destroy_except_frontend(
        descriptor,
        network=ctx.network,
        identity=ctx.identity,
    )
    ctx.cycles_evacuated = int(result.get("cycles_evacuated") or 0)
    console.print(
        f"  Cycles reclaimed: {int(result['cycles_reclaimed']):,}; "
        f"evacuated to wallet: {ctx.cycles_evacuated:,}"
    )
    console.print(f"  Preserved frontends: {', '.join(result['preserved_frontend_ids'])}")
    _save_descriptor(descriptor, ctx)


def phase_validate(descriptor: Descriptor, ctx: DeployContext) -> None:
    errors = descriptor.validate_descriptor()
    if errors:
        raise RuntimeError("descriptor validation failed:\n  - " + "\n  - ".join(errors))

    # Runs in every deploy and resume, before anything resolves a canister by
    # name on --network ic, so the shared "ic" rows cannot still be pointing at
    # the environment that deployed last.
    try:
        realigned = align_ic_alias(_find_repo_root(ctx), descriptor)
    except PlatformError:
        realigned = {}
    for name, (old, new) in realigned.items():
        console.print(
            f"  canister_ids.json: ic alias for {name} "
            f"{old or '(absent)'} -> {new or '(absent)'}"
        )

    try:
        casals_root = require_casals_checkout(ctx.casals_src)
    except PlatformError as exc:
        raise RuntimeError(str(exc)) from exc
    console.print(f"  Casals checkout: {casals_root}")

    report = run_preflight(
        descriptor,
        ctx.identity,
        ctx.network,
        required_cycles=ctx.required_cycles or DEFAULT_CYCLES_PER_CANISTER * DEFAULT_CANISTER_COUNT,
    )
    ctx.preflight = report
    if not report.ok:
        failed = [c.detail for c in report.checks if not c.passed]
        raise RuntimeError("preflight failed:\n  - " + "\n  - ".join(failed))
    if ctx.network == "ic" and report.cycles_plan and report.cycles_plan.pending_topups:
        apply_headroom_topups(
            report.cycles_plan,
            ctx.network,
            identity=ctx.identity,
        )
    print_log_path()


def _fund_bootstrap_canisters(descriptor: Descriptor, ctx: DeployContext) -> None:
    """Raise the casals-minted canisters to their per-role cycle headroom.

    ``casals new`` mints the conductor, its frontend and its file registry with
    its own flat allowance, and it runs *after* the preflight top-up pass. On a
    from-scratch deploy nothing else funds them, so the conductor would enter
    ``deploy_sheet`` far below the treasury headroom the plan reserved for it
    and die with IC0504 mid-sheet. Topping up here closes that window; it is a
    no-op once each canister already holds its target.
    """
    if ctx.network != "ic":
        return
    for name in CASALS_BOOTSTRAP_NAMES:
        canister_id = (descriptor.canisters.get(name) or "").strip()
        if not canister_id:
            continue
        target = canister_headroom(name, descriptor)
        balance = dfx.canister_cycles_balance(
            canister_id, ctx.network, identity=ctx.identity
        )
        if balance is None or balance >= target:
            continue
        shortfall = target - balance
        console.print(f"  funding {name} ({canister_id}) +{shortfall:,}")
        dfx.top_up_canister(
            canister_id, shortfall, ctx.network, identity=ctx.identity
        )


def phase_create_canisters(descriptor: Descriptor, ctx: DeployContext) -> None:
    dfx.use_identity(ctx.identity)
    principal = dfx.get_principal(ctx.identity)

    result = run_casals_new(
        descriptor,
        network=ctx.network,
        identity=ctx.identity,
        casals_src=ctx.casals_src,
        yes=True,
        force_create=ctx.destroy_except_frontend,
    )
    for entry in result.get("healed_bootstrap_pins") or []:
        console.print(
            f"  {entry['name']}: healed stale bootstrap pin {entry['dead_id']}"
        )
    _save_descriptor(descriptor, ctx)
    mode = "adopt" if result.get("mode") == "upgrade" else "created"
    casals_ids = ", ".join(
        f"{name}={descriptor.canisters[name]}"
        for name in CASALS_BOOTSTRAP_NAMES
        if descriptor.canisters.get(name)
    )
    console.print(f"  casals new: {mode} {casals_ids}")
    _fund_bootstrap_canisters(descriptor, ctx)

    for name in KNOWN_CANISTER_NAMES:
        if name in CASALS_BOOTSTRAP_NAMES:
            continue
        existing_id = (descriptor.canisters.get(name) or "").strip()
        if existing_id and _try_adopt_pinned_canister(
            name, existing_id, descriptor, ctx, principal
        ):
            continue

        new_id = _create_and_register_canister(name, descriptor, ctx, principal)
        if existing_id and existing_id != new_id:
            console.print(
                f"  {name}: replaced dead pin {existing_id} with {new_id}"
            )

    _persist_and_guard_portal_frontends(descriptor, ctx, require_http=False)

    casals_id = (descriptor.canisters.get("casals_backend") or "").strip()
    if ctx.cycles_evacuated > 0 and casals_id:
        dfx.top_up_canister(
            casals_id,
            ctx.cycles_evacuated,
            ctx.network,
            identity=ctx.identity,
        )
        console.print(
            f"  casals_backend: restored {ctx.cycles_evacuated:,} evacuated cycles"
        )
        try:
            dfx.canister_call(
                casals_id,
                "get_cycles",
                "()",
                ctx.network,
                identity=ctx.identity,
                query=False,
            )
            console.print("  casals_backend: primed cycles snapshot (get_cycles)")
        except Exception as exc:
            console.print(
                f"[yellow]  warning: get_cycles after treasury restore failed: {exc}[/yellow]"
            )


def _platform_release(descriptor: Descriptor) -> tuple[str | None, str]:
    if descriptor.platform:
        return descriptor.platform.version, descriptor.platform.release_repo
    return None, DEFAULT_PLATFORM_RELEASE_REPO


def _find_repo_root(ctx: DeployContext) -> Path:
    """Locate the gos-as-a-service checkout: prefer cwd, then the descriptor's dir."""
    starts = [Path.cwd()]
    if ctx.descriptor_path is not None:
        starts.append(ctx.descriptor_path.parent)
    for start in starts:
        try:
            return find_gos_repo_root(start)
        except PlatformError:
            continue
    return find_gos_repo_root(starts[0])  # raise the canonical error


def _backend_install_mode(canister_id: str, ctx: DeployContext) -> str:
    # reinstall wipes canister state (heap + stable); use only when a clean
    # slate is intended — the pipeline re-seeds platform state afterwards,
    # but registry user data (realms, credits, slugs) is NOT restored.
    if ctx.reinstall_backends:
        return "reinstall"
    return dfx.detect_install_mode(canister_id, ctx.network, identity=ctx.identity)


def phase_install_backends(descriptor: Descriptor, ctx: DeployContext) -> None:
    platform_version, release_repo = _platform_release(descriptor)
    work = _work_dir(ctx)
    repo_root = None
    try:
        repo_root = _find_repo_root(ctx)
    except PlatformError:
        if platform_version is None:
            raise

    backends = {
        "realm_registry_backend": _registry_config_json(descriptor),
        "realm_installer": _installer_config_json(descriptor),
        "casals_backend": "",
    }

    for canister, init_json in backends.items():
        canister_id = descriptor.canisters.get(canister)
        if not canister_id:
            raise RuntimeError(f"missing canister ID for {canister}")

        if canister == "casals_backend":
            wasm = resolve_casals_wasm(
                descriptor.casals.version,
                descriptor.casals.release_repo,
                work / "casals",
                casals_src=ctx.casals_src,
                session=ctx.http,
            )
        else:
            wasm = resolve_platform_backend_wasm(
                canister,
                platform_version=platform_version,
                release_repo=release_repo,
                work_dir=work,
                repo_root=repo_root,
                session=ctx.http,
            )

        mode = _backend_install_mode(canister_id, ctx)
        init_arg = _opt_text_init_arg(init_json) if init_json else "(null)"
        console.print(f"  {canister}: {mode} ({wasm.name})")
        dfx.install_wasm(
            canister_id,
            str(wasm),
            ctx.network,
            mode,
            init_arg,
            identity=ctx.identity,
            yes=True,
        )

    casals_fr_id = descriptor.canisters.get("casals_file_registry")
    if casals_fr_id:
        # Casals' bundled file_registry (v0.3.x submodule) has only
        # finalize_chunked_file. Seed needs finalize_chunked_file_step for
        # multi-MB WASMs (one-shot finalize hits IC0522). Install this repo's
        # file_registry wasm onto the Casals-owned canister on every network.
        if repo_root is not None:
            wasm = resolve_platform_backend_wasm(
                "file_registry",
                platform_version=platform_version,
                release_repo=release_repo,
                work_dir=work,
                repo_root=repo_root,
                session=ctx.http,
            )
        else:
            wasm = resolve_casals_file_registry_wasm(
                descriptor.casals.version,
                descriptor.casals.release_repo,
                work / "casals",
                casals_src=ctx.casals_src,
                session=ctx.http,
            )
        mode = _backend_install_mode(casals_fr_id, ctx)
        console.print(f"  casals_file_registry: {mode} ({wasm.name})")
        dfx.install_wasm(
            casals_fr_id,
            str(wasm),
            ctx.network,
            mode,
            "(null)",
            identity=ctx.identity,
            yes=True,
        )


def _parse_registry_configure(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("("):
        raw = raw[1:-1].strip() if raw.endswith(")") else raw[1:].strip()
    if "Ok = " in raw:
        inner = raw.split("Ok = ", 1)[1].rstrip(" })").strip()
        if inner.startswith('"') and inner.endswith('"'):
            inner = inner[1:-1].replace('\\"', '"')
        return json.loads(inner)
    if raw.startswith("(variant { Err") or raw.startswith("variant { Err"):
        err = raw.split("Err = ", 1)[1].rstrip(" })").strip('"')
        raise RuntimeError(f"configure failed: {err}")
    return json.loads(raw)


def phase_configure_backends(descriptor: Descriptor, ctx: DeployContext) -> None:
    registry_id = descriptor.canisters.get("realm_registry_backend")
    installer_id = descriptor.canisters.get("realm_installer")
    if not registry_id or not installer_id:
        raise RuntimeError("registry/installer canister IDs required before configure")

    registry_json = _registry_config_json(descriptor)
    installer_json = _installer_config_json(descriptor)

    registry_raw = dfx.canister_call(
        registry_id,
        "configure",
        dfx.candid_text_arg(registry_json),
        ctx.network,
        identity=ctx.identity,
    )
    _parse_registry_configure(registry_raw)

    installer_raw = dfx.canister_call(
        installer_id,
        "configure",
        dfx.candid_text_arg(installer_json),
        ctx.network,
        identity=ctx.identity,
    )
    installer_result = json.loads(installer_raw)
    if not installer_result.get("success", True):
        raise RuntimeError(f"installer configure failed: {installer_result}")

    env_raw = dfx.canister_call(
        registry_id,
        "get_env_config",
        dfx.candid_text_arg(""),
        ctx.network,
        identity=ctx.identity,
        query=True,
    )
    env_cfg = json.loads(env_raw)
    if env_cfg.get("portal_url", "").rstrip("/") != _portal_url(descriptor):
        raise RuntimeError(
            f"registry get_env_config portal_url mismatch: {env_cfg.get('portal_url')!r}"
        )

    inst_cfg_raw = dfx.canister_call(
        installer_id,
        "get_installer_config",
        dfx.candid_text_arg(""),
        ctx.network,
        identity=ctx.identity,
        query=True,
    )
    inst_cfg = json.loads(inst_cfg_raw)
    expected_registry = descriptor.canisters.get("realm_registry_backend", "")
    if inst_cfg.get("registry_backend_id") != expected_registry:
        raise RuntimeError(
            "installer get_installer_config registry_backend_id mismatch: "
            f"{inst_cfg.get('registry_backend_id')!r} != {expected_registry!r}"
        )
    console.print("  registry + installer configure verified")

    runtime_json = _registry_runtime_config_json(descriptor, ctx.network)
    if runtime_json:
        runtime_raw = dfx.canister_call(
            registry_id,
            "set_canister_config_json",
            dfx.candid_text_arg(runtime_json),
            ctx.network,
            identity=ctx.identity,
        )
        runtime_result = json.loads(runtime_raw)
        if not runtime_result.get("success"):
            raise RuntimeError(
                f"registry set_canister_config_json failed: {runtime_result}"
            )
        flags_raw = dfx.canister_call(
            registry_id,
            "get_runtime_flags",
            dfx.candid_text_arg(""),
            ctx.network,
            identity=ctx.identity,
            query=True,
        )
        flags = json.loads(flags_raw)
        expected_casals = (descriptor.canisters.get("casals_frontend") or "").strip()
        if expected_casals and flags.get("casals_frontend_canister_id") != expected_casals:
            raise RuntimeError(
                "registry casals_frontend_canister_id mismatch after "
                f"set_canister_config_json: {flags!r}"
            )
        runtime_payload = json.loads(runtime_json)
        requested_flags = runtime_payload.get("test_flags") or {}
        if requested_flags:
            # Verify what the descriptor asked for, flag by flag. Asserting
            # test_mode and ii_bypass are true only held while test was the one
            # environment declaring test_flags; staging declares them all false.
            mismatched = {
                name: {
                    "requested": want,
                    "live": flags.get(_RUNTIME_FLAG_KEYS.get(name, name)),
                }
                for name, want in requested_flags.items()
                if flags.get(_RUNTIME_FLAG_KEYS.get(name, name)) != want
            }
            if mismatched:
                raise RuntimeError(
                    "registry runtime flags mismatch after set_canister_config_json: "
                    f"{mismatched!r} (live: {flags!r})"
                )
            console.print("  registry runtime test flags verified")
        if expected_casals:
            console.print("  registry casals_frontend verified")

    casals_id = descriptor.canisters.get("casals_backend")
    if not casals_id:
        raise RuntimeError("casals_backend canister ID required before set_settings")

    deployer = dfx.get_principal(ctx.identity)
    settings_json = _casals_settings_json(descriptor, deployer)
    settings_raw = dfx.canister_call(
        casals_id,
        "set_settings",
        dfx.candid_text_arg(settings_json),
        ctx.network,
        identity=ctx.identity,
    )
    settings_result = _parse_casals_settings_response(settings_raw)
    if not settings_result.get("ok", True):
        raise RuntimeError(f"casals set_settings failed: {settings_result}")
    console.print("  casals_backend set_settings verified")


def phase_seed_file_registry(descriptor: Descriptor, ctx: DeployContext) -> None:
    realms_registry_id = descriptor.canisters.get("file_registry")
    gos_registry_id = _gos_binary_registry_id(descriptor)
    registry_backend_id = descriptor.canisters.get("realm_registry_backend")
    if not gos_registry_id:
        raise RuntimeError("casals_file_registry or file_registry canister ID required")
    if not realms_registry_id:
        console.print(
            "[yellow]  skip Realms-GOS package catalog seeding: file_registry not in "
            "descriptor (realms-managed infrastructure)[/yellow]"
        )

    work = _work_dir(ctx)
    seeded_catalog_sources: set[tuple[str, str]] = set()
    for entry in descriptor.gos:
        resolved = resolve_deploy_version(
            entry.version, entry.release_repo, session=ctx.http
        )
        version = resolved.catalog_version
        backend_ns = f"wasm/{entry.artifacts.backend_wasm_key}/{version}"
        frontend_ns = f"frontend/{entry.artifacts.frontend_wasm_key}/{version}"
        backend_asset = entry.artifacts.resolved_backend_asset(entry.implementation)
        backend_path = backend_asset
        backend_hash = ""
        version_label = _gos_version_label(entry, session=ctx.http)

        # Pinned semver releases are immutable once seeded; ``main`` is rebuilt from
        # HEAD on every seed so the frontend bundle in the GOS binary registry stays current.
        needs_seed = True
        if resolved.source_build:
            console.print(
                f"  {entry.implementation}@{version_label}: re-seeding (main channel)"
            )
        elif namespace_published(gos_registry_id, backend_ns, ctx.network, identity=ctx.identity):
            hashes = fetch_namespace_hashes(
                gos_registry_id, backend_ns, ctx.network, identity=ctx.identity
            )
            if hashes:
                needs_seed = False
                backend_hash = hashes.get(backend_path, "")
                console.print(
                    f"  {entry.implementation}@{version_label}: already seeded ({backend_ns})"
                )

        clone_parent = work / "src-clone"
        existing_realms_checkout = clone_parent / entry.release_repo.replace("/", "_")

        if needs_seed:
            frontend_asset = entry.artifacts.resolved_frontend_asset(entry.implementation)
            artifact_dir = work / "gos" / entry.implementation / resolved.descriptor_version
            backend_file, frontend_file = resolve_gos_artifacts(
                implementation=entry.implementation,
                version=entry.version,
                release_repo=entry.release_repo,
                backend_asset=backend_asset,
                frontend_asset=frontend_asset,
                dest_dir=artifact_dir,
                clone_parent=clone_parent,
                session=ctx.http,
            )
            console.print(
                f"  seeding {entry.implementation}@{version_label} → {backend_ns}, {frontend_ns}"
            )
            seed_gos_entry(
                gos_registry_id,
                backend_ns,
                frontend_ns,
                backend_file,
                frontend_file,
                ctx.network,
                identity=ctx.identity,
            )
            backend_hash = sha256_file(backend_file)
            ctx.seed_artifacts.append(
                SeedArtifactSummary(
                    f"{backend_ns}/{backend_path}",
                    backend_hash,
                    "uploaded",
                )
            )
        elif backend_hash:
            ctx.seed_artifacts.append(
                SeedArtifactSummary(
                    f"{backend_ns}/{backend_path}",
                    backend_hash,
                    "already_seeded",
                )
            )

        if registry_backend_id:
            status = ensure_version_catalog_entry(
                registry_backend_id,
                gos_registry_id,
                version,
                backend_ns,
                frontend_ns,
                backend_path,
                backend_hash,
                ctx.network,
                identity=ctx.identity,
            )
            if status == "published":
                console.print(
                    f"  published {entry.implementation}@{version_label} to version catalog"
                )
            elif status == "skipped":
                console.print(
                    f"  {entry.implementation}@{version_label}: already in version catalog"
                )

        catalog_key = (entry.release_repo, resolved.descriptor_version)
        catalog_spec = entry.resolved_catalog()
        if realms_registry_id:
            if catalog_spec is None:
                console.print(
                    f"  skip codex/extension catalog seed for {entry.implementation} "
                    f"(no catalog declared)"
                )
            elif catalog_key not in seeded_catalog_sources:
                seed_codex_catalog(
                    realms_registry_id,
                    entry.release_repo,
                    entry.version,
                    work,
                    ctx.network,
                    identity=ctx.identity,
                    catalog=catalog_spec,
                    existing_realms_checkout=existing_realms_checkout
                    if existing_realms_checkout.is_dir()
                    else None,
                    session=ctx.http,
                    marketplace_id=(
                        descriptor.canisters.get("marketplace_backend") or ""
                    ).strip()
                    or None,
                )
                seeded_catalog_sources.add(catalog_key)
        elif catalog_spec is not None:
            console.print(
                f"  skip codex/extension catalog seed for {entry.implementation} "
                f"(file_registry absent)"
            )


def phase_seed_namespace_approvals(descriptor: Descriptor, ctx: DeployContext) -> None:
    registry_id = (descriptor.canisters.get("file_registry") or "").strip()
    marketplace_id = (descriptor.canisters.get("marketplace_backend") or "").strip()
    if not registry_id or not marketplace_id:
        console.print(
            "[yellow]  skip namespace approvals: file_registry and/or "
            "marketplace_backend not in descriptor[/yellow]"
        )
        return

    try:
        result = seed_namespace_approvals(
            registry_id,
            marketplace_id,
            ctx.network,
            ctx.identity,
            force=True,
        )
    except RuntimeError as exc:
        if ctx.network in ("local", "localhost"):
            console.print(f"[yellow]  warning: {exc}[/yellow]")
            return
        raise
    console.print(
        f"  namespace approvals: granted={result['granted']}, "
        f"approved={result['approved']}, skipped={result['skipped']}, "
        f"failed={result['failed']}"
    )


def _is_interactive(ctx: DeployContext) -> bool:
    return not ctx.yes and sys.stdin.isatty()


def _persist_and_guard_portal_frontends(
    descriptor: Descriptor,
    ctx: DeployContext,
    *,
    require_http: bool,
) -> None:
    """Rewrite inventory IDs and fail if a baked Casals frontend is dead."""
    casals_frontend_id = (descriptor.canisters.get("casals_frontend") or "").strip()
    try:
        assert_casals_frontend_live(
            casals_frontend_id,
            ctx.network,
            require_http=require_http,
        )
    except CanisterNotFoundError as exc:
        raise RuntimeError(str(exc)) from exc

    try:
        repo_root = _find_repo_root(ctx)
    except PlatformError:
        return
    persist_descriptor_canister_ids(repo_root, descriptor)
    console.print(
        f"  persisted canister IDs to {repo_root / 'canister_ids.json'} "
        f"({descriptor.name})"
    )


def phase_install_frontends(descriptor: Descriptor, ctx: DeployContext) -> None:
    platform_version, release_repo = _platform_release(descriptor)
    repo_root = _find_repo_root(ctx)
    gaas_env_path: Path | None = None
    casals_staging = repo_root / "casals_frontend_dist"

    try:
        _persist_and_guard_portal_frontends(descriptor, ctx, require_http=False)
        gaas_env_path = write_gaas_env(
            repo_root, descriptor, ctx.network, deployer_principal=dfx.get_principal(ctx.identity)
        )
        console.print(f"  wrote {gaas_env_path}")

        env = {
            **os.environ,
            "DFX_NETWORK": ctx.network,
            "GAAS_ENV": descriptor.name,
        }
        run_log = get_run_log()
        if run_log is None:
            raise RuntimeError("run log not initialized for frontend build phase")

        run_log.run_step(
            "npm install (repo root)",
            ["npm", "install", "--legacy-peer-deps"],
            cwd=repo_root,
            env=env,
        )
        run_log.run_step(
            "building realm_registry_frontend",
            ["npm", "run", "build", "--workspace=src/realm_registry_frontend"],
            cwd=repo_root,
            env=env,
        )

        work = _work_dir(ctx)

        for canister in ("realm_registry_frontend",):
            canister_id = descriptor.canisters.get(canister)
            if not canister_id:
                raise RuntimeError(f"missing canister ID for {canister}")

            dist = frontend_dist_dir(
                canister,
                platform_version=platform_version,
                release_repo=release_repo,
                work_dir=work,
                repo_root=repo_root,
                session=ctx.http,
            )
            if not dist.is_dir() or not any(dist.iterdir()):
                if platform_version:
                    archive = fetch_platform_frontend_archive(
                        canister,
                        platform_version,
                        release_repo,
                        work / "frontends" / canister,
                        session=ctx.http,
                    )
                    extract_dir = work / "frontends" / canister / "dist"
                    extract_dir.mkdir(parents=True, exist_ok=True)
                    with tarfile.open(archive, "r:gz") as tar:
                        tar.extractall(extract_dir)
                    dist = extract_dir
                else:
                    raise RuntimeError(f"frontend build produced empty dist for {canister}")

            dfx_name = DFX_CANISTER_NAMES[canister]
            if not dfx_name:
                raise RuntimeError(f"no dfx mapping for {canister}")
            backend_id = descriptor.canisters.get("realm_registry_backend") or ""
            if backend_id:
                inject_portal_ic_env_assets(dist, backend_id, canister_id)
                console.print(
                    f"  {canister}: injected ic_env cookie "
                    f"realm_registry_backend={backend_id}"
                )
            console.print(f"  {canister}: reinstall assets to {canister_id}")
            start = time.monotonic()
            dfx.deploy_assets_canister(
                dfx_name,
                canister_id,
                ctx.network,
                repo_root=repo_root,
                identity=ctx.identity,
                mode="reinstall",
                yes=True,
                extra_network_ids=dict(descriptor.canisters),
            )
            console.print(
                f"  {canister}: reinstall assets done "
                f"({format_duration(time.monotonic() - start)})"
            )

        casals_frontend_id = descriptor.canisters.get("casals_frontend")
        if not casals_frontend_id:
            raise RuntimeError("missing canister ID for casals_frontend")

        casals_dist = resolve_casals_frontend_dist(
            descriptor.casals.version,
            descriptor.casals.release_repo,
            work / "casals" / "frontend",
            casals_src=ctx.casals_src,
            session=ctx.http,
            conductor_canister_id=descriptor.canisters.get("casals_backend", ""),
            frontend_canister_id=casals_frontend_id,
            monitor_url=_resolve_monitor_service_url(descriptor) or "",
        )
        if casals_staging.exists():
            shutil.rmtree(casals_staging)
        shutil.copytree(casals_dist, casals_staging)
        console.print(f"  casals_frontend: reinstall assets to {casals_frontend_id}")
        start = time.monotonic()
        dfx.deploy_assets_canister(
            "casals_frontend",
            casals_frontend_id,
            ctx.network,
            repo_root=repo_root,
            identity=ctx.identity,
            mode="reinstall",
            yes=True,
        )
        console.print(
            f"  casals_frontend: reinstall assets done "
            f"({format_duration(time.monotonic() - start)})"
        )
        _persist_and_guard_portal_frontends(descriptor, ctx, require_http=True)

    finally:
        if gaas_env_path and not ctx.keep_env_file:
            remove_gaas_env(repo_root)
        if casals_staging.exists():
            shutil.rmtree(casals_staging)


def phase_domain_wiring(descriptor: Descriptor, ctx: DeployContext) -> None:
    if ctx.network == "local":
        console.print("  skipping domain wiring on local network")
        return

    frontend_id = descriptor.canisters.get("realm_registry_frontend")
    if not frontend_id:
        raise RuntimeError("realm_registry_frontend ID required for domain wiring")

    records = render_dns_records(descriptor.domain, frontend_id)
    table = Table(title=f"DNS records for {descriptor.domain}")
    table.add_column("Type")
    table.add_column("Host")
    table.add_column("Value")
    for record in records:
        table.add_row(record.record_type, record.host, record.value)
    console.print(table)

    if ctx.skip_dns_wait:
        console.print("  --skip-dns-wait: continuing without DNS poll")
    else:
        timeout = float(ctx.dns_timeout_min * 60)
        console.print(f"  waiting up to {ctx.dns_timeout_min} min for DNS propagation...")
        if not wait_for_dns(descriptor.domain, frontend_id, timeout=timeout):
            console.print(
                "[red]DNS records not detected in time.[/red] Configure the records above, "
                "register the domain at https://reg.icp0.io if needed, then re-run deploy."
            )
            _save_descriptor(descriptor, ctx)
            ctx.stopped = True
            raise RuntimeError("domain wiring timed out waiting for DNS propagation")

    ok, detail = attempt_domain_registration(descriptor.domain, timeout=120.0)
    if ok:
        console.print("  domain registration API: active")
    else:
        console.print(f"  [yellow]domain registration API (best-effort):[/yellow] {detail}")


def _http_get(url: str, timeout: float = 30.0) -> tuple[int, str]:
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read(1024).decode("utf-8", errors="replace")
            return response.status, body
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(256).decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", exc)
        return 0, str(reason)


def phase_smoke_checks(descriptor: Descriptor, ctx: DeployContext) -> None:
    seed_keys = [
        f"{entry.artifacts.backend_wasm_key}@{_gos_catalog_version(entry, session=ctx.http)}"
        for entry in descriptor.gos
    ]

    for name, canister_id in descriptor.canisters.items():
        status = dfx.canister_status(canister_id, ctx.network, identity=ctx.identity)
        if status.status != "running":
            raise RuntimeError(f"{name} ({canister_id}) status is {status.status}, expected running")

    registry_id = descriptor.canisters["realm_registry_backend"]
    env_raw = dfx.canister_call(
        registry_id,
        "get_env_config",
        dfx.candid_text_arg(""),
        ctx.network,
        identity=ctx.identity,
        query=True,
    )
    env_cfg = json.loads(env_raw)
    if descriptor.domain not in env_cfg.get("portal_url", ""):
        raise RuntimeError("registry portal_url smoke check failed")

    gos_registry_id = _gos_binary_registry_id(descriptor)
    for entry in descriptor.gos:
        version = _gos_catalog_version(entry, session=ctx.http)
        backend_ns = f"wasm/{entry.artifacts.backend_wasm_key}/{version}"
        hashes = fetch_namespace_hashes(
            gos_registry_id, backend_ns, ctx.network, identity=ctx.identity
        )
        if not hashes:
            raise RuntimeError(
                f"GOS binary registry missing seeded namespace {backend_ns}"
            )

    if ctx.network == "ic":
        frontend_id = descriptor.canisters.get("realm_registry_frontend") or ""
        if ctx.skip_dns_wait and frontend_id:
            portal_url = f"https://{frontend_id}.icp0.io/"
            well_known_url = f"https://{frontend_id}.icp0.io/.well-known/ic-domains"
            console.print(
                f"  --skip-dns-wait: HTTP smoke via {portal_url} "
                f"(not https://{descriptor.domain}/)"
            )
        else:
            portal_url = f"https://{descriptor.domain}/"
            well_known_url = f"https://{descriptor.domain}/.well-known/ic-domains"
        deadline = time.monotonic() + 90.0
        last_status = 0
        last_body = ""
        while time.monotonic() < deadline:
            last_status, last_body = _http_get(portal_url)
            if last_status == 200:
                break
            time.sleep(5)
        if last_status != 200:
            raise RuntimeError(
                f"{portal_url} returned {last_status}, expected 200 ({last_body[:200]})"
            )

        ic_status, ic_body = _http_get(well_known_url)
        if ic_status != 200 or descriptor.domain not in ic_body:
            raise RuntimeError("ic-domains well-known check failed")
    else:
        for frontend_name in ("realm_registry_frontend", "casals_frontend"):
            frontend_id = descriptor.canisters.get(frontend_name)
            if not frontend_id:
                raise RuntimeError(f"missing canister ID for {frontend_name}")
            local_url = f"http://{frontend_id}.localhost:4943/"
            status, _body = _http_get(local_url)
            if status != 200:
                console.print(
                    f"  [yellow]local {frontend_name} HTTP check returned "
                    f"{status} for {local_url}[/yellow]"
                )

    table = Table(title="Deployment summary")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("Environment", descriptor.name)
    table.add_row("Domain", descriptor.domain)
    table.add_row("Network", ctx.network)
    for name, canister_id in descriptor.canisters.items():
        table.add_row(name, canister_id)
    table.add_row("Seed keys", ", ".join(seed_keys))
    table.add_row(
        "Next steps",
        f"Open https://{descriptor.domain} (or re-run gaas if domain wiring was skipped)",
    )
    console.print(table)


def phase_seed_conductor(descriptor: Descriptor, ctx: DeployContext) -> None:
    casals_id = descriptor.canisters.get("casals_backend")
    gos_registry_id = _gos_binary_registry_id(descriptor)
    if not casals_id:
        raise RuntimeError("casals_backend ID required")
    if not gos_registry_id:
        raise RuntimeError("casals_file_registry or file_registry ID required")

    repo_root: Path | None = None
    try:
        repo_root = _find_repo_root(ctx)
    except PlatformError:
        pass

    try:
        seed_orchestration_templates(
            casals_id,
            gos_registry_id,
            ctx.network,
            identity=ctx.identity,
            casals_src=ctx.casals_src,
        )
    except RuntimeError as exc:
        if ctx.network in ("local", "localhost") and "missing orchestration template" in str(
            exc
        ):
            console.print(
                f"[yellow]  warning: {exc}; skipping remaining conductor seed[/yellow]"
            )
            return
        raise
    for entry in descriptor.gos:
        auth_result = authorize_gos_entry(
            casals_id,
            gos_registry_id,
            descriptor,
            entry,
            ctx.network,
            identity=ctx.identity,
            session=ctx.http,
            repo_root=repo_root,
        )
        ctx.seed_authorizations.extend(
            [
                SeedAuthSummary(
                    auth_result["backend_key"],
                    auth_result["backend_hash"],
                    auth_result["backend_status"],
                ),
                SeedAuthSummary(
                    auth_result["frontend_key"],
                    auth_result["frontend_hash"],
                    auth_result["frontend_status"],
                ),
            ]
        )
    ensure_sheet_and_deploy_multisig(
        casals_id, ctx.network, identity=ctx.identity
    )
    ensure_casals_co_controller(descriptor, ctx)
    platform_canisters: list[tuple[str, str, str]] = []
    for name, key, kind in (
        ("realm-registry-backend", "realm_registry_backend", "backend"),
        ("realm-installer", "realm_installer", "backend"),
        ("realm-registry-frontend", "realm_registry_frontend", "frontend"),
    ):
        canister_id = descriptor.canisters.get(key)
        if not canister_id:
            raise RuntimeError(f"{key} ID required for platform stand registration")
        platform_canisters.append((name, canister_id, kind))
    ensure_platform_stand(
        casals_id,
        platform_canisters,
        ctx.network,
        identity=ctx.identity,
    )
    installer_id = descriptor.canisters.get("realm_installer")
    if not installer_id:
        raise RuntimeError("realm_installer ID required")
    ensure_deployments_commander(
        casals_id, installer_id, ctx.network, identity=ctx.identity
    )
    if descriptor.casals.commanders:
        tree = get_tree(casals_id, ctx.network, identity=ctx.identity)
        sections = sorted(_section_names(tree) - {""})
        ensure_section_commanders(
            casals_id,
            sections,
            descriptor.casals.commanders,
            ctx.network,
            identity=ctx.identity,
        )


REFRESH_CANISTERS_BATCH_MAX = 3


def collect_tree_canisters(tree: dict[str, Any]) -> list[tuple[str, str]]:
    """Return (name, canister_id) for orchestra canisters with a principal."""
    found: list[tuple[str, str]] = []
    for sec in tree.get("sections") or []:
        for stand in sec.get("stands") or []:
            for canister in stand.get("canisters") or []:
                name = (canister.get("name") or "").strip()
                canister_id = (canister.get("canister_id") or "").strip()
                if name and canister_id:
                    found.append((name, canister_id))
    return found


def collect_tree_canister_names(tree: dict[str, Any]) -> list[str]:
    """Return orchestra canister names that have a non-empty principal."""
    return [name for name, _cid in collect_tree_canisters(tree)]


def _casals_co_controller_targets(
    descriptor: Descriptor, tree: dict[str, Any] | None = None
) -> list[tuple[str, str]]:
    """Canisters Casals must co-control before seed/prime (not Casals itself)."""
    casals_id = (descriptor.canisters.get("casals_backend") or "").strip()
    seen: set[str] = {casals_id} if casals_id else set()
    targets: list[tuple[str, str]] = []

    def _add(label: str, canister_id: str) -> None:
        cid = (canister_id or "").strip()
        if not cid or cid in seen:
            return
        seen.add(cid)
        targets.append((label, cid))

    for name in (
        *_infra_canister_names(),
        "casals_file_registry",
        # Casals reads canister_status on every canister in its tree to prime the
        # cycles snapshot, so it must control the file-registry UI too. Leaving it
        # out makes the snapshot report a permanent "not allowed to read the
        # canister status" error for that row.
        "casals_file_registry_frontend",
        "casals_frontend",
    ):
        _add(name, descriptor.canisters.get(name, ""))
    _add("multisig", descriptor.multisig.backend_id or "")
    if tree:
        _add("multisig", _find_canister_id(tree, "multisig"))
    return targets


def ensure_casals_co_controller(descriptor: Descriptor, ctx: DeployContext) -> None:
    """Add Casals as a co-controller; keep deployer and any other existing controllers.

    Seed and prime call Casals to grant permissions and read canister_status.
    Topology (last) still replaces the set. Fresh-minted canisters only have the
    deployer until this runs.
    """
    casals_id = (descriptor.canisters.get("casals_backend") or "").strip()
    if not casals_id:
        raise RuntimeError("casals_backend ID required")
    deployer = dfx.get_principal(ctx.identity)
    tree: dict[str, Any] | None = None
    try:
        tree = get_tree(casals_id, ctx.network, identity=ctx.identity)
    except Exception:
        tree = None

    for name, canister_id in _casals_co_controller_targets(descriptor, tree):
        try:
            status = dfx.canister_status(
                canister_id, ctx.network, identity=ctx.identity
            )
        except dfx.DfxError as exc:
            detail = str(exc)
            if "IC0301" in detail or "not found" in detail.lower():
                console.print(
                    f"  {name}: skip add Casals ({canister_id} not found)"
                )
                continue
            raise
        if casals_id in status.controllers:
            console.print(f"  {name}: Casals already controller")
            continue
        if deployer not in status.controllers:
            raise RuntimeError(
                f"{name} ({canister_id}): deployer is not a controller; "
                f"cannot add Casals as co-controller "
                f"(actual: {', '.join(status.controllers)})"
            )
        console.print(f"  {name}: add Casals as co-controller")
        dfx.add_canister_controller(
            canister_id, casals_id, ctx.network, identity=ctx.identity
        )


def chunk_canister_names(
    names: list[str], batch_max: int = REFRESH_CANISTERS_BATCH_MAX
) -> list[list[str]]:
    """Split canister names into batches of at most ``batch_max``."""
    return [names[i : i + batch_max] for i in range(0, len(names), batch_max)]


def _cycles_snapshot_by_name(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        (row.get("name") or "").strip(): row
        for row in (snapshot.get("canisters") or [])
        if (row.get("name") or "").strip()
    }


def _refresh_canisters_response_is_error(response: dict[str, Any]) -> bool:
    if response.get("ok") is False:
        return True
    if response.get("error"):
        return True
    return "canisters" not in response and "totals" not in response


def _canister_row_has_error(row: dict[str, Any] | None) -> bool:
    if row is None:
        return True
    return (row.get("status") or "").strip().lower() == "error"


def verify_cycles_snapshot_covers_tree(
    tree_names: list[str],
    snapshot: dict[str, Any],
    *,
    name_to_id: dict[str, str] | None = None,
) -> list[str]:
    """Ensure every tree canister appears in the snapshot.

    Matches by orchestra name, or by canister id when Casals stores the same
    principal under a different System-stand name. Returns names whose snapshot
    row has status ``error``. Raises ``RuntimeError`` when a tree canister is
    missing from the snapshot entirely.
    """
    by_name = _cycles_snapshot_by_name(snapshot)
    by_id = {
        (row.get("canister_id") or "").strip(): row
        for row in (snapshot.get("canisters") or [])
        if (row.get("canister_id") or "").strip()
    }
    ids = name_to_id or {}
    missing: list[str] = []
    errors: list[str] = []
    for name in tree_names:
        row = by_name.get(name)
        if row is None:
            cid = (ids.get(name) or "").strip()
            if cid:
                row = by_id.get(cid)
        if row is None:
            missing.append(name)
        elif _canister_row_has_error(row):
            errors.append(name)
    if missing:
        raise RuntimeError(
            "cycles snapshot missing conductor canisters after refresh: "
            + ", ".join(sorted(missing))
        )
    return errors


def _call_refresh_canisters(
    casals_id: str,
    names: list[str],
    network: str,
    *,
    identity: str | None,
) -> dict[str, Any]:
    payload = json.dumps({"canisters": names})
    raw = dfx.canister_call(
        casals_id,
        "refresh_canisters",
        dfx.candid_text_arg(payload),
        network,
        identity=identity,
    )
    return json.loads(raw)


def _refresh_canisters_batch_with_retries(
    casals_id: str,
    names: list[str],
    network: str,
    *,
    identity: str | None,
) -> list[str]:
    """Refresh canisters in batches; retry failures individually. Returns names still failing."""
    still_failing: list[str] = []
    for batch in chunk_canister_names(names):
        response = _call_refresh_canisters(casals_id, batch, network, identity=identity)
        if _refresh_canisters_response_is_error(response):
            retry_names = list(batch)
        else:
            by_name = _cycles_snapshot_by_name(response)
            retry_names = [name for name in batch if _canister_row_has_error(by_name.get(name))]
        for name in retry_names:
            individual = _call_refresh_canisters(
                casals_id, [name], network, identity=identity
            )
            if _refresh_canisters_response_is_error(individual):
                still_failing.append(name)
                continue
            row = _cycles_snapshot_by_name(individual).get(name)
            if _canister_row_has_error(row):
                still_failing.append(name)
    return still_failing


def phase_prime_cycles_snapshot(descriptor: Descriptor, ctx: DeployContext) -> None:
    casals_id = descriptor.canisters.get("casals_backend")
    if not casals_id:
        raise RuntimeError("casals_backend ID required")

    ensure_casals_co_controller(descriptor, ctx)

    tree = get_tree(casals_id, ctx.network, identity=ctx.identity)
    pairs = collect_tree_canisters(tree)
    names = [name for name, _cid in pairs]
    name_to_id = {name: cid for name, cid in pairs}
    if not names:
        console.print("  skip: no orchestra canisters in tree")
        return

    batches = chunk_canister_names(names)
    console.print(
        f"  priming cycles snapshot for {len(names)} canister(s) "
        f"in {len(batches)} batch(es)..."
    )
    for index, batch in enumerate(batches, start=1):
        console.print(f"  refresh batch {index}/{len(batches)}: {', '.join(batch)}")

    failed = _refresh_canisters_batch_with_retries(
        casals_id, names, ctx.network, identity=ctx.identity
    )
    if failed:
        console.print(
            "[yellow]  warning: refresh failed for "
            f"{', '.join(sorted(failed))}[/yellow]"
        )

    cached_raw = dfx.canister_call(
        casals_id,
        "get_cycles_cached",
        "()",
        ctx.network,
        identity=ctx.identity,
        query=True,
    )
    snapshot = json.loads(cached_raw)
    error_names = verify_cycles_snapshot_covers_tree(
        names, snapshot, name_to_id=name_to_id
    )
    for name in error_names:
        row = _cycles_snapshot_by_name(snapshot)[name]
        detail = row.get("error") or row.get("status") or "error"
        console.print(f"  [yellow]warning: {name} cycles status error: {detail}[/yellow]")

    totals = snapshot.get("totals") or {}
    ok_count = totals.get("ok", "?")
    err_count = totals.get("error", "?")
    console.print(
        f"  cycles snapshot verified: {len(names)} tree canister(s) "
        f"({ok_count} ok, {err_count} error in snapshot)"
    )


def phase_configure_multisig(descriptor: Descriptor, ctx: DeployContext) -> None:
    """Mandatory governance step: configure the orchestra multisig as N-of-M.

    Every ``gaas new`` deploy must finish with a configured multisig before
    controller topology hands IC control to it. Prefer ``multisig.signers`` from
    the descriptor (e.g. a single Internet Identity principal for 1-of-1). When
    empty, fall back to the deployer identity (legacy bootstrap only).

    Always reconciles ``multisig.backend_id`` with the live conductor tree so a
    stale descriptor ID cannot configure the wrong canister.
    """
    casals_id = descriptor.canisters.get("casals_backend")
    if not casals_id:
        raise RuntimeError("casals_backend ID required")

    deployer = dfx.get_principal(ctx.identity)
    descriptor_id = (descriptor.multisig.backend_id or "").strip()

    tree = get_tree(casals_id, ctx.network, identity=ctx.identity)
    tree_id = _find_canister_id(tree, "multisig")
    if not tree_id:
        if ctx.network in ("local", "localhost"):
            console.print(
                "[yellow]  skip: no multisig in conductor tree "
                "(orchestration templates unavailable)[/yellow]"
            )
            return
        raise RuntimeError(
            "multisig not found in conductor tree; run seed_conductor first"
        )

    if descriptor_id and descriptor_id != tree_id:
        console.print(
            f"  [yellow]warning: descriptor multisig.backend_id={descriptor_id} "
            f"differs from live tree {tree_id}; configuring the live canister[/yellow]"
        )
    multisig_id = tree_id
    if descriptor_id != multisig_id:
        descriptor.set_multisig_backend_id(multisig_id)
        _save_descriptor(descriptor, ctx)
    console.print(f"  multisig: {multisig_id}")

    signers = list(descriptor.multisig.signers or [])
    threshold = int(descriptor.multisig.threshold or 1)
    if not signers:
        signers = [deployer]
        console.print(
            "  [yellow]multisig.signers empty — using deployer as sole 1-of-1 signer. "
            "Set multisig.signers in the descriptor for production governance.[/yellow]"
        )
    if threshold > len(signers):
        raise RuntimeError(
            f"multisig.threshold ({threshold}) exceeds signer count ({len(signers)})"
        )

    console.print(
        f"  configuring {threshold}-of-{len(signers)}: {', '.join(signers)}"
    )
    configure_multisig_signers(
        multisig_id,
        signers,
        ctx.network,
        identity=ctx.identity,
        threshold=threshold,
    )


def _resolve_multisig_backend_id(
    descriptor: Descriptor, ctx: DeployContext, *, require: bool = True
) -> str | None:
    multisig_id = (descriptor.multisig.backend_id or "").strip()
    if not multisig_id:
        casals_id = (descriptor.canisters.get("casals_backend") or "").strip()
        if casals_id:
            tree = get_tree(casals_id, ctx.network, identity=ctx.identity)
            multisig_id = _find_canister_id(tree, "multisig") or ""
    if multisig_id:
        return multisig_id
    if ctx.network in ("local", "localhost"):
        return None
    if require:
        raise RuntimeError("multisig backend_id required for controller topology")
    return None


def _platform_infra_canister_names(descriptor: Descriptor) -> list[str]:
    names = list(_infra_canister_names())
    if descriptor.canisters.get("casals_file_registry"):
        names.append("casals_file_registry")
    return names


def platform_controller_expectations(
    descriptor: Descriptor,
    ctx: DeployContext,
    *,
    multisig_id: str | None = None,
) -> dict[str, list[str]]:
    casals_backend_id = (descriptor.canisters.get("casals_backend") or "").strip()
    if not casals_backend_id:
        raise RuntimeError("casals_backend ID required")
    multisig = (multisig_id or "").strip() or _resolve_multisig_backend_id(
        descriptor, ctx, require=ctx.network not in ("local", "localhost")
    )
    if not multisig and ctx.network not in ("local", "localhost"):
        raise RuntimeError("multisig backend_id required for controller topology")

    deployer = dfx.get_principal(ctx.identity)
    test_mode = _resolve_can_test_mode(descriptor)

    def with_deployer(base: list[str]) -> list[str]:
        if test_mode and deployer and deployer not in base:
            return base + [deployer]
        return list(base)

    expectations: dict[str, list[str]] = {}
    if multisig:
        for name in ("casals_backend", "casals_frontend"):
            if descriptor.canisters.get(name):
                expectations[name] = with_deployer([multisig])
    for name in _platform_infra_canister_names(descriptor):
        if descriptor.canisters.get(name):
            expectations[name] = with_deployer([casals_backend_id])
    return expectations


def _canister_id_for_expectation_key(descriptor: Descriptor, name: str) -> str:
    canister_id = (descriptor.canisters.get(name) or "").strip()
    if not canister_id:
        raise RuntimeError(f"missing canister ID for {name}")
    return canister_id


def verify_platform_controller_topology(
    descriptor: Descriptor, ctx: DeployContext
) -> None:
    if ctx.network in ("local", "localhost"):
        console.print(
            "[yellow]  skip: no platform controller verification on local[/yellow]"
        )
        return

    multisig_id = _resolve_multisig_backend_id(descriptor, ctx, require=True)
    expectations = platform_controller_expectations(
        descriptor, ctx, multisig_id=multisig_id
    )
    errors: list[str] = []
    casals_backend_id = (descriptor.canisters.get("casals_backend") or "").strip()

    for name, expected in expectations.items():
        canister_id = _canister_id_for_expectation_key(descriptor, name)
        try:
            status = dfx.canister_status(
                canister_id, ctx.network, identity=ctx.identity
            )
        except dfx.DfxError as exc:
            errors.append(f"{name} ({canister_id}): cannot read status ({exc})")
            continue
        actual = set(status.controllers)
        expected_set = set(expected)
        if actual != expected_set:
            errors.append(
                f"{name} ({canister_id}): actual={sorted(actual)} "
                f"expected={sorted(expected_set)}"
            )
        elif (
            name in _platform_infra_canister_names(descriptor)
            and casals_backend_id not in actual
        ):
            errors.append(
                f"{name} ({canister_id}): missing Casals backend controller "
                f"{casals_backend_id}"
            )

    if errors:
        raise RuntimeError(
            "platform controller verification failed:\n  - "
            + "\n  - ".join(errors)
        )
    console.print(
        f"  verified controller topology on {len(expectations)} platform canister(s)"
    )


def apply_platform_controller_topology(
    descriptor: Descriptor, ctx: DeployContext
) -> None:
    if ctx.network in ("local", "localhost"):
        console.print(
            "[yellow]  skip: no multisig backend_id "
            "(orchestration templates unavailable)[/yellow]"
        )
        return

    multisig_id = _resolve_multisig_backend_id(descriptor, ctx, require=True)
    expectations = platform_controller_expectations(
        descriptor, ctx, multisig_id=multisig_id
    )
    test_mode = _resolve_can_test_mode(descriptor)
    changed = 0

    for name, target in expectations.items():
        canister_id = _canister_id_for_expectation_key(descriptor, name)
        status = dfx.canister_status(
            canister_id, ctx.network, identity=ctx.identity
        )
        target_set = set(target)
        if set(status.controllers) == target_set:
            console.print(f"  {name}: controllers already correct")
            continue
        console.print(f"  {name}: controllers -> {', '.join(target)}")
        dfx.update_canister_settings(
            canister_id, target, ctx.network, identity=ctx.identity
        )
        status = dfx.canister_status(
            canister_id, ctx.network, identity=ctx.identity
        )
        if set(status.controllers) != target_set:
            raise RuntimeError(
                f"{name} ({canister_id}) controller apply failed: "
                f"{status.controllers} != {target}"
            )
        changed += 1

    if changed:
        console.print(f"  updated controllers on {changed} canister(s)")
    else:
        console.print("  controller topology already applied (no changes)")

    if test_mode:
        console.print(
            "  test mode: deployer retained as co-controller on platform canisters"
        )
    else:
        console.print(
            "  production: gaas deployer no longer controls platform canisters"
        )


def phase_controller_topology(descriptor: Descriptor, ctx: DeployContext) -> None:
    apply_platform_controller_topology(descriptor, ctx)


def phase_verify_controller_topology(descriptor: Descriptor, ctx: DeployContext) -> None:
    verify_platform_controller_topology(descriptor, ctx)


def repair_platform_controllers(descriptor: Descriptor, ctx: DeployContext) -> None:
    """Apply then verify platform controller topology (standalone repair)."""
    apply_platform_controller_topology(descriptor, ctx)
    verify_platform_controller_topology(descriptor, ctx)


def phase_grant_commanders(descriptor: Descriptor, ctx: DeployContext) -> None:
    casals_id = descriptor.canisters.get("casals_backend")
    if not casals_id:
        console.print("  skip: no casals_backend canister ID")
        return

    tree = get_tree(casals_id, ctx.network, identity=ctx.identity)
    sections = sorted(_section_names(tree) - {""})
    if not sections:
        console.print("  skip: no orchestra sections found")
        return

    # descriptor.casals.commanders is the durable record of who should hold
    # commander rights, so grant it on every run instead of only when an
    # operator is present. set_commander adds-or-updates, so this is idempotent.
    declared = [p for p in descriptor.casals.commanders if p]
    if declared:
        ensure_section_commanders(
            casals_id,
            sections,
            declared,
            ctx.network,
            identity=ctx.identity,
        )

    if not _is_interactive(ctx):
        if not declared:
            console.print(
                "  skip: no commanders declared in descriptor (casals.commanders) "
                "and not on a TTY to prompt for one"
            )
        return

    casals_frontend_id = descriptor.canisters.get("casals_frontend")
    if casals_frontend_id:
        ui_url = f"https://{casals_frontend_id}.icp0.io"
        console.print(f"  Open {ui_url} in your browser.")
        console.print(
            "  Log in with Internet Identity. If an access-denied modal appears, "
            "copy the principal it shows."
        )

    while True:
        principal = console.input(
            "[yellow]Principal to grant commander rights on all orchestra sections "
            "(empty to finish): [/yellow]"
        ).strip()
        if not principal:
            break
        if not CANISTER_ID_RE.match(principal):
            console.print(
                f"[yellow]Warning: {principal!r} does not look like an IC principal; "
                "try again.[/yellow]"
            )
            continue
        try:
            ensure_section_commanders(
                casals_id,
                sections,
                [principal],
                ctx.network,
                identity=ctx.identity,
            )
        except Exception as exc:
            console.print(f"[red]Error granting commander: {exc}[/red]")
            continue
        if principal not in descriptor.casals.commanders:
            descriptor.casals.commanders.append(principal)
            _save_descriptor(descriptor, ctx)


def validate_seed_prerequisites(descriptor: Descriptor) -> None:
    errors = descriptor.validate_descriptor()
    if errors:
        raise RuntimeError("descriptor validation failed:\n  - " + "\n  - ".join(errors))

    missing = [
        name for name in SEED_PHASE_CANISTERS if not descriptor.canisters.get(name)
    ]
    if missing:
        raise RuntimeError(
            "seed requires canister IDs in descriptor: " + ", ".join(missing)
        )
    if not _gos_binary_registry_id(descriptor):
        raise RuntimeError(
            "seed requires a GOS binary registry: set casals_file_registry "
            "(preferred) or file_registry in the descriptor"
        )


def phase_seed_validate(descriptor: Descriptor, ctx: DeployContext) -> None:
    validate_seed_prerequisites(descriptor)
    try:
        casals_root = require_casals_checkout(ctx.casals_src)
    except PlatformError as exc:
        raise RuntimeError(str(exc)) from exc
    console.print(f"  Casals checkout: {casals_root}")


SEED_PHASES: list[tuple[str, str, PhaseFunc]] = [
    ("seed_validate", "Validating descriptor for seed", phase_seed_validate),
    ("seed_file_registry", "Seeding file registry", phase_seed_file_registry),
    (
        "seed_namespace_approvals",
        "Seeding file-registry namespace approvals",
        phase_seed_namespace_approvals,
    ),
    ("seed_conductor", "Seeding conductor orchestra", phase_seed_conductor),
]


def print_seed_summary(ctx: DeployContext) -> None:
    table = Table(title="Seed summary")
    table.add_column("Kind")
    table.add_column("Key")
    table.add_column("Hash")
    table.add_column("Status")
    for artifact in ctx.seed_artifacts:
        table.add_row("artifact", artifact.key, artifact.wasm_hash[:16] + "…", artifact.status)
    for auth in ctx.seed_authorizations:
        table.add_row("authorization", auth.key, auth.wasm_hash[:16] + "…", auth.status)
    console.print(table)


def format_phase_catalog(phases: list[tuple[str, str, PhaseFunc]]) -> str:
    lines = ["valid --from-phase values:"]
    for index, (phase_id, title, _func) in enumerate(phases, start=1):
        lines.append(f"  {index:>2}  {phase_id}  {title}")
    return "\n".join(lines)


def parse_from_phase(
    from_phase: str | None,
    phases: list[tuple[str, str, PhaseFunc]],
) -> int:
    """Return a 0-based start index. ``from_phase`` is a 1-based index or phase id."""
    if from_phase is None:
        return 0
    raw = str(from_phase).strip()
    if not raw:
        return 0
    ids = [phase_id for phase_id, _title, _func in phases]
    if raw.isdigit():
        number = int(raw)
        if number < 1 or number > len(phases):
            raise RuntimeError(
                f"--from-phase {raw} is out of range 1..{len(phases)}\n"
                + format_phase_catalog(phases)
            )
        return number - 1
    key = raw.replace("-", "_")
    if key in ids:
        return ids.index(key)
    raise RuntimeError(
        f"unknown --from-phase {raw!r}\n" + format_phase_catalog(phases)
    )


def phase_ids_to_run(
    phases: list[tuple[str, str, PhaseFunc]],
    from_phase: str | None,
    *,
    validate_phase_id: str,
    mandatory_phase_ids: tuple[str, ...] = (),
) -> set[str]:
    start = parse_from_phase(from_phase, phases)
    run_ids = {phase_id for phase_id, _title, _func in phases[start:]}
    for mandatory_id in (validate_phase_id, *mandatory_phase_ids):
        mandatory_index = next(
            (i for i, (phase_id, _, _) in enumerate(phases) if phase_id == mandatory_id),
            None,
        )
        if mandatory_index is not None and start > mandatory_index:
            run_ids.add(mandatory_id)
    return run_ids


def _bound_phase_func(func: PhaseFunc) -> PhaseFunc:
    """Honor test patches of ``gaas.phases.<func.__name__>`` after PHASES was built."""
    current = globals().get(func.__name__)
    if callable(current):
        return current  # type: ignore[return-value]
    return func


def _run_phase_table(
    descriptor: Descriptor,
    ctx: DeployContext,
    phases: list[tuple[str, str, PhaseFunc]],
    *,
    validate_phase_id: str,
    mandatory_phase_ids: tuple[str, ...] = (),
    on_phase_start: Callable[[int, str, str], None] | None = None,
) -> DeployContext:
    total = len(phases)
    start = parse_from_phase(ctx.from_phase, phases)
    run_ids = phase_ids_to_run(
        phases,
        ctx.from_phase,
        validate_phase_id=validate_phase_id,
        mandatory_phase_ids=mandatory_phase_ids,
    )
    if start > 0:
        skipped = [
            phase_id
            for phase_id, _title, _func in phases[:start]
            if phase_id not in run_ids
        ]
        if skipped:
            console.print(
                f"  resuming from {phases[start][0]} "
                f"(skipped: {', '.join(skipped)})"
            )
        if ctx.destroy_except_frontend and "destroy_except_frontend" in skipped:
            console.print(
                "[yellow]  --from-phase skips destroy-except even though "
                "--destroy-except-realm-registry-frontend was set[/yellow]"
            )

    for index, (phase_id, title, func) in enumerate(phases, start=1):
        if phase_id not in run_ids:
            continue
        ctx.current_phase = phase_id
        if on_phase_start:
            on_phase_start(index, phase_id, title)
        else:
            console.print(f"[{index}/{total}] {title}...")
        _bound_phase_func(func)(descriptor, ctx)
        ctx.completed_phases.append(phase_id)
        ctx.current_phase = None
        if ctx.stopped:
            break
    return ctx


def run_seed_phases(
    descriptor: Descriptor,
    ctx: DeployContext,
    *,
    on_phase_start: Callable[[int, str, str], None] | None = None,
) -> DeployContext:
    _run_phase_table(
        descriptor,
        ctx,
        SEED_PHASES,
        validate_phase_id="seed_validate",
        on_phase_start=on_phase_start,
    )
    print_seed_summary(ctx)
    return ctx


PHASES: list[tuple[str, str, PhaseFunc]] = [
    (
        "destroy_except_frontend",
        "Destroying canisters except realm registry frontend",
        phase_destroy_except_frontend,
    ),
    ("validate", "Validating descriptor, identity, cycles", phase_validate),
    ("create_canisters", "Creating canisters", phase_create_canisters),
    ("install_backends", "Installing backends", phase_install_backends),
    ("configure_backends", "Configuring backends", phase_configure_backends),
    ("seed_file_registry", "Seeding file registry", phase_seed_file_registry),
    (
        "seed_namespace_approvals",
        "Seeding file-registry namespace approvals",
        phase_seed_namespace_approvals,
    ),
    ("seed_conductor", "Seeding conductor orchestra", phase_seed_conductor),
    (
        "prime_cycles_snapshot",
        "Priming conductor cycles snapshot",
        phase_prime_cycles_snapshot,
    ),
    ("configure_multisig", "Configuring multisig signers", phase_configure_multisig),
    (
        "controller_topology",
        "Applying controller topology",
        phase_controller_topology,
    ),
    ("install_frontends", "Building + installing frontends", phase_install_frontends),
    ("domain_wiring", "Domain wiring", phase_domain_wiring),
    ("smoke_checks", "Smoke checks", phase_smoke_checks),
    ("grant_commanders", "Granting Casals commanders", phase_grant_commanders),
    (
        "verify_controller_topology",
        "Verifying platform controller topology",
        phase_verify_controller_topology,
    ),
]


def run_phases(
    descriptor: Descriptor,
    ctx: DeployContext,
    *,
    on_phase_start: Callable[[int, str, str], None] | None = None,
) -> DeployContext:
    return _run_phase_table(
        descriptor,
        ctx,
        PHASES,
        validate_phase_id="validate",
        mandatory_phase_ids=("controller_topology", "verify_controller_topology"),
        on_phase_start=on_phase_start,
    )
