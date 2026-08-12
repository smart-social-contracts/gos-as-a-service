"""Unit tests for realm_installer.stand_create_args."""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src/realm_installer"))

from stand_create_args import build_stand_create_args, casals_placement_from_cfg

_EXPLICIT_SUBNET = (
    "bkfrj-6k62g-dycql-7h53p-atvkj-zg4to-gaogh-netha-ptyij-ntsg4-rqe"
)


def test_no_placement_fields():
    args = build_stand_create_args("Deployments", "my-realm", "realm My Realm")
    assert args == {
        "section": "Deployments",
        "name": "my-realm",
        "description": "realm My Realm",
    }


def test_subnet_type_placement():
    args = build_stand_create_args(
        "Deployments", "my-realm", "realm My Realm", subnet_type="european",
    )
    assert args == {
        "section": "Deployments",
        "name": "my-realm",
        "description": "realm My Realm",
        "subnet_type": "european",
    }


def test_explicit_subnet_placement():
    args = build_stand_create_args(
        "Deployments", "my-realm", "realm My Realm", subnet=_EXPLICIT_SUBNET,
    )
    assert args == {
        "section": "Deployments",
        "name": "my-realm",
        "description": "realm My Realm",
        "subnet": _EXPLICIT_SUBNET,
    }


def test_both_set_subnet_wins():
    args = build_stand_create_args(
        "Deployments",
        "my-realm",
        "realm My Realm",
        subnet=_EXPLICIT_SUBNET,
        subnet_type="european",
    )
    assert args == {
        "section": "Deployments",
        "name": "my-realm",
        "description": "realm My Realm",
        "subnet": _EXPLICIT_SUBNET,
    }
    assert "subnet_type" not in args


def test_whitespace_only_treated_as_absent():
    subnet, subnet_type = casals_placement_from_cfg(
        {"subnet": "  ", "subnet_type": "\t"},
    )
    assert subnet == ""
    assert subnet_type == ""

    args = build_stand_create_args(
        "Deployments", "my-realm", "realm My Realm", subnet, subnet_type,
    )
    assert args == {
        "section": "Deployments",
        "name": "my-realm",
        "description": "realm My Realm",
    }


def test_casals_placement_from_cfg_strips_values():
    subnet, subnet_type = casals_placement_from_cfg(
        {"subnet": f"  {_EXPLICIT_SUBNET}  ", "subnet_type": " european "},
    )
    assert subnet == _EXPLICIT_SUBNET
    assert subnet_type == "european"
