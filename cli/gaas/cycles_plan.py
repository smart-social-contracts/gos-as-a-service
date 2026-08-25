"""Cycles requirement estimation and balance verification for deploy preflight.

The conductor (casals_backend) creates realm canisters at the descriptor cycle
threshold each (its ``create_cycles`` setting) and pays for orchestration work
(wasm pulls, bundle uploads, inter-canister calls). A single realm deployment
creates backend + frontend + baton (3 canisters) plus ~1T ops margin. We price
the conductor for ``REALMS_PER_DEPLOY_ASSUMPTION`` realm deployments on top of
its treasury reserve (the same threshold). All platform canisters share one
minimum headroom from ``descriptor.cycles.threshold_tc``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from rich.console import Console
from rich.table import Table

from gaas import dfx
from gaas.descriptor import Descriptor
from gaas.known import (
    IC_CREATE_FEE_CYCLES,
    KNOWN_CANISTER_NAMES,
    PLATFORM_CANISTER_NAMES,
)

# Wallet pays dfx canister create --with-cycles (threshold + CMC create fee).
WALLET_CREATE_CYCLES: int = 100_000_000_000  # leftover buffer; not used for budget
WALLET_INITIAL_FUNDING: int = IC_CREATE_FEE_CYCLES  # 0.5T CMC create fee

# Conductor realm-provisioning budget (observed on test.gos.earth: ~2T/create_canister).
REALM_OPS_MARGIN_CYCLES: int = 1_000_000_000_000  # 1T — wasm pulls, bundle upload, inter-canister calls
REALMS_PER_DEPLOY_ASSUMPTION: int = 2  # price conductor for a couple of realm deployments
REALM_CANISTERS_PER_DEPLOY: int = 3  # backend + frontend + baton

ICP_TO_CYCLES: int = 1_000_000_000_000  # ~1 ICP ≈ 1T cycles for convert remediation


@dataclass(frozen=True)
class CyclesLineItem:
    label: str
    canister_id: str | None
    required: int
    available: int | None

    @property
    def shortfall(self) -> int:
        if self.available is None:
            return self.required
        return max(0, self.required - self.available)


@dataclass
class CyclesPlan:
    network: str
    items: list[CyclesLineItem] = field(default_factory=list)
    remediations: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(item.shortfall == 0 for item in self.items)

    @property
    def wallet_ok(self) -> bool:
        return all(item.shortfall == 0 for item in self.items if item.label == "wallet")

    @property
    def wallet_required(self) -> int:
        for item in self.items:
            if item.label == "wallet":
                return item.required
        return 0


def _threshold_cycles(descriptor: Descriptor) -> int:
    return descriptor.threshold_cycles()


def _realm_provisioning_budget(threshold_cycles: int) -> int:
    """Cycles the conductor spends provisioning one realm (3 creates + ops)."""
    return (
        REALM_CANISTERS_PER_DEPLOY * threshold_cycles
        + REALM_OPS_MARGIN_CYCLES
    )


def _casals_backend_required(descriptor: Descriptor) -> int:
    """Treasury reserve plus budget for assumed realm deployments."""
    threshold = _threshold_cycles(descriptor)
    multisig_extra = 0 if descriptor.multisig.backend_id else threshold
    realm_budget = REALMS_PER_DEPLOY_ASSUMPTION * _realm_provisioning_budget(threshold)
    return threshold + realm_budget + multisig_extra


def _canister_headroom(name: str, descriptor: Descriptor) -> int:
    if name == "casals_backend":
        return _casals_backend_required(descriptor)
    return _threshold_cycles(descriptor)


def create_with_cycles(threshold_cycles: int) -> int:
    """Initial ``--with-cycles`` so leftover after the CMC create fee is ``threshold``."""
    return max(int(threshold_cycles), 0) + IC_CREATE_FEE_CYCLES


def _wallet_required_per_canister(descriptor: Descriptor) -> int:
    return create_with_cycles(_threshold_cycles(descriptor))


def _format_cycles(amount: int) -> str:
    if amount >= 1_000_000_000_000:
        value = amount / 1_000_000_000_000
        if value == int(value):
            return f"{int(value)} TC"
        return f"{value:.3f} TC"
    if amount >= 1_000_000_000:
        value = amount / 1_000_000_000
        if value == int(value):
            return f"{int(value)} B"
        return f"{value:.1f} B"
    return f"{amount:,}"


def wallet_convert_amount_icp(shortfall_cycles: int) -> float:
    """Round cycle shortfall up to the nearest 0.5 ICP for `dfx cycles convert`."""
    icp = shortfall_cycles / ICP_TO_CYCLES
    return math.ceil(icp * 2) / 2


def remediation_wallet_convert(shortfall_cycles: int, network: str) -> str:
    amount = wallet_convert_amount_icp(shortfall_cycles)
    formatted = f"{amount:g}"
    return f"dfx cycles convert --amount={formatted} --network {network}"


def remediation_canister_top_up(
    canister_id: str, shortfall_cycles: int, network: str
) -> str:
    return f"dfx cycles top-up {canister_id} {shortfall_cycles} --network {network}"


def build_cycles_plan(
    descriptor: Descriptor,
    network: str,
    *,
    identity: str | None = None,
    wallet_balance: int | None = None,
    canister_balances: dict[str, int | None] | None = None,
) -> CyclesPlan:
    """Build wallet and canister cycle requirements for a descriptor."""
    plan = CyclesPlan(network=network)
    balances = canister_balances or {}

    wallet_required = 0
    per_create = _wallet_required_per_canister(descriptor)
    for name in PLATFORM_CANISTER_NAMES:
        if name not in descriptor.canisters:
            wallet_required += per_create

    if wallet_balance is None and network == "ic":
        try:
            wallet_balance = dfx.cycles_balance(network, identity=identity)
        except dfx.DfxError:
            wallet_balance = None

    plan.items.append(
        CyclesLineItem(
            label="wallet",
            canister_id=None,
            required=wallet_required,
            available=wallet_balance,
        )
    )

    for name in KNOWN_CANISTER_NAMES:
        canister_id = descriptor.canisters.get(name)
        if not canister_id:
            continue
        required = _canister_headroom(name, descriptor)
        available = balances.get(name)
        if available is None and network == "ic":
            try:
                available = dfx.canister_cycles_balance(
                    canister_id, network, identity=identity
                )
            except dfx.DfxError:
                available = None
        plan.items.append(
            CyclesLineItem(
                label=name,
                canister_id=canister_id,
                required=required,
                available=available,
            )
        )

    for item in plan.items:
        if item.shortfall <= 0:
            continue
        if item.label == "wallet":
            plan.remediations.append(
                remediation_wallet_convert(item.shortfall, network)
            )
        elif item.canister_id:
            plan.remediations.append(
                f"auto-top {item.label} ({item.canister_id}) by "
                f"{_format_cycles(item.shortfall)} during deploy"
            )

    return plan


def render_cycles_plan_table(plan: CyclesPlan) -> Table:
    table = Table(title="Cycles plan")
    table.add_column("Item")
    table.add_column("Required", justify="right")
    table.add_column("Available", justify="right")
    table.add_column("Shortfall", justify="right")
    for item in plan.items:
        available = (
            _format_cycles(item.available)
            if item.available is not None
            else "unknown"
        )
        shortfall = _format_cycles(item.shortfall) if item.shortfall else "—"
        label = item.label
        if item.label == "casals_backend":
            label = "casals_backend (treasury + realm provisioning)"
        if item.canister_id:
            label = f"{label}\n{item.canister_id}"
        table.add_row(
            label,
            _format_cycles(item.required),
            available,
            shortfall,
        )
    return table


def print_cycles_plan(plan: CyclesPlan, console: Console | None = None) -> None:
    console = console or Console()
    console.print(render_cycles_plan_table(plan))
    if plan.remediations:
        if plan.wallet_ok:
            console.print(
                "[yellow]Canister shortfalls will be auto-topped during deploy:[/yellow]"
            )
        else:
            console.print("[yellow]Suggested remediation:[/yellow]")
        for line in plan.remediations:
            console.print(f"  {line}")
