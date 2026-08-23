"""Single source of truth for known canister names, GOS implementations, and default pins."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

PLATFORM_CANISTER_NAMES: Final[tuple[str, ...]] = (
    "realm_registry_backend",
    "realm_registry_frontend",
    "realm_installer",
    "casals_backend",
    "casals_frontend",
    "casals_file_registry",
)

# Valid in descriptors and adopted when present, but never created, deployed,
# or cycle-budgeted by gaas (external services wired in by configuration).
ADOPT_ONLY_CANISTER_NAMES: Final[tuple[str, ...]] = (
    "file_registry",
    "file_registry_frontend",
    "marketplace_backend",
    "marketplace_frontend",
)

KNOWN_CANISTER_NAMES: Final[tuple[str, ...]] = (
    PLATFORM_CANISTER_NAMES + ADOPT_ONLY_CANISTER_NAMES
)

DEFAULT_CASALS_VERSION: Final[str] = "v0.3.0"
DEFAULT_CASALS_RELEASE_REPO: Final[str] = "smart-social-contracts/Casals"
DEFAULT_PLATFORM_VERSION: Final[str] = "v0.3.1"
DEFAULT_PLATFORM_RELEASE_REPO: Final[str] = "smart-social-contracts/gos-as-a-service"
DEFAULT_CASALS_SECTION: Final[str] = "Deployments"

# Maps platform canister names to dfx.json canister names (None = create via ledger).
DFX_CANISTER_NAMES: Final[dict[str, str | None]] = {
    "realm_registry_backend": "realm_registry_backend",
    "realm_registry_frontend": "realm_registry_frontend",
    "realm_installer": "realm_installer",
    "casals_backend": None,
    "casals_frontend": "casals_frontend",
    "casals_file_registry": None,
}

PLATFORM_BACKEND_WASMS: Final[dict[str, str]] = {
    "realm_registry_backend": "realm_registry_backend.wasm.gz",
    "realm_installer": "realm_installer.wasm.gz",
}

PLATFORM_FRONTEND_ARCHIVES: Final[dict[str, str]] = {
    "realm_registry_frontend": "realm_registry_frontend.tar.gz",
}

CASALS_BACKEND_WASM_ASSET: Final[str] = "casals_backend.wasm.gz"
CASALS_FILE_REGISTRY_WASM_ASSET: Final[str] = "file_registry.wasm.gz"
CASALS_FILE_REGISTRY_WASM_ASSETS: Final[tuple[str, ...]] = (
    "file_registry.wasm.gz",
    "ic_file_registry.wasm.gz",
)
CASALS_FRONTEND_ARCHIVE: Final[str] = "casals_frontend.tar.gz"

DEFAULT_CYCLES_PER_CANISTER: Final[int] = 1_000_000_000_000  # 1T
DEFAULT_CANISTER_COUNT: Final[int] = len(PLATFORM_CANISTER_NAMES)
DEFAULT_INSTALL_BUFFER_CYCLES: Final[int] = 2_000_000_000_000  # 2T
DEFAULT_REQUIRED_CYCLES: Final[int] = (
    DEFAULT_CANISTER_COUNT * DEFAULT_CYCLES_PER_CANISTER + DEFAULT_INSTALL_BUFFER_CYCLES
)


@dataclass(frozen=True)
class GosArtifactKeys:
    backend_wasm_key: str
    frontend_wasm_key: str
    backend_asset: str
    frontend_asset: str


@dataclass(frozen=True)
class GosCatalog:
    """Declares codex/extension catalog seeding for a GOS implementation."""

    codices_repo_suffix: str
    extensions_repo_suffix: str


@dataclass(frozen=True)
class GosImplementation:
    id: str
    label: str
    default_version: str
    release_repo: str
    artifacts: GosArtifactKeys
    loader_profile: str
    catalog: GosCatalog | None = None
    wasm_type: str = "basilisk"
    available: bool = True
    unavailable_reason: str | None = None


GOS_IMPLEMENTATIONS: Final[dict[str, GosImplementation]] = {
    "realms-gos": GosImplementation(
        id="realms-gos",
        label="Realms GOS",
        default_version="v0.3.1",
        release_repo="smart-social-contracts/realms",
        artifacts=GosArtifactKeys(
            backend_wasm_key="realm-backend",
            frontend_wasm_key="realm-assets",
            backend_asset="realm_backend.wasm.gz",
            frontend_asset="realm_frontend.tar.gz",
        ),
        loader_profile="realms-iframe-v1",
        catalog=GosCatalog(
            codices_repo_suffix="realms-codices",
            extensions_repo_suffix="realms-extensions",
        ),
        available=True,
    ),
    "chora-gos": GosImplementation(
        id="chora-gos",
        label="Chora GOS",
        default_version="v0.1.0",
        release_repo="smart-social-contracts/chora-gos",
        artifacts=GosArtifactKeys(
            backend_wasm_key="chora-backend",
            frontend_wasm_key="chora-assets",
            backend_asset="chora_backend.wasm.gz",
            frontend_asset="chora_frontend.tar.gz",
        ),
        loader_profile="chora-iframe-v1",
        wasm_type="motoko",
        available=True,
    ),
}

AVAILABLE_GOS_IDS: Final[tuple[str, ...]] = tuple(
    impl.id for impl in GOS_IMPLEMENTATIONS.values() if impl.available
)
