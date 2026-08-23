"""Tests for Realms marketplace checkout resolution and backend wiring."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from gaas.descriptor import Descriptor
from gaas.marketplace import (
    MarketplaceError,
    configure_marketplace_backend,
    find_realms_root,
)
from tests.conftest import SAMPLE_DESCRIPTOR, VALID_CANISTER_ID


def _descriptor(**overrides) -> Descriptor:
    data = dict(SAMPLE_DESCRIPTOR)
    data.update(overrides)
    return Descriptor.model_validate(data)


def _write_backend_main(root: Path) -> None:
    main = root / "src" / "marketplace_backend" / "main.py"
    main.parent.mkdir(parents=True, exist_ok=True)
    main.write_text("# marketplace backend\n", encoding="utf-8")


def test_find_realms_root_uses_realms_src(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    realms = tmp_path / "custom-realms"
    _write_backend_main(realms)
    monkeypatch.setenv("REALMS_SRC", str(realms))
    found = find_realms_root(
        _descriptor(),
        gos_repo_root=tmp_path / "gos-as-a-service",
        work_dir=tmp_path / "work",
    )
    assert found == realms.resolve()


def test_find_realms_root_uses_sibling_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("REALMS_SRC", raising=False)
    gos = tmp_path / "gos-as-a-service"
    gos.mkdir()
    realms = tmp_path / "realms"
    _write_backend_main(realms)
    found = find_realms_root(
        _descriptor(),
        gos_repo_root=gos,
        work_dir=tmp_path / "work",
    )
    assert found == realms.resolve()


def test_find_realms_root_rejects_empty_realms_src(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REALMS_SRC", str(tmp_path / "missing"))
    with pytest.raises(MarketplaceError, match="REALMS_SRC"):
        find_realms_root(
            _descriptor(),
            gos_repo_root=tmp_path / "gos-as-a-service",
            work_dir=tmp_path / "work",
        )


@patch("gaas.marketplace.dfx.canister_call")
def test_configure_marketplace_backend_sets_registry_and_billing(mock_call) -> None:
    descriptor = _descriptor(
        canisters={
            "marketplace_backend": VALID_CANISTER_ID,
            "file_registry": "aaaaa-aaaaa-aaaaa-aaaaa-aaa",
        },
        services={"billing_service_principal": VALID_CANISTER_ID},
    )
    configure_marketplace_backend(descriptor, network="ic", identity="deployer")
    methods = [call.args[1] for call in mock_call.call_args_list]
    assert methods == [
        "set_file_registry_canister_id",
        "set_billing_service_principal",
    ]


@patch("gaas.marketplace.dfx.canister_call")
def test_configure_marketplace_backend_skips_when_ids_missing(mock_call) -> None:
    configure_marketplace_backend(_descriptor(), network="ic", identity="deployer")
    mock_call.assert_not_called()