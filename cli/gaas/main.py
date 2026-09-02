"""Typer entry point for the GaaS CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.syntax import Syntax
from rich.table import Table

from gaas import dfx
from gaas.descriptor import Descriptor
from gaas.destroy import destroy_via_casals
from gaas.dns import render_dns_records
from gaas.known import DEFAULT_REQUIRED_CYCLES
from gaas.namespace_approval_seed import (
    ApprovalStampError,
    refuse_demo_environment,
    seed_namespace_approvals,
)
from gaas.phases import DeployContext, PHASES, run_phases, run_seed_phases
from gaas.preflight import PreflightReport
from gaas.runlog import print_log_path, start_run_log, stop_run_log
from gaas.wizard import confirm_deploy, run_wizard

app = typer.Typer(
    name="gaas",
    help="GaaS platform deployment CLI — descriptor-driven one-command deploys",
    no_args_is_help=True,
)
console = Console()


def _apply_flag_config(
    desc: Descriptor,
    *,
    can_test_mode: bool,
    open_mode: bool,
    test_flags_json: str | None,
) -> None:
    """Apply explicit CLI flag config. Never invents flags from --network."""
    if can_test_mode or open_mode:
        desc.flags["can_test_mode"] = True
    if not test_flags_json:
        return
    try:
        parsed = json.loads(test_flags_json)
    except json.JSONDecodeError as exc:
        console.print(f"[red]--test-flags is not valid JSON: {exc}[/red]")
        raise typer.Exit(code=1) from exc
    if not isinstance(parsed, dict):
        console.print("[red]--test-flags must be a JSON object[/red]")
        raise typer.Exit(code=1)
    desc.test_flags = {str(k): bool(v) for k, v in parsed.items()}


def _print_preflight(report: PreflightReport) -> None:
    table = Table(title="Preflight report")
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail")
    for check in report.checks:
        status = "[green]pass[/green]" if check.passed else "[red]fail[/red]"
        table.add_row(check.name, status, check.detail)
    console.print(table)
    if report.network == "ic" and report.cycles_plan is None:
        console.print(
            f"Required cycles estimate: {report.required_cycles:,} cycles"
        )


def _print_dns_table(descriptor: Descriptor) -> None:
    frontend_id = descriptor.canisters.get("realm_registry_frontend")
    if not frontend_id:
        console.print(
            "[yellow]No realm_registry_frontend canister ID in descriptor; "
            "using placeholder for record preview.[/yellow]"
        )
        frontend_id = "yhw3g-fyaaa-aaaas-qgorq-cai"

    records = render_dns_records(descriptor.domain, frontend_id)
    table = Table(title=f"DNS records for {descriptor.domain}")
    table.add_column("Type")
    table.add_column("Host")
    table.add_column("Value")
    table.add_column("Notes")
    for record in records:
        table.add_row(record.record_type, record.host, record.value, record.notes)
    console.print(table)


def _run_deploy_pipeline(
    descriptor: Descriptor,
    identity: str,
    network: str,
    *,
    descriptor_path: Path | None = None,
    yes: bool = False,
    casals_src: Path | None = None,
    dns_timeout_min: int = 20,
    skip_dns_wait: bool = False,
    keep_env_file: bool = False,
    reinstall_backends: bool = False,
    destroy_except_frontend: bool = False,
) -> None:
    ctx = DeployContext(
        identity=identity,
        network=network,
        required_cycles=DEFAULT_REQUIRED_CYCLES,
        descriptor_path=descriptor_path,
        yes=yes,
        casals_src=casals_src,
        dns_timeout_min=dns_timeout_min,
        skip_dns_wait=skip_dns_wait,
        keep_env_file=keep_env_file,
        reinstall_backends=reinstall_backends,
        destroy_except_frontend=destroy_except_frontend,
    )
    total = len(PHASES)
    run_log = start_run_log(descriptor.name)

    def on_start(index: int, _phase_id: str, title: str) -> None:
        console.print(f"[{index}/{total}] {title}...")

    try:
        run_phases(descriptor, ctx, on_phase_start=on_start)
    except RuntimeError as exc:
        console.print(f"[red]Deployment failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        print_log_path()
        stop_run_log()

    if ctx.preflight:
        _print_preflight(ctx.preflight)

    if ctx.stopped and len(ctx.completed_phases) < total:
        console.print(
            f"\n[yellow]Pipeline paused after phase {len(ctx.completed_phases)}/{total}.[/yellow]"
        )
        if descriptor_path:
            console.print(
                f"Resume later with: gaas new {descriptor_path} --identity {identity} --network {network}"
            )
        raise typer.Exit(code=1)

    console.print("\n[green]Deployment complete.[/green]")


def _run_seed_pipeline(
    descriptor: Descriptor,
    identity: str,
    network: str,
    *,
    descriptor_path: Path | None = None,
    yes: bool = False,
    casals_src: Path | None = None,
) -> None:
    ctx = DeployContext(
        identity=identity,
        network=network,
        descriptor_path=descriptor_path,
        yes=yes,
        casals_src=casals_src,
    )
    total = 3
    start_run_log(descriptor.name)

    def on_start(index: int, _phase_id: str, title: str) -> None:
        console.print(f"[{index}/{total}] {title}...")

    try:
        run_seed_phases(descriptor, ctx, on_phase_start=on_start)
    except RuntimeError as exc:
        console.print(f"[red]Seed failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        print_log_path()
        stop_run_log()

    console.print("\n[green]Seed complete.[/green]")


@app.command("new")
def new_command(
    descriptor: Optional[Path] = typer.Argument(
        None,
        help="Descriptor JSON path; omit to run the interactive wizard",
    ),
    identity: Optional[str] = typer.Option(
        None,
        "--identity",
        help="dfx identity (overrides wizard / descriptor default)",
    ),
    network: Optional[str] = typer.Option(
        None,
        "--network",
        help="Target network: ic or local",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Skip interactive confirmations (required for ic frontend reinstall in CI)",
    ),
    casals_src: Optional[Path] = typer.Option(
        None,
        "--casals-src",
        help="Local Casals checkout for building casals_backend when release assets are missing",
    ),
    dns_timeout_min: int = typer.Option(
        20,
        "--dns-timeout-min",
        help="Minutes to wait for DNS propagation on ic before failing domain wiring",
    ),
    skip_dns_wait: bool = typer.Option(
        False,
        "--skip-dns-wait",
        help="Print DNS records and skip propagation polling",
    ),
    keep_env_file: bool = typer.Option(
        False,
        "--keep-env-file",
        help="Keep gaas-env.json at the repo root after frontend build",
    ),
    reinstall_backends: bool = typer.Option(
        False,
        "--reinstall-backends",
        help=(
            "Wipe backend canisters (registry, installer, conductor) via --mode reinstall "
            "instead of upgrading in place; platform state is re-seeded, but registry user "
            "data (realms, credits, slugs) is permanently reset"
        ),
    ),
    destroy_except_frontend: bool = typer.Option(
        False,
        "--destroy-except-realm-registry-frontend",
        help=(
            "Drain-destroy all canisters except DNS-mapped frontends "
            "(realm_registry_frontend for *.gos.earth; marketplace_frontend for "
            "*.realmsgos.org when present). Other frontends are destroyed. "
            "Evacuates the Casals treasury to the cycles wallet, then recreates "
            "the rest of the platform"
        ),
    ),
    can_test_mode: bool = typer.Option(
        False,
        "--can-test-mode",
        help="Set flags.can_test_mode true (overrides descriptor). Does not invent test_flags.",
    ),
    open_mode: bool = typer.Option(
        False,
        "--open-mode",
        hidden=True,
        help="Deprecated alias for --can-test-mode",
    ),
    test_flags_json: Optional[str] = typer.Option(
        None,
        "--test-flags",
        help=(
            "JSON object of runtime test flags (test_mode, ii_bypass, demo_data, …). "
            "Overrides descriptor.test_flags. Prefer putting them in the env JSON."
        ),
    ),
) -> None:
    """Create or deploy a GaaS environment from a descriptor."""
    if network is not None and network not in {"ic", "local"}:
        console.print("[red]--network must be 'ic' or 'local'[/red]")
        raise typer.Exit(code=1)

    descriptor_path = descriptor

    if descriptor_path is None:
        desc, resolved_identity, resolved_network, output_path = run_wizard(
            identity=identity,
            network=network,
        )
        _apply_flag_config(
            desc,
            can_test_mode=can_test_mode,
            open_mode=open_mode,
            test_flags_json=test_flags_json,
        )
        desc.save(output_path)
        console.print(f"\n[green]Wrote descriptor:[/green] {output_path}\n")
        console.print(Syntax(desc.to_pretty_json(), "json", theme="monokai"))

        if confirm_deploy(network=resolved_network):
            _run_deploy_pipeline(
                desc,
                resolved_identity,
                resolved_network,
                descriptor_path=output_path,
                yes=yes,
                casals_src=casals_src,
                dns_timeout_min=dns_timeout_min,
                skip_dns_wait=skip_dns_wait,
                keep_env_file=keep_env_file,
                reinstall_backends=reinstall_backends,
                destroy_except_frontend=destroy_except_frontend,
            )
        else:
            cmd_identity = resolved_identity
            cmd_network = resolved_network
            console.print(
                f"\nDeploy later with:\n"
                f"  gaas new {output_path} --identity {cmd_identity} --network {cmd_network}"
            )
        return

    desc = Descriptor.load(descriptor_path)
    _apply_flag_config(
        desc,
        can_test_mode=can_test_mode,
        open_mode=open_mode,
        test_flags_json=test_flags_json,
    )
    resolved_identity = identity or "default"
    resolved_network = network or "ic"
    if not yes and sys.stdin.isatty():
        if not confirm_deploy(network=resolved_network):
            console.print("Deploy cancelled.")
            raise typer.Exit(code=0)
    _run_deploy_pipeline(
        desc,
        resolved_identity,
        resolved_network,
        descriptor_path=descriptor_path,
        yes=yes,
        casals_src=casals_src,
        dns_timeout_min=dns_timeout_min,
        skip_dns_wait=skip_dns_wait,
        keep_env_file=keep_env_file,
        reinstall_backends=reinstall_backends,
        destroy_except_frontend=destroy_except_frontend,
    )


@app.command("seed")
def seed_command(
    descriptor: Path = typer.Argument(..., help="Descriptor JSON path"),
    identity: str = typer.Option(..., "--identity", help="dfx identity"),
    network: str = typer.Option("ic", "--network", help="Target network: ic or local"),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Skip interactive confirmations",
    ),
    casals_src: Optional[Path] = typer.Option(
        None,
        "--casals-src",
        help="Local Casals checkout for orchestration template WASM",
    ),
) -> None:
    """Re-seed GOS artifacts and conductor authorization on an existing environment."""
    if network not in {"ic", "local"}:
        console.print("[red]--network must be 'ic' or 'local'[/red]")
        raise typer.Exit(code=1)

    desc = Descriptor.load(descriptor)
    _run_seed_pipeline(
        desc,
        identity,
        network,
        descriptor_path=descriptor,
        yes=yes,
        casals_src=casals_src,
    )


@app.command("stamp-namespace-approvals")
def stamp_namespace_approvals_command(
    descriptor: Path = typer.Argument(..., help="Descriptor JSON path"),
    identity: str = typer.Option(..., "--identity", help="dfx identity"),
    network: str = typer.Option("ic", "--network", help="Target network: ic or local"),
    force: bool = typer.Option(
        True,
        "--force/--no-force",
        help="Restamp every ext/ and codex/ namespace (default: yes; republish invalidates hashes)",
    ),
    namespace: Optional[str] = typer.Option(
        None,
        "--namespace",
        help="Stamp only this namespace (repeat not supported; comma-separated ok)",
    ),
) -> None:
    """Stamp marketplace approvals on file-registry ext/ and codex/ namespaces.

    Routes through marketplace admin_approve_namespace so realms accept the
    stamp. Refuses demo. Used after gaas publish and as the deploy-files hook.
    """
    if network not in {"ic", "local"}:
        console.print("[red]--network must be 'ic' or 'local'[/red]")
        raise typer.Exit(code=1)

    desc = Descriptor.load(descriptor)
    try:
        refuse_demo_environment(desc.name)
    except ApprovalStampError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    registry_id = (desc.canisters.get("file_registry") or "").strip()
    marketplace_id = (desc.canisters.get("marketplace_backend") or "").strip()
    if not registry_id or not marketplace_id:
        console.print(
            "[red]descriptor must list file_registry and marketplace_backend[/red]"
        )
        raise typer.Exit(code=1)

    namespaces = None
    if namespace:
        namespaces = [part.strip() for part in namespace.split(",") if part.strip()]

    try:
        result = seed_namespace_approvals(
            registry_id,
            marketplace_id,
            network,
            identity,
            force=force,
            namespaces=namespaces,
        )
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(
        f"namespace approvals: granted={result['granted']}, "
        f"approved={result['approved']}, skipped={result['skipped']}, "
        f"failed={result['failed']}"
    )


@app.command("dns-records")
def dns_records_command(
    descriptor: Path = typer.Argument(..., help="Descriptor JSON path"),
) -> None:
    """Print DNS records required for the environment domain."""
    desc = Descriptor.load(descriptor)
    _print_dns_table(desc)


@app.command("status")
def status_command(
    descriptor: Path = typer.Argument(..., help="Descriptor JSON path"),
    network: str = typer.Option("ic", "--network", help="dfx network"),
    identity: Optional[str] = typer.Option(
        "default",
        "--identity",
        help="dfx identity used for canister status queries",
    ),
) -> None:
    """Print canister status for all IDs listed in the descriptor."""
    desc = Descriptor.load(descriptor)
    if not desc.canisters:
        console.print("[yellow]No canisters listed in descriptor.[/yellow]")
        raise typer.Exit(code=0)

    table = Table(title=f"Canister status ({network})")
    table.add_column("Name")
    table.add_column("Canister ID")
    table.add_column("Status")
    for name, canister_id in desc.canisters.items():
        try:
            status = dfx.canister_status(canister_id, network, identity=identity)
            table.add_row(name, canister_id, status.status)
        except dfx.DfxError as exc:
            table.add_row(name, canister_id, f"error: {exc}")
    console.print(table)


@app.command("destroy")
def destroy_command(
    descriptor: Path = typer.Argument(..., help="Descriptor JSON path"),
    stand: Optional[str] = typer.Option(None, "--stand", help="Casals stand name to destroy"),
    canister_id: Optional[str] = typer.Option(
        None,
        "--canister-id",
        help="Single canister ID to destroy via Casals drain-then-delete",
    ),
    identity: str = typer.Option(..., "--identity", help="dfx identity"),
    network: str = typer.Option("ic", "--network", help="Target network: ic or local"),
    yes: bool = typer.Option(False, "--yes", help="Skip interactive confirmation"),
    platform: bool = typer.Option(
        False,
        "--platform",
        help="Allow destroying a descriptor platform canister by ID",
    ),
) -> None:
    """Destroy a Casals stand or canister (drain cycles, then delete)."""
    if network not in {"ic", "local"}:
        console.print("[red]--network must be 'ic' or 'local'[/red]")
        raise typer.Exit(code=1)

    desc = Descriptor.load(descriptor)
    if not yes:
        if not typer.confirm(
            "Destroy via Casals (drain cycles then delete)? This cannot be undone."
        ):
            raise typer.Exit(code=1)

    try:
        result = destroy_via_casals(
            desc,
            network=network,
            identity=identity,
            stand=stand,
            canister_id=canister_id,
            allow_platform=platform,
        )
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    reclaimed = result.get("total_cycles_reclaimed") or result.get("cycles_reclaimed")
    if reclaimed is not None:
        console.print(f"Cycles reclaimed: {int(reclaimed):,}")
    console.print("[green]Destroy complete.[/green]")


if __name__ == "__main__":
    app()
