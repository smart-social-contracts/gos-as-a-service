"""Pre-deployment checks for identity, cycles, and local replica."""

from __future__ import annotations

from dataclasses import dataclass, field

from rich.console import Console

from gaas import dfx
from gaas.cycles_plan import CyclesPlan, build_cycles_plan, print_cycles_plan
from gaas.descriptor import Descriptor
from gaas.known import (
    DEFAULT_CYCLES_PER_CANISTER,
    DEFAULT_INSTALL_BUFFER_CYCLES,
    DEFAULT_REQUIRED_CYCLES,
    KNOWN_CANISTER_NAMES,
)

_console = Console()


@dataclass
class PreflightCheck:
    name: str
    passed: bool
    detail: str


@dataclass
class PreflightReport:
    identity: str
    network: str
    checks: list[PreflightCheck] = field(default_factory=list)
    required_cycles: int = DEFAULT_REQUIRED_CYCLES
    available_cycles: int | None = None
    cycles_plan: CyclesPlan | None = None

    @property
    def ok(self) -> bool:
        return all(check.passed for check in self.checks)


def run_preflight(
    descriptor: Descriptor,
    identity: str,
    network: str,
    *,
    required_cycles: int = DEFAULT_REQUIRED_CYCLES,
    console: Console | None = None,
) -> PreflightReport:
    # Legacy estimate kept for summary output; detailed plan replaces this on ic.
    to_create = [n for n in KNOWN_CANISTER_NAMES if n not in descriptor.canisters]
    if to_create:
        required_cycles = (
            len(to_create) * DEFAULT_CYCLES_PER_CANISTER + DEFAULT_INSTALL_BUFFER_CYCLES
        )
    else:
        required_cycles = 0
    report = PreflightReport(
        identity=identity,
        network=network,
        required_cycles=required_cycles,
    )
    out = console or _console

    if dfx.identity_exists(identity):
        report.checks.append(
            PreflightCheck(
                name="identity_exists",
                passed=True,
                detail=f"dfx identity {identity!r} found",
            )
        )
    else:
        report.checks.append(
            PreflightCheck(
                name="identity_exists",
                passed=False,
                detail=f"dfx identity {identity!r} not found",
            )
        )
        return report

    try:
        principal = dfx.get_principal(identity)
        report.checks.append(
            PreflightCheck(
                name="principal",
                passed=True,
                detail=f"principal: {principal}",
            )
        )
    except dfx.DfxError as exc:
        report.checks.append(
            PreflightCheck(
                name="principal",
                passed=False,
                detail=str(exc),
            )
        )
        return report

    if network == "ic":
        try:
            plan = build_cycles_plan(descriptor, network, identity=identity)
            report.cycles_plan = plan
            report.required_cycles = plan.wallet_required
            wallet_item = next(item for item in plan.items if item.label == "wallet")
            report.available_cycles = wallet_item.available
            print_cycles_plan(plan, out)

            if plan.ok:
                if plan.pending_topups:
                    detail = (
                        f"wallet can fund headroom top-ups for: "
                        f"{', '.join(item.label for item in plan.pending_topups)}"
                    )
                else:
                    detail = "wallet and canister cycles sufficient for deploy estimate"
                report.checks.append(
                    PreflightCheck(
                        name="cycles_plan",
                        passed=True,
                        detail=detail,
                    )
                )
            else:
                short_items = [
                    item.label
                    for item in plan.items
                    if item.shortfall > 0
                ]
                detail = (
                    f"insufficient cycles for: {', '.join(short_items)}; "
                    "see cycles plan table and remediation commands above"
                )
                report.checks.append(
                    PreflightCheck(
                        name="cycles_plan",
                        passed=False,
                        detail=detail,
                    )
                )
        except dfx.DfxError as exc:
            report.checks.append(
                PreflightCheck(
                    name="cycles_plan",
                    passed=False,
                    detail=str(exc),
                )
            )
    else:
        if dfx.ping_local():
            report.checks.append(
                PreflightCheck(
                    name="local_replica",
                    passed=True,
                    detail="local replica responded to dfx ping",
                )
            )
        else:
            report.checks.append(
                PreflightCheck(
                    name="local_replica",
                    passed=False,
                    detail="local replica not running (dfx ping local failed)",
                )
            )

    return report
