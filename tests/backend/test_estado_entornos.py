"""Tests del informe "estado de los entornos" — sin IC en vivo.

El E2E corre ``scripts/estado_entornos.py --fixtures`` contra el mundo
enlatado de ``fixtures/estado_entornos/`` (ver su README). Los unit tests
cubren los parsers candid, el formato "hace …" y la conversión Zurich.
"""

import importlib.util
import json
import re
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "estado_entornos.py"
_FIXTURES = _REPO_ROOT / "tests" / "backend" / "fixtures" / "estado_entornos"

_spec = importlib.util.spec_from_file_location("estado_entornos", _SCRIPT)
ee = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("estado_entornos", ee)
_spec.loader.exec_module(ee)

NOW = 1788004800  # 2026-08-29 12:00:00 UTC

_PRINCIPAL_RE = re.compile(r"\b[a-z0-9]{5}(?:-[a-z0-9]{5}){3,}-[a-z0-9]{3}\b")


# ---------------------------------------------------------------------------
# Unit tests de formato y parseo
# ---------------------------------------------------------------------------


def test_hace_minutos():
    assert ee.hace(NOW - 20 * 60, NOW) == "hace 20 min"


def test_hace_un_dia_y_tres_horas():
    assert ee.hace(NOW - (27 * 3600), NOW) == "hace 1 día y 3 horas"


def test_hace_singular_y_bordes():
    assert ee.hace(NOW - 30, NOW) == "hace un momento"
    assert ee.hace(NOW - 3600, NOW) == "hace 1 hora"
    assert ee.hace(NOW - 2 * 86400, NOW) == "hace 2 días"
    assert ee.hace(NOW + 60, NOW) == "en el futuro"


def test_zurich_conversion():
    # Agosto → CEST (UTC+2): 10:00 UTC se muestra 12:00.
    assert ee.zurich_str(1787911200) == "2026-08-28 12:00"


def test_parse_build_datetime_release_stamp():
    assert ee.parse_build_datetime("2026-08-28 10:00:00") == 1787911200
    assert ee.parse_build_datetime("2026-08-28T10:00:00") == 1787911200
    assert ee.parse_build_datetime("no es fecha") is None


def test_sniff_epoch_units():
    assert ee.sniff_epoch(1787911200) == 1787911200  # s
    assert ee.sniff_epoch(1787911200000) == 1787911200  # ms
    assert ee.sniff_epoch(1787911200000000000) == 1787911200  # ns
    assert ee.sniff_epoch("1787911200000000000") == 1787911200
    assert ee.sniff_epoch("") is None
    assert ee.sniff_epoch(0) is None


def test_candid_string_escapes():
    raw = '( "{\\"a\\": \\"C:\\\\new\\"}" )'
    assert ee.extract_candid_string(raw) == '{"a": "C:\\new"}'


def test_parse_records_finds_nested_job_records():
    raw = (
        "(variant { Ok = record { jobs = vec { "
        'record { job_id = "job_1"; backend_canister_id = "b"; count = 1 : nat32 }; '
        'record { job_id = "job_2"; backend_canister_id = "c" } '
        "}; count = 2 : nat32 } })"
    )
    jobs = ee.parse_records_with(raw, ("job_id", "backend_canister_id"))
    assert [j["job_id"] for j in jobs] == ["job_1", "job_2"]


def test_parse_status_reply_variants():
    ok = '(variant { Ok = record { version = "0.3.1"; commit = "aa11bb2"; status = "ok" } })'
    assert ee.parse_status_reply(ok)["commit"] == "aa11bb2"
    assert ee.parse_status_reply('(variant { Err = "boom" })') is None


def test_probe_app_status_ignores_placeholders():
    class FakeCli(ee.BaseCli):
        def call_raw(self, cid, method, arg="()"):
            return '(variant { Ok = record { version = "VERSION_PLACEHOLDER"; commit = "COMMIT_HASH_PLACEHOLDER"; commit_datetime = "COMMIT_DATETIME_PLACEHOLDER"; status = "ok" } })'

    assert ee.probe_app_status(FakeCli(), "whatever") is None


# ---------------------------------------------------------------------------
# E2E contra fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def informe(capsys):
    rc = ee.main(["--fixtures", str(_FIXTURES), "--now", str(NOW)])
    out = capsys.readouterr().out
    assert rc == 0
    return out


def _fila(out, pieza):
    for line in out.splitlines():
        if line.strip().startswith(pieza):
            return line
    raise AssertionError(f"fila no encontrada: {pieza}\n{out}")


def test_seis_secciones_en_orden(informe):
    pos = 0
    for env in ("TEST", "STAGING", "DEMO"):
        pos_env = informe.index(f"ENTORNO {env}", pos)
        pos_gaas = informe.index("GaaS (plataforma)", pos_env)
        pos_realms = informe.index("Realms", pos_gaas)
        assert pos_env < pos_gaas < pos_realms
        pos = pos_realms


def test_portal_be_test_con_sha_y_fecha(informe):
    fila = _fila(informe, "Test portal BE")
    assert "aa11bb2" in fila
    assert "0x11111111…" in fila
    assert "2026-08-28 12:00" in fila  # 10:00 UTC → 12:00 Zurich (CEST)
    assert "hace 1 día y 2 horas" in fila


def test_portal_fe_test_via_meta_tags(informe):
    fila = _fila(informe, "Test portal FE")
    assert "ff44ee5" in fila
    assert "2026-08-28 14:30" in fila
    assert "hace 23 horas" in fila


def test_installer_test(informe):
    fila = _fila(informe, "Test installer")
    assert "bb22cc3" in fila
    assert "hace 2 días y 2 horas" in fila


def test_realm_be_via_deploy_record_y_wasm_map(informe):
    # Sin acceso controller al realm: el hash viene del deploy record y el
    # mapa wasm del file_registry aporta versión y fecha de publicación.
    fila = _fila(informe, "realmstest9 BE")
    assert "v0.3.1" in fila
    assert "SHA desconocido" in fila
    assert "0x93a44bbb…" in fila
    assert "2026-08-20 12:00" in fila
    assert "hace 9 días y 2 horas" in fila


def test_realm_fe_con_fecha_de_deploy_y_hash_ilegible(informe):
    fila = _fila(informe, "realmstest9 FE")
    assert "no pude leerla" in fila
    assert "hace 20 min" in fila


def test_staging_casals_be_totalmente_ilegible(informe):
    fila = _fila(informe, "Staging Casals BE")
    assert fila.count("no pude leerla") == 2
    assert "hora desconocida" in fila


def test_staging_portal_fe_sin_stamp_sha_desconocido(informe):
    fila = _fila(informe, "Staging portal FE")
    assert "SHA desconocido" in fila
    assert "0x52525252…" in fila
    assert "hora desconocida" in fila


def test_staging_valencia_ilegible(informe):
    fila = _fila(informe, "Valencia BE")
    assert "no pude leerla" in fila
    assert "hora desconocida" in fila


def test_demo_sin_realms(informe):
    assert "(sin realms registrados o no pude leerlos)" in informe
    # Tras la reconstrucción de demo, el descriptor solo conserva el portal FE
    # (DNS); el resto de piezas se reportan honestamente como ilegibles — no se
    # inventa ningún SHA.
    fila_fe = _fila(informe, "Demo portal FE")
    assert "0x62626262…" in fila_fe
    assert "SHA desconocido" in fila_fe
    fila_be = _fila(informe, "Demo portal BE")
    assert "sin id en descriptor" in fila_be
    assert "no pude leerla" in fila_be


def test_file_registry_fe_solo_donde_existe(informe):
    assert _fila(informe, "Test file registry FE")
    # Solo test lo lista en su descriptor: demo lo perdió en la reconstrucción
    # y staging no lo tiene; la fila no aparece donde no existe.
    assert "Demo file registry FE" not in informe
    assert "Staging file registry FE" not in informe


def test_nunca_imprime_principales(informe):
    assert not _PRINCIPAL_RE.search(
        informe
    ), "la salida no debe contener principals/canister ids"


def test_json_output(capsys):
    rc = ee.main(["--fixtures", str(_FIXTURES), "--now", str(NOW), "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert [e["entorno"] for e in payload["entornos"]] == ["test", "staging", "demo"]
    test_env = payload["entornos"][0]
    piezas = {row["pieza"] for row in test_env["gaas"]}
    assert "Test portal BE" in piezas
    assert "Test file registry FE" in piezas
    realm_be = next(r for r in test_env["realms"] if r["pieza"] == "realmstest9 BE")
    assert realm_be["version"] == "v0.3.1"
    assert realm_be["hash_modulo"].startswith("0x93a44bbb")
    assert realm_be["hace"] == "hace 9 días y 2 horas"
    assert not _PRINCIPAL_RE.search(out), "el JSON tampoco debe llevar principals"


def test_env_filter(capsys):
    rc = ee.main(["--fixtures", str(_FIXTURES), "--now", str(NOW), "--env", "demo"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ENTORNO DEMO" in out
    assert "ENTORNO TEST" not in out


# ---------------------------------------------------------------------------
# Anclaje con el repo real (sin red)
# ---------------------------------------------------------------------------


def test_piezas_gaas_cubren_los_descriptores_reales():
    known = {key for key, _piece, _kind in ee.GAAS_PIECES}
    for env in ("test", "staging", "demo"):
        descriptor = json.loads(
            (_REPO_ROOT / "environments" / f"{env}.json").read_text(encoding="utf-8")
        )
        for key in descriptor.get("canisters", {}):
            assert key in known, f"{env}: {key} no tiene fila GaaS en el informe"


def test_fixtures_cubren_todos_los_entornos():
    for env in ("test", "staging", "demo"):
        assert (_FIXTURES / env).is_dir(), f"falta fixture para {env}"
