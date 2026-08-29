#!/usr/bin/env python3
"""Estado de los entornos — informe de solo lectura de Test / Staging / Demo.

Imprime, para cada entorno (Test, Staging, Demo), dos secciones:

  * GaaS   — todas las piezas de plataforma (portal FE/BE, installer, Casals
             FE/BE, marketplace FE/BE, file_registry y su FE si existe).
  * Realms — cada realm vivo registrado en el registry del entorno (FE y BE).

Cada fila muestra: nombre de la pieza, SHA corto de GitHub si se puede leer,
hash de módulo corto, fecha/hora del build en Europe/Zurich y un "hace …"
humano (hace 20 min, hace 1 día y 3 horas). Lo que no se puede leer se dice
explícitamente: ``no pude leerla`` / ``hora desconocida`` / ``SHA desconocido``.
Nunca se inventa un valor.

Fuentes de datos (todas de solo lectura):

  * ``environments/{test,staging,demo}.json`` — inventario de canisters.
  * ``dfx canister status`` / ``icp canister status`` — module_hash (solo
    funciona donde la identidad es controller; si no, se marca ilegible).
  * ``status()`` (query) en registry / installer — llevan commit y
    commit_datetime estampados por el release workflow.
  * Meta tags ``commit-hash`` / ``commit-datetime`` / ``version`` del HTML del
    portal (y de cualquier FE que los estampe).
  * ``list_realms`` (query) del registry — inventario de realms vivos.
  * ``list_deployment_jobs`` (query) del installer — historial de deploys con
    ``actual_wasm_hash`` (module hash) y ``completed_at`` por realm.
  * file_registry ``list_namespaces`` / ``list_files`` / ``get_file_chunk`` —
    mapa module_hash → (versión, fecha de publicación) para WASMs `wasm/**`
    (descarga + gunzip + sha256; desactivar con ``--no-wasm-map``).

Uso:

  ./scripts/estado_entornos.sh --identity deployer
  python3 scripts/estado_entornos.py --identity my-dev-identity1
  python3 scripts/estado_entornos.py --fixtures tests/backend/fixtures/estado_entornos

Solo stdlib. Nunca hace upgrade, reinstall ni escrituras: todas las llamadas
de canister son ``--query`` y ``canister status`` es lectura del management.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    from zoneinfo import ZoneInfo

    _ZURICH = ZoneInfo("Europe/Zurich")
except Exception:  # sin tzdata — no inventar: se muestra UTC etiquetado
    _ZURICH = None

REPO_ROOT = Path(__file__).resolve().parent.parent

ENVIRONMENTS = ("test", "staging", "demo")
ENV_LABEL = {"test": "Test", "staging": "Staging", "demo": "Demo"}

# Piezas GaaS en orden de informe: (clave en descriptor `canisters`, nombre
# visible, tipo). El FE de file_registry solo aparece si el descriptor lo lista.
GAAS_PIECES: tuple[tuple[str, str, str], ...] = (
    ("realm_registry_frontend", "portal FE", "frontend"),
    ("realm_registry_backend", "portal BE", "backend"),
    ("realm_installer", "installer", "backend"),
    ("casals_frontend", "Casals FE", "frontend"),
    ("casals_backend", "Casals BE", "backend"),
    ("marketplace_frontend", "marketplace FE", "frontend"),
    ("marketplace_backend", "marketplace BE", "backend"),
    ("file_registry", "file registry", "backend"),
    ("file_registry_frontend", "file registry FE", "frontend"),
)

# Backends donde merece la pena probar status() con commit estampado.
# (Casals/marketplace son Motoko y hoy no lo llevan; se prueba igualmente —
# una query fallida solo marca el campo como ilegible.)
APP_STATUS_PROBE_KINDS = ("backend",)

NO_LEIDA = "no pude leerla"
HORA_DESCONOCIDA = "hora desconocida"
SHA_DESCONOCIDO = "SHA desconocido"

_CANISTER_ID_RE = re.compile(r"^[a-z0-9]{5}(?:-[a-z0-9]{5}){3,10}-[a-z]{3}$")
_PRINCIPAL_LIKE_RE = re.compile(r"\b[a-z0-9]{5}(?:-[a-z0-9]{5}){3,10}-[a-z0-9]{3}\b")
_MODULE_HASH_RE = re.compile(r"module\s*hash:\s*(0x[0-9a-fA-F]+|none)", re.I)
_STATUS_LINE_RE = re.compile(r"^status:\s*(\w+)", re.I | re.M)
_PLACEHOLDER_RE = re.compile(r"PLACEHOLDER|^local$|^dev$", re.I)
_META_RE = re.compile(
    r"<meta\s+[^>]*name=[\"'](?P<name>[a-z-]+)[\"'][^>]*content=[\"'](?P<content>[^\"']*)[\"']",
    re.I,
)
_META_RE_ALT = re.compile(
    r"<meta\s+[^>]*content=[\"'](?P<content>[^\"']*)[\"'][^>]*name=[\"'](?P<name>[a-z-]+)[\"']",
    re.I,
)

_DFX_ENV = {
    "TERM": "xterm",
    "NO_COLOR": "1",
    "DFX_WARNING": "-mainnet_plaintext_identity",
}

# Todos los entornos viven en mainnet; los networks test/staging/demo de
# dfx.json apuntan a icp0.io. Usar `ic` (built-in) hace que el script funcione
# desde cualquier directorio, no solo desde la raíz del repo.
IC_NETWORK = "ic"

_CHUNK = 128 * 1024  # tope servidor de file_registry get_file_chunk


class CliError(RuntimeError):
    """Una llamada al CLI (o su fixture) falló; el campo queda ilegible."""


# ---------------------------------------------------------------------------
# Adaptadores CLI (dfx / icp / fixtures)
# ---------------------------------------------------------------------------


class BaseCli:
    name = "base"

    def canister_status_raw(self, canister_id: str) -> str:
        raise NotImplementedError

    def call_raw(self, canister_id: str, method: str, arg: str = "()") -> str:
        raise NotImplementedError


class SubprocessCli(BaseCli):
    def __init__(self, identity: str | None, timeout: int):
        self.identity = identity
        self.timeout = timeout

    def _run(self, args: list[str]) -> str:
        env = os.environ.copy()
        env.update(_DFX_ENV)
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=env,
                check=False,
            )
        except FileNotFoundError as exc:
            raise CliError(f"ejecutable no encontrado: {args[0]}") from exc
        except subprocess.TimeoutExpired as exc:
            raise CliError(f"timeout ({self.timeout}s): {' '.join(args)}") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise CliError(f"exit {result.returncode}: {detail[-300:]}")
        return result.stdout


class DfxCli(SubprocessCli):
    name = "dfx"

    def canister_status_raw(self, canister_id: str) -> str:
        args = ["dfx", "canister", "--network", IC_NETWORK, "status", canister_id]
        if self.identity:
            args += ["--identity", self.identity]
        return self._run(args)

    def call_raw(self, canister_id: str, method: str, arg: str = "()") -> str:
        args = [
            "dfx",
            "canister",
            "call",
            canister_id,
            method,
            arg,
            "--query",
            "--network",
            IC_NETWORK,
        ]
        if self.identity:
            args += ["--identity", self.identity]
        return self._run(args)


class IcpCli(SubprocessCli):
    name = "icp"

    def canister_status_raw(self, canister_id: str) -> str:
        args = ["icp", "canister", "status", canister_id, "--network", IC_NETWORK]
        if self.identity:
            args += ["--identity", self.identity]
        return self._run(args)

    def call_raw(self, canister_id: str, method: str, arg: str = "()") -> str:
        args = [
            "icp",
            "canister",
            "call",
            canister_id,
            method,
            arg,
            "--network",
            IC_NETWORK,
            "--query",
        ]
        if self.identity:
            args += ["--identity", self.identity]
        return self._run(args)


def detect_cli(prefer: str, identity: str | None, timeout: int) -> BaseCli:
    """Prefiere `icp` si está en PATH; si no, `dfx`."""
    candidates = {"icp": IcpCli, "dfx": DfxCli}
    order = ("icp", "dfx") if prefer == "auto" else (prefer,)
    for name in order:
        if shutil.which(name):
            return candidates[name](identity, timeout)
    if prefer != "auto":
        raise CliError(f"CLI pedido no encontrado en PATH: {prefer}")
    raise CliError("ni `icp` ni `dfx` están en PATH")


def _candid_arg_payload(arg: str) -> str:
    """Extrae el string JSON de un argumento candid `(\"...\")`."""
    try:
        return extract_candid_string(arg)
    except CliError:
        return ""


class FixtureCli(BaseCli):
    """CLI de mentira para `--fixtures`: lee respuestas de un directorio.

    Layout:
      <root>/<env>/status/<canister_id>.txt          salida de canister status
      <root>/<env>/call/<canister_id>/<method>.txt   respuesta candid
      <root>/<env>/call/<canister_id>/list_files__<ns-slug>.txt
      <root>/<env>/objects/<namespace>/<path>.b64    objetos del file_registry
    Un fichero ausente equivale a un error del CLI (p.ej. no controller).
    """

    name = "fixtures"

    def __init__(self, root: Path, env: str):
        self.root = Path(root)
        self.env = env

    def _read(self, path: Path, what: str) -> str:
        if not path.is_file():
            raise CliError(f"fixture ausente ({what}): {path}")
        return path.read_text(encoding="utf-8")

    def canister_status_raw(self, canister_id: str) -> str:
        return self._read(
            self.root / self.env / "status" / f"{canister_id}.txt", "canister status"
        )

    def call_raw(self, canister_id: str, method: str, arg: str = "()") -> str:
        base = self.root / self.env / "call" / canister_id
        if method in ("get_file_size", "get_file_chunk"):
            return self._serve_object(method, arg)
        if method == "list_files":
            ns = ""
            try:
                ns = json.loads(_candid_arg_payload(arg) or "{}").get("namespace", "")
            except json.JSONDecodeError:
                pass
            slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", ns)
            return self._read(base / f"list_files__{slug}.txt", f"list_files {ns}")
        return self._read(base / f"{method}.txt", method)

    def _serve_object(self, method: str, arg: str) -> str:
        import base64

        try:
            params = json.loads(_candid_arg_payload(arg) or "{}")
        except json.JSONDecodeError:
            params = {}
        ns = str(params.get("namespace", ""))
        rel = str(params.get("path", "")).lstrip("/")
        obj = self.root / self.env / "objects" / ns / f"{rel}.b64"
        if not obj.is_file():
            payload = json.dumps({"error": f"Not found: {ns}/{rel}"})
            return f'("{payload}")'
        data = base64.b64decode(obj.read_text(encoding="ascii").strip())
        if method == "get_file_size":
            payload = json.dumps(
                {
                    "size": len(data),
                    "content_type": "application/wasm",
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
            return f'("{payload}")'
        offset = int(params.get("offset", 0))
        length = int(params.get("length", _CHUNK)) or _CHUNK
        length = max(1, min(length, _CHUNK))
        chunk = data[offset : offset + length]
        payload = json.dumps(
            {
                "content_b64": base64.b64encode(chunk).decode("ascii"),
                "offset": offset,
                "length": len(chunk),
                "total_size": len(data),
                "eof": (offset + len(chunk)) >= len(data),
            }
        )
        return f'("{payload}")'


# ---------------------------------------------------------------------------
# HTTP (meta tags de frontends)
# ---------------------------------------------------------------------------


class HttpGetter:
    def __init__(self, timeout: int, fixtures: Path | None = None, env: str = ""):
        self.timeout = timeout
        self.fixtures = fixtures
        self.env = env

    def get(self, url: str) -> str:
        if self.fixtures is not None:
            host = urllib.request.urlparse(url).hostname or ""
            path = self.fixtures / self.env / "http" / f"{host}.html"
            if not path.is_file():
                raise CliError(f"fixture ausente (http): {path}")
            return path.read_text(encoding="utf-8")
        req = urllib.request.Request(url, headers={"User-Agent": "estado-entornos/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read(512 * 1024).decode("utf-8", errors="replace")
        except (urllib.error.URLError, OSError, ValueError) as exc:
            raise CliError(f"HTTP {url}: {exc}") from exc


# ---------------------------------------------------------------------------
# Candid text helpers (stdlib; suficiente para las respuestas que leemos)
# ---------------------------------------------------------------------------

_CANDID_ESCAPE_RE = re.compile(r"\\(?:([0-9a-fA-F]{2})|(.))")
_CANDID_NAMED = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "'": "'", "\\": "\\"}


def decode_candid_text(text: str) -> str:
    """Decodifica escapes candid en una sola pasada (\\\\ antes que \\n)."""
    out: list[str] = []
    hexbuf = bytearray()
    pos = 0

    def flush_hex() -> None:
        nonlocal hexbuf
        if hexbuf:
            out.append(hexbuf.decode("utf-8", errors="replace"))
            hexbuf = bytearray()

    for match in _CANDID_ESCAPE_RE.finditer(text):
        if match.start() > pos:
            flush_hex()
            out.append(text[pos : match.start()])
        hex_digits, named = match.groups()
        if hex_digits is not None:
            hexbuf.append(int(hex_digits, 16))
        else:
            flush_hex()
            out.append(_CANDID_NAMED.get(named, named))
        pos = match.end()
    flush_hex()
    out.append(text[pos:])
    return "".join(out)


def extract_candid_string(raw: str) -> str:
    """`(\"...\")` → contenido decodificado. CliError si no es un string."""
    text = raw.strip()
    if text.startswith("(") and text.endswith(")"):
        text = text[1:-1].strip()
    if text.endswith(","):
        text = text[:-1].strip()
    if not (text.startswith('"') and text.endswith('"')):
        raise CliError(f"no es un string candid: {raw[:80]!r}")
    return decode_candid_text(text[1:-1])


def _scan_blobs(text: str, keyword: str) -> list[str]:
    """Devuelve los cuerpos `{...}` de cada `<keyword> {` respetando strings."""
    blobs: list[str] = []
    i = 0
    needle = re.compile(re.escape(keyword) + r"\s*\{")
    while True:
        match = needle.search(text, i)
        if match is None:
            return blobs
        depth = 0
        in_str = False
        escaped = False
        j = match.end() - 1  # la llave de apertura
        while j < len(text):
            ch = text[j]
            if in_str:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        blobs.append(text[match.end() : j])
                        break
            j += 1
        # Seguir justo después de la llave de apertura: los records anidados
        # (p.ej. jobs dentro de `jobs = vec { record … }`) también importan.
        i = match.end()
        if depth != 0:
            return blobs


def _split_top_level(body: str, sep: str = ";") -> list[str]:
    parts: list[str] = []
    depth = 0
    in_str = False
    escaped = False
    current: list[str] = []
    for ch in body:
        if in_str:
            current.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
            current.append(ch)
        elif ch in "{(":
            depth += 1
            current.append(ch)
        elif ch in "})":
            depth -= 1
            current.append(ch)
        elif ch == sep and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(ch)
    if current:
        parts.append("".join(current))
    return parts


_BARE_VALUE_RE = re.compile(r"^([^:]+?)(?:\s*:\s*[A-Za-z0-9_ ]+)?$")


def parse_flat_record(body: str) -> dict[str, str]:
    """`a = "x"; b = 12 : nat64` → {"a": "x", "b": "12"} (nivel superior)."""
    fields: dict[str, str] = {}
    for part in _split_top_level(body):
        if "=" not in part:
            continue
        key, _, value = part.partition("=")
        key = key.strip().strip('"')
        value = value.strip()
        if not key:
            continue
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            fields[key] = decode_candid_text(value[1:-1])
        elif value.startswith(("record", "vec", "variant", "opt", "principal")):
            fields[key] = value  # crudo; los callers solo usan campos planos
        else:
            match = _BARE_VALUE_RE.match(value)
            token = (match.group(1) if match else value).strip()
            fields[key] = token.replace("_", "")
    return fields


def parse_records_with(
    text: str, required_keys: tuple[str, ...]
) -> list[dict[str, str]]:
    """Todos los `record {...}` del texto que contienen las claves pedidas."""
    out: list[dict[str, str]] = []
    for blob in _scan_blobs(text, "record"):
        fields = parse_flat_record(blob)
        if all(k in fields for k in required_keys):
            out.append(fields)
    return out


def parse_status_reply(raw: str) -> dict[str, str] | None:
    """`variant { Ok = record { … } }` o text JSON; None si Err/ilegible."""
    if re.search(r"variant\s*\{\s*Err", raw):
        return None
    for fields in parse_records_with(raw, ("commit",)):
        return fields
    for fields in parse_records_with(raw, ("version", "status")):
        return fields
    try:
        data = json.loads(extract_candid_string(raw))
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except (CliError, json.JSONDecodeError):
        pass
    return None


# ---------------------------------------------------------------------------
# Probes
# ---------------------------------------------------------------------------


def probe_module_hash(cli: BaseCli, canister_id: str) -> tuple[str | None, str | None]:
    """(module_hash con 0x, status) o (None, None) si no somos controller."""
    raw = cli.canister_status_raw(canister_id)
    module_hash = None
    match = _MODULE_HASH_RE.search(raw)
    if match and match.group(1).lower() != "none":
        module_hash = match.group(1).lower()
    status = None
    status_match = _STATUS_LINE_RE.search(raw)
    if status_match:
        status = status_match.group(1).lower()
    return module_hash, status


def probe_app_status(cli: BaseCli, canister_id: str) -> dict[str, str] | None:
    """status() query → {version, commit, commit_datetime}; placeholders fuera."""
    try:
        raw = cli.call_raw(canister_id, "status", "()")
    except CliError:
        return None
    fields = parse_status_reply(raw)
    if not fields:
        return None
    cleaned: dict[str, str] = {}
    for key in ("version", "commit", "commit_datetime"):
        value = (fields.get(key) or "").strip()
        if value and not _PLACEHOLDER_RE.search(value):
            cleaned[key] = value
    return cleaned or None


def probe_frontend_meta(http: HttpGetter, urls: list[str]) -> dict[str, str] | None:
    """Meta tags commit-hash / commit-datetime / version del HTML servido."""
    for url in urls:
        try:
            html = http.get(url)
        except CliError:
            continue
        metas: dict[str, str] = {}
        for match in _META_RE.finditer(html):
            metas[match.group("name")] = match.group("content")
        for match in _META_RE_ALT.finditer(html):
            metas.setdefault(match.group("name"), match.group("content"))
        cleaned: dict[str, str] = {}
        for meta_name, field_name in (
            ("commit-hash", "commit"),
            ("commit-datetime", "commit_datetime"),
            ("version", "version"),
        ):
            value = (metas.get(meta_name) or "").strip()
            if value and not _PLACEHOLDER_RE.search(value):
                cleaned[field_name] = value
        if cleaned:
            return cleaned
    return None


def list_realms(cli: BaseCli, registry_id: str) -> list[dict[str, str]]:
    raw = cli.call_raw(registry_id, "list_realms", "()")
    realms = []
    for fields in parse_records_with(raw, ("id", "name", "frontend_canister_id")):
        realms.append(
            {
                "id": fields.get("id", ""),
                "name": fields.get("name", "") or fields.get("id", ""),
                "frontend_canister_id": fields.get("frontend_canister_id", ""),
            }
        )
    return realms


def list_jobs(cli: BaseCli, installer_id: str) -> list[dict[str, str]]:
    raw = cli.call_raw(installer_id, "list_deployment_jobs", "(null, null)")
    jobs = []
    for fields in parse_records_with(raw, ("job_id", "backend_canister_id")):
        jobs.append(fields)
    return jobs


def _json_text_call(
    cli: BaseCli, canister_id: str, method: str, payload: dict | None
) -> object:
    """Llama un método `(text) -> text` (o `() -> text` si payload es None)."""
    if payload is None:
        arg = "()"
    else:
        arg = (
            '("' + json.dumps(payload).replace("\\", "\\\\").replace('"', '\\"') + '")'
        )
    raw = cli.call_raw(canister_id, method, arg)
    return json.loads(extract_candid_string(raw))


def build_wasm_map(cli: BaseCli, file_registry_id: str, log) -> dict[str, dict]:
    """module_hash (hex, sin 0x) → {version, updated, path} vía file_registry.

    Descarga cada `wasm/**/*.wasm[.gz]`, lo descomprime y calcula el sha256
    del módulo — que es lo que el IC reporta como module_hash.
    """
    mapping: dict[str, dict] = {}
    try:
        namespaces = _json_text_call(cli, file_registry_id, "list_namespaces", None)
    except (CliError, json.JSONDecodeError) as exc:
        log(f"  file_registry list_namespaces ilegible: {exc}")
        return mapping
    if not isinstance(namespaces, list):
        return mapping
    wasm_namespaces = sorted(
        entry.get("namespace", "")
        for entry in namespaces
        if isinstance(entry, dict)
        and str(entry.get("namespace", "")).startswith("wasm/")
    )
    for namespace in wasm_namespaces:
        version = namespace.rsplit("/", 1)[-1]
        try:
            files = _json_text_call(
                cli, file_registry_id, "list_files", {"namespace": namespace}
            )
        except (CliError, json.JSONDecodeError) as exc:
            log(f"  list_files({namespace}) ilegible: {exc}")
            continue
        if not isinstance(files, list):
            continue
        for entry in files:
            if not isinstance(entry, dict):
                continue
            path = str(entry.get("path", ""))
            if not (path.endswith(".wasm.gz") or path.endswith(".wasm")):
                continue
            try:
                blob = _download_file(cli, file_registry_id, namespace, path)
            except CliError as exc:
                log(f"  descarga {namespace}/{path} falló: {exc}")
                continue
            module = blob
            if path.endswith(".gz"):
                try:
                    module = gzip.decompress(blob)
                except OSError:
                    log(f"  {namespace}/{path}: no es gzip válido; se hashea crudo")
            digest = hashlib.sha256(module).hexdigest()
            mapping[digest] = {
                "version": version,
                "updated": entry.get("updated", 0),
                "path": f"{namespace}/{path}",
            }
            log(f"  mapa wasm: {namespace}/{path} → módulo 0x{digest[:8]}…")
    return mapping


def _download_file(
    cli: BaseCli, file_registry_id: str, namespace: str, path: str
) -> bytes:
    import base64

    chunks: list[bytes] = []
    offset = 0
    while True:
        reply = _json_text_call(
            cli,
            file_registry_id,
            "get_file_chunk",
            {"namespace": namespace, "path": path, "offset": offset, "length": _CHUNK},
        )
        if not isinstance(reply, dict) or "content_b64" not in reply:
            raise CliError(f"get_file_chunk {namespace}/{path}: {reply!r:.120}")
        chunks.append(base64.b64decode(reply["content_b64"]))
        if reply.get("eof"):
            return b"".join(chunks)
        offset += int(reply.get("length") or 0) or _CHUNK


# ---------------------------------------------------------------------------
# Tiempo: parseo, Europe/Zurich y "hace …"
# ---------------------------------------------------------------------------


def sniff_epoch(value: object) -> float | None:
    """Acepta segundos, ms o ns (numéricos o string) → segundos epoch."""
    try:
        number = float(str(value).replace("_", ""))
    except (TypeError, ValueError):
        return None
    if number <= 0:
        return None
    if number > 1e14:  # ns
        return number / 1e9
    if number > 1e11:  # ms
        return number / 1e3
    return number


def parse_build_datetime(text: str) -> float | None:
    """`2026-08-28 15:04:05` (UTC, formato del release stamp) o ISO → epoch."""
    cleaned = text.strip().replace(" UTC", "").replace("Z", "")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return (
                datetime.strptime(cleaned, fmt).replace(tzinfo=timezone.utc).timestamp()
            )
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.timestamp()
    except ValueError:
        return None


TZ_LABEL = "Europe/Zurich" if _ZURICH is not None else "UTC (sin tzdata)"


def zurich_str(epoch: float) -> str:
    if _ZURICH is not None:
        return datetime.fromtimestamp(epoch, tz=_ZURICH).strftime("%Y-%m-%d %H:%M")
    return datetime.fromtimestamp(epoch, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def hace(epoch: float, now: float) -> str:
    delta = int(now - epoch)
    if delta < 0:
        return "en el futuro"
    if delta < 60:
        return "hace un momento"
    minutes = delta // 60
    if minutes < 60:
        return f"hace {minutes} min"
    hours = delta // 3600
    days = delta // 86400
    if days < 1:
        return f"hace {hours} hora" + ("" if hours == 1 else "s")
    rem_hours = (delta % 86400) // 3600
    label = f"{days} día" + ("" if days == 1 else "s")
    if rem_hours:
        label += f" y {rem_hours} hora" + ("" if rem_hours == 1 else "s")
    return f"hace {label}"


# ---------------------------------------------------------------------------
# Informe
# ---------------------------------------------------------------------------


@dataclass
class Row:
    pieza: str
    sha: str | None = None
    module_hash: str | None = None  # con 0x
    fecha_epoch: float | None = None
    version: str | None = None
    nota: str = ""
    fuentes: dict[str, str] = field(default_factory=dict)

    def sha_cell(self) -> str:
        if self.sha:
            return self.sha[:7]
        if self.module_hash:
            return SHA_DESCONOCIDO
        return NO_LEIDA

    def hash_cell(self) -> str:
        if self.module_hash:
            return f"{self.module_hash[:10]}…"
        return NO_LEIDA

    def fecha_cell(self) -> str:
        if self.fecha_epoch is not None:
            return zurich_str(self.fecha_epoch)
        return HORA_DESCONOCIDA

    def hace_cell(self, now: float) -> str:
        if self.fecha_epoch is not None:
            return hace(self.fecha_epoch, now)
        return "—"

    def pieza_cell(self) -> str:
        label = self.pieza
        if self.version:
            label += f" · {self.version}"
        if self.nota:
            label += f" ({self.nota})"
        return label

    def to_json(self, now: float) -> dict:
        return {
            "pieza": self.pieza,
            "version": self.version,
            "sha": self.sha[:7] if self.sha else None,
            "sha_estado": (
                "ok"
                if self.sha
                else ("desconocido" if self.module_hash else "ilegible")
            ),
            "hash_modulo": self.module_hash,
            "fecha_zurich": (
                zurich_str(self.fecha_epoch) if self.fecha_epoch is not None else None
            ),
            "hace": self.hace_cell(now) if self.fecha_epoch is not None else None,
            "nota": self.nota or None,
            "fuentes": self.fuentes,
        }


def _short_sha(commit: str) -> str | None:
    cleaned = commit.strip()
    if re.fullmatch(r"[0-9a-fA-F]{7,40}", cleaned):
        return cleaned[:7].lower()
    return None


def _apply_app_fields(row: Row, app: dict[str, str] | None) -> None:
    if not app:
        return
    sha = _short_sha(app.get("commit", ""))
    if sha and not row.sha:
        row.sha = sha
        row.fuentes["sha"] = "status()/meta"
    if app.get("commit_datetime") and row.fecha_epoch is None:
        epoch = parse_build_datetime(app["commit_datetime"])
        if epoch is not None:
            row.fecha_epoch = epoch
            row.fuentes["fecha"] = "status()/meta commit_datetime"
    if app.get("version") and not row.version:
        row.version = app["version"]
        row.fuentes["version"] = "status()/meta"


def _apply_wasm_map(row: Row, wasm_map: dict[str, dict]) -> None:
    if not row.module_hash:
        return
    entry = wasm_map.get(
        row.module_hash[2:] if row.module_hash.startswith("0x") else row.module_hash
    )
    if not entry:
        return
    if not row.version and entry.get("version"):
        row.version = entry["version"]
        row.fuentes["version"] = f"file_registry {entry.get('path', '')}"
    if row.fecha_epoch is None:
        epoch = sniff_epoch(entry.get("updated"))
        if epoch is not None:
            row.fecha_epoch = epoch
            row.fuentes["fecha"] = f"file_registry updated ({entry.get('path', '')})"


def _probe_canister(
    cli: BaseCli,
    canister_id: str,
    row: Row,
    log,
) -> None:
    if not _CANISTER_ID_RE.match(canister_id or ""):
        row.nota = "id de canister ilegible"
        return
    try:
        module_hash, _status = probe_module_hash(cli, canister_id)
        if module_hash:
            row.module_hash = module_hash
            row.fuentes["hash"] = "canister_status"
        elif not row.nota:
            # La llamada funcionó (somos controller) pero no hay módulo.
            row.nota = "sin módulo instalado"
    except CliError as exc:
        log(f"  canister_status ilegible: {exc}")


def assemble_env(
    env: str,
    descriptor: dict,
    cli: BaseCli,
    http: HttpGetter,
    *,
    wasm_map_enabled: bool,
    log,
) -> dict:
    label = ENV_LABEL.get(env, env.capitalize())
    domain = str(descriptor.get("domain", ""))
    canisters = descriptor.get("canisters") or {}

    gaas_rows: list[Row] = []
    realm_rows: list[Row] = []
    warnings: list[str] = []

    def warn(msg: str) -> None:
        # Los errores del CLI pueden traer el canister id; nunca se imprimen.
        msg = _PRINCIPAL_LIKE_RE.sub("〈id〉", msg)
        warnings.append(msg)
        log(f"  aviso: {msg}")

    # Mapa module_hash → versión/fecha vía file_registry (una vez por entorno).
    wasm_map: dict[str, dict] = {}
    file_registry_id = canisters.get("file_registry", "")
    if wasm_map_enabled and _CANISTER_ID_RE.match(file_registry_id or ""):
        log("  construyendo mapa de WASMs del file_registry…")
        try:
            wasm_map = build_wasm_map(cli, file_registry_id, log)
        except Exception as exc:  # nunca romper el informe por el mapa
            warn(f"mapa de WASMs ilegible: {exc}")

    # ── Sección GaaS ────────────────────────────────────────────────────
    for key, piece, kind in GAAS_PIECES:
        canister_id = str(canisters.get(key, "") or "")
        if not canister_id:
            if key == "file_registry_frontend":
                continue  # no existe en este entorno; no es un error
            gaas_rows.append(Row(pieza=f"{label} {piece}", nota="sin id en descriptor"))
            continue
        row = Row(pieza=f"{label} {piece}")
        _probe_canister(cli, canister_id, row, log)
        if kind in APP_STATUS_PROBE_KINDS:
            _apply_app_fields(row, probe_app_status(cli, canister_id))
        else:
            urls = [f"https://{canister_id}.icp0.io/"]
            if key == "realm_registry_frontend" and domain:
                urls.insert(0, f"https://{domain}/")
            try:
                _apply_app_fields(row, probe_frontend_meta(http, urls))
            except Exception as exc:
                log(f"  meta http ilegible para {piece}: {exc}")
        _apply_wasm_map(row, wasm_map)
        gaas_rows.append(row)

    # ── Sección Realms ──────────────────────────────────────────────────
    registry_id = str(canisters.get("realm_registry_backend", "") or "")
    installer_id = str(canisters.get("realm_installer", "") or "")
    realms: list[dict[str, str]] = []
    if _CANISTER_ID_RE.match(registry_id):
        try:
            realms = list_realms(cli, registry_id)
        except CliError as exc:
            warn(f"list_realms ilegible: {exc}")
    jobs: list[dict[str, str]] = []
    if _CANISTER_ID_RE.match(installer_id):
        try:
            jobs = list_jobs(cli, installer_id)
        except CliError as exc:
            warn(f"list_deployment_jobs ilegible: {exc}")

    jobs_by_backend: dict[str, dict[str, str]] = {}
    jobs_by_frontend: dict[str, dict[str, str]] = {}
    for job in sorted(jobs, key=lambda j: sniff_epoch(j.get("created_at")) or 0):
        backend = (job.get("backend_canister_id") or "").strip()
        frontend = (job.get("frontend_canister_id") or "").strip()
        if backend:
            jobs_by_backend[backend] = job  # el más reciente gana
        if frontend:
            jobs_by_frontend[frontend] = job

    for realm in realms:
        name = realm["name"]
        backend_id = realm["id"].strip()
        frontend_id = realm["frontend_canister_id"].strip()

        be_row = Row(pieza=f"{name} BE")
        backend_job = jobs_by_backend.get(backend_id)
        if _CANISTER_ID_RE.match(backend_id):
            _probe_canister(cli, backend_id, be_row, log)
            _apply_app_fields(be_row, probe_app_status(cli, backend_id))
        else:
            be_row.nota = "id de backend ilegible"
        if not be_row.module_hash and backend_job:
            job_hash = (backend_job.get("actual_wasm_hash") or "").strip().lower()
            if re.fullmatch(r"[0-9a-f]{64}", job_hash):
                be_row.module_hash = f"0x{job_hash}"
                be_row.fuentes["hash"] = "deploy record (installer)"
        _apply_wasm_map(be_row, wasm_map)
        if be_row.fecha_epoch is None and backend_job:
            epoch = sniff_epoch(backend_job.get("completed_at")) or sniff_epoch(
                backend_job.get("created_at")
            )
            if epoch is not None:
                be_row.fecha_epoch = epoch
                be_row.fuentes["fecha"] = "deploy record (installer)"
        realm_rows.append(be_row)

        if _CANISTER_ID_RE.match(frontend_id):
            fe_row = Row(pieza=f"{name} FE")
            _probe_canister(cli, frontend_id, fe_row, log)
            try:
                _apply_app_fields(
                    fe_row,
                    probe_frontend_meta(http, [f"https://{frontend_id}.icp0.io/"]),
                )
            except Exception as exc:
                log(f"  meta http ilegible para {name} FE: {exc}")
            frontend_job = jobs_by_frontend.get(frontend_id)
            if not fe_row.module_hash and frontend_job:
                job_hash = (
                    (frontend_job.get("actual_frontend_wasm_hash") or "")
                    .strip()
                    .lower()
                )
                if re.fullmatch(r"[0-9a-f]{64}", job_hash):
                    fe_row.module_hash = f"0x{job_hash}"
                    fe_row.fuentes["hash"] = "deploy record (installer)"
            if fe_row.fecha_epoch is None and frontend_job:
                epoch = sniff_epoch(frontend_job.get("completed_at")) or sniff_epoch(
                    frontend_job.get("created_at")
                )
                if epoch is not None:
                    fe_row.fecha_epoch = epoch
                    fe_row.fuentes["fecha"] = "deploy record (installer)"
            realm_rows.append(fe_row)
        else:
            realm_rows.append(Row(pieza=f"{name} FE", nota="sin frontend registrado"))

    return {
        "entorno": env,
        "label": label,
        "dominio": domain,
        "gaas": gaas_rows,
        "realms": realm_rows,
        "avisos": warnings,
    }


# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------


def print_env_text(section: dict, now: float, out) -> None:
    line = "═" * 74
    print(line, file=out)
    header = f"ENTORNO {section['entorno'].upper()}"
    if section["dominio"]:
        header += f" — {section['dominio']}"
    print(header, file=out)
    print(line, file=out)

    def table(rows: list[Row]) -> None:
        headers = ("pieza", "SHA", "hash módulo", "fecha (Zurich)", "hace")
        body = [
            (
                row.pieza_cell(),
                row.sha_cell(),
                row.hash_cell(),
                row.fecha_cell(),
                row.hace_cell(now),
            )
            for row in rows
        ]
        widths = [
            (
                max(len(headers[i]), *(len(r[i]) for r in body))
                if body
                else len(headers[i])
            )
            for i in range(len(headers))
        ]
        fmt = "  " + "  ".join(f"{{:<{w}}}" for w in widths)
        print(fmt.format(*headers), file=out)
        print(fmt.format(*("-" * w for w in widths)), file=out)
        for r in body:
            print(fmt.format(*r), file=out)

    print("GaaS (plataforma)", file=out)
    table(section["gaas"])
    print("", file=out)
    print("Realms", file=out)
    if section["realms"]:
        table(section["realms"])
    else:
        print("  (sin realms registrados o no pude leerlos)", file=out)
    for aviso in section["avisos"]:
        print(f"  aviso: {aviso}", file=out)
    print("", file=out)


def load_descriptor(repo_root: Path, env: str) -> dict:
    path = repo_root / "environments" / f"{env}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="estado_entornos",
        description="Estado de los entornos GaaS (Test/Staging/Demo) — solo lectura.",
    )
    parser.add_argument(
        "--identity",
        default=os.environ.get("DFX_IDENTITY", "deployer"),
        help="identidad dfx/icp controller (default: deployer)",
    )
    parser.add_argument(
        "--env",
        default=",".join(ENVIRONMENTS),
        help="entornos separados por coma (default: test,staging,demo)",
    )
    parser.add_argument(
        "--cli",
        choices=("auto", "dfx", "icp"),
        default="auto",
        help="CLI a usar (default: auto — prefiere icp si existe)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="timeout por llamada en segundos (default: 60)",
    )
    parser.add_argument(
        "--no-wasm-map",
        action="store_true",
        help="no descargar WASMs del file_registry (más rápido, "
        "sin versión/fecha para hashes de módulo)",
    )
    parser.add_argument(
        "--no-http",
        action="store_true",
        help="no sondear meta tags HTTP de los frontends",
    )
    parser.add_argument("--json", action="store_true", help="salida JSON")
    parser.add_argument(
        "--fixtures",
        metavar="DIR",
        help="dry-run: leer respuestas de DIR en vez de llamar al IC",
    )
    parser.add_argument(
        "--repo-root",
        default=str(REPO_ROOT),
        help="raíz del repo (default: la del script)",
    )
    parser.add_argument(
        "--now",
        type=float,
        default=None,
        help="epoch de referencia para 'hace …' (tests)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="diagnósticos por canister en stderr"
    )
    args = parser.parse_args(argv)

    now = (
        args.now if args.now is not None else datetime.now(tz=timezone.utc).timestamp()
    )

    def log(msg: str) -> None:
        if args.verbose or args.fixtures:
            print(msg, file=sys.stderr)

    envs = [e.strip() for e in args.env.split(",") if e.strip()]
    unknown = [e for e in envs if e not in ENVIRONMENTS]
    if unknown:
        print(
            f"Entornos desconocidos: {', '.join(unknown)} "
            f"(válidos: {', '.join(ENVIRONMENTS)})",
            file=sys.stderr,
        )
        return 2

    fixtures_root = Path(args.fixtures) if args.fixtures else None
    cli: BaseCli | None = None
    if fixtures_root is None:
        try:
            cli = detect_cli(args.cli, args.identity, args.timeout)
        except CliError as exc:
            print(f"No puedo hablar con el IC: {exc}", file=sys.stderr)
            return 2

    sections = []
    for env in envs:
        if fixtures_root is not None:
            cli_env: BaseCli = FixtureCli(fixtures_root, env)
            http = HttpGetter(args.timeout, fixtures=fixtures_root, env=env)
        else:
            assert cli is not None
            cli_env = cli
            if args.no_http:
                # HTTP desactivado: getter que siempre falla → campos ilegibles.
                http = HttpGetter(args.timeout, fixtures=Path("/nonexistent"), env=env)
            else:
                http = HttpGetter(args.timeout)
        try:
            descriptor = load_descriptor(Path(args.repo_root), env)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"No pude leer environments/{env}.json: {exc}", file=sys.stderr)
            return 2
        log(f"■ {env}: sondeando…")
        sections.append(
            assemble_env(
                env,
                descriptor,
                cli_env,
                http,
                wasm_map_enabled=not args.no_wasm_map,
                log=log,
            )
        )

    if args.json:
        payload = {
            "generado_zurich": zurich_str(now),
            "identidad": None if fixtures_root else args.identity,
            "cli": "fixtures" if fixtures_root else (cli.name if cli else None),
            "entornos": [
                {
                    "entorno": s["entorno"],
                    "dominio": s["dominio"],
                    "gaas": [row.to_json(now) for row in s["gaas"]],
                    "realms": [row.to_json(now) for row in s["realms"]],
                    "avisos": s["avisos"],
                }
                for s in sections
            ],
        }
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0

    cli_name = "fixtures" if fixtures_root else (cli.name if cli else "?")
    print(
        f"ESTADO DE LOS ENTORNOS — generado {zurich_str(now)} "
        f"({TZ_LABEL}) — identidad: "
        f"{'fixtures' if fixtures_root else args.identity} — CLI: {cli_name}"
    )
    print("", file=sys.stdout)
    for section in sections:
        print_env_text(section, now, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
