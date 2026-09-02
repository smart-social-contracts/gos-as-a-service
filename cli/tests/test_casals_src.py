"""Tests for Casals checkout discovery and fail-fast require."""

from __future__ import annotations

from pathlib import Path

import pytest

from gaas.platform import (
    PlatformError,
    is_casals_checkout,
    require_casals_checkout,
    resolve_casals_src,
)


def _make_casals(root: Path) -> Path:
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.py").write_text("pass\n", encoding="utf-8")
    (root / "casals_backend.did").write_text("service : {}\n", encoding="utf-8")
    return root


def _no_gos(start=None):
    raise PlatformError("no gos")


def _isolate(monkeypatch, tmp_path: Path) -> Path:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    monkeypatch.delenv("CASALS_SRC", raising=False)
    monkeypatch.setattr("gaas.platform.find_gos_repo_root", _no_gos)
    monkeypatch.setattr("gaas.platform._SRV_CASALS", tmp_path / "srv-missing")
    return cwd


def test_is_casals_checkout_requires_both_markers(tmp_path: Path) -> None:
    root = tmp_path / "Casals"
    root.mkdir()
    (root / "src").mkdir()
    (root / "src" / "main.py").write_text("pass\n", encoding="utf-8")
    assert is_casals_checkout(root) is False
    (root / "casals_backend.did").write_text("service : {}\n", encoding="utf-8")
    assert is_casals_checkout(root) is True


def test_resolve_casals_src_explicit(tmp_path: Path, monkeypatch) -> None:
    _isolate(monkeypatch, tmp_path)
    casals = _make_casals(tmp_path / "explicit-Casals")
    assert resolve_casals_src(casals) == casals.resolve()


def test_resolve_casals_src_explicit_rejects_invalid(tmp_path: Path) -> None:
    with pytest.raises(PlatformError, match="--casals-src"):
        resolve_casals_src(tmp_path / "not-casals")


def test_resolve_casals_src_env(tmp_path: Path, monkeypatch) -> None:
    _isolate(monkeypatch, tmp_path)
    casals = _make_casals(tmp_path / "env-Casals")
    monkeypatch.setenv("CASALS_SRC", str(casals))
    assert resolve_casals_src() == casals.resolve()


def test_resolve_casals_src_env_rejects_invalid(tmp_path: Path, monkeypatch) -> None:
    _isolate(monkeypatch, tmp_path)
    monkeypatch.setenv("CASALS_SRC", str(tmp_path / "bogus"))
    with pytest.raises(PlatformError, match="CASALS_SRC="):
        resolve_casals_src()


def test_resolve_casals_src_sibling_of_gos(tmp_path: Path, monkeypatch) -> None:
    _isolate(monkeypatch, tmp_path)
    gos = tmp_path / "gos-as-a-service"
    gos.mkdir()
    casals = _make_casals(tmp_path / "Casals")
    monkeypatch.setattr("gaas.platform.find_gos_repo_root", lambda start=None: gos)
    assert resolve_casals_src() == casals.resolve()


def test_resolve_casals_src_nested_in_gos(tmp_path: Path, monkeypatch) -> None:
    _isolate(monkeypatch, tmp_path)
    gos = tmp_path / "gos-as-a-service"
    gos.mkdir()
    casals = _make_casals(gos / "Casals")
    monkeypatch.setattr("gaas.platform.find_gos_repo_root", lambda start=None: gos)
    assert resolve_casals_src() == casals.resolve()


def test_resolve_casals_src_cwd_sibling(tmp_path: Path, monkeypatch) -> None:
    _isolate(monkeypatch, tmp_path)
    casals = _make_casals(tmp_path / "Casals")
    realms = tmp_path / "realms"
    realms.mkdir()
    monkeypatch.chdir(realms)
    assert resolve_casals_src() == casals.resolve()


def test_resolve_casals_src_missing_returns_none(tmp_path: Path, monkeypatch) -> None:
    _isolate(monkeypatch, tmp_path)
    assert resolve_casals_src() is None


def test_require_casals_checkout_explains_how_to_fix(
    tmp_path: Path, monkeypatch
) -> None:
    _isolate(monkeypatch, tmp_path)
    with pytest.raises(PlatformError, match="--casals-src"):
        require_casals_checkout()
