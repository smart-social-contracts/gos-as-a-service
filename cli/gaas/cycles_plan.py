"""Cycles requirement estimation and balance verification for deploy preflight."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from rich.console import Console
from rich.table import Table

from gaas import dfx
from gaas.descriptor import Descriptor
from gaas.known import KNOWN_CANISTER_NAMES

# Wallet pays dfx canister create (ledger fee) plus initial --with-cycles funding.
WALLET_CREATE_CYCLES: int = 100_000_000_000  # 0.1T — IC canister creation fee
WALLET_INITIAL_FUNDING: int = 500_000_000_000  # 0.5T — headroom for first install per canister

# Minimum in-canister balances before deploy steps that consume cycles.
CANISTER_HEADROOM_DEFAULT: int = 200_000_000_000  # 0.2T — backends/frontends
CANISTER_HEADROOM_FILE_REGISTRY: int = 500_000_000_000  # 0.5T — heavy WASM/asset seeding
CANISTER_HEADROOM_REALM_INSTALLER: int = 300_000_000_000  # 0.3T — realm provisioning installs
CANISTER_HEADROOM_CASALS_BACKEND: int = 1_000_000_000_000  # 1T — treasury reserve + orchestration
MULTISIG_CREATE_CYCLES: int = 2_000_000_000_000  # 2T — conductor creates multisig when absent

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
    def wallet_required(self) -> int:
        for item in self.items:
            if item.label == "wallet":
                return item.required
        return 0


def _canister_headroom(name: str, descriptor: Descriptor) -> int:
    if name == "file_registry":
        return CANISTER_HEADROOM_FILE_REGISTRY
    if name == "realm_installer":
        return CANISTER_HEADROOM_REALM_INSTALLER
    if name == "casals_backend":
        extra = 0 if descriptor.multisig.backend_id else MULTISIG_CREATE_CYCLES
        return CANISTER_HEADROOM_CASALS_BACKEND + extra
    return CANISTER_HEADROOM_DEFAULT


def _wallet_required_per_canister() -> int:
    return WALLET_CREATE_CYCLES + WALLET_INITIAL_FUNDING


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
    for name in KNOWN_CANISTER_NAMES:
        if name not in descriptor.canisters:
            wallet_required += _wallet_required_per_canister()

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
                remediation_canister_top_up(
                    item.canister_id, item.shortfall, network
                )
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
        if item.canister_id:
            label = f"{item.label}\n{item.canister_id}"
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
        console.print("[yellow]Suggested remediation:[/yellow]")
        for line in plan.remediations:
            console.print(f"  {line}")
