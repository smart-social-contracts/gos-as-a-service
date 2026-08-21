"""CLI tests for marketplace gaas-env wiring."""

from __future__ import annotations

from gaas.descriptor import Descriptor
from gaas.gaas_env import build_gaas_env
from tests.conftest import SAMPLE_DESCRIPTOR, VALID_CANISTER_ID


def test_build_gaas_env_defaults_marketplace_to_deployer() -> None:
    desc = Descriptor.model_validate(SAMPLE_DESCRIPTOR)
    env = build_gaas_env(desc, "ic", deployer_principal="deployer-principal-id")
    assert env["canisters"]["marketplace_backend"]["ic"] == "deployer-principal-id"


def test_build_gaas_env_keeps_configured_marketplace_canister() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["canisters"] = {"marketplace_backend": VALID_CANISTER_ID}
    desc = Descriptor.model_validate(data)
    env = build_gaas_env(desc, "ic", deployer_principal="deployer-principal-id")
    assert env["canisters"]["marketplace_backend"]["ic"] == VALID_CANISTER_ID


def test_build_gaas_env_marketplace_override() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["marketplace"] = {"approver_principal": "custom-approver"}
    desc = Descriptor.model_validate(data)
    env = build_gaas_env(desc, "ic", deployer_principal="deployer-principal-id")
    assert env["canisters"]["marketplace_backend"]["ic"] == "custom-approver"
