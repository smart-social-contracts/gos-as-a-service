"""Deployment phase runner."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol

import requests
from rich.console import Console
from rich.table import Table

from gaas import dfx
from gaas.artifacts import fetch_release_assets
from gaas.descriptor import CANISTER_ID_RE, Descriptor
from gaas.dns import render_dns_records, wait_for_dns
from gaas.domain_reg import attempt_domain_registration
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
    approve_marketplace_namespaces,
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
    KNOWN_CANISTER_NAMES,
)
from gaas.platform import (
    PlatformError,
    fetch_platform_frontend_archive,
    find_gos_repo_root,
    frontend_dist_dir,
    resolve_casals_frontend_dist,
    resolve_casals_wasm,
    resolve_platform_backend_wasm,
)
from gaas.preflight import PreflightReport, run_preflight
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
    "file_registry",
    "realm_registry_backend",
    "casals_backend",
    "realm_registry_frontend",
    "realm_installer",
    "file_registry_frontend",
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


def _resolve_open_mode(descriptor: Descriptor) -> bool:
    """Precedence: explicit flags.open_mode > deprecated services.open_mode >
    derived (open when no billing_url is configured)."""
    if "open_mode" in descriptor.flags:
        return descriptor.flags["open_mode"]
    if descriptor.services.open_mode is not None:
        return descriptor.services.open_mode
    return descriptor.services.billing_url is None


def _registry_config_json(descriptor: Descriptor) -> str:
    payload: dict = {
        "portal_url": _portal_url(descriptor),
        "open_mode": _resolve_open_mode(descriptor),
    }
    if descriptor.services.billing_url:
        payload["billing_url"] = descriptor.services.billing_url
    installer_id = descriptor.canisters.get("realm_installer", "")
    if installer_id:
        payload["installer_id"] = installer_id
    for key, value in descriptor.flags.items():
        if key != "open_mode":
            payload[key] = value
    return json.dumps(payload)


def _installer_config_json(descriptor: Descriptor) -> str:
    canisters = descriptor.canisters
    payload = {
        "registry_backend_id": canisters.get("realm_registry_backend", ""),
        "file_registry_id": canisters.get("file_registry", ""),
        "casals_canister_id": canisters.get("casals_backend", ""),
        "casals_section": DEFAULT_CASALS_SECTION,
        "portal_url": _portal_url(descriptor),
        "provision_via_casals": True,
        "create_stand_baton": True,
    }
    return json.dumps(payload)


def _casals_settings_json(descriptor: Descriptor, deployer_principal: str) -> str:
    canisters = descriptor.canisters
    payload: dict = {
        "file_registry_canister_id": canisters.get("file_registry", ""),
        "file_registry_frontend_canister_id": canisters.get("file_registry_frontend", ""),
        "casals_frontend_canister_id": canisters.get("casals_frontend", ""),
        "realm_installer_canister_id": canisters.get("realm_installer", ""),
        "default_min_cycles": 500_000_000_000,
        "default_topup_cycles": 1_000_000_000_000,
        "treasury_reserve": 1_000_000_000_000,
        "create_cycles": 2_000_000_000_000,
        "monitor_enabled": False,
    }
    if descriptor.services.monitor_url:
        payload["monitor_enabled"] = True
        payload["monitor_service_url"] = descriptor.services.monitor_url
    if _resolve_open_mode(descriptor):
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


def _opt_text_init_arg(config_json: str) -> str:
    if not config_json:
        return "(null)"
    escaped = config_json.replace("\\", "\\\\").replace('"', '\\"')
    return f'(opt "{escaped}")'


def phase_validate(descriptor: Descriptor, ctx: DeployContext) -> None:
    errors = descriptor.validate_descriptor()
    if errors:
        raise RuntimeError("descriptor validation failed:\n  - " + "\n  - ".join(errors))

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


def phase_create_canisters(descriptor: Descriptor, ctx: DeployContext) -> None:
    dfx.use_identity(ctx.identity)
    principal = dfx.get_principal(ctx.identity)
    cycles = DEFAULT_CYCLES_PER_CANISTER if ctx.network == "ic" else None

    for name in KNOWN_CANISTER_NAMES:
        existing_id = descriptor.canisters.get(name)
        if existing_id:
            status = dfx.canister_status(existing_id, ctx.network, identity=ctx.identity)
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
        "file_registry": "",
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

        mode = dfx.detect_install_mode(canister_id, ctx.network, identity=ctx.identity)
        init_arg = _opt_text_init_arg(init_json) if init_json else "(null)"
        console.print(f"  {canister}: {mode} ({wasm.name})")
        dfx.install_wasm(
            canister_id,
            str(wasm),
            ctx.network,
            mode,
            init_arg,
            identity=ctx.identity,
            yes=ctx.yes,
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
    registry_id = descriptor.canisters.get("file_registry")
    registry_backend_id = descriptor.canisters.get("realm_registry_backend")
    if not registry_id:
        raise RuntimeError("file_registry canister ID required")

    work = _work_dir(ctx)
    seeded_catalog_sources: set[tuple[str, str]] = set()
    marketplace_namespaces: list[str] = []
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

        needs_seed = True
        if namespace_published(registry_id, backend_ns, ctx.network, identity=ctx.identity):
            hashes = fetch_namespace_hashes(
                registry_id, backend_ns, ctx.network, identity=ctx.identity
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
                registry_id,
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
                registry_id,
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
        if catalog_spec is None:
            console.print(
                f"  skip codex/extension catalog seed for {entry.implementation} "
                f"(no catalog declared)"
            )
        elif catalog_key not in seeded_catalog_sources:
            seeded = seed_codex_catalog(
                registry_id,
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
            marketplace_namespaces.extend(seeded)
            seeded_catalog_sources.add(catalog_key)

    if marketplace_namespaces:
        console.print(
            f"  approving {len(set(marketplace_namespaces))} codex/extension namespace(s)"
        )
        approve_marketplace_namespaces(
            registry_id,
            marketplace_namespaces,
            ctx.network,
            identity=ctx.identity,
        )


def _is_interactive(ctx: DeployContext) -> bool:
    return not ctx.yes and sys.stdin.isatty()


def _confirm_reinstall(ctx: DeployContext) -> None:
    if ctx.yes or ctx.network != "ic":
        return
    answer = console.input(
        "[yellow]Reinstall asset canisters on ic? This wipes frontend state. [y/N]: [/yellow]"
    )
    if answer.strip().lower() not in {"y", "yes"}:
        raise RuntimeError("frontend reinstall cancelled (pass --yes to skip prompt)")


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

        env = {**os.environ, "DFX_NETWORK": ctx.network}
        console.print("  npm install (repo root)...")
        subprocess.run(
            ["npm", "install", "--legacy-peer-deps"],
            cwd=repo_root,
            env=env,
            check=True,
        )
        console.print("  building realm_registry_frontend...")
        subprocess.run(
            ["npm", "run", "build", "--workspace=src/realm_registry_frontend"],
            cwd=repo_root,
            env=env,
            check=True,
        )
        console.print("  building file_registry_frontend...")
        subprocess.run(
            ["npm", "run", "build", "--workspace=src/file_registry_frontend"],
            cwd=repo_root,
            env=env,
            check=True,
        )

        _confirm_reinstall(ctx)
        work = _work_dir(ctx)

        for canister in ("realm_registry_frontend", "file_registry_frontend"):
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
            dfx.deploy_assets_canister(
                dfx_name,
                canister_id,
                ctx.network,
                repo_root=repo_root,
                identity=ctx.identity,
                mode="reinstall",
                yes=True,
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
        )
        if casals_staging.exists():
            shutil.rmtree(casals_staging)
        shutil.copytree(casals_dist, casals_staging)
        console.print(f"  casals_frontend: reinstall assets to {casals_frontend_id}")
        dfx.deploy_assets_canister(
            "casals_frontend",
            casals_frontend_id,
            ctx.network,
            repo_root=repo_root,
            identity=ctx.identity,
            mode="reinstall",
            yes=True,
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

    file_registry_id = descriptor.canisters["file_registry"]
    for entry in descriptor.gos:
        version = _gos_catalog_version(entry, session=ctx.http)
        backend_ns = f"wasm/{entry.artifacts.backend_wasm_key}/{version}"
        hashes = fetch_namespace_hashes(
            file_registry_id, backend_ns, ctx.network, identity=ctx.identity
        )
        if not hashes:
            raise RuntimeError(f"file_registry missing seeded namespace {backend_ns}")

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
    registry_id = descriptor.canisters.get("file_registry")
    if not casals_id or not registry_id:
        raise RuntimeError("casals_backend and file_registry IDs required")

    repo_root: Path | None = None
    try:
        repo_root = _find_repo_root(ctx)
    except PlatformError:
        pass

    seed_orchestration_templates(
        casals_id,
        registry_id,
        ctx.network,
        identity=ctx.identity,
        casals_src=ctx.casals_src,
    )
    for entry in descriptor.gos:
        auth_result = authorize_gos_entry(
            casals_id,
            registry_id,
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


def phase_configure_multisig(descriptor: Descriptor, ctx: DeployContext) -> None:
    casals_id = descriptor.canisters.get("casals_backend")
    if not casals_id:
        raise RuntimeError("casals_backend ID required")

    deployer = dfx.get_principal(ctx.identity)
    multisig_id = (descriptor.multisig.backend_id or "").strip()

    if multisig_id:
        console.print(f"  multisig: adopt {multisig_id}")
    else:
        tree = get_tree(casals_id, ctx.network, identity=ctx.identity)
        multisig_id = _find_canister_id(tree, "multisig")
        if not multisig_id:
            raise RuntimeError(
                "multisig not found in conductor tree; run seed_conductor first"
            )
        descriptor.set_multisig_backend_id(multisig_id)
        _save_descriptor(descriptor, ctx)
        console.print(f"  multisig: created {multisig_id}")

    configure_multisig_signers(
        multisig_id,
        [deployer],
        ctx.network,
        identity=ctx.identity,
        threshold=1,
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
    test_mode = _resolve_open_mode(descriptor)
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

    for name in _infra_canister_names():
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

    if not _is_interactive(ctx):
        console.print(
            "  skip: grant Casals commanders interactively "
            "(re-run without --yes on a TTY)"
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


def phase_seed_validate(descriptor: Descriptor, ctx: DeployContext) -> None:
    validate_seed_prerequisites(descriptor)


SEED_PHASES: list[tuple[str, str, PhaseFunc]] = [
    ("seed_validate", "Validating descriptor for seed", phase_seed_validate),
    ("seed_file_registry", "Seeding file registry", phase_seed_file_registry),
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
    ("validate", "Validating descriptor, identity, cycles", phase_validate),
    ("create_canisters", "Creating canisters", phase_create_canisters),
    ("install_backends", "Installing backends", phase_install_backends),
    ("configure_backends", "Configuring backends", phase_configure_backends),
    ("seed_file_registry", "Seeding file registry", phase_seed_file_registry),
    ("seed_conductor", "Seeding conductor orchestra", phase_seed_conductor),
    ("configure_multisig", "Configuring multisig signers", phase_configure_multisig),
    ("install_frontends", "Building + installing frontends", phase_install_frontends),
    ("domain_wiring", "Domain wiring", phase_domain_wiring),
    ("smoke_checks", "Smoke checks", phase_smoke_checks),
    ("grant_commanders", "Granting Casals commanders", phase_grant_commanders),
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
