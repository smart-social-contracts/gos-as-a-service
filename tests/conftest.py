"""Shared mock database setup for backend unit tests."""

import os
import sys
import time
from unittest.mock import MagicMock

import pytest

# Match Basilisk import resolution (repo root + canister package root).
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src"))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src/realm_registry_backend"))

import _cdk as basilisk  # noqa: E402

mock_ic = MagicMock()
mock_ic.time.return_value = int(time.time() * 1_000_000_000)
basilisk.ic = mock_ic

from ic_python_db import Database  # noqa: E402


class MockStorage:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def insert(self, key, value):
        self.data[key] = value

    def remove(self, key):
        self.data.pop(key, None)

    def items(self):
        return self.data.items()

    def keys(self):
        return self.data.keys()


@pytest.fixture(scope="session", autouse=True)
def _mock_database():
    try:
        Database.init(db_storage=MockStorage(), audit_enabled=False)
    except RuntimeError:
        pass
    yield
