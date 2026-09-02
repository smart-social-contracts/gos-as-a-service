"""Interactive console wizard for building a GaaS descriptor."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import questionary
from questionary import Choice
from rich.console import Console

from gaas.descriptor import (
    CasalsConfig,
    CyclesConfig,
    Descriptor,
    DnsConfig,
    GosArtifacts,
    GosEntry,
    PlatformConfig,
    ServicesConfig,
)
from gaas.versions import validate_descriptor_version
from gaas.known import (
    ADOPT_ONLY_CANISTER_NAMES,
    DEFAULT_CASALS_RELEASE_REPO,
    DEFAULT_CASALS_VERSION,
    DEFAULT_PLATFORM_RELEASE_REPO,
    DEFAULT_PLATFORM_VERSION,
    GOS_IMPLEMENTATIONS,
    PLATFORM_CANISTER_NAMES,
)

console = Console()

ASSET_FRONTEND_CANISTERS = (
    "realm_registry_frontend",
    "casals_frontend",
)


def deploy_confirmation_message(*, network: str = "ic") -> str:
    if network == "ic":
        names = ", ".join(ASSET_FRONTEND_CANISTERS)
        return (
            "Deploy now? This will create or update canisters, install backend WASM, "
            "seed the file registry and conductor, and reinstall asset canisters "
            f"({names}) on IC mainnet — this wipes existing frontend state on those "
            "canisters."
        )
    return (
        "Deploy now? This will create or update canisters, install backends, seed "
        "artifacts, and reinstall frontend asset canisters."
    )


def _validate_domain(value: str) -> bool | str:
    if not value.strip():
        return "domain is required"
    try:
        Descriptor.model_validate(
            {
                "name": "tmp",
                "domain": value.strip(),
                "gos": [
                    {
                        "implementation": "realms-gos",
                        "version": "v0.3.1",
                        "release_repo": "smart-social-contracts/realms",
                        "artifacts": {
                            "backend_wasm_key": "realm-backend",
                            "frontend_wasm_key": "realm-assets",
                        },
                        "loader_profile": "realms-iframe-v1",
                    }
                ],
                "casals": {"version": DEFAULT_CASALS_VERSION},
            }
        )
    except Exception as exc:
        return str(exc)
    return True


def _validate_slug(value: str) -> bool | str:
    if not value.strip():
        return "name is required"
    try:
        Descriptor.model_validate(
            {
                "name": value.strip(),
                "domain": "example.gos.earth",
                "gos": [
                    {
                        "implementation": "realms-gos",
                        "version": "v0.3.1",
                        "release_repo": "smart-social-contracts/realms",
                        "artifacts": {
                            "backend_wasm_key": "realm-backend",
                            "frontend_wasm_key": "realm-assets",
                        },
                        "loader_profile": "realms-iframe-v1",
                    }
                ],
                "casals": {"version": DEFAULT_CASALS_VERSION},
            }
        )
    except Exception as exc:
        return str(exc)
    return True


def _validate_canister_id(value: str) -> bool | str:
    if not value.strip():
        return True
    try:
        Descriptor.model_validate(
            {
                "name": "tmp",
                "domain": "example.gos.earth",
                "gos": [
                    {
                        "implementation": "realms-gos",
                        "version": "v0.3.1",
                        "release_repo": "smart-social-contracts/realms",
                        "artifacts": {
                            "backend_wasm_key": "realm-backend",
                            "frontend_wasm_key": "realm-assets",
                        },
                        "loader_profile": "realms-iframe-v1",
                    }
                ],
                "canisters": {"realm_registry_backend": value.strip()},
                "casals": {"version": DEFAULT_CASALS_VERSION},
            }
        )
    except Exception as exc:
        return str(exc)
    return True


def _validate_version(value: str) -> bool | str:
    try:
        validate_descriptor_version(value)
    except ValueError as exc:
        return str(exc)
    return True


_VERSION_HELP = (
    "vX.Y.Z (pinned release), latest (newest GitHub release), or "
    "main (unreproducible source build of HEAD — test/local only)"
)


def _validate_https_optional(value: str, *, field: str = "billing_url") -> bool | str:
    if not value.strip():
        return True
    try:
        ServicesConfig.model_validate({field: value.strip()})
    except Exception as exc:
        return str(exc)
    return True


def _validate_monitor_principal_optional(value: str) -> bool | str:
    if not value.strip():
        return True
    try:
        ServicesConfig.model_validate({"monitor_principal": value.strip()})
    except Exception as exc:
        return str(exc)
    return True


def _validate_billing_service_principal_optional(value: str) -> bool | str:
    if not value.strip():
        return True
    try:
        ServicesConfig.model_validate({"billing_service_principal": value.strip()})
    except Exception as exc:
        return str(exc)
    return True


def _parse_commanders(value: str) -> list[str]:
    if not value.strip():
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _validate_commanders_optional(value: str) -> bool | str:
    if not value.strip():
        return True
    try:
        CasalsConfig.model_validate(
            {
                "version": DEFAULT_CASALS_VERSION,
                "commanders": _parse_commanders(value),
            }
        )
    except Exception as exc:
        return str(exc)
    return True


def _validate_threshold_tc(value: str) -> bool | str:
    if not value.strip():
        return True
    try:
        CyclesConfig.model_validate({"threshold_tc": float(value.strip())})
    except Exception as exc:
        return str(exc)
    return True


def _gos_choices() -> list[Choice]:
    choices: list[Choice] = []
    for impl in GOS_IMPLEMENTATIONS.values():
        label = impl.label
        if not impl.available:
            label = f"{label} ({impl.unavailable_reason})"
        choices.append(
            Choice(
                title=label,
                value=impl.id,
                disabled=not impl.available,
            )
        )
    return choices


def run_wizard(
    *,
    identity: str | None = None,
    network: str | None = None,
    ask: Callable[..., object] | None = None,
) -> tuple[Descriptor, str, str, Path]:
    """Run the interactive wizard; return descriptor, identity, network, output path."""
    prompt = ask or questionary

    console.print("[bold]GaaS environment wizard[/bold]\n")

    name = prompt.text(
        "Environment name (slug):",
        validate=_validate_slug,
    ).ask()
    if name is None:
        raise SystemExit(0)
    name = name.strip()

    domain = prompt.text(
        "Domain:",
        validate=_validate_domain,
    ).ask()
    if domain is None:
        raise SystemExit(0)
    domain = domain.strip()

    if network is None:
        network_choice = prompt.select(
            "Network:",
            choices=["ic", "local"],
            default="ic",
        ).ask()
        if network_choice is None:
            raise SystemExit(0)
        network = str(network_choice)
    else:
        console.print(f"Network: {network} (from flag)")

    if identity is None:
        identity_value = prompt.text(
            "dfx identity:",
            default="default",
        ).ask()
        if identity_value is None:
            raise SystemExit(0)
        identity = identity_value.strip()
    else:
        console.print(f"Identity: {identity} (from flag)")

    platform_source = prompt.select(
        "Platform canisters:",
        choices=[
            "Build from local gos-as-a-service checkout",
            "Fetch from GitHub release",
        ],
        default="Build from local gos-as-a-service checkout",
    ).ask()
    if platform_source is None:
        raise SystemExit(0)

    platform: PlatformConfig | None = None
    if str(platform_source).startswith("Fetch"):
        release_version = prompt.text(
            "Platform release version:",
            default=DEFAULT_PLATFORM_VERSION,
        ).ask()
        if release_version is None:
            raise SystemExit(0)
        platform = PlatformConfig(
            version=release_version.strip(),
            release_repo=DEFAULT_PLATFORM_RELEASE_REPO,
        )
    else:
        console.print("Platform: build from local checkout (descriptor.platform omitted)")

    selected_gos = prompt.checkbox(
        "GOS implementations:",
        choices=_gos_choices(),
        validate=lambda values: True
        if values
        else "select at least one GOS implementation",
    ).ask()
    if selected_gos is None:
        raise SystemExit(0)

    gos_entries: list[GosEntry] = []
    for impl_id in selected_gos:
        impl = GOS_IMPLEMENTATIONS[impl_id]
        version = prompt.text(
            f"{impl.label} version ({_VERSION_HELP}):",
            default=impl.default_version,
            validate=_validate_version,
        ).ask()
        if version is None:
            raise SystemExit(0)
        gos_entries.append(
            GosEntry(
                implementation=impl.id,
                version=version.strip(),
                release_repo=impl.release_repo,
                artifacts=GosArtifacts(
                    backend_wasm_key=impl.artifacts.backend_wasm_key,
                    frontend_wasm_key=impl.artifacts.frontend_wasm_key,
                    backend_asset=impl.artifacts.backend_asset,
                    frontend_asset=impl.artifacts.frontend_asset,
                ),
                loader_profile=impl.loader_profile,
            )
        )

    canisters: dict[str, str] = {}
    console.print(
        "\nExisting canister IDs (leave blank to create new). "
        "Marketplace and the Realms package catalog belong to `realms seed`:"
    )
    for canister_name in PLATFORM_CANISTER_NAMES + ADOPT_ONLY_CANISTER_NAMES:
        hint = ""
        if canister_name in ADOPT_ONLY_CANISTER_NAMES:
            hint = " [DNS-mapped, optional]"
        value = prompt.text(
            f"  {canister_name}{hint}:",
            validate=_validate_canister_id,
        ).ask()
        if value is None:
            raise SystemExit(0)
        if value.strip():
            canisters[canister_name] = value.strip()

    casals_version = prompt.text(
        f"Casals version ({_VERSION_HELP}):",
        default=DEFAULT_CASALS_VERSION,
        validate=_validate_version,
    ).ask()
    if casals_version is None:
        raise SystemExit(0)

    commanders_raw = prompt.text(
        "Additional Casals UI admin principals (comma-separated, optional):",
        validate=_validate_commanders_optional,
    ).ask()
    if commanders_raw is None:
        raise SystemExit(0)

    threshold_raw = prompt.text(
        "Cycle threshold (TC) for running canisters (autopilot floor):",
        default="2",
        validate=_validate_threshold_tc,
    ).ask()
    if threshold_raw is None:
        raise SystemExit(0)

    billing_url = prompt.text(
        "Billing service URL (optional, https):",
        validate=lambda value: _validate_https_optional(value, field="billing_url"),
    ).ask()
    if billing_url is None:
        raise SystemExit(0)

    billing_service_principal: str | None = None
    if billing_url.strip():
        billing_principal_raw = prompt.text(
            "Billing service principal (optional, IC principal for add_credits):",
            validate=_validate_billing_service_principal_optional,
        ).ask()
        if billing_principal_raw is None:
            raise SystemExit(0)
        billing_service_principal = billing_principal_raw.strip() or None

    deploy_url = prompt.text(
        "Deploy service URL (optional, https):",
        validate=lambda value: _validate_https_optional(value, field="deploy_url"),
    ).ask()
    if deploy_url is None:
        raise SystemExit(0)

    monitor_url = prompt.text(
        "Casals monitor URL (optional, https):",
        validate=lambda value: _validate_https_optional(value, field="monitor_url"),
    ).ask()
    if monitor_url is None:
        raise SystemExit(0)

    monitor_principal: str | None = None
    if monitor_url.strip():
        monitor_principal_raw = prompt.text(
            "Casals monitor principal (optional):",
            validate=_validate_monitor_principal_optional,
        ).ask()
        if monitor_principal_raw is None:
            raise SystemExit(0)
        monitor_principal = monitor_principal_raw.strip() or None

    can_test_mode = prompt.confirm(
        "Enable can_test_mode (skip billing credit checks; enables portal test auth)?",
        default=False,
    ).ask()
    if can_test_mode is None:
        raise SystemExit(0)

    default_path = Path.cwd() / f"{name}.gaas.json"
    output_raw = prompt.text(
        "Descriptor output path:",
        default=str(default_path),
    ).ask()
    if output_raw is None:
        raise SystemExit(0)
    output_path = Path(output_raw.strip())

    flags: dict[str, bool] = {}
    if can_test_mode:
        flags["can_test_mode"] = True

    descriptor = Descriptor(
        name=name,
        domain=domain,
        gos=gos_entries,
        canisters=canisters,
        platform=platform,
        casals=CasalsConfig(
            version=casals_version.strip(),
            release_repo=DEFAULT_CASALS_RELEASE_REPO,
            commanders=_parse_commanders(commanders_raw),
        ),
        services=ServicesConfig(
            billing_url=billing_url.strip() or None,
            billing_service_principal=billing_service_principal,
            deploy_url=deploy_url.strip() or None,
            monitor_url=monitor_url.strip() or None,
            monitor_principal=monitor_principal,
        ),
        cycles=CyclesConfig(
            threshold_tc=float(threshold_raw.strip() or "2"),
            create_tc=2,
        ),
        flags=flags,
        dns=DnsConfig(provider="manual"),
    )

    return descriptor, identity, network, output_path


def confirm_deploy(*, network: str = "ic") -> bool:
    answer = questionary.confirm(
        deploy_confirmation_message(network=network),
        default=False,
    ).ask()
    return bool(answer)
