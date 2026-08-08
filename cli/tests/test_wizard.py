"""Tests for the interactive wizard with mocked questionary."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from gaas.wizard import run_wizard


def test_wizard_builds_descriptor(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    answers = iter(
        [
            "myenv",
            "myenv.gos.earth",
            "ic",
            "deployer",
            "Build from local gos-as-a-service checkout",
            ["realms-gos"],
            "v0.3.1",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "v0.3.0",
            "",
            "",
            "",
            False,
            str(tmp_path / "myenv.gaas.json"),
        ]
    )

    def fake_ask(*args, **kwargs):
        method = MagicMock()
        method.ask.return_value = next(answers)
        return method

    prompt = MagicMock()
    prompt.text.side_effect = fake_ask
    prompt.select.side_effect = fake_ask
    prompt.checkbox.side_effect = fake_ask
    prompt.confirm.side_effect = fake_ask

    desc, identity, network, output_path = run_wizard(
        identity=None,
        network=None,
        ask=prompt,
    )

    assert desc.name == "myenv"
    assert desc.domain == "myenv.gos.earth"
    assert desc.gos[0].version == "v0.3.1"
    assert desc.casals.version == "v0.3.0"
    assert desc.dns.provider == "manual"
    assert desc.flags.get("open_mode") is not True
    assert identity == "deployer"
    assert network == "ic"
    assert output_path == tmp_path / "myenv.gaas.json"


def test_wizard_honors_flag_overrides() -> None:
    answers = iter(
        [
            "flagenv",
            "flag.gos.earth",
            "Build from local gos-as-a-service checkout",
            ["realms-gos"],
            "v0.3.1",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "v0.3.0",
            "",
            "",
            "",
            False,
            "./flagenv.gaas.json",
        ]
    )

    def fake_ask(*args, **kwargs):
        method = MagicMock()
        method.ask.return_value = next(answers)
        return method

    prompt = MagicMock()
    prompt.text.side_effect = fake_ask
    prompt.select.side_effect = fake_ask
    prompt.checkbox.side_effect = fake_ask
    prompt.confirm.side_effect = fake_ask

    _desc, identity, network, _path = run_wizard(
        identity="override-id",
        network="local",
        ask=prompt,
    )

    assert identity == "override-id"
    assert network == "local"
    prompt.select.assert_called()


def test_wizard_open_mode_prompt_sets_flag(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    answers = iter(
        [
            "openenv",
            "open.gos.earth",
            "ic",
            "deployer",
            "Build from local gos-as-a-service checkout",
            ["realms-gos"],
            "v0.3.1",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "v0.3.0",
            "",
            "",
            "",
            True,
            str(tmp_path / "openenv.gaas.json"),
        ]
    )

    def fake_ask(*args, **kwargs):
        method = MagicMock()
        method.ask.return_value = next(answers)
        return method

    prompt = MagicMock()
    prompt.text.side_effect = fake_ask
    prompt.select.side_effect = fake_ask
    prompt.checkbox.side_effect = fake_ask
    prompt.confirm.side_effect = fake_ask

    desc, _identity, _network, _output_path = run_wizard(ask=prompt)

    assert desc.flags.get("open_mode") is True
    prompt.confirm.assert_called()


def test_wizard_parses_casals_commanders(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    answers = iter(
        [
            "cmdenv",
            "cmd.gos.earth",
            "ic",
            "deployer",
            "Build from local gos-as-a-service checkout",
            ["realms-gos"],
            "v0.3.1",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "v0.3.0",
            "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa, bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
            "",
            "",
            False,
            str(tmp_path / "cmdenv.gaas.json"),
        ]
    )

    def fake_ask(*args, **kwargs):
        method = MagicMock()
        method.ask.return_value = next(answers)
        return method

    prompt = MagicMock()
    prompt.text.side_effect = fake_ask
    prompt.select.side_effect = fake_ask
    prompt.checkbox.side_effect = fake_ask
    prompt.confirm.side_effect = fake_ask

    desc, _identity, _network, _output_path = run_wizard(ask=prompt)

    assert desc.casals.commanders == [
        "aaaaa-aaaaa-aaaaa-aaaaa-aaaaa-aaa",
        "bbbbb-bbbbb-bbbbb-bbbbb-bbbbb-bbb",
    ]
