"""Regression tests for registry request_deployment provisioning triggers."""

import ast
import os


def test_request_deployment_does_not_schedule_casals_provision():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    main_path = os.path.join(repo_root, "src/realm_registry_backend/main.py")
    with open(main_path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read(), filename=main_path)

    fn = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "request_deployment"
    )
    called_names = {
        node.func.id
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_schedule_casals_provision" not in called_names


def test_schedule_casals_provision_helper_removed():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    main_path = os.path.join(repo_root, "src/realm_registry_backend/main.py")
    with open(main_path, encoding="utf-8") as fh:
        source = fh.read()
    assert "def _schedule_casals_provision" not in source
