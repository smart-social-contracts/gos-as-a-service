"""Pydantic models for the GaaS deployment descriptor."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from gaas.known import (
    DEFAULT_CASALS_RELEASE_REPO,
    DEFAULT_CASALS_VERSION,
    DEFAULT_PLATFORM_RELEASE_REPO,
    GOS_IMPLEMENTATIONS,
    GosCatalog,
    KNOWN_CANISTER_NAMES,
)
from gaas.versions import VERSION_TAG_RE, validate_descriptor_version

SLUG_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")
# Canister IDs end in a 3-letter CRC (typically -cai). User principals use the
# same base32-grouped shape but the final group may include digits (e.g. -2ae).
CANISTER_ID_RE = re.compile(r"^[a-z0-9]{5}(?:-[a-z0-9]{5}){3,10}-[a-z]{3}$")
PRINCIPAL_RE = re.compile(r"^[a-z0-9]{5}(?:-[a-z0-9]{5}){3,10}-[a-z0-9]{1,3}$")
HOSTNAME_RE = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$",
    re.IGNORECASE,
)
HTTPS_URL_RE = re.compile(r"^https://[^\s/]+(?:/[^\s]*)?$", re.IGNORECASE)


class GosArtifacts(BaseModel):
    backend_wasm_key: str
    frontend_wasm_key: str
    backend_asset: str | None = None
    frontend_asset: str | None = None

    def resolved_backend_asset(self, implementation: str) -> str:
        if self.backend_asset:
            return self.backend_asset
        impl = GOS_IMPLEMENTATIONS.get(implementation)
        if impl:
            return impl.artifacts.backend_asset
        raise ValueError(f"no backend_asset for unknown implementation {implementation!r}")

    def resolved_frontend_asset(self, implementation: str) -> str:
        if self.frontend_asset:
            return self.frontend_asset
        impl = GOS_IMPLEMENTATIONS.get(implementation)
        if impl:
            return impl.artifacts.frontend_asset
        raise ValueError(
            f"no frontend_asset for unknown implementation {implementation!r}"
        )


class GosCatalogConfig(BaseModel):
    codices_repo_suffix: str
    extensions_repo_suffix: str

    @field_validator("codices_repo_suffix", "extensions_repo_suffix")
    @classmethod
    def validate_repo_suffix(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or "/" in normalized:
            raise ValueError(
                "catalog repo suffix must be a non-empty repo name without '/'"
            )
        return normalized

    def to_gos_catalog(self) -> GosCatalog:
        return GosCatalog(
            codices_repo_suffix=self.codices_repo_suffix,
            extensions_repo_suffix=self.extensions_repo_suffix,
        )


class GosEntry(BaseModel):
    implementation: str
    version: str
    release_repo: str
    artifacts: GosArtifacts
    loader_profile: str
    catalog: GosCatalogConfig | None = None

    def resolved_catalog(self) -> GosCatalog | None:
        """Effective codex/extension catalog for seeding.

        Absent ``catalog`` in the descriptor uses the known implementation default.
        Explicit ``null`` disables seeding. A non-null object overrides the default.
        """
        if "catalog" in self.model_fields_set:
            if self.catalog is None:
                return None
            return self.catalog.to_gos_catalog()
        impl = GOS_IMPLEMENTATIONS.get(self.implementation)
        return impl.catalog if impl else None

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        try:
            return validate_descriptor_version(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class CasalsConfig(BaseModel):
    version: str
    release_repo: str = DEFAULT_CASALS_RELEASE_REPO
    commanders: list[str] = Field(default_factory=list)

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        try:
            return validate_descriptor_version(value)
        except ValueError as exc:
            raise ValueError(f"casals.version: {exc}") from exc

    @field_validator("commanders")
    @classmethod
    def validate_commanders(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for index, entry in enumerate(value):
            principal = entry.strip() if isinstance(entry, str) else ""
            if not principal:
                raise ValueError(f"casals.commanders[{index}]: principal must be non-empty")
            if not PRINCIPAL_RE.match(principal):
                raise ValueError(
                    f"casals.commanders[{index}]: invalid principal {entry!r}"
                )
            normalized.append(principal)
        return normalized


class ServicesConfig(BaseModel):
    # Public HTTPS URL for credits / Stripe billing; default unset (open mode when absent).
    billing_url: str | None = None
    deploy_url: str | None = None
    # Public HTTPS URL for the off-chain Casals cycles/health monitor; default unset.
    monitor_url: str | None = None
    # Public IC principal the monitor service uses; default unset (not a secret).
    monitor_principal: str | None = None
    # Public IC principal of the realms-billing host; default unset (not a secret).
    billing_service_principal: str | None = None
    # Deprecated alias — prefer flags.can_test_mode. Still read by the resolver.
    open_mode: bool | None = None

    @field_validator("billing_url", "deploy_url", "monitor_url")
    @classmethod
    def validate_https_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not HTTPS_URL_RE.match(value):
            raise ValueError(f"service URL must be https (got {value!r})")
        return value

    @field_validator("monitor_principal", "billing_service_principal")
    @classmethod
    def validate_service_principal(cls, value: str | None, info) -> str | None:
        if value is None or value == "":
            return None
        principal = value.strip()
        field = info.field_name
        if not principal:
            raise ValueError(f"services.{field} must be non-empty when set")
        if not PRINCIPAL_RE.match(principal):
            raise ValueError(f"services.{field}: invalid principal {value!r}")
        return principal


class PlatformConfig(BaseModel):
    version: str
    release_repo: str = DEFAULT_PLATFORM_RELEASE_REPO

    @field_validator("version")
    @classmethod
    def validate_version(cls, value: str) -> str:
        if not VERSION_TAG_RE.match(value):
            raise ValueError(f"platform.version must match vX.Y.Z (got {value!r})")
        return value


class MultisigConfig(BaseModel):
    backend_id: str | None = None
    # Sole / committee signers for the governance multisig. Required for a
    # finished deploy: phase configure_multisig calls Motoko `configure` with
    # these principals at `threshold` (default 1 → 1-of-N). When empty, gaas
    # falls back to the deployer identity only (legacy / bootstrap).
    signers: list[str] = Field(default_factory=list)
    threshold: int = 1

    @field_validator("backend_id")
    @classmethod
    def validate_backend_id(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not CANISTER_ID_RE.match(value):
            raise ValueError(f"multisig.backend_id: invalid canister ID {value!r}")
        return value

    @field_validator("signers")
    @classmethod
    def validate_signers(cls, value: list[str]) -> list[str]:
        cleaned: list[str] = []
        for index, entry in enumerate(value or []):
            principal = (entry or "").strip()
            if not principal:
                raise ValueError(f"multisig.signers[{index}]: principal must be non-empty")
            if not PRINCIPAL_RE.match(principal):
                raise ValueError(
                    f"multisig.signers[{index}]: invalid principal {entry!r}"
                )
            if principal not in cleaned:
                cleaned.append(principal)
        return cleaned

    @field_validator("threshold")
    @classmethod
    def validate_threshold(cls, value: int) -> int:
        if value < 1:
            raise ValueError("multisig.threshold must be >= 1")
        return value


class CyclesConfig(BaseModel):
    """Unified cycle threshold (TC) for all platform canisters."""

    threshold_tc: float = 2

    @field_validator("threshold_tc")
    @classmethod
    def validate_threshold_tc(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("cycles.threshold_tc must be a positive number")
        return value

    def threshold_cycles(self) -> int:
        return int(self.threshold_tc * 1_000_000_000_000)


class DnsConfig(BaseModel):
    provider: str = "manual"


class MarketplaceConfig(BaseModel):
    """Optional marketplace / approver override for realm manifests."""

    approver_principal: str | None = None

    @field_validator("approver_principal")
    @classmethod
    def validate_approver_principal(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        principal = value.strip()
        if not principal:
            raise ValueError("marketplace.approver_principal must be non-empty when set")
        return principal


class Descriptor(BaseModel):
    version: int = 1
    name: str
    domain: str
    gos: list[GosEntry]
    canisters: dict[str, str] = Field(default_factory=dict)
    casals: CasalsConfig
    multisig: MultisigConfig = Field(default_factory=MultisigConfig)
    platform: PlatformConfig | None = None
    services: ServicesConfig = Field(default_factory=ServicesConfig)
    marketplace: MarketplaceConfig | None = None
    flags: dict[str, bool] = Field(default_factory=dict)  # can_test_mode: skip billing credit checks
    test_flags: dict[str, bool] = Field(default_factory=dict)
    cycles: CyclesConfig = Field(default_factory=CyclesConfig)
    dns: DnsConfig = Field(default_factory=DnsConfig)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not SLUG_RE.match(value):
            raise ValueError(
                f"name must be slug-safe lowercase alphanumeric with hyphens (got {value!r})"
            )
        return value

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        normalized = value.rstrip(".").lower()
        if not HOSTNAME_RE.match(normalized):
            raise ValueError(f"domain must be a valid hostname (got {value!r})")
        return normalized

    @field_validator("canisters")
    @classmethod
    def validate_canister_keys(cls, value: dict[str, str]) -> dict[str, str]:
        unknown = set(value) - set(KNOWN_CANISTER_NAMES)
        if unknown:
            # Leftover Realms GOS product keys in old descriptors are ignored.
            return {k: v for k, v in value.items() if k in KNOWN_CANISTER_NAMES}
        return value

    @field_validator("test_flags", mode="before")
    @classmethod
    def validate_test_flags(cls, value: object) -> dict[str, bool]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("test_flags must be an object")
        for key, flag in value.items():
            if not isinstance(flag, bool):
                raise ValueError(f"test_flags.{key} must be a boolean")
        return value

    @model_validator(mode="after")
    def validate_canister_ids(self) -> Descriptor:
        for name, canister_id in self.canisters.items():
            if not CANISTER_ID_RE.match(canister_id):
                raise ValueError(
                    f"canisters.{name}: invalid IC principal/canister ID {canister_id!r}"
                )
        return self

    @classmethod
    def load(cls, path: str | Path) -> Descriptor:
        path = Path(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls.model_validate(data)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(
            self.model_dump(mode="json", exclude_none=True),
            indent=2,
            sort_keys=False,
        )
        payload += "\n"
        fd, tmp_path = tempfile.mkstemp(
            dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def validate_descriptor(self) -> list[str]:
        errors: list[str] = []
        try:
            self.model_validate(self.model_dump(mode="python"))
        except Exception as exc:
            errors.append(str(exc))
            return errors

        if self.version != 1:
            errors.append(f"unsupported descriptor version {self.version} (expected 1)")

        if not self.gos:
            errors.append("gos must contain at least one implementation")

        frontend_id = self.canisters.get("realm_registry_frontend")
        if frontend_id and not CANISTER_ID_RE.match(frontend_id):
            errors.append(
                f"canisters.realm_registry_frontend: invalid ID {frontend_id!r}"
            )

        return errors

    def set_canister_id(self, name: str, canister_id: str) -> None:
        if name not in KNOWN_CANISTER_NAMES:
            raise ValueError(f"unknown canister name: {name}")
        if not CANISTER_ID_RE.match(canister_id):
            raise ValueError(f"invalid canister ID: {canister_id!r}")
        self.canisters[name] = canister_id

    def threshold_cycles(self) -> int:
        return self.cycles.threshold_cycles()

    def set_multisig_backend_id(self, canister_id: str) -> None:
        if not CANISTER_ID_RE.match(canister_id):
            raise ValueError(f"invalid multisig backend ID: {canister_id!r}")
        self.multisig.backend_id = canister_id

    def to_pretty_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json", exclude_none=True),
            indent=2,
            sort_keys=False,
        ) + "\n"
