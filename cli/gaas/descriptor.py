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
CANISTER_ID_RE = re.compile(r"^[a-z0-9]{5}(?:-[a-z0-9]{5}){3,10}-[a-z]{3}$")
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
            if not CANISTER_ID_RE.match(principal):
                raise ValueError(
                    f"casals.commanders[{index}]: invalid principal {entry!r}"
                )
            normalized.append(principal)
        return normalized


class ServicesConfig(BaseModel):
    billing_url: str | None = None
    deploy_url: str | None = None
    monitor_url: str | None = None
    # Lives on ServicesConfig (with billing_url) — open_mode controls whether the
    # registry skips credit holds during realm deploy/upgrade, independent of whether
    # a billing URL is configured for the frontend.
    open_mode: bool | None = None

    @field_validator("billing_url", "deploy_url", "monitor_url")
    @classmethod
    def validate_https_url(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not HTTPS_URL_RE.match(value):
            raise ValueError(f"service URL must be https (got {value!r})")
        return value


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

    @field_validator("backend_id")
    @classmethod
    def validate_backend_id(cls, value: str | None) -> str | None:
        if value is None or value == "":
            return None
        if not CANISTER_ID_RE.match(value):
            raise ValueError(f"multisig.backend_id: invalid canister ID {value!r}")
        return value


class DnsConfig(BaseModel):
    provider: str = "manual"


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
    flags: dict[str, bool] = Field(default_factory=dict)
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
            raise ValueError(
                f"unknown canister name(s): {', '.join(sorted(unknown))}; "
                f"known: {', '.join(KNOWN_CANISTER_NAMES)}"
            )
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
