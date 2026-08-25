"""Deployment phase runner."""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator, Protocol

import requests
import typer
from rich.console import Console
from rich.table import Table

from gaas import dfx
from gaas.artifacts import fetch_release_assets
from gaas.cycles_plan import create_with_cycles
from gaas.descriptor import CANISTER_ID_RE, Descriptor
from gaas.destroy import destroy_except_frontend
from gaas.dns import render_dns_records, wait_for_dns
from gaas.domain_reg import attempt_domain_registration, custom_domain_already_live
from gaas.codex_seed import seed_codex_catalog
from gaas.conductor_seed import (
    authorize_gos_entry,
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
    ADOPT_ONLY_CANISTER_NAMES,
    DEFAULT_CANISTER_COUNT,
    DEFAULT_CASALS_SECTION,
    DEFAULT_CYCLES_PER_CANISTER,
    DEFAULT_PLATFORM_RELEASE_REPO,
    DFX_CANISTER_NAMES,
    DNS_LOCKED_CANISTER_NAMES,
    KNOWN_CANISTER_NAMES,
    WALLET_RESERVE_CYCLES,
)
from gaas.marketplace import (
    build_marketplace_backend_wasm,
    build_marketplace_frontend,
    configure_marketplace_backend,
)
from gaas.namespace_approval_seed import seed_namespace_approvals
from gaas.platform import (
    PlatformError,
    fetch_platform_frontend_archive,
    find_gos_repo_root,
    frontend_dist_dir,
    resolve_casals_file_registry_wasm,
    resolve_casals_frontend_dist,
    resolve_casals_src,
    resolve_casals_wasm,
    resolve_platform_backend_wasm,
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
    for key, value in descriptor.flags.items():
        if key not in ("open_mode", "can_test_mode"):
            payload[key] = value
    return json.dumps(payload)


def _registry_runtime_config_json(descriptor: Descriptor, network: str) -> str | None:
    """Runtime test flags for can_test_mode portal auth (set_canister_config_json).

    Returns None when can_test_mode is false so production registries stay secure.
  """
    if not _resolve_can_test_mode(descriptor):
        return None
    payload: dict = {
        "test_flags": {
            "test_mode": True,
            "ii_bypass": True,
        }
    }
    # Registry runtime_flags rejects test flags when network=ic; omit on mainnet.
    if network != "ic":
        payload["network"] = network
    return json.dumps(payload)


def _installer_config_json(descriptor: Descriptor) -> str:
    canisters = descriptor.canisters
    payload = {
        "registry_backend_id": canisters.get("realm_registry_backend", ""),
        "file_registry_id": canisters.get("file_registry", ""),
        "marketplace_id": canisters.get("marketplace_backend", ""),
        "casals_canister_id": canisters.get("casals_backend", ""),
        "casals_section": DEFAULT_CASALS_SECTION,
        "portal_url": _portal_url(descriptor),
        "provision_via_casals": True,
        "create_stand_baton": True,
        "baton_wasm_key": "orchestration-baton@1.3.0",
        "cycle_threshold_cycles": descriptor.threshold_cycles(),
    }
    return json.dumps(payload)


# IC create_canister charges a 500B fee from the initial balance. Casals
# create_cycles is threshold (floored at 2T) plus that fee so leftover meets
# default_min_cycles.
_CASALS_CREATE_CYCLES_MIN = 2_000_000_000_000


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
        "default_min_cycles": threshold,
        "default_topup_cycles": threshold,
        "treasury_reserve": threshold,
        "create_cycles": create_with_cycles(max(threshold, _CASALS_CREATE_CYCLES_MIN)),
        "monitor_enabled": False,
    }
    file_registry_frontend_id = canisters.get("file_registry_frontend")
    if file_registry_frontend_id:
        payload["file_registry_frontend_canister_id"] = file_registry_frontend_id
    if descriptor.services.monitor_url:
        payload["monitor_enabled"] = True
        payload["monitor_service_url"] = descriptor.services.monitor_url
    if descriptor.services.monitor_principal:
        payload["monitor_principal"] = descriptor.services.monitor_principal
    if _resolve_can_test_mode(descriptor):
        payload["extra_controller_principals"] = [deployer_principal]
    return json.dumps(payload)


def _parse_casals_settings_response(raw: str) -> dict:
    return json.loads(raw)


def _infra_canister_names() -> tuple[str, ...]:
    return (
        "realm_registry_backend",
        "realm_registry_frontend",
        "realm_installer",
        "file_registry",
        "file_registry_frontend",
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
            "Destroy ALL platform canisters except DNS-mapped frontends "
            f"(realm_registry_frontend {descriptor.canisters.get('realm_registry_frontend', '?')}"
            + (
                f", marketplace_frontend {descriptor.canisters.get('marketplace_frontend', '?')}"
                if (descriptor.canisters.get("marketplace_frontend") or "").strip()
                else ""
            )
            + ")? "
            "Other frontends are destroyed. Cycles go to your cycles wallet; "
            "DNS-mapped frontend IDs are kept. This cannot be undone.",
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


def _drop_missing_canister_ids(descriptor: Descriptor, ctx: DeployContext) -> None:
    """Forget descriptor IDs that are not on-chain, except DNS-locked frontends."""
    dropped = False
    for name in list(descriptor.canisters):
        canister_id = descriptor.canisters[name]
        if dfx.canister_exists(canister_id, ctx.network, identity=ctx.identity):
            continue
        if name in DNS_LOCKED_CANISTER_NAMES:
            raise RuntimeError(
                f"DNS-mapped canister {name} ({canister_id}) does not exist on-chain; "
                "refusing to mint a replacement ID"
            )
        console.print(f"  {name}: dropping missing ID {canister_id}")
        descriptor.canisters.pop(name, None)
        dfx_name = DFX_CANISTER_NAMES.get(name) or name
        dfx.drop_local_canister_id(dfx_name, ctx.network)
        dropped = True
    if dropped:
        _save_descriptor(descriptor, ctx)


def _fmt_tc(amount: int) -> str:
    return f"{amount / 1_000_000_000_000:.2f}T"


def _canister_cycle_shortfalls(
    descriptor: Descriptor, ctx: DeployContext
) -> list[tuple[str, str, int]]:
    if ctx.network != "ic":
        return []
    threshold = descriptor.threshold_cycles()
    out: list[tuple[str, str, int]] = []
    for name in KNOWN_CANISTER_NAMES:
        if name == "casals_backend":
            continue
        canister_id = (descriptor.canisters.get(name) or "").strip()
        if not canister_id:
            continue
        try:
            balance = dfx.canister_cycles_balance(
                canister_id, ctx.network, identity=ctx.identity
            )
        except dfx.DfxError:
            continue
        if balance is None or balance >= threshold:
            continue
        out.append((name, canister_id, threshold - balance))
    return out


def _add_controller_if_missing(
    canister_id: str, principal: str, ctx: DeployContext
) -> None:
    status = dfx.canister_status(canister_id, ctx.network, identity=ctx.identity)
    if principal in status.controllers:
        return
    dfx.update_canister_settings(
        canister_id,
        list(status.controllers) + [principal],
        ctx.network,
        identity=ctx.identity,
    )


def _casals_top_up(
    casals_id: str, canister_id: str, amount: int, ctx: DeployContext
) -> None:
    raw = dfx.canister_call(
        casals_id,
        "top_up",
        dfx.candid_text_arg(
            json.dumps({"canister_id": canister_id, "amount": amount})
        ),
        ctx.network,
        identity=ctx.identity,
        query=False,
    )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Casals top_up returned non-JSON: {raw!r}") from exc
    if isinstance(payload, dict) and payload.get("ok") is False:
        raise RuntimeError(payload.get("error") or payload.get("message") or raw)


def _wallet_top_up_shortfalls(
    shortfalls: list[tuple[str, str, int]], ctx: DeployContext
) -> None:
    for name, canister_id, amount in shortfalls:
        console.print(f"  {name}: wallet top-up +{_fmt_tc(amount)}")
        dfx.top_up_canister(
            canister_id, amount, ctx.network, identity=ctx.identity
        )


def _restore_casals_treasury(descriptor: Descriptor, ctx: DeployContext) -> None:
    casals_id = (descriptor.canisters.get("casals_backend") or "").strip()
    if not casals_id:
        return
    shortfalls = _canister_cycle_shortfalls(descriptor, ctx)
    keep_for_floors = sum(amount for _name, _cid, amount in shortfalls)
    amount = ctx.cycles_evacuated
    if amount <= 0:
        try:
            wallet_bal = dfx.wallet_cycles_balance(ctx.network, identity=ctx.identity)
        except dfx.DfxError as exc:
            console.print(
                f"[yellow]  warning: wallet balance unavailable: {exc}[/yellow]"
            )
            wallet_bal = 0
        amount = max(0, wallet_bal - WALLET_RESERVE_CYCLES - keep_for_floors)
        if amount > 0:
            console.print(
                f"  casals_backend: restoring wallet surplus {amount:,} cycles "
                f"(keeping {WALLET_RESERVE_CYCLES:,} in wallet"
                + (
                    f" + {_fmt_tc(keep_for_floors)} for cycle floors"
                    if keep_for_floors
                    else ""
                )
                + ")"
            )
    else:
        amount = max(0, amount - keep_for_floors)
        if keep_for_floors:
            console.print(
                f"  holding {_fmt_tc(keep_for_floors)} in wallet to top skinny canisters"
            )
    if amount > 0:
        dfx.send_wallet_cycles(
            casals_id,
            amount,
            ctx.network,
            identity=ctx.identity,
        )
        console.print(f"  casals_backend: restored {amount:,} cycles from wallet")
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
    if shortfalls:
        _wallet_top_up_shortfalls(shortfalls, ctx)


def phase_validate(descriptor: Descriptor, ctx: DeployContext) -> None:
    errors = descriptor.validate_descriptor()
    if errors:
        raise RuntimeError("descriptor validation failed:\n  - " + "\n  - ".join(errors))

    _drop_missing_canister_ids(descriptor, ctx)

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
    print_log_path()


def phase_create_canisters(descriptor: Descriptor, ctx: DeployContext) -> None:
    dfx.use_identity(ctx.identity)
    principal = dfx.get_principal(ctx.identity)
    cycles = (
        create_with_cycles(descriptor.threshold_cycles())
        if ctx.network == "ic"
        else None
    )

    for name in KNOWN_CANISTER_NAMES:
        existing_id = descriptor.canisters.get(name)
        if existing_id:
            if not dfx.canister_exists(
                existing_id, ctx.network, identity=ctx.identity
            ):
                if name in DNS_LOCKED_CANISTER_NAMES:
                    raise RuntimeError(
                        f"DNS-mapped canister {name} ({existing_id}) does not exist "
                        "on-chain; refusing to mint a replacement ID"
                    )
                console.print(f"  {name}: dropping missing ID {existing_id}")
                descriptor.canisters.pop(name, None)
                dfx_name = DFX_CANISTER_NAMES.get(name) or name
                dfx.drop_local_canister_id(dfx_name, ctx.network)
                _save_descriptor(descriptor, ctx)
                existing_id = None
            else:
                status = dfx.canister_status(
                    existing_id, ctx.network, identity=ctx.identity
                )
                controllers = status.controllers
                if controllers and principal not in controllers:
                    raise RuntimeError(
                        f"identity {principal!r} is not a controller of adopted canister "
                        f"{name} ({existing_id}); controllers: {', '.join(controllers)}"
                    )
                console.print(f"  {name}: adopt {existing_id} ({status.status})")
                continue

        if name in ADOPT_ONLY_CANISTER_NAMES:
            continue

        dfx_name = DFX_CANISTER_NAMES.get(name)
        if dfx_name:
            canister_id = dfx.create_canister(
                dfx_name,
                ctx.network,
                identity=ctx.identity,
                with_cycles=cycles,
            )
        else:
            canister_id = dfx.create_canister_via_ledger(
                ctx.network,
                identity=ctx.identity,
                controller=principal,
            )
            if cycles and ctx.network == "ic":
                dfx.top_up_canister(
                    canister_id,
                    cycles,
                    ctx.network,
                    identity=ctx.identity,
                )

        descriptor.set_canister_id(name, canister_id)
        _save_descriptor(descriptor, ctx)
        console.print(f"  {name}: created {canister_id}")

    _restore_casals_treasury(descriptor, ctx)


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


def _asset_install_mode(canister_id: str, ctx: DeployContext) -> str:
    """Empty asset canisters must use install; reinstall requires existing wasm."""
    if dfx.detect_install_mode(canister_id, ctx.network, identity=ctx.identity) == "install":
        return "install"
    return "reinstall"


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

    file_registry_id = descriptor.canisters.get("file_registry")
    if file_registry_id:
        wasm = resolve_platform_backend_wasm(
            "file_registry",
            platform_version=platform_version,
            release_repo=release_repo,
            work_dir=work,
            repo_root=repo_root,
            session=ctx.http,
        )
        mode = _backend_install_mode(file_registry_id, ctx)
        console.print(f"  file_registry: {mode} ({wasm.name})")
        dfx.install_wasm(
            file_registry_id,
            str(wasm),
            ctx.network,
            mode,
            "(null)",
            identity=ctx.identity,
            yes=True,
        )

    marketplace_id = descriptor.canisters.get("marketplace_backend")
    if marketplace_id:
        if repo_root is None:
            try:
                repo_root = _find_repo_root(ctx)
            except PlatformError:
                repo_root = work
        wasm = build_marketplace_backend_wasm(
            descriptor,
            gos_repo_root=repo_root,
            work_dir=work,
        )
        mode = _backend_install_mode(marketplace_id, ctx)
        console.print(f"  marketplace_backend: {mode} ({wasm.name})")
        dfx.install_wasm(
            marketplace_id,
            str(wasm),
            ctx.network,
            mode,
            "(null)",
            identity=ctx.identity,
            yes=True,
        )
        configure_marketplace_backend(
            descriptor,
            network=ctx.network,
            identity=ctx.identity,
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
        if not flags.get("test_mode") or not flags.get("test_mode_ii_bypass"):
            raise RuntimeError(
                "registry runtime flags mismatch after set_canister_config_json: "
                f"{flags!r}"
            )
        console.print("  registry runtime test flags verified")

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

    result = seed_namespace_approvals(
        registry_id,
        marketplace_id,
        ctx.network,
        ctx.identity,
    )
    console.print(
        f"  namespace approvals: granted={result['granted']}, "
        f"approved={result['approved']}, skipped={result['skipped']}, "
        f"failed={result['failed']}"
    )


def _is_interactive(ctx: DeployContext) -> bool:
    return not ctx.yes and sys.stdin.isatty()


_EMPTY_VARIANT_PAYLOAD = re.compile(r"(\w+)\s*:\s*(?=;|\})")


def _rewrite_empty_candid_variants(text: str) -> str:
    """Basilisk emits unit variants as ``Tag : ;``, which candid rejects."""
    return _EMPTY_VARIANT_PAYLOAD.sub(r"\1", text)


def _ensure_casals_backend_did(repo_root: Path, casals_src: Path | None) -> None:
    """Copy gitignored ``casals_backend.did`` so ``dfx generate casals_backend`` works."""
    dest = repo_root / "casals_backend.did"
    if not dest.is_file():
        src_root = resolve_casals_src(casals_src)
        if src_root is None:
            return
        src = src_root / "casals_backend.did"
        if not src.is_file():
            return
        shutil.copy2(src, dest)
        console.print(f"  copied {src} -> {dest}")
    text = dest.read_text(encoding="utf-8")
    fixed = _rewrite_empty_candid_variants(text)
    if fixed != text:
        dest.write_text(fixed, encoding="utf-8")
        console.print(f"  sanitized empty variant payloads in {dest}")


def phase_install_frontends(descriptor: Descriptor, ctx: DeployContext) -> None:
    platform_version, release_repo = _platform_release(descriptor)
    repo_root = _find_repo_root(ctx)
    gaas_env_path: Path | None = None
    casals_staging = repo_root / "casals_frontend_dist"

    try:
        gaas_env_path = write_gaas_env(
            repo_root, descriptor, ctx.network, deployer_principal=dfx.get_principal(ctx.identity)
        )
        console.print(f"  wrote {gaas_env_path}")
        _ensure_casals_backend_did(repo_root, ctx.casals_src)

        env = {**os.environ, "DFX_NETWORK": ctx.network}
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
            console.print(f"  {canister}: reinstall assets to {canister_id}")
            start = time.monotonic()
            dfx.deploy_assets_canister(
                dfx_name,
                canister_id,
                ctx.network,
                repo_root=repo_root,
                identity=ctx.identity,
                mode=_asset_install_mode(canister_id, ctx),
                yes=True,
            )
            console.print(
                f"  {canister}: reinstall assets done "
                f"({format_duration(time.monotonic() - start)})"
            )

        file_registry_frontend_id = descriptor.canisters.get("file_registry_frontend")
        if file_registry_frontend_id:
            canister = "file_registry_frontend"
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
            file_registry_id = descriptor.canisters.get("file_registry") or ""
            console.print(f"  {canister}: reinstall assets to {file_registry_frontend_id}")
            start = time.monotonic()
            with _injected_file_registry_id(dist / "index.html", file_registry_id):
                dfx.deploy_assets_canister(
                    dfx_name,
                    file_registry_frontend_id,
                    ctx.network,
                    repo_root=repo_root,
                    identity=ctx.identity,
                    mode=_asset_install_mode(file_registry_frontend_id, ctx),
                    yes=True,
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
            monitor_url=descriptor.services.monitor_url or "",
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
            mode=_asset_install_mode(casals_frontend_id, ctx),
            yes=True,
        )
        console.print(
            f"  casals_frontend: reinstall assets done "
            f"({format_duration(time.monotonic() - start)})"
        )

        marketplace_frontend_id = descriptor.canisters.get("marketplace_frontend")
        if marketplace_frontend_id:
            marketplace_backend_id = descriptor.canisters.get("marketplace_backend") or ""
            file_registry_id = descriptor.canisters.get("file_registry") or ""
            if not marketplace_backend_id:
                raise RuntimeError(
                    "marketplace_backend ID required to rebuild marketplace_frontend"
                )
            console.print(
                f"  marketplace_frontend: build + reinstall assets to {marketplace_frontend_id}"
            )
            start = time.monotonic()
            build_marketplace_frontend(
                descriptor,
                gos_repo_root=repo_root,
                work_dir=work,
                marketplace_backend_id=marketplace_backend_id,
                file_registry_id=file_registry_id,
            )
            dfx.deploy_assets_canister(
                "marketplace_frontend",
                marketplace_frontend_id,
                ctx.network,
                repo_root=repo_root,
                identity=ctx.identity,
                mode=_asset_install_mode(marketplace_frontend_id, ctx),
                yes=True,
            )
            console.print(
                f"  marketplace_frontend: reinstall assets done "
                f"({format_duration(time.monotonic() - start)})"
            )
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

    if custom_domain_already_live(descriptor.domain):
        console.print(
            f"  {descriptor.domain} already serving; "
            "skipping DNS wait and IC registration"
        )
        return

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
        deadline = time.monotonic() + 90.0
        last_status = 0
        while time.monotonic() < deadline:
            status, body = _http_get(f"https://{descriptor.domain}/")
            last_status = status
            if status == 200:
                break
            time.sleep(5)
        if last_status != 200:
            raise RuntimeError(f"https://{descriptor.domain}/ returned {last_status}, expected 200")

        ic_status, ic_body = _http_get(f"https://{descriptor.domain}/.well-known/ic-domains")
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

    seed_orchestration_templates(
        casals_id,
        gos_registry_id,
        ctx.network,
        identity=ctx.identity,
        casals_src=ctx.casals_src,
    )
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
    platform_canisters: list[tuple[str, str, str]] = []
    for name, key, kind in (
        ("realm-registry-backend", "realm_registry_backend", "backend"),
        ("realm-registry-frontend", "realm_registry_frontend", "frontend"),
        ("realm-installer", "realm_installer", "backend"),
        ("file-registry", "file_registry", "backend"),
        ("file-registry-frontend", "file_registry_frontend", "frontend"),
        ("casals-file-registry", "casals_file_registry", "backend"),
        ("casals-frontend", "casals_frontend", "frontend"),
        ("marketplace-backend", "marketplace_backend", "backend"),
        ("marketplace-frontend", "marketplace_frontend", "frontend"),
    ):
        canister_id = descriptor.canisters.get(key)
        if not canister_id:
            # Adopt-only / optional canisters are registered only when present.
            if key in (
                "casals_file_registry",
                "file_registry",
                "file_registry_frontend",
                "casals_frontend",
                "marketplace_backend",
                "marketplace_frontend",
            ):
                continue
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


def collect_tree_canister_names(tree: dict[str, Any]) -> list[str]:
    """Return orchestra canister names that have a non-empty principal."""
    names: list[str] = []
    for sec in tree.get("sections") or []:
        for stand in sec.get("stands") or []:
            for canister in stand.get("canisters") or []:
                name = (canister.get("name") or "").strip()
                canister_id = (canister.get("canister_id") or "").strip()
                if name and canister_id:
                    names.append(name)
    return names


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
    tree_names: list[str], snapshot: dict[str, Any]
) -> list[str]:
    """Ensure every tree canister appears in the snapshot.

    Returns names whose snapshot row has status ``error``. Raises ``RuntimeError``
    when a tree canister is missing from the snapshot entirely.
    """
    by_name = _cycles_snapshot_by_name(snapshot)
    missing = [name for name in tree_names if name not in by_name]
    if missing:
        raise RuntimeError(
            "cycles snapshot missing conductor canisters after refresh: "
            + ", ".join(sorted(missing))
        )
    return [name for name in tree_names if _canister_row_has_error(by_name.get(name))]


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

    tree = get_tree(casals_id, ctx.network, identity=ctx.identity)
    names = collect_tree_canister_names(tree)
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
    try:
        error_names = verify_cycles_snapshot_covers_tree(names, snapshot)
    except RuntimeError as exc:
        missing = [
            name
            for name in names
            if name not in _cycles_snapshot_by_name(snapshot)
        ]
        # Topology has not made Casals a controller yet, so refresh often
        # cannot read status and those rows never land in the cache.
        if missing and set(missing) <= set(failed):
            console.print(f"[yellow]  warning: {exc}[/yellow]")
            error_names = []
        else:
            raise
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


def phase_controller_topology(descriptor: Descriptor, ctx: DeployContext) -> None:
    multisig_id = (descriptor.multisig.backend_id or "").strip()
    if not multisig_id:
        casals_id = descriptor.canisters.get("casals_backend", "")
        if casals_id:
            tree = get_tree(casals_id, ctx.network, identity=ctx.identity)
            multisig_id = _find_canister_id(tree, "multisig")
    if not multisig_id:
        raise RuntimeError("multisig backend_id required for controller topology")

    deployer = dfx.get_principal(ctx.identity)
    test_mode = _resolve_can_test_mode(descriptor)
    casals_backend_id = descriptor.canisters.get("casals_backend", "")

    def controllers(base: list[str]) -> list[str]:
        if test_mode and deployer not in base:
            return base + [deployer]
        return base

    casals_pair = ("casals_backend", "casals_frontend")
    for name in casals_pair:
        canister_id = descriptor.canisters.get(name)
        if not canister_id:
            raise RuntimeError(f"missing canister ID for {name}")
        target = controllers([multisig_id])
        console.print(f"  {name}: controllers -> {', '.join(target)}")
        dfx.update_canister_settings(
            canister_id, target, ctx.network, identity=ctx.identity
        )
        status = dfx.canister_status(canister_id, ctx.network, identity=ctx.identity)
        if set(status.controllers) != set(target):
            raise RuntimeError(
                f"{name} controller verify failed: {status.controllers} != {target}"
            )

    infra_names = list(_infra_canister_names())
    if descriptor.canisters.get("casals_file_registry"):
        infra_names.append("casals_file_registry")
    if descriptor.canisters.get("marketplace_backend"):
        infra_names.append("marketplace_backend")
    if descriptor.canisters.get("marketplace_frontend"):
        infra_names.append("marketplace_frontend")
    for name in infra_names:
        canister_id = descriptor.canisters.get(name)
        if not canister_id:
            raise RuntimeError(f"missing canister ID for {name}")
        target = controllers([casals_backend_id])
        console.print(f"  {name}: controllers -> {', '.join(target)}")
        dfx.update_canister_settings(
            canister_id, target, ctx.network, identity=ctx.identity
        )
        status = dfx.canister_status(canister_id, ctx.network, identity=ctx.identity)
        if set(status.controllers) != set(target):
            raise RuntimeError(
                f"{name} controller verify failed: {status.controllers} != {target}"
            )

    if test_mode:
        console.print("  test mode: deployer retained as co-controller on platform canisters")
    else:
        console.print("  production: gaas deployer no longer controls platform canisters")


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

    listed = [p for p in descriptor.casals.commanders if p]
    if listed:
        console.print(
            f"  applying {len(listed)} commander(s) from descriptor"
        )
        ensure_section_commanders(
            casals_id,
            sections,
            listed,
            ctx.network,
            identity=ctx.identity,
        )

    if not _is_interactive(ctx):
        console.print(
            "  skip extra interactive commander grants "
            "(descriptor commanders already applied)"
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


def phase_ensure_cycle_floors(descriptor: Descriptor, ctx: DeployContext) -> None:
    """Top every platform canister to ``cycles.threshold_tc`` before topology.

    Prefers the Casals treasury (where destroy-except evacuates cycles). Wallet
    top-up is the fallback. Runs while the deployer still controls canisters.
    """
    if ctx.network != "ic":
        console.print("  skipping cycle floors on local network")
        return
    threshold = descriptor.threshold_cycles()
    shortfalls = _canister_cycle_shortfalls(descriptor, ctx)
    if not shortfalls:
        console.print(f"  all adopted canisters already at {_fmt_tc(threshold)}")
        return
    casals_id = (descriptor.canisters.get("casals_backend") or "").strip()
    remaining: list[tuple[str, str, int]] = []
    for name, canister_id, amount in shortfalls:
        if not casals_id:
            remaining.append((name, canister_id, amount))
            continue
        try:
            _add_controller_if_missing(canister_id, casals_id, ctx)
            console.print(f"  {name}: Casals treasury top-up +{_fmt_tc(amount)}")
            _casals_top_up(casals_id, canister_id, amount, ctx)
        except Exception as exc:
            console.print(
                f"[yellow]  {name}: Casals top-up failed ({exc}); trying wallet[/yellow]"
            )
            remaining.append((name, canister_id, amount))
    if remaining:
        _wallet_top_up_shortfalls(remaining, ctx)
    still_short = _canister_cycle_shortfalls(descriptor, ctx)
    if still_short:
        detail = ", ".join(
            f"{name} needs +{_fmt_tc(amount)}" for name, _cid, amount in still_short
        )
        raise RuntimeError(f"cycle floor not met after auto-top: {detail}")


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


def run_seed_phases(
    descriptor: Descriptor,
    ctx: DeployContext,
    *,
    on_phase_start: Callable[[int, str, str], None] | None = None,
) -> DeployContext:
    phases: list[tuple[str, str, PhaseFunc]] = [
        ("seed_validate", "Validating descriptor for seed", phase_seed_validate),
        ("seed_file_registry", "Seeding file registry", phase_seed_file_registry),
        (
            "seed_namespace_approvals",
            "Seeding file-registry namespace approvals",
            phase_seed_namespace_approvals,
        ),
        ("seed_conductor", "Seeding conductor orchestra", phase_seed_conductor),
    ]
    total = len(phases)
    for index, (phase_id, title, func) in enumerate(phases, start=1):
        if on_phase_start:
            on_phase_start(index, phase_id, title)
        else:
            console.print(f"[{index}/{total}] {title}...")
        func(descriptor, ctx)
        ctx.completed_phases.append(phase_id)
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
    ("install_frontends", "Building + installing frontends", phase_install_frontends),
    ("domain_wiring", "Domain wiring", phase_domain_wiring),
    ("smoke_checks", "Smoke checks", phase_smoke_checks),
    ("grant_commanders", "Granting Casals commanders", phase_grant_commanders),
    ("ensure_cycle_floors", "Ensuring cycle floors", phase_ensure_cycle_floors),
    ("controller_topology", "Applying controller topology", phase_controller_topology),
]


def run_phases(
    descriptor: Descriptor,
    ctx: DeployContext,
    *,
    on_phase_start: Callable[[int, str, str], None] | None = None,
) -> DeployContext:
    total = len(PHASES)
    for index, (phase_id, title, func) in enumerate(PHASES, start=1):
        if on_phase_start:
            on_phase_start(index, phase_id, title)
        else:
            console.print(f"[{index}/{total}] {title}...")
        func(descriptor, ctx)
        ctx.completed_phases.append(phase_id)
        if ctx.stopped:
            break
    return ctx
