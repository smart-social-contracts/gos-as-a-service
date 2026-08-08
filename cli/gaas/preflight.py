"""Pre-deployment checks for identity, cycles, and local replica."""

from __future__ import annotations

from dataclasses import dataclass, field

from gaas import dfx
from gaas.descriptor import Descriptor
from gaas.known import (
    DEFAULT_CYCLES_PER_CANISTER,
    DEFAULT_INSTALL_BUFFER_CYCLES,
    DEFAULT_REQUIRED_CYCLES,
    KNOWN_CANISTER_NAMES,
)


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

    @property
    def ok(self) -> bool:
        return all(check.passed for check in self.checks)


def run_preflight(
    descriptor: Descriptor,
    identity: str,
    network: str,
    *,
    required_cycles: int = DEFAULT_REQUIRED_CYCLES,
) -> PreflightReport:
    # Only canisters absent from the descriptor need creation cycles; adopted
    # canisters pay for their own installs from their existing balances.
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
            balance = dfx.cycles_balance(network)
            report.available_cycles = balance
            if balance is None:
                report.checks.append(
                    PreflightCheck(
                        name="cycles_balance",
                        passed=False,
                        detail="could not parse cycles balance on ic",
                    )
                )
            elif balance >= required_cycles:
                report.checks.append(
                    PreflightCheck(
                        name="cycles_balance",
                        passed=True,
                        detail=(
                            f"available: {balance:,} cycles; "
                            f"required estimate: {required_cycles:,} cycles"
                        ),
                    )
                )
            else:
                report.checks.append(
                    PreflightCheck(
                        name="cycles_balance",
                        passed=False,
                        detail=(
                            f"insufficient cycles: have {balance:,}, "
                            f"need ~{required_cycles:,} "
                            f"({len(to_create)} canisters to create × 1T + 2T install buffer)"
                        ),
                    )
                )
        except dfx.DfxError as exc:
            report.checks.append(
                PreflightCheck(
                    name="cycles_balance",
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
