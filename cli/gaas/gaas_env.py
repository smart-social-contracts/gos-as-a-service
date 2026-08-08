"""Generate gaas-env.json for registry frontend builds."""

from __future__ import annotations

import json
from pathlib import Path

from gaas.descriptor import Descriptor


def frontend_ic_origin(canister_id: str) -> str:
    return f"https://{canister_id}.icp0.io"


def build_gaas_env(descriptor: Descriptor, network: str) -> dict:
    frontend_id = descriptor.canisters.get("realm_registry_frontend", "")
    ii_origins: list[str] = []
    if frontend_id:
        ii_origins.append(frontend_ic_origin(frontend_id))

    payload: dict = {
        "name": descriptor.name,
        "domain": descriptor.domain,
        "network": network,
        "services": {},
        "canisters": {
            "ic": dict(descriptor.canisters),
        },
        "gos": [
            {
                "implementation": entry.implementation,
                "version": entry.version,
                "loader_profile": entry.loader_profile,
                "available": True,
            }
            for entry in descriptor.gos
        ],
        "ii_alternative_origins": ii_origins,
    }
    if descriptor.services.billing_url:
        payload["services"]["billing_url"] = descriptor.services.billing_url
    if descriptor.services.deploy_url:
        payload["services"]["deploy_url"] = descriptor.services.deploy_url
    if not payload["services"]:
        del payload["services"]
    return payload


def write_gaas_env(repo_root: Path, descriptor: Descriptor, network: str) -> Path:
    path = repo_root / "gaas-env.json"
    payload = build_gaas_env(descriptor, network)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def remove_gaas_env(repo_root: Path) -> None:
    path = repo_root / "gaas-env.json"
    if path.is_file():
        path.unlink()
