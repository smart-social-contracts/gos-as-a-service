"""Every canister whose candid declares init arguments needs an ``init_arg``.

``dfx deploy <name>`` fails with "Expected arguments but found none" when the
candid service takes init parameters and dfx.json supplies nothing — which is
how the CI integration job died on `dfx deploy realm_registry_backend`. The
Basilisk canisters declare ``service : (text) -> {…}`` because their ``@init``
takes a config JSON string, so their entry needs the argument spelled out.
"""

import json
import os
import re

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

# ``service : (text) -> {`` (init args) vs ``service : {`` (none).
_SERVICE_WITH_INIT = re.compile(r"^service\s*:\s*\(([^)]*)\)\s*->", re.MULTILINE)


def _dfx_json() -> dict:
    with open(os.path.join(_REPO_ROOT, "dfx.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _local_candid_canisters():
    """(name, config, candid path) for canisters whose candid lives in this repo."""
    for name, config in (_dfx_json().get("canisters") or {}).items():
        candid = (config.get("candid") or "").strip()
        if not candid or candid.startswith("http"):
            continue
        path = os.path.join(_REPO_ROOT, candid)
        if os.path.isfile(path):
            yield name, config, path


def _init_params(candid_path: str) -> str:
    with open(candid_path, encoding="utf-8") as fh:
        match = _SERVICE_WITH_INIT.search(fh.read())
    return (match.group(1).strip() if match else "")


def test_canisters_with_init_params_declare_an_init_arg():
    missing = []
    for name, config, path in _local_candid_canisters():
        if not _init_params(path):
            continue
        if not (config.get("init_arg") or config.get("init_arg_file")):
            missing.append(name)
    assert not missing, (
        "dfx deploy will fail with 'Expected arguments but found none' for: "
        f"{', '.join(missing)} — add an init_arg to dfx.json"
    )


def test_the_basilisk_backends_are_covered_by_that_rule():
    """Guard the guard: these two are the ones that broke CI."""
    covered = {
        name: _init_params(path)
        for name, _config, path in _local_candid_canisters()
    }
    assert covered.get("realm_registry_backend") == "text"
    assert covered.get("realm_installer") == "text"


def test_declared_init_args_are_candid_text_tuples():
    for name, config, path in _local_candid_canisters():
        init_arg = (config.get("init_arg") or "").strip()
        if not init_arg:
            continue
        assert init_arg.startswith("(") and init_arg.endswith(")"), (
            f"{name}: init_arg must be a candid tuple, got {init_arg!r}"
        )
        if _init_params(path) == "text":
            assert '"' in init_arg, f"{name}: init_arg must carry a text value"
