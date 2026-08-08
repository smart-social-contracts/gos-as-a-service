"""Tests for descriptor version validation and deploy-time resolution."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from gaas.artifacts import ArtifactError
from gaas.descriptor import Descriptor
from gaas.versions import (
    clear_latest_tag_cache,
    normalize_catalog_version,
    resolve_deploy_version,
    resolve_latest_tag,
    validate_descriptor_version,
)
from tests.conftest import SAMPLE_DESCRIPTOR


@pytest.fixture(autouse=True)
def _clear_latest_cache() -> None:
    clear_latest_tag_cache()
    yield
    clear_latest_tag_cache()


@pytest.mark.parametrize(
    "value,expected",
    [
        ("main", "main"),
        ("MAIN", "main"),
        ("latest", "latest"),
        ("LATEST", "latest"),
        ("v0.4.0", "v0.4.0"),
    ],
)
def test_validate_descriptor_version_accepts_special(value: str, expected: str) -> None:
    assert validate_descriptor_version(value) == expected


@pytest.mark.parametrize("value", ["0.4.0", "mainline", "v1", ""])
def test_validate_descriptor_version_rejects_invalid(value: str) -> None:
    with pytest.raises(ValueError, match="vX.Y.Z|main|latest"):
        validate_descriptor_version(value)


def test_descriptor_accepts_main_and_latest() -> None:
    for version in ("main", "latest"):
        data = dict(SAMPLE_DESCRIPTOR)
        data["gos"] = [{**data["gos"][0], "version": version}]
        data["casals"] = {**data["casals"], "version": version}
        desc = Descriptor.model_validate(data)
        assert desc.gos[0].version == version
        assert desc.casals.version == version


def test_descriptor_rejects_bogus_version() -> None:
    data = dict(SAMPLE_DESCRIPTOR)
    data["gos"] = [{**data["gos"][0], "version": "not-a-version"}]
    with pytest.raises(ValidationError, match="vX.Y.Z|main|latest"):
        Descriptor.model_validate(data)


def test_normalize_catalog_version() -> None:
    assert normalize_catalog_version("main") == "main"
    assert normalize_catalog_version("v0.4.0") == "0.4.0"
    assert normalize_catalog_version("0.4.0") == "0.4.0"


def test_resolve_latest_tag_from_github_api() -> None:
    session = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"tag_name": "v0.4.0"}
    session.get.return_value = response

    tag = resolve_latest_tag("smart-social-contracts/realms", session=session)
    assert tag == "v0.4.0"
    assert session.get.call_count == 1

    # Cached for the same process.
    assert resolve_latest_tag("smart-social-contracts/realms", session=session) == "v0.4.0"
    assert session.get.call_count == 1


def test_resolve_latest_tag_invalid_response() -> None:
    session = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"tag_name": "not-semver"}
    session.get.return_value = response

    with pytest.raises(ArtifactError, match="invalid tag"):
        resolve_latest_tag("org/repo", session=session)


def test_resolve_deploy_version_main_and_latest() -> None:
    main = resolve_deploy_version("main", "smart-social-contracts/realms")
    assert main.source_build is True
    assert main.catalog_version == "main"
    assert main.fetch_tag is None

    session = MagicMock()
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {"tag_name": "v0.3.1"}
    session.get.return_value = response

    latest = resolve_deploy_version(
        "latest", "smart-social-contracts/realms", session=session
    )
    assert latest.source_build is False
    assert latest.fetch_tag == "v0.3.1"
    assert latest.catalog_version == "0.3.1"
