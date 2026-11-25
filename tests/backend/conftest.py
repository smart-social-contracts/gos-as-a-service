"""Fixtures for the tests that run the installer on a simulated IC (``installer_sim``)."""

import pytest

import installer_sim


@pytest.fixture
def installer():
    """The installer's real main.py, with every installer and registry row removed around the test."""
    module = installer_sim.load_installer()
    installer_sim.empty_databases(module)
    yield module
    installer_sim.empty_databases(module)
