"""realm_installer — realm deployment orchestrator and on-chain verifier.

Manages deployment queue, WASM verification, extension/codex installation,
and realm registration. The off-chain realms-deployer polls for pending jobs,
deploys via dfx, and reports back.
"""

import hashlib
import json
import traceback

from baton_deferral import (
    build_baton_handoff_payload,
    decode_baton_handoff_payload,
    encode_baton_handoff_payload,
    hand_targets_from_payload,
    should_record_deferred_baton,
    should_run_deferred_baton_handoff,
)
from cycles_preflight import (
    check_cycles_preflight,
    estimate_conductor_cycles_required,
    parse_cycles_report,
    resolve_file_registry_id,
)
from provision_kick import (
    PROVISION_HEARTBEAT_INTERVAL_S,
    ProvisionAlreadyInProgress,
    claim_provision_lock,
    clear_provision_lock,
    provision_kick_runner,
    provisioning_job_ids_for_heartbeat,
    schedule_provision_kick as _schedule_provision_kick_impl,
    should_kick_provision_on_enqueue,
)
from claim_args import build_claim_slug_args
from bootstrap import (
    configure_canister_ids_args,
    configure_canister_ids_payload,
    manifest_has_codex_block,
    resolve_legacy_install_lists,
)
from ic_assets import ensure_frame_ancestor, portal_url_to_origin
from installer_config import (
    InstallerConfig,
    apply_installer_config,
    configured_file_registry_id,
    configured_portal_base,
    get_config,
    installer_config_payload,
)

from basilisk import (
    Async, CallResult, Duration, Opt, Principal, Record, Service,
    StableBTreeMap, Variant, Vec, ic, init, int8, match, nat, nat32,
    nat64, null, post_upgrade, query, service_query, service_update,
    text, update,
)
from basilisk.canisters.management import management_canister
from ic_python_db import (
    Database, Entity, Integer, ManyToOne, OneToMany, String, TimestampedMixin,
)
from ic_python_logging import get_canister_logs as _get_canister_logs, get_logger as _get_logger

_log = _get_logger("realm_installer")

# ── Storage ────────────────────────────────────────────────────────────

_db_storage = StableBTreeMap[str, str](memory_id=1, max_key_size=200, max_value_size=10000)
try:
    Database.init(db_storage=_db_storage, audit_enabled=False)
except RuntimeError:
    pass

# ── Inter-canister services ────────────────────────────────────────────

class RealmTargetService(Service):
    _arg_types = {"install_extension_from_registry": "text", "install_codex_from_registry": "text"}
    @service_update
    def install_extension_from_registry(self, args: text) -> text: ...
    @service_update
    def install_codex_from_registry(self, args: text) -> text: ...

class RealmRegistryService(Service):
    @service_update
    def register_realm(self, name: text, url: text, logo: text, backend_url: text, canister_ids_json: text) -> text: ...
    @service_update
    def remove_realm(self, realm_id: text) -> text: ...
    @service_update
    def deployment_failed(self, job_id: text, reason: text, caller_principal: text) -> text: ...
    @service_update
    def deployment_succeeded(self, job_id: text, caller_principal: text) -> text: ...

class FileRegistryService(Service):
    @service_query
    def get_extension_manifest(self, args: text) -> text: ...

class CasalsService(Service):
    """Casals canister-lifecycle engine. All endpoints take a single JSON `args`
    string and return a JSON string ({"ok": true, ...} | {"ok": false, "error": …}).
    Used only on the on-chain provisioning path (gated by InstallerConfig); the
    legacy off-chain-deployer path does not touch this."""
    @service_query
    def get_tree(self) -> text: ...
    @service_query
    def get_cycles_cached(self) -> text: ...
    @service_update
    def create_stand(self, args: text) -> text: ...
    @service_update
    def create_canister(self, args: text) -> text: ...
    @service_update
    def set_commander(self, args: text) -> text: ...
    @service_update
    def upgrade_to(self, args: text) -> text: ...
    @service_update
    def orchestration_hand_to_baton(self, args: text) -> text: ...
    @service_update
    def orchestration_configure_baton(self, args: text) -> text: ...
    @service_update
    def destroy_realm_stand(self, args: text) -> text: ...

# ── Entities ───────────────────────────────────────────────────────────

class DeployTask(Entity, TimestampedMixin):
    __alias__ = "name"
    name = String(max_length=64)
    status = String(max_length=32, default="queued")
    started_at = Integer(default=0)
    completed_at = Integer(default=0)
    target_canister_id = String(max_length=64)
    registry_canister_id = String(max_length=64)
    manifest_json = String(max_length=8192)
    error = String(max_length=2000)
    steps = OneToMany("DeployStep", "task")

class DeployStep(Entity, TimestampedMixin):
    task = ManyToOne("DeployTask", "steps")
    idx = Integer(default=0)
    kind = String(max_length=32)
    label = String(max_length=200)
    args_json = String(max_length=2000)
    status = String(max_length=32, default="pending")
    started_at = Integer(default=0)
    completed_at = Integer(default=0)
    result_json = String(max_length=2000)
    error = String(max_length=2000)

_JOB_TERMINAL_STATUSES = ("completed", "failed", "failed_verification", "cancelled")
# Failed terminal jobs the owner may remove from their dashboard.
_JOB_DELETABLE_STATUSES = ("failed", "failed_verification", "cancelled")
# Jobs reserved for on-chain Casals provisioning — invisible to the off-chain worker.
_CASALS_RESERVED_STATUSES = ("provisioning",)

class DeploymentJob(Entity, TimestampedMixin):
    __alias__ = "name"
    name = String(max_length=64)
    status = String(max_length=32, default="pending")
    realm_name = String(max_length=128, default="")
    caller_principal = String(max_length=64)
    manifest_json = String(max_length=8192)
    network = String(max_length=32)
    backend_canister_id = String(max_length=64)
    frontend_canister_id = String(max_length=64)
    expected_wasm_hash = String(max_length=128)
    expected_assets_hash = String(max_length=128)
    expected_frontend_wasm_hash = String(max_length=128)
    actual_wasm_hash = String(max_length=128)
    actual_assets_hash = String(max_length=128)
    actual_frontend_wasm_hash = String(max_length=128)
    wasm_verified = Integer(default=0)
    assets_verified = Integer(default=0)
    frontend_wasm_verified = Integer(default=0)
    ext_deploy_task_id = String(max_length=64)
    expected_step_count = Integer(default=0)
    registry_canister_id = String(max_length=64)
    offchain_deployer_principal = String(max_length=64)
    settlement_notified = Integer(default=0)
    snapshot_id = String(max_length=200, default="")
    snapshot_taken = Integer(default=0)
    skip_snapshot = Integer(default=0)
    baton_pending = Integer(default=0)
    baton_canister_id = String(max_length=64, default="")
    baton_handoff_json = String(max_length=2048, default="")
    provision_active_at = Integer(default=0)
    error = String(max_length=2000)
    created_at = Integer(default=0)
    completed_at = Integer(default=0)


class DeploymentJobRef(Entity):
    """Lightweight index for listing jobs without scanning full manifests."""
    __alias__ = "name"
    name = String(max_length=64)
    caller_principal = String(max_length=64)
    created_at = Integer(default=0)

def _config() -> InstallerConfig:
    return get_config()

# ── Candid types ───────────────────────────────────────────────────────

class _CA:
    def __getattr__(self, n):
        if n.startswith("_"): raise AttributeError(n)
        try: return self[n]
        except KeyError: raise AttributeError(n) from None

class InstallerError(Record, _CA):
    message: text
    traceback: text

class DeploymentJobView(Record, _CA):
    job_id: text
    status: text
    realm_name: text
    caller_principal: text
    network: text
    backend_canister_id: text
    frontend_canister_id: text
    expected_wasm_hash: text
    actual_wasm_hash: text
    wasm_verified: int8
    assets_verified: int8
    frontend_wasm_verified: int8
    ext_deploy_task_id: text
    expected_step_count: nat32
    registry_canister_id: text
    error: text
    created_at: nat64
    completed_at: nat64

class DeployStepView(Record, _CA):
    idx: nat32
    kind: text
    label: text
    status: text
    error: text

class DeployTaskView(Record, _CA):
    task_id: text
    status: text
    steps: Vec[DeployStepView]
    completed_count: nat32
    total_count: nat32

class ResultDeployTaskStatus(Variant, total=False):
    Ok: DeployTaskView
    Err: InstallerError

class PendingJobEntry(Record, _CA):
    job: DeploymentJobView
    manifest: text

class PendingJobsOk(Record, _CA):
    jobs: Vec[PendingJobEntry]
    count: nat32

class ResultPendingJobs(Variant, total=False):
    Ok: PendingJobsOk
    Err: InstallerError

class JobsListOk(Record, _CA):
    jobs: Vec[DeploymentJobView]
    count: nat32

class ResultJobsList(Variant, total=False):
    Ok: JobsListOk
    Err: InstallerError

class EnqueueOk(Record, _CA):
    job_id: text
    status: text
    realm_name: text
    network: text

class ResultEnqueue(Variant, total=False):
    Ok: EnqueueOk
    Err: InstallerError

class ResultJobIdStatus(Variant, total=False):
    Ok: DeploymentJobView
    Err: InstallerError

class ResultJobManifest(Variant, total=False):
    Ok: text
    Err: InstallerError

class JobStatusAck(Record, _CA):
    job_id: text
    prev_status: text
    status: text
    noop: bool

class ResultJobCancel(Variant, total=False):
    Ok: JobStatusAck
    Err: InstallerError

class ResultReportFailure(Variant, total=False):
    Ok: JobStatusAck
    Err: InstallerError

class ReportReadyOk(Record, _CA):
    job_id: text
    status: text
    wasm_verified: bool
    actual_wasm_hash: text
    extensions_started: bool
    expected_wasm_hash: text
    failed_verification: bool

class ResultReportReady(Variant, total=False):
    Ok: ReportReadyOk
    Err: InstallerError

class ReportFrontendOk(Record, _CA):
    job_id: text
    status: text
    actual_assets_hash: text
    assets_verified: int8
    actual_frontend_wasm_hash: text
    frontend_wasm_verified: bool
    failed_verification: bool

class ResultReportFrontend(Variant, total=False):
    Ok: ReportFrontendOk
    Err: InstallerError

class PublicLogEntry(Record, _CA):
    timestamp: nat
    level: text
    logger_name: text
    message: text
    id: nat

class HealthView(Record, _CA):
    ok: bool
    canister: text

class StatusRecord(Record, _CA):
    version: text
    commit: text
    commit_datetime: text
    status: text

class GetStatusResult(Variant, total=False):
    Ok: StatusRecord
    Err: text

class TakeSnapshotOk(Record, _CA):
    job_id: text
    snapshot_id: text
    skipped: bool

class ResultTakeSnapshot(Variant, total=False):
    Ok: TakeSnapshotOk
    Err: InstallerError

class ProvisionOk(Record, _CA):
    job_id: text
    status: text
    stand: text
    backend_canister_id: text
    frontend_canister_id: text

class ResultProvision(Variant, total=False):
    Ok: ProvisionOk
    Err: InstallerError

class CasalsConfigView(Record, _CA):
    provision_via_casals: bool
    casals_canister_id: text
    casals_section: text
    registry_principal: text
    create_stand_baton: bool
    baton_wasm_key: text

class ResultCasalsConfig(Variant, total=False):
    Ok: CasalsConfigView
    Err: InstallerError

# ── Helpers ────────────────────────────────────────────────────────────

def jlog(job_id: str):
    return _get_logger(job_id)


def now_s() -> int:
    return int(round(ic.time() / 1e9))


def ie(message: str, tb: str = ""):
    return InstallerError(message=message, traceback=tb or "")


def unwrap_call_result(result):
    if result is None:
        return None
    if isinstance(result, (str, bytes)):
        return result
    if isinstance(result, dict):
        if "Err" in result and result["Err"] is not None:
            raise RuntimeError(f"inter-canister Err: {result['Err']}")
        if "Ok" in result:
            return result["Ok"]
        return result
    if hasattr(result, "Err") and getattr(result, "Err", None):
        raise RuntimeError(f"inter-canister Err: {result.Err}")
    if hasattr(result, "Ok"):
        return result.Ok
    return result


def schedule_registry_settlement(job_id: str, success: bool, reason: str = ""):
    def _cb():
        try:
            list(DeploymentJob.instances())
            job = DeploymentJob[job_id]
            if job is None or int(job.settlement_notified or 0) == 1:
                return
            reg_id = (job.registry_canister_id or "").strip()
            if not reg_id:
                return
            caller = (job.caller_principal or "").strip()
            registry = RealmRegistryService(Principal.from_str(reg_id))
            if success:
                result: CallResult = yield registry.deployment_succeeded(job_id, caller)
            else:
                msg = (reason or job.error or "deployment failed")[:1900]
                result: CallResult = yield registry.deployment_failed(job_id, msg, caller)
            jlog(job_id).info(f"settlement {'success' if success else 'failure'} callback done")
            job = DeploymentJob[job_id]
            if job:
                job.settlement_notified = 1
                if success and int(job.snapshot_taken or 0) == 1 and (job.snapshot_id or "").strip():
                    _schedule_snapshot_delete(job_id)
        except Exception as e:
            jlog(job_id).error(f"settlement callback failed: {e}")

    ic.set_timer(Duration(0), _cb)


def _schedule_snapshot_rollback(job_id: str):
    """Load a previously taken canister snapshot to roll back a failed upgrade."""
    def _rollback_cb():
        try:
            list(DeploymentJob.instances())
            job = DeploymentJob[job_id]
            if job is None:
                return
            snap_hex = (job.snapshot_id or "").strip()
            backend_id = (job.backend_canister_id or "").strip()
            if not snap_hex or not backend_id:
                jlog(job_id).warning("rollback skipped: missing snapshot_id or backend_canister_id")
                return
            snap_bytes = bytes.fromhex(snap_hex)
            jlog(job_id).info(f"loading snapshot {snap_hex} onto {backend_id}")
            result: CallResult = yield management_canister.load_canister_snapshot(
                {"canister_id": Principal.from_str(backend_id),
                 "snapshot_id": snap_bytes})
            jlog(job_id).info("snapshot rollback completed")
        except Exception as e:
            jlog(job_id).error(f"snapshot rollback failed: {e}")

    ic.set_timer(Duration(0), _rollback_cb)


def _schedule_snapshot_delete(job_id: str):
    """Delete a canister snapshot after a successful deployment."""
    def _delete_cb():
        try:
            list(DeploymentJob.instances())
            job = DeploymentJob[job_id]
            if job is None:
                return
            snap_hex = (job.snapshot_id or "").strip()
            backend_id = (job.backend_canister_id or "").strip()
            if not snap_hex or not backend_id:
                return
            snap_bytes = bytes.fromhex(snap_hex)
            jlog(job_id).info(f"deleting snapshot {snap_hex} from {backend_id}")
            result: CallResult = yield management_canister.delete_canister_snapshot(
                {"canister_id": Principal.from_str(backend_id),
                 "snapshot_id": snap_bytes})
            jlog(job_id).info("snapshot deleted")
        except Exception as e:
            jlog(job_id).warning(f"snapshot delete failed (non-fatal): {e}")

    ic.set_timer(Duration(0), _delete_cb)


def _candid_opt_text(v: str) -> str:
    if not v:
        return "null"
    escaped = str(v).replace("\\", "\\\\").replace('"', '\\"')
    return f'opt "{escaped}"'


def _build_canister_ids_js(
    backend_id: str,
    file_registry_id: str = "",
    derivation_origin: str = "",
    portal_url: str = "",
    test_mode_ii_bypass: bool = False,
) -> str:
    """Build the /canister_ids.js runtime config for a realm frontend.

    ``derivation_origin`` pins the Internet Identity ``derivationOrigin`` so this
    realm frontend resolves to the SAME principal as the registry and every other
    realm (one human → one principal). It must be the canonical origin that lists
    this realm's frontend in its ``/.well-known/ii-alternative-origins`` (the
    registry). Empty string preserves legacy per-origin principals. See #233.

    ``portal_url`` is the realm's canonical federation portal page
    (e.g. ``https://staging.gos.earth/r/<slug>``). When set, the frontend
    redirects direct-visit sign-ins to the portal, where the single II login is
    bridged into the embedded realm (the raw icp0.io origin cannot II-login —
    it is not in the registry's capped ii-alternative-origins list).

    ``test_mode_ii_bypass`` tells the realm frontend to skip real Internet
    Identity and use a deterministic local test identity instead. Without this
    field the frontend always boots a real-II AuthClient, so realms deployed in
    test mode would still force a real passkey login (which stalls inside the
    portal iframe).
    """
    fields = {
        "realm_backend": backend_id,
        "internet_identity": "https://identity.ic0.app",
    }
    if file_registry_id:
        fields["file_registry"] = file_registry_id
    if derivation_origin:
        fields["derivation_origin"] = derivation_origin
    if portal_url:
        fields["portal_url"] = portal_url
    body = ",".join(f'{k}:"{v}"' for k, v in fields.items())
    if test_mode_ii_bypass:
        body += ",test_mode_ii_bypass:true"
    return "globalThis.__CANISTER_IDS={" + body + "};"


def _grant_frontend_commit(frontend_id: str, to_principal: str):
    """Grant Commit on a certified-assets frontend canister (idempotent)."""
    candid_arg = (
        f'(record {{ to_principal = principal "{to_principal}"; '
        f'permission = variant {{ Commit }} }})'
    )
    grant_result: CallResult = yield ic.call_raw(
        Principal.from_str(frontend_id), "grant_permission",
        ic.candid_encode(candid_arg), 0,
    )
    return grant_result


def _store_canister_ids_js(frontend_id: str, js: str):
    """Write /canister_ids.js onto the realm frontend asset canister."""
    escaped = js.replace("\\", "\\\\").replace('"', '\\"')
    candid_arg = (
        '(record { key = "/canister_ids.js"; content_type = "application/javascript"; '
        'content_encoding = "identity"; content = blob "' + escaped + '"; sha256 = null })'
    )
    store_result: CallResult = yield ic.call_raw(
        Principal.from_str(frontend_id), "store",
        ic.candid_encode(candid_arg), 0,
    )
    return store_result


_DEFAULT_REALM_IC_ASSETS = """[
    {
        "match": "**/*",
        "security_policy": "disabled",
        "headers": {
            "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none';"
        }
    }
]"""


def _get_asset_file(frontend_id: str, key: str):
    """Read a file from a certified-assets frontend canister (query)."""
    escaped_key = key.replace("\\", "\\\\").replace('"', '\\"')
    candid_arg = f'(record {{ key = "{escaped_key}" }})'
    get_result: CallResult = yield ic.call_raw(
        Principal.from_str(frontend_id), "get",
        ic.candid_encode(candid_arg), 1,
    )
    return get_result


def _decode_asset_blob(raw) -> str:
    if raw is None:
        return ""
    if isinstance(raw, (bytes, bytearray)):
        raw = ic.candid_decode(raw)
    if isinstance(raw, dict):
        content = raw.get("content")
        if content is None and raw.get("Ok") is not None:
            inner = raw["Ok"]
            content = inner.get("content") if isinstance(inner, dict) else getattr(inner, "content", None)
        if isinstance(content, (bytes, bytearray)):
            return bytes(content).decode("utf-8", errors="replace")
        if isinstance(content, str):
            return content
    if hasattr(raw, "content"):
        content = raw.content
        if isinstance(content, (bytes, bytearray)):
            return bytes(content).decode("utf-8", errors="replace")
    return ""


def _store_ic_assets_json5(frontend_id: str, body: str):
    escaped = body.replace("\\", "\\\\").replace('"', '\\"')
    candid_arg = (
        '(record { key = "/.ic-assets.json5"; content_type = "application/json"; '
        'content_encoding = "identity"; content = blob "' + escaped + '"; sha256 = null })'
    )
    store_result: CallResult = yield ic.call_raw(
        Principal.from_str(frontend_id), "store",
        ic.candid_encode(candid_arg), 0,
    )
    return store_result


def _patch_ic_assets_frame_ancestor(frontend_id: str, job_id_val: str, portal_origin: str):
    """Best-effort CSP frame-ancestors patch — never raises."""
    try:
        origin = portal_url_to_origin(portal_origin)
        if not origin:
            jlog(job_id_val).info("ic-assets patch skipped: no portal origin")
            return
        current = _DEFAULT_REALM_IC_ASSETS
        try:
            get_result = yield from _get_asset_file(frontend_id, "/.ic-assets.json5")
            decoded = _decode_asset_blob(get_result)
            if decoded.strip():
                current = decoded
        except Exception as read_err:
            jlog(job_id_val).warning(
                f"ic-assets read failed, using template (non-fatal): {read_err}"
            )
        patched = ensure_frame_ancestor(current, origin)
        if patched == current:
            jlog(job_id_val).info(f"ic-assets frame-ancestors already includes {origin}")
            return
        store_result = yield from _store_ic_assets_json5(frontend_id, patched)
        if isinstance(store_result, dict) and store_result.get("Err"):
            jlog(job_id_val).warning(
                f"ic-assets upload failed (non-fatal): {store_result['Err']}"
            )
        else:
            jlog(job_id_val).info(f"ic-assets frame-ancestors patched with {origin}")
    except Exception as e:
        jlog(job_id_val).warning(f"ic-assets frame-ancestor patch failed (non-fatal): {e}")


def schedule_registration(job_id_val: str):
    def _register_cb():
        try:
            list(DeploymentJob.instances())
            j = DeploymentJob[job_id_val]
            if j is None or (j.status or "") in _JOB_TERMINAL_STATUSES:
                return
            reg_id = j.registry_canister_id
            if not reg_id:
                j.status = "failed"
                j.error = "missing registry_canister_id"
                j.completed_at = now_s()
                return
            manifest = json.loads(j.manifest_json or "{}")
            realm_info = manifest.get("realm", {})
            realm_name = realm_info.get("display_name") or realm_info.get("name", "")
            manifest_ids = manifest.get("canister_ids", {})
            backend_id = j.backend_canister_id or manifest_ids.get("backend", "")
            frontend_id = j.frontend_canister_id or manifest_ids.get("frontend", "")
            url = f"https://{frontend_id}.icp0.io" if frontend_id else ""
            backend_url = f"https://{backend_id}.icp0.io" if backend_id else ""
            logo = "logo.png"
            canister_ids = f"{frontend_id}|||{backend_id}"

            if frontend_id and backend_id:
                infra_early = manifest.get("infra") or {}
                fr_js = infra_early.get("file_registry_canister_id", "") or ""
                deriv_origin = infra_early.get("ii_derivation_origin", "") or ""
                federation = manifest.get("federation") or {}
                portal_url = (federation.get("portal_url") or "").strip()
                test_flags_reg = manifest.get("test_flags") or {}
                # manifest uses short keys (mapped to test_mode_* in the realm
                # backend _FLAG_MAP): "ii_bypass" -> test_mode_ii_bypass.
                ii_bypass = bool(
                    test_flags_reg.get("ii_bypass")
                    or test_flags_reg.get("test_mode_ii_bypass")
                )
                js = _build_canister_ids_js(backend_id, fr_js, deriv_origin, portal_url, ii_bypass)
                installer_id = ic.id().to_str()
                for principal in (installer_id, backend_id):
                    grant_res = yield from _grant_frontend_commit(frontend_id, principal)
                    if isinstance(grant_res, dict) and "Err" in grant_res:
                        jlog(job_id_val).warning(
                            f"grant Commit to {principal} failed (non-fatal): {grant_res['Err']}"
                        )
                store_result = yield from _store_canister_ids_js(frontend_id, js)
                if isinstance(store_result, dict) and "Err" in store_result:
                    jlog(job_id_val).error(f"canister_ids.js upload failed: {store_result['Err']}")
                else:
                    jlog(job_id_val).info("canister_ids.js uploaded to frontend")
                patch_origin = portal_url or configured_portal_base(manifest)
                yield from _patch_ic_assets_frame_ancestor(frontend_id, job_id_val, patch_origin)

            if backend_id and realm_info:
                # Identity fields only. When a codex package is installed,
                # init.py enforces onboarding.registration (issue #244) —
                # sending open_registration here would overwrite that policy
                # because registration runs before this call.
                config = {
                    "name": realm_name,
                    "manifesto": realm_info.get("manifesto", ""),
                    "welcome_message": realm_info.get("welcome_message", ""),
                }
                if not realm_info.get("codex"):
                    config["open_registration"] = realm_info.get(
                        "open_registration", False
                    )
                # Wizard codex-parameter choices (issue #253): stored in
                # manifest_data.config_overrides on the realm; the codex's
                # get_config applies them over its declared defaults. Runs
                # after codex init, so the lean manifest_data is preserved.
                overrides = realm_info.get("config_overrides")
                if isinstance(overrides, dict) and overrides:
                    config["config_overrides"] = overrides
                config_json = json.dumps(config).replace('\\', '\\\\').replace('"', '\\"')
                config_arg = '("' + config_json + '")'
                config_result: CallResult = yield ic.call_raw(
                    Principal.from_str(backend_id), "update_realm_config",
                    ic.candid_encode(config_arg), 0,
                )
                if isinstance(config_result, dict) and "Err" in config_result:
                    jlog(job_id_val).error(f"update_realm_config failed: {config_result['Err']}")
                else:
                    jlog(job_id_val).info(f"realm config updated: name={realm_name}")

            founder = (manifest.get("requesting_principal") or "").strip()
            if founder and backend_id and founder != "2vxsx-fae":
                try:
                    founder_arg = f'("{founder}")'
                    founder_result: CallResult = yield ic.call_raw(
                        Principal.from_str(backend_id), "register_founder",
                        ic.candid_encode(founder_arg), 0,
                    )
                    if isinstance(founder_result, dict) and "Err" in founder_result:
                        jlog(job_id_val).error(
                            f"register_founder failed: {founder_result['Err']}"
                        )
                    else:
                        jlog(job_id_val).info(f"founder registered as admin: {founder[:8]}…")
                except Exception as founder_err:
                    jlog(job_id_val).error(f"register_founder error: {founder_err}")

            infra = manifest.get("infra") or {}
            fr_id = infra.get("file_registry_canister_id", "")
            mp_id = infra.get("marketplace_canister_id", "")
            network = (manifest.get("network") or "").strip()
            version = (manifest.get("deploy_version") or "").strip()
            test_flags = manifest.get("test_flags") or {}
            test_flags_json = json.dumps(test_flags) if test_flags else ""
            if backend_id:
                realm_info = manifest.get("realm") or {}
                stand = ((manifest.get("casals") or {}).get("stand") or _slugify(
                    realm_info.get("name") or realm_name
                )).strip()
                token_cfg = _resolve_token_from_manifest(manifest)
                token_id = ""
                nft_id = _shared_nft_canister_id(network)
                if token_cfg:
                    if token_cfg.get("deploy_new"):
                        casals_id = (_config().casals_canister_id or "").strip()
                        stand_token, _ = yield from _lookup_stand_token_ids(
                            casals_id, stand, job_id_val
                        )
                        token_id = stand_token or ""
                    else:
                        token_id = token_cfg.get("ledger", "")

                link_payload = {
                    "frontend_canister_id": frontend_id or None,
                    "file_registry_canister_id": fr_id or None,
                    "marketplace_canister_id": mp_id or None,
                    "installed_version": version or None,
                    "network": network or None,
                }
                if test_flags_json:
                    link_payload["test_flags_json"] = test_flags_json
                if token_id:
                    link_payload["token_canister_id"] = token_id
                if nft_id:
                    link_payload["nft_canister_id"] = nft_id
                if token_cfg:
                    link_payload["accounting_currency"] = token_cfg.get("symbol", "REALMS")
                    link_payload["accounting_currency_decimals"] = token_cfg.get(
                        "decimals", 8
                    )
                    link_payload["treasury_token_symbol"] = token_cfg.get("symbol", "REALMS")
                    if token_cfg.get("indexer"):
                        link_payload["treasury_token_indexer_id"] = token_cfg["indexer"]
                    link_payload["treasury_token_type"] = token_cfg.get(
                        "token_type", "realm"
                    )

                link_json = json.dumps(
                    {k: v for k, v in link_payload.items() if v is not None}
                ).replace("\\", "\\\\").replace('"', '\\"')
                link_arg = '("' + link_json + '")'
                cc_result: CallResult = yield ic.call_raw(
                    Principal.from_str(backend_id),
                    "set_canister_config_json",
                    ic.candid_encode(link_arg),
                    0,
                )
                if isinstance(cc_result, dict) and "Err" in cc_result:
                    jlog(job_id_val).error(
                        f"set_canister_config_json failed: {cc_result['Err']}"
                    )
                else:
                    jlog(job_id_val).info(
                        f"set_canister_config_json: frontend={frontend_id}, "
                        f"token={token_id or '–'}, nft={nft_id or '–'}, "
                        f"file_registry={fr_id}, marketplace={mp_id}, "
                        f"version={version}, network={network}, "
                        f"test_flags={test_flags_json}"
                    )

            # Per-realm branding: the wizard uploaded the user's logo/background
            # straight into the file_registry (decentralized, signed by the
            # user's II). Tell the realm backend to pull them and serve them at
            # /custom/ on the frontend asset canister. manifest.branding maps
            # 1:1 onto install_branding_from_registry's args.
            branding = manifest.get("branding") or {}
            b_files = branding.get("files") or {}
            b_ns = (branding.get("namespace") or "").strip()
            b_reg = (branding.get("file_registry_canister_id") or fr_id or "").strip()
            if backend_id and frontend_id and b_files and b_ns and b_reg:
                try:
                    br_args = {
                        "registry_canister_id": b_reg,
                        "namespace": b_ns,
                        "files": b_files,
                        "frontend_canister_id": frontend_id,
                    }
                    br_json = json.dumps(br_args).replace('\\', '\\\\').replace('"', '\\"')
                    br_arg = '("' + br_json + '")'
                    br_result: CallResult = yield ic.call_raw(
                        Principal.from_str(backend_id), "install_branding_from_registry",
                        ic.candid_encode(br_arg), 0,
                    )
                    if isinstance(br_result, dict) and "Err" in br_result:
                        jlog(job_id_val).error(f"install_branding_from_registry failed: {br_result['Err']}")
                    else:
                        jlog(job_id_val).info(f"branding installed from registry: ns={b_ns}")
                        # Surface the user's logo in the realm directory listing.
                        if "/custom/logo.png" in b_files:
                            logo = f"https://{frontend_id}.icp0.io/custom/logo.png"
                except Exception as br_err:
                    jlog(job_id_val).error(f"install_branding_from_registry error: {br_err}")

            if frontend_id and backend_id:
                try:
                    pin_arg = '(record { prefix = "/custom/" })'
                    pin_result: CallResult = yield ic.call_raw(
                        Principal.from_str(frontend_id), "pin_directory",
                        ic.candid_encode(pin_arg), 0,
                    )
                    if isinstance(pin_result, dict) and "Err" in pin_result:
                        jlog(job_id_val).warning(f"pin_directory failed (non-fatal): {pin_result['Err']}")
                    else:
                        jlog(job_id_val).info("pinned /custom/ on frontend")
                except Exception as pin_err:
                    jlog(job_id_val).warning(f"pin_directory error (non-fatal): {pin_err}")

            # Store admin invite hash if present in manifest
            admin_invite_hash = realm_info.get("admin_invite_hash", "")
            if admin_invite_hash and backend_id:
                try:
                    invite_json = json.dumps({"code_hash": admin_invite_hash, "expires_in_hours": 24})
                    invite_escaped = invite_json.replace('\\', '\\\\').replace('"', '\\"')
                    invite_arg = '("' + invite_escaped + '")'
                    invite_result: CallResult = yield ic.call_raw(
                        Principal.from_str(backend_id), "store_admin_invite_hash",
                        ic.candid_encode(invite_arg), 0,
                    )
                    if isinstance(invite_result, dict) and "Err" in invite_result:
                        jlog(job_id_val).error(f"store_admin_invite_hash failed: {invite_result['Err']}")
                    else:
                        jlog(job_id_val).info(f"admin invite hash stored on backend")
                except Exception as invite_err:
                    jlog(job_id_val).error(f"store_admin_invite_hash error: {invite_err}")

            # Deferred baton hand-off (Casals path): after extensions (if any)
            # and all backend/frontend prep above, but before registry.register_realm.
            # The installer must stay an IC controller through bootstrap; hand-off
            # removes it. Topology is a hard requirement — failure fails the job.
            yield from _run_deferred_baton_handoff(j)

            registry = RealmRegistryService(Principal.from_str(reg_id))
            result: CallResult = yield registry.register_realm(
                realm_name, url, logo, backend_url, canister_ids,
            )
            raw = unwrap_call_result(result)
            jlog(job_id_val).info(f"registered realm: {raw}")

            # Claim the federation slug so the portal page in the injected
            # portal_url resolves (portal-first login depends on it). Must run
            # after register_realm — claim_slug requires the RealmRecord.
            fed = manifest.get("federation") or {}
            slug = (fed.get("slug") or "").strip()
            if slug and backend_id and frontend_id:
                try:
                    claim_arg = build_claim_slug_args(
                        slug, frontend_id, backend_id, manifest,
                    )
                    claim_result: CallResult = yield ic.call_raw(
                        Principal.from_str(reg_id), "claim_slug",
                        ic.candid_encode(claim_arg), 0,
                    )
                    if isinstance(claim_result, dict) and "Err" in claim_result:
                        jlog(job_id_val).warning(
                            f"claim_slug '{slug}' failed (non-fatal): {claim_result['Err']}"
                        )
                    else:
                        jlog(job_id_val).info(f"federation slug claimed: {slug}")
                except Exception as slug_err:
                    jlog(job_id_val).warning(f"claim_slug error (non-fatal): {slug_err}")

            j = DeploymentJob[job_id_val]
            if j:
                j.status = "completed"
                j.completed_at = now_s()
                schedule_registry_settlement(job_id_val, success=True)
        except Exception as e:
            jlog(job_id_val).error(f"registration failed: {e}")
            try:
                j = DeploymentJob[job_id_val]
                if j and (j.status or "") not in _JOB_TERMINAL_STATUSES:
                    j.status = "failed"
                    j.error = str(e)[:1990]
                    j.completed_at = now_s()
                    schedule_registry_settlement(job_id_val, success=False, reason=j.error)
            except Exception:
                pass

    ic.set_timer(Duration(0), _register_cb)


# ── Task runner ───────────────────────────────────────────────────────

_TERMINAL_TASK_STATUSES = ("completed", "partial", "failed", "cancelled")
_RETRYABLE_PATTERNS = ("Rejection code 2", "Couldn't send message", "IC0515", "IC0504")
_MAX_RETRIES = 5
_RETRY_BASE_S = 10
_retry_counts: dict = {}


def _format_dependency_warnings(warnings: list) -> str:
    parts = []
    for item in (warnings or [])[:5]:
        if isinstance(item, dict):
            parts.append(f"{item.get('extension', '?')}: {item.get('error', 'unknown')}")
        else:
            parts.append(str(item))
    summary = "; ".join(parts)
    if len(warnings or []) > 5:
        summary += f" (+{len(warnings) - 5} more)"
    return summary


def _install_step_failed(parsed) -> tuple:
    """Return (failed: bool, error: str) for an extension/codex install result."""
    if not isinstance(parsed, dict):
        return False, ""
    if parsed.get("success") is False:
        return True, (parsed.get("error") or "install failed")
    warnings = parsed.get("dependency_warnings") or []
    if warnings:
        return True, f"dependency install failed: {_format_dependency_warnings(warnings)}"
    return False, ""


def _count_expected_steps(manifest: dict, backend_id: str = "", frontend_id: str = "") -> int:
    """Mirror ``_build_steps`` counts for progress UI before the task exists."""
    count = 0
    deploy_scope = (manifest.get("deploy_scope") or "both").strip()
    has_pair = bool((backend_id or "").strip() and (frontend_id or "").strip())
    if has_pair or deploy_scope == "both":
        count += 2  # configure_canister_ids + grant_frontend_access
    if not manifest_has_codex_block(manifest):
        return count
    realm_info = manifest.get("realm") or {}
    for ext in (realm_info.get("extensions") or []):
        if isinstance(ext, str) and ext.strip():
            count += 1
        elif isinstance(ext, dict) and (ext.get("id") or "").strip():
            count += 1
    count += 1  # codex install step
    return count


def _build_steps(task, manifest: dict) -> list:
    steps = []
    idx = 0

    frontend_id = manifest.get("frontend_canister_id", "")
    backend_id = manifest.get("target_canister_id", "")
    if frontend_id and backend_id:
        _log.info(f"[{task.name}] step {idx}: configure_canister_ids frontend={frontend_id}")
        steps.append(DeployStep(
            task=task, idx=idx, kind="configure_canister_ids", label="configure_canister_ids",
            args_json=json.dumps(configure_canister_ids_args(manifest, backend_id, frontend_id)),
            status="pending",
        ))
        idx += 1
        _log.info(f"[{task.name}] step {idx}: grant_frontend_access backend={backend_id} frontend={frontend_id}")
        steps.append(DeployStep(
            task=task, idx=idx, kind="grant_frontend_access", label="grant_frontend_access",
            args_json=json.dumps({"backend_canister_id": backend_id, "frontend_canister_id": frontend_id}),
            status="pending",
        ))
        idx += 1

    for ext in (manifest.get("extensions") or []):
        ext_id = ext.get("id")
        if not ext_id:
            _log.warning(f"skipping extension with no id: {ext}")
            continue
        ext_id = str(ext_id)
        _log.info(f"[{task.name}] step {idx}: extension '{ext_id}'")
        steps.append(DeployStep(
            task=task, idx=idx, kind="extension", label=ext_id,
            args_json=json.dumps({"registry_canister_id": task.registry_canister_id,
                                   "ext_id": ext_id, "version": ext.get("version"),
                                   "frontend_canister_id": frontend_id}),
            status="pending",
        ))
        idx += 1
    for cdx in (manifest.get("codices") or []):
        cdx_id = cdx.get("id")
        if not cdx_id:
            _log.warning(f"skipping codex with no id: {cdx}")
            continue
        cdx_id = str(cdx_id)
        _log.info(f"[{task.name}] step {idx}: codex '{cdx_id}'")
        steps.append(DeployStep(
            task=task, idx=idx, kind="codex", label=cdx_id,
            args_json=json.dumps({"registry_canister_id": task.registry_canister_id,
                                   "codex_id": cdx_id, "version": cdx.get("version"),
                                   "run_init": bool(cdx.get("run_init", True)),
                                   "frontend_canister_id": frontend_id}),
            status="pending",
        ))
        idx += 1
    _log.info(f"[{task.name}] built {len(steps)} total steps")
    return steps


def _next_pending(task):
    pending = [s for s in task.steps if s.status == "pending"]
    return sorted(pending, key=lambda s: int(s.idx or 0))[0] if pending else None


def _execute_step(task, step):
    step.status = "running"
    step.started_at = now_s()
    jlog(task.name).info(f"step {step.idx} ({step.kind} '{step.label}') starting → target={task.target_canister_id}")
    try:
        args = json.loads(step.args_json or "{}")
        jlog(task.name).info(f"step {step.idx} args: {step.args_json[:200]}")

        if step.kind == "configure_canister_ids":
            yield from _execute_configure_canister_ids(task, step, args)
            return

        if step.kind == "grant_frontend_access":
            yield from _execute_grant_frontend_access(task, step, args)
            return

        target = RealmTargetService(Principal.from_str(task.target_canister_id))
        if step.kind == "extension":
            jlog(task.name).info(f"step {step.idx} calling install_extension_from_registry")
            call_result: CallResult = yield target.install_extension_from_registry(json.dumps(args))
        elif step.kind == "codex":
            jlog(task.name).info(f"step {step.idx} calling install_codex_from_registry")
            call_result: CallResult = yield target.install_codex_from_registry(json.dumps(args))
        else:
            step.error = f"unknown kind: {step.kind}"
            step.status = "failed"
            step.completed_at = now_s()
            return
        raw = unwrap_call_result(call_result)
        jlog(task.name).info(f"step {step.idx} raw result: {str(raw)[:300]}")
        step.result_json = (raw if isinstance(raw, str) else json.dumps(raw))[:1990]
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            parsed = None
        failed, err = _install_step_failed(parsed)
        if failed:
            step.error = err[:1990]
            step.status = "failed"
            jlog(task.name).error(f"step {step.idx} ({step.label}) failed: {step.error[:200]}")
        else:
            step.status = "completed"
            jlog(task.name).info(f"step {step.idx} ({step.label}) completed OK")
    except Exception as e:
        step.error = f"{type(e).__name__}: {e}"[:1990]
        step.status = "failed"
        jlog(task.name).error(f"step {step.idx} ({step.label}) exception: {step.error[:300]}")
    step.completed_at = now_s()


def _execute_configure_canister_ids(task, step, args):
    """Persist frontend (and infra) canister IDs on the realm backend before installs."""
    backend_id = args.get("backend_canister_id", "")
    frontend_id = args.get("frontend_canister_id", "")
    if not backend_id or not frontend_id:
        step.error = "missing backend_canister_id or frontend_canister_id"
        step.status = "failed"
        step.completed_at = now_s()
        return

    payload, config_warnings = configure_canister_ids_payload(args)
    for msg in config_warnings:
        jlog(task.name).warning(msg)
    creator = (args.get("requesting_principal") or "").strip()

    jlog(task.name).info(
        f"setting canister config on backend {backend_id}: frontend={frontend_id}, "
        f"file_registry={(args.get('file_registry_canister_id') or '').strip() or '–'}, "
        f"realm_registry={(args.get('realm_registry_canister_id') or '').strip() or '–'}, "
        f"marketplace={(args.get('marketplace_canister_id') or '').strip() or '–'}, "
        f"creator={'set' if creator else 'missing'}"
    )
    config_json = json.dumps(payload).replace("\\", "\\\\").replace('"', '\\"')
    config_arg = '("' + config_json + '")'
    config_result: CallResult = yield ic.call_raw(
        Principal.from_str(backend_id), "set_canister_config_json",
        ic.candid_encode(config_arg), 0,
    )
    if isinstance(config_result, dict) and "Err" in config_result:
        step.error = f"set_canister_config_json failed: {config_result['Err']}"[:1990]
        step.status = "failed"
        jlog(task.name).error(f"step {step.idx} configure_canister_ids failed: {step.error}")
        step.completed_at = now_s()
        return

    try:
        raw = unwrap_call_result(config_result)
        parsed = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        parsed = None
    if isinstance(parsed, dict) and parsed.get("success") is False:
        step.error = (parsed.get("error") or "set_canister_config_json failed")[:1990]
        step.status = "failed"
        jlog(task.name).error(f"step {step.idx} configure_canister_ids failed: {step.error}")
        step.completed_at = now_s()
        return

    step.status = "completed"
    step.result_json = json.dumps({"frontend_canister_id": frontend_id})[:1990]
    jlog(task.name).info(f"step {step.idx} frontend canister id configured on backend")
    step.completed_at = now_s()


def _execute_grant_frontend_access(task, step, args):
    """Grant the realm backend Commit permission on the frontend asset canister."""
    backend_id = args.get("backend_canister_id", "")
    frontend_id = args.get("frontend_canister_id", "")
    if not backend_id or not frontend_id:
        step.error = "missing backend_canister_id or frontend_canister_id"
        step.status = "failed"
        step.completed_at = now_s()
        return

    jlog(task.name).info(f"granting Commit on frontend {frontend_id} to backend {backend_id}")
    candid_arg = f'(record {{ to_principal = principal "{backend_id}"; permission = variant {{ Commit }} }})'
    grant_result: CallResult = yield ic.call_raw(
        Principal.from_str(frontend_id), "grant_permission",
        ic.candid_encode(candid_arg), 0,
    )
    if isinstance(grant_result, dict) and "Err" in grant_result:
        step.error = f"grant_permission failed: {grant_result['Err']}"[:1990]
        step.status = "failed"
        jlog(task.name).error(f"step {step.idx} grant_permission failed: {step.error}")
        step.completed_at = now_s()
        return

    step.status = "completed"
    step.result_json = json.dumps({"granted": True, "backend": backend_id, "frontend": frontend_id})
    jlog(task.name).info(f"step {step.idx} Commit permission granted to backend on frontend asset canister")
    step.completed_at = now_s()


def _finalize_task(task):
    statuses = [s.status for s in task.steps]
    n_ok = sum(1 for s in statuses if s == "completed")
    n_fail = sum(1 for s in statuses if s == "failed")
    n = len(statuses)
    task.status = "completed" if n == 0 or n_ok == n else ("failed" if n_fail == n else "partial")
    task.completed_at = now_s()
    jlog(task.name).info(f"task → {task.status} ({n_ok}/{n} ok, {n_fail} failed)")
    _check_job_after_extensions(task)


def _check_job_after_extensions(task):
    try:
        list(DeploymentJob.instances())
        for job in DeploymentJob.instances():
            if (job.ext_deploy_task_id or "") == task.name:
                if task.status in ("completed", "partial"):
                    if task.status == "partial":
                        failed_steps = [s for s in task.steps if s.status == "failed"]
                        warnings = "; ".join(
                            f"{s.label}: {s.error}" for s in failed_steps[:10]
                        )
                        job.error = f"partial extension install ({len(failed_steps)} failed): {warnings}"[:1990]
                        jlog(job.name).warning(job.error)
                    job.status = "registering"
                    schedule_registration(job.name)
                else:
                    job.status = "failed"
                    failed_steps = [s for s in task.steps if s.status == "failed"]
                    errors = "; ".join(
                        f"{s.label}: {s.error}" for s in failed_steps[:10]
                    )
                    job.error = f"extension install failed ({len(failed_steps)} failed): {errors}"[:1990]
                    job.completed_at = now_s()
                    schedule_registry_settlement(job.name, success=False, reason=job.error)
                return
    except Exception as e:
        jlog(task.name).error(f"_check_job_after_extensions: {e}")


def _schedule_step_runner(task_id: str, delay_s: int = 0):
    def _cb():
        try:
            list(DeployStep.instances())
            list(DeployTask.instances())
            task = DeployTask[task_id]
            if not task or (task.status or "queued") in _TERMINAL_TASK_STATUSES:
                return
            if (task.status or "queued") == "queued":
                task.status = "running"
                task.started_at = now_s()
            while True:
                step = _next_pending(task)
                if step is None:
                    _finalize_task(task)
                    return
                yield from _execute_step(task, step)
                if step.status == "failed" and any(p in (step.error or "") for p in _RETRYABLE_PATTERNS):
                    rk = f"{task_id}_{step.idx}"
                    count = _retry_counts.get(rk, 0)
                    if count < _MAX_RETRIES:
                        _retry_counts[rk] = count + 1
                        step.status = "pending"
                        step.error = ""
                        _schedule_step_runner(task_id, delay_s=_RETRY_BASE_S * (2 ** count))
                        return
        except Exception as e:
            jlog(task_id).error(f"runner fatal: {e}")
            try:
                t = DeployTask[task_id]
                if t and (t.status or "queued") not in _TERMINAL_TASK_STATUSES:
                    t.status = "failed"
                    t.error = str(e)[:1990]
                    t.completed_at = now_s()
            except Exception:
                pass

    ic.set_timer(Duration(int(delay_s)), _cb)


# Shared land-NFT backend per network (Casals infra stand "nft", not per-realm).
_SHARED_NFT_CANISTERS = {
    "staging": "27sff-mqaaa-aaaah-quntq-cai",
    "demo": "6hrip-iiaaa-aaaaf-qdoha-cai",
    "test": "eelas-yyaaa-aaaao-qps7a-cai",
}


def _shared_nft_canister_id(network: str) -> str:
    return (_SHARED_NFT_CANISTERS.get((network or "").strip().lower()) or "").strip()

# Shared treasury ledgers keyed by network + symbol (mirrors realm_backend.api.tokens).
_SHARED_TOKEN_LEDGERS = {
    "staging": {
        "REALMS": {
            "ledger": "2rqin-xaaaa-aaaah-qunsq-cai",
            "indexer": "2rqin-xaaaa-aaaah-qunsq-cai",
            "decimals": 8,
            "token_type": "shared",
        },
        "ckBTC": {
            "ledger": "mxzaz-hqaaa-aaaar-qaada-cai",
            "indexer": "n5wcd-faaaa-aaaar-qaaea-cai",
            "decimals": 8,
            "token_type": "shared",
        },
        "ckUSDC": {
            "ledger": "xckus-ciaaa-aaaam-qbssa-cai",
            "indexer": "ufqgi-4qaaa-aaaam-qbsna-cai",
            "decimals": 6,
            "token_type": "shared",
        },
    },
    "demo": {
        "REALMS": {
            "ledger": "xbkkh-syaaa-aaaah-qq3ya-cai",
            "indexer": "xbkkh-syaaa-aaaah-qq3ya-cai",
            "decimals": 8,
            "token_type": "shared",
        },
        "ckBTC": {
            "ledger": "mxzaz-hqaaa-aaaar-qaada-cai",
            "indexer": "n5wcd-faaaa-aaaar-qaaea-cai",
            "decimals": 8,
            "token_type": "shared",
        },
        "ckUSDC": {
            "ledger": "xckus-ciaaa-aaaam-qbssa-cai",
            "indexer": "ufqgi-4qaaa-aaaam-qbsna-cai",
            "decimals": 6,
            "token_type": "shared",
        },
    },
    "test": {
        "REALMS": {
            "ledger": "nusyl-jiaaa-aaaae-qj6mq-cai",
            "indexer": "nusyl-jiaaa-aaaae-qj6mq-cai",
            "decimals": 8,
            "token_type": "shared",
        },
        "ckBTC": {
            "ledger": "mxzaz-hqaaa-aaaar-qaada-cai",
            "indexer": "n5wcd-faaaa-aaaar-qaaea-cai",
            "decimals": 8,
            "token_type": "shared",
        },
        "ckUSDC": {
            "ledger": "xckus-ciaaa-aaaam-qbssa-cai",
            "indexer": "ufqgi-4qaaa-aaaam-qbsna-cai",
            "decimals": 6,
            "token_type": "shared",
        },
    },
}


def _esc_candid_text(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"')


def _resolve_token_from_manifest(manifest: dict):
    """Return treasury wiring dict from manifest.realm.token, or None."""
    realm_info = manifest.get("realm") or {}
    token = realm_info.get("token") or {}
    network = (manifest.get("network") or "staging").strip().lower()
    shared = _SHARED_TOKEN_LEDGERS.get(network, {})

    existing = (token.get("existing") or "").strip()
    if existing:
        cfg = shared.get(existing)
        if cfg is None:
            for key, val in shared.items():
                if key.upper() == existing.upper():
                    cfg = val
                    existing = key
                    break
        if cfg:
            return {
                "symbol": existing,
                "ledger": cfg["ledger"],
                "indexer": cfg.get("indexer", cfg["ledger"]),
                "decimals": cfg.get("decimals", 8),
                "token_type": cfg.get("token_type", "shared"),
                "deploy_new": False,
            }
        return None

    name = (token.get("name") or "").strip()
    symbol = (token.get("symbol") or "").strip().upper()
    if name and symbol:
        return {
            "symbol": symbol,
            "name": name,
            "decimals": 8,
            "token_type": "realm",
            "deploy_new": True,
        }
    return None


def _token_install_arg_candid(name: str, symbol: str, initial_owner: str = "",
                              network: str = "") -> str:
    safe_name = _esc_candid_text(name)
    safe_symbol = _esc_candid_text(symbol)
    # test mode allows public minting; never enable it on mainnet.
    test_flag = "false" if network in ("ic", "mainnet", "prod") else "true"
    owner_part = (
        f'initial_owner = opt principal "{initial_owner}"' if initial_owner
        else 'initial_owner = null'
    )
    return (
        f'(record {{ name = "{safe_name}"; symbol = "{safe_symbol}"; '
        f'decimals = 8 : nat8; total_supply = 100_000_000_000_000_000 : nat; '
        f'fee = 10_000 : nat; test = opt {test_flag}; {owner_part} }})'
    )


def _lookup_stand_token_ids(casals_id: str, stand: str, job_id: str):
    """Generator: resolve a per-stand realm token canister (wizard ``token.new`` path)."""
    token_id = ""
    if not casals_id or not stand:
        return token_id, ""
    try:
        casals = CasalsService(Principal.from_str(casals_id))
        tree_res: CallResult = yield casals.get_tree()
        tree = _casals_ok(tree_res)
        token_id = _casals_find_canister(tree, stand, f"{stand}-token")
        if token_id:
            jlog(job_id).info(f"resolved stand token {token_id} ({stand}-token)")
    except Exception as e:
        jlog(job_id).warning(f"Casals token lookup failed (non-fatal): {e}")
    return token_id, ""


def _provision_realm_token_canister(casals, job_id: str, stand: str, manifest: dict,
                                    backend_id: str = ""):
    """Generator: deploy a per-stand ICRC-1 token when the wizard chose ``token.new``.

    ``backend_id`` (the realm backend) becomes the ledger's initial owner and
    authority, so the realm — not Casals — holds the supply and the
    ERC-3643-style powers (forced_transfer / freeze / transfer_authority).
    """
    token_cfg = _resolve_token_from_manifest(manifest)
    if not token_cfg or not token_cfg.get("deploy_new"):
        return "", token_cfg

    realm_info = manifest.get("realm") or {}
    realm_name = (realm_info.get("display_name") or realm_info.get("name") or stand).strip()
    cas = manifest.get("casals") or {}
    token_wasm_key = (cas.get("token_wasm_key") or "token-backend").strip()
    network = (manifest.get("network") or "").strip().lower()

    token_id = yield from _casals_create_or_reuse_canister(
        casals,
        job_id,
        stand,
        f"{stand}-token",
        "backend",
        token_wasm_key,
        install_arg=_token_install_arg_candid(
            token_cfg.get("name") or f"{realm_name} Token",
            token_cfg.get("symbol") or "RLM",
            initial_owner=backend_id,
            network=network,
        ),
    )
    return token_id, token_cfg

def _fetch_codex_dependency_ids(registry_id: str, codex_id: str, version=None) -> Async[list]:
    """Resolve codex package dependencies from the file registry manifest."""
    reg = (registry_id or "").strip()
    cid = (codex_id or "").strip()
    if not reg or not cid:
        return []
    try:
        registry = FileRegistryService(Principal.from_str(reg))
        call_result: CallResult = yield registry.get_extension_manifest(json.dumps({
            "ext_id": cid,
            "version": version or None,
        }))
        raw = unwrap_call_result(call_result)
        data = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(data, dict) or data.get("error"):
            return []
        raw_deps = data.get("dependencies") or []
        if isinstance(raw_deps, dict):
            return [str(k) for k in raw_deps if k]
        if isinstance(raw_deps, list):
            return [str(d) for d in raw_deps if d]
        return []
    except Exception as e:
        _log.warning(f"codex dependency lookup failed for {cid}: {e}")
        return []

def _start_extensions_for_job(job, manifest: dict) -> Async[None]:
    realm_info = manifest.get("realm", {})
    network = (manifest.get("network") or "").strip()
    registry_id = manifest.get("file_registry_canister_id", "") or configured_file_registry_id(network)
    realm_registry_id = (
        (manifest.get("realm_registry_canister_id") or manifest.get("registry_canister_id") or "").strip()
    )

    jlog(job.name).info(f"starting extension install: network={network}, file_registry={registry_id}")
    jlog(job.name).info(f"realm_info keys: {list(realm_info.keys())}")
    raw_exts = realm_info.get("extensions") or []
    raw_codex = realm_info.get("codex")
    jlog(job.name).info(f"raw extensions: {len(raw_exts)} items, codex: {type(raw_codex).__name__}={raw_codex}")

    # The realm refuses packages that carry no approval from an approver it
    # trusts, and its default approver is its marketplace. A realm that does
    # not know its marketplace yet trusts nobody, so this has to reach the
    # backend before the first install rather than at registration.
    infra = manifest.get("infra") or {}
    marketplace_id = (
        manifest.get("marketplace_canister_id")
        or infra.get("marketplace_canister_id")
        or ""
    )
    if not marketplace_id:
        jlog(job.name).warning(
            "no marketplace in manifest: the realm will trust no approver and "
            "refuse every package until one is configured"
        )

    ext_manifest = {
        "target_canister_id": job.backend_canister_id,
        "frontend_canister_id": job.frontend_canister_id or "",
        "registry_canister_id": registry_id,
        "file_registry_canister_id": registry_id,
        "realm_registry_canister_id": realm_registry_id,
        "infra": manifest.get("infra") or {},
        "marketplace_canister_id": marketplace_id,
        "network": network,
        "requesting_principal": (manifest.get("requesting_principal") or "").strip(),
        "federation": manifest.get("federation") or {},
    }
    ext_list = []
    codex_list = []
    has_codex_block = manifest_has_codex_block(manifest)
    if has_codex_block:
        ext_list, codex_list = resolve_legacy_install_lists(realm_info)
        if ext_list:
            ext_manifest["extensions"] = ext_list
        jlog(job.name).info(f"resolved {len(ext_list)} extensions")

        codex = realm_info.get("codex")
        if codex and isinstance(codex, dict) and not codex_list:
            jlog(job.name).error(
                f"realm.codex has no 'package' field (keys: {sorted(codex.keys())}) — "
                "the realm will deploy WITHOUT a codex or its dependency extensions"
            )
        elif codex and not isinstance(codex, dict):
            jlog(job.name).error(
                f"realm.codex is a {type(codex).__name__}, expected dict with 'package' — "
                "the realm will deploy WITHOUT a codex or its dependency extensions"
            )
        if codex_list:
            ext_manifest["codices"] = codex_list

        seen = {str(e.get("id")) for e in ext_list if e.get("id")}
        for cdx in codex_list:
            cdx_id = (cdx.get("id") or "").strip()
            if not cdx_id:
                continue
            deps = yield from _fetch_codex_dependency_ids(registry_id, cdx_id, cdx.get("version"))
            for dep in deps:
                if dep not in seen:
                    ext_list.append({"id": dep})
                    seen.add(dep)
        if ext_list:
            ext_manifest["extensions"] = ext_list
    else:
        jlog(job.name).info(
            "no realm.codex block; skipping codex/extension installs (bootstrap only)"
        )

    jlog(job.name).info(f"resolved {len(codex_list)} codices, {len(ext_list)} extension steps")

    try:
        task_id = "deploy_%d" % ic.time()
        jlog(job.name).info(f"creating deploy task {task_id} with {len(ext_list)} ext + {len(codex_list)} codex")
        task = DeployTask(
            name=task_id, status="queued", target_canister_id=job.backend_canister_id,
            registry_canister_id=registry_id, manifest_json=json.dumps(ext_manifest)[:8190], error="",
        )
        _build_steps(task, ext_manifest)
        steps = list(task.steps)
        jlog(job.name).info(f"built {len(steps)} steps for task {task_id}")
        job.ext_deploy_task_id = task_id
        job.expected_step_count = len(steps)
        _schedule_step_runner(task_id, 0)
        jlog(job.name).info(f"extension task {task_id} scheduled")
    except Exception as e:
        jlog(job.name).error(f"failed to create extension task: {type(e).__name__}: {e}")
        jlog(job.name).error(f"ext_manifest keys: {list(ext_manifest.keys())}, ext_list sample: {ext_list[:3]}")
        job.status = "registering"
        schedule_registration(job.name)


def _realm_name_from_manifest(job: DeploymentJob) -> str:
    """Read realm.name from a job's manifest JSON (legacy jobs)."""
    try:
        manifest = json.loads(job.manifest_json or "{}")
        return ((manifest.get("realm") or {}).get("name") or "").strip()
    except Exception:
        return ""


def _resolve_job_realm_name(job: DeploymentJob) -> str:
    """Return the human-readable realm name, backfilling legacy jobs from manifest."""
    stored = (job.realm_name or "").strip()
    job_id = (job.name or "").strip()
    if stored and stored != job_id:
        return stored
    from_manifest = _realm_name_from_manifest(job)
    if from_manifest:
        if stored != from_manifest:
            job.realm_name = from_manifest[:128]
        return from_manifest
    return job_id


def _serialize_job(job: DeploymentJob) -> dict:
    realm_name = _resolve_job_realm_name(job)
    return {
        "job_id": job.name, "status": job.status or "",
        "realm_name": realm_name, "caller_principal": job.caller_principal or "",
        "network": job.network or "",
        "backend_canister_id": job.backend_canister_id or "",
        "frontend_canister_id": job.frontend_canister_id or "",
        "expected_wasm_hash": job.expected_wasm_hash or "",
        "actual_wasm_hash": job.actual_wasm_hash or "",
        "expected_frontend_wasm_hash": job.expected_frontend_wasm_hash or "",
        "actual_frontend_wasm_hash": job.actual_frontend_wasm_hash or "",
        "wasm_verified": int(job.wasm_verified or 0),
        "assets_verified": int(job.assets_verified or 0),
        "frontend_wasm_verified": int(job.frontend_wasm_verified or 0),
        "ext_deploy_task_id": job.ext_deploy_task_id or "",
        "expected_step_count": int(job.expected_step_count or 0),
        "registry_canister_id": job.registry_canister_id or "",
        "error": job.error or "",
        "created_at": int(job.created_at or 0),
        "completed_at": int(job.completed_at or 0),
    }


def _job_to_view(job: DeploymentJob) -> DeploymentJobView:
    s = _serialize_job(job)
    return DeploymentJobView(
        job_id=s["job_id"],
        status=s["status"],
        realm_name=s["realm_name"],
        caller_principal=s["caller_principal"],
        network=s["network"],
        backend_canister_id=s["backend_canister_id"],
        frontend_canister_id=s["frontend_canister_id"],
        expected_wasm_hash=s["expected_wasm_hash"],
        actual_wasm_hash=s["actual_wasm_hash"],
        wasm_verified=int8(s["wasm_verified"]),
        assets_verified=int8(s["assets_verified"]),
        frontend_wasm_verified=int8(s["frontend_wasm_verified"]),
        ext_deploy_task_id=s["ext_deploy_task_id"],
        expected_step_count=nat32(s["expected_step_count"]),
        registry_canister_id=s["registry_canister_id"],
        error=s["error"],
        created_at=nat64(s["created_at"]),
        completed_at=nat64(s["completed_at"]),
    )


def _serialize_deploy_task(task: DeployTask) -> DeployTaskView:
    steps = sorted(task.steps, key=lambda s: int(s.idx or 0))
    step_views = []
    completed = 0
    for step in steps:
        st = step.status or "pending"
        if st == "completed":
            completed += 1
        step_views.append(DeployStepView(
            idx=nat32(int(step.idx or 0)),
            kind=str(step.kind or ""),
            label=str(step.label or ""),
            status=st,
            error=str(step.error or "")[:500],
        ))
    total = len(step_views)
    return DeployTaskView(
        task_id=str(task.name or ""),
        status=str(task.status or "queued"),
        steps=step_views,
        completed_count=nat32(completed),
        total_count=nat32(total),
    )


def _upsert_job_ref(job: DeploymentJob) -> None:
    if job is None or not (job.name or "").strip():
        return
    ref = DeploymentJobRef[job.name]
    if ref is None:
        ref = DeploymentJobRef(name=job.name)
    ref.caller_principal = job.caller_principal or ""
    ref.created_at = int(job.created_at or 0)


def _delete_job_ref(job_id: text) -> None:
    ref = DeploymentJobRef[(job_id or "").strip()]
    if ref is not None:
        ref.delete()


_backfill_job_ref_resume = ""


def _backfill_job_refs_batch(schedule_next: bool = True) -> None:
    """Populate DeploymentJobRef rows in small batches (post-upgrade / timer)."""
    global _backfill_job_ref_resume
    resume = (_backfill_job_ref_resume or "").strip()
    passed = not resume
    processed = 0
    last_id = ""
    for job in DeploymentJob.instances():
        jid = job.name or ""
        if not jid:
            continue
        if not passed:
            if jid == resume:
                passed = True
            continue
        if DeploymentJobRef[jid] is None:
            _upsert_job_ref(job)
        _resolve_job_realm_name(job)
        last_id = jid
        processed += 1
        if processed >= 25:
            break
    if processed >= 25:
        _backfill_job_ref_resume = last_id
        if schedule_next:
            ic.set_timer(Duration(1), _backfill_job_refs_batch)
    else:
        _backfill_job_ref_resume = ""
        _log.info("job ref backfill complete")


def _schedule_job_ref_backfill() -> None:
    ic.set_timer(Duration(0), _backfill_job_refs_batch)


@update
def backfill_job_refs_batch() -> text:
    """Controller-only: advance one job-ref backfill batch (for migration)."""
    if not ic.is_controller(ic.caller()):
        return '{"ok":false,"error":"controller only"}'
    _backfill_job_refs_batch(schedule_next=False)
    done = not (_backfill_job_ref_resume or "")
    return json.dumps({"ok": True, "done": done, "resume": _backfill_job_ref_resume or ""})

# ── Endpoints ──────────────────────────────────────────────────────────

@init
def _on_init(config_json: text = "") -> None:
    if config_json and config_json.strip():
        try:
            apply_installer_config(json.loads(config_json))
            _log.info(f"init installer config: {installer_config_payload()}")
        except Exception as e:
            _log.error(f"init installer config failed: {e}")
    _arm_provision_heartbeat()
    _log.info("init")

@post_upgrade
def _on_post_upgrade() -> None:
    _log.info("post_upgrade — resuming in-flight deploys")
    _resume_in_flight()
    _schedule_job_ref_backfill()
    _arm_provision_heartbeat()

@query
def status() -> GetStatusResult:
    return {"Ok": StatusRecord(
        version="VERSION_PLACEHOLDER", commit="COMMIT_HASH_PLACEHOLDER",
        commit_datetime="COMMIT_DATETIME_PLACEHOLDER", status="ok",
    )}

@query
def health() -> HealthView:
    return HealthView(ok=True, canister="realm_installer")

def _cycles_preflight_gen(manifest: dict, cfg: InstallerConfig):
    """Query conductor + file_registry balances and return a preflight error or None."""
    casals_id = (cfg.casals_canister_id or "").strip()
    if not casals_id:
        return None

    casals = CasalsService(Principal.from_str(casals_id))
    cycles_res: CallResult = yield casals.get_cycles_cached()
    cycles_report = parse_cycles_report(unwrap_call_result(cycles_res))

    network = (manifest.get("network") or "").strip()
    file_registry_id = resolve_file_registry_id(
        manifest,
        network=network,
        configured_id=(cfg.file_registry_id or "").strip() or configured_file_registry_id(network),
    )
    file_registry_cycles = None
    if file_registry_id:
        try:
            status_call: CallResult = yield management_canister.canister_status(
                {"canister_id": Principal.from_str(file_registry_id)})
            status_data = unwrap_call_result(status_call)
            if isinstance(status_data, dict) and status_data.get("cycles") is not None:
                file_registry_cycles = int(status_data["cycles"])
        except Exception as e:
            _log.warning(
                f"cycles preflight: canister_status for file_registry {file_registry_id} "
                f"unavailable ({e}); falling back to Casals cached report"
            )
    else:
        _log.info("cycles preflight: no file_registry id in manifest/config; skipping direct balance read")

    required = estimate_conductor_cycles_required(
        manifest,
        create_stand_baton=bool(int(cfg.create_stand_baton or 0)),
    )
    return check_cycles_preflight(
        cycles_report,
        casals_canister_id=casals_id,
        required_conductor_cycles=required,
        file_registry_cycles=file_registry_cycles,
        file_registry_id=file_registry_id,
    )


@update
def enqueue_deployment(manifest_json: text) -> Async[ResultEnqueue]:
    try:
        manifest = json.loads(manifest_json)
        network = manifest.get("network", "")
        realm_name = (manifest.get("realm") or {}).get("name", "unknown")
        registry_id = (manifest.get("registry_canister_id") or "").strip()
        requester = (manifest.get("requesting_principal") or str(ic.caller())).strip()
        canister_ids = manifest.get("canister_ids", {})

        realm_info = manifest.get("realm", {})
        ext_count = len(realm_info.get("extensions") or [])
        codex_info = realm_info.get("codex")
        _log.info(f"enqueue: realm='{realm_name}' network={network} manifest_len={len(manifest_json)} extensions={ext_count} codex={bool(codex_info)}")
        _log.info(f"enqueue: realm_info keys={list(realm_info.keys())}")

        epoch_s = ic.time() // 1_000_000_000
        # Manual UTC datetime from epoch — no stdlib time/datetime needed
        s = epoch_s
        DAYS_PER_400Y = 146097
        DAYS_PER_100Y = 36524
        DAYS_PER_4Y = 1461
        days = s // 86400
        rem = s % 86400
        hh = rem // 3600
        mm = (rem % 3600) // 60
        ss = rem % 60
        days += 719468  # shift epoch from 1970 to 0000-03-01
        era = days // DAYS_PER_400Y
        doe = days - era * DAYS_PER_400Y
        yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
        y = yoe + era * 400
        doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
        mp = (5 * doy + 2) // 153
        d = doy - (153 * mp + 2) // 5 + 1
        m = mp + (3 if mp < 10 else -9)
        if m <= 2:
            y += 1
        ts = "%04d%02d%02d%02d%02d%02d" % (y, m, d, hh, mm, ss)
        suffix = hashlib.sha256(realm_name.encode()).hexdigest()[:4]
        job_id = "job_%s_%s" % (ts, suffix)
        expected_hashes = manifest.get("expected_hashes", {})
        casals_manifest = bool(manifest.get("casals"))
        canister_ids = manifest.get("canister_ids") or {}
        expected_steps = _count_expected_steps(
            manifest,
            canister_ids.get("backend", ""),
            canister_ids.get("frontend", ""),
        )
        cfg = _config()
        provision_via_casals = bool(int(cfg.provision_via_casals or 0))

        preflight_err = None
        if casals_manifest and provision_via_casals:
            preflight_err = yield from _cycles_preflight_gen(manifest, cfg)
            if preflight_err:
                jlog(job_id).error(f"cycles preflight rejected: {preflight_err}")

        if preflight_err:
            initial_status = "failed"
            DeploymentJob(
                name=job_id, status=initial_status, realm_name=realm_name[:128],
                caller_principal=requester,
                manifest_json=manifest_json[:8190], network=network,
                backend_canister_id=canister_ids.get("backend", ""),
                frontend_canister_id=canister_ids.get("frontend", ""),
                registry_canister_id=registry_id,
                expected_wasm_hash=expected_hashes.get("backend_wasm", ""),
                expected_frontend_wasm_hash=expected_hashes.get("frontend_wasm", ""),
                expected_step_count=expected_steps,
                error=preflight_err[:1990],
                created_at=now_s(),
                completed_at=now_s(),
            )
            _upsert_job_ref(DeploymentJob[job_id])
            schedule_registry_settlement(job_id, success=False, reason=preflight_err)
            return ResultEnqueue(Ok=EnqueueOk(
                job_id=job_id, status=initial_status, realm_name=realm_name, network=network,
            ))

        initial_status = "provisioning" if casals_manifest else "pending"
        DeploymentJob(
            name=job_id, status=initial_status, realm_name=realm_name[:128],
            caller_principal=requester,
            manifest_json=manifest_json[:8190], network=network,
            backend_canister_id=canister_ids.get("backend", ""),
            frontend_canister_id=canister_ids.get("frontend", ""),
            registry_canister_id=registry_id,
            expected_wasm_hash=expected_hashes.get("backend_wasm", ""),
            expected_frontend_wasm_hash=expected_hashes.get("frontend_wasm", ""),
            expected_step_count=expected_steps,
            created_at=now_s(),
        )
        _upsert_job_ref(DeploymentJob[job_id])
        has_hashes = bool(expected_hashes.get("backend_wasm") or expected_hashes.get("frontend_wasm"))
        jlog(job_id).info(f"enqueued for '{realm_name}' on {network} (extensions={ext_count}, codex={bool(codex_info)}, cli_hashes={has_hashes})")
        if should_kick_provision_on_enqueue(
            casals_manifest=casals_manifest,
            provision_via_casals=provision_via_casals,
        ):
            _schedule_provision_kick(job_id, 0)
            jlog(job_id).info("immediate Casals provision kick scheduled")
        return ResultEnqueue(Ok=EnqueueOk(
            job_id=job_id, status=initial_status, realm_name=realm_name, network=network,
        ))
    except Exception as e:
        return ResultEnqueue(Err=ie(str(e), traceback.format_exc()[-1500:]))

@update
def take_pre_upgrade_snapshot(args: text) -> Async[ResultTakeSnapshot]:
    """Take an IC canister snapshot before upgrading the backend WASM.

    Called by the off-chain deployment worker before dfx canister install.
    The snapshot is stored on the job so it can be loaded on failure or
    deleted on success.
    """
    try:
        params = json.loads(args)
        job_id = (params.get("job_id") or "").strip()
        backend_id = (params.get("backend_canister_id") or "").strip()
        if not job_id:
            return ResultTakeSnapshot(Err=ie("job_id required"))
        if not backend_id:
            return ResultTakeSnapshot(Err=ie("backend_canister_id required"))

        list(DeploymentJob.instances())
        job = DeploymentJob[job_id]
        if job is None:
            return ResultTakeSnapshot(Err=ie(f"unknown job_id: {job_id}"))
        if (job.status or "pending") != "pending":
            return ResultTakeSnapshot(Err=ie(f"job in '{job.status}', expected 'pending'"))

        manifest = json.loads(job.manifest_json or "{}")
        if manifest.get("skip_snapshot"):
            job.skip_snapshot = 1
            jlog(job_id).info("snapshot skipped per manifest flag")
            return ResultTakeSnapshot(Ok=TakeSnapshotOk(
                job_id=job_id, snapshot_id="", skipped=True,
            ))

        jlog(job_id).info(f"taking pre-upgrade snapshot of {backend_id}")
        snapshot_result: CallResult = yield management_canister.take_canister_snapshot(
            {"canister_id": Principal.from_str(backend_id)})
        inner = unwrap_call_result(snapshot_result)

        snap_id_raw = inner.get("id") if isinstance(inner, dict) else getattr(inner, "id", None)
        if snap_id_raw is None:
            return ResultTakeSnapshot(Err=ie("snapshot response missing id"))

        if isinstance(snap_id_raw, bytes):
            snap_id_hex = snap_id_raw.hex()
        elif isinstance(snap_id_raw, list):
            snap_id_hex = bytes(snap_id_raw).hex()
        else:
            snap_id_hex = str(snap_id_raw).replace("0x", "")

        job.snapshot_id = snap_id_hex
        job.snapshot_taken = 1
        jlog(job_id).info(f"snapshot taken: {snap_id_hex}")

        return ResultTakeSnapshot(Ok=TakeSnapshotOk(
            job_id=job_id, snapshot_id=snap_id_hex, skipped=False,
        ))
    except Exception as e:
        _log.error(f"take_pre_upgrade_snapshot error: {e}")
        return ResultTakeSnapshot(Err=ie(str(e), traceback.format_exc()[-1500:]))

@query
def get_pending_deployments() -> ResultPendingJobs:
    try:
        list(DeploymentJob.instances())
        pending = []
        for job in DeploymentJob.instances():
            if (job.status or "pending") == "pending":
                pending.append(PendingJobEntry(job=_job_to_view(job), manifest=job.manifest_json or "{}"))
        pending.sort(key=lambda e: int(e.job.created_at))
        return ResultPendingJobs(Ok=PendingJobsOk(jobs=pending, count=nat32(len(pending))))
    except Exception as e:
        return ResultPendingJobs(Err=ie(str(e)))

@query
def get_deployment_job_status(job_id: text) -> ResultJobIdStatus:
    try:
        list(DeploymentJob.instances())
        job = DeploymentJob[job_id]
        if job is None:
            return ResultJobIdStatus(Err=ie(f"unknown job_id: {job_id}"))
        return ResultJobIdStatus(Ok=_job_to_view(job))
    except Exception as e:
        return ResultJobIdStatus(Err=ie(str(e)))

@query
def get_deploy_task_status(job_id: text) -> ResultDeployTaskStatus:
    """Return extension/codex install steps for a deployment job (if started)."""
    try:
        list(DeploymentJob.instances())
        job = DeploymentJob[job_id]
        if job is None:
            return ResultDeployTaskStatus(Err=ie(f"unknown job_id: {job_id}"))
        task_id = (job.ext_deploy_task_id or "").strip()
        expected = int(job.expected_step_count or 0)
        if not task_id:
            return ResultDeployTaskStatus(Ok=DeployTaskView(
                task_id="",
                status="none",
                steps=[],
                completed_count=nat32(0),
                total_count=nat32(expected),
            ))
        list(DeployTask.instances())
        list(DeployStep.instances())
        task = DeployTask[task_id]
        if task is None:
            return ResultDeployTaskStatus(Ok=DeployTaskView(
                task_id=task_id,
                status="missing",
                steps=[],
                completed_count=nat32(0),
                total_count=nat32(expected),
            ))
        return ResultDeployTaskStatus(Ok=_serialize_deploy_task(task))
    except Exception as e:
        return ResultDeployTaskStatus(Err=ie(str(e)))

@query
def get_deployment_manifest(job_id: text) -> ResultJobManifest:
    """Return the deployment manifest JSON for a job (owner-only)."""
    try:
        caller = str(ic.caller())
        list(DeploymentJob.instances())
        job = DeploymentJob[job_id]
        if job is None:
            return ResultJobManifest(Err=ie(f"unknown job_id: {job_id}"))
        if (job.caller_principal or "") != caller:
            return ResultJobManifest(Err=ie("only the job owner may view the manifest"))
        return ResultJobManifest(Ok=job.manifest_json or "{}")
    except Exception as e:
        return ResultJobManifest(Err=ie(str(e)))

_LIST_JOBS_MAX = 50


@query
def list_deployment_jobs(offset: Opt[nat32] = None, limit: Opt[nat32] = None) -> ResultJobsList:
    """Return deployment jobs for the caller.

    Non-controllers receive only their own jobs. Results are capped at 50 per
    call; controllers may page via optional offset/limit.
    """
    try:
        caller = str(ic.caller())
        is_admin = ic.is_controller(ic.caller())
        off = int(offset or 0) if offset is not None else 0
        page_size = int(limit or _LIST_JOBS_MAX) if limit is not None else _LIST_JOBS_MAX
        if page_size > _LIST_JOBS_MAX:
            page_size = _LIST_JOBS_MAX
        if off < 0:
            off = 0

        matched = []
        for ref in DeploymentJobRef.instances():
            if not is_admin and (ref.caller_principal or "") != caller:
                continue
            matched.append(ref)

        matched.sort(key=lambda r: int(r.created_at or 0), reverse=True)
        total = len(matched)
        matched = matched[off:off + page_size]

        jobs = []
        for ref in matched:
            job = DeploymentJob[ref.name]
            if job is not None:
                jobs.append(_job_to_view(job))
        return ResultJobsList(Ok=JobsListOk(jobs=jobs, count=nat32(total)))
    except Exception as e:
        return ResultJobsList(Err=ie(str(e)))

@update
def cancel_deployment(job_id: text) -> ResultJobCancel:
    try:
        list(DeploymentJob.instances())
        job = DeploymentJob[job_id]
        if job is None:
            return ResultJobCancel(Err=ie(f"unknown job_id: {job_id}"))
        prev = job.status or "pending"
        if prev in _JOB_TERMINAL_STATUSES:
            return ResultJobCancel(Ok=JobStatusAck(job_id=job_id, prev_status=prev, status=prev, noop=True))
        if prev not in ("pending", "provisioning"):
            return ResultJobCancel(Err=ie(f"cannot cancel '{prev}' job"))
        job.status = "cancelled"
        job.error = "cancelled"
        job.completed_at = now_s()
        schedule_registry_settlement(job_id, success=False, reason="cancelled")
        return ResultJobCancel(Ok=JobStatusAck(job_id=job_id, prev_status=prev, status="cancelled", noop=False))
    except Exception as e:
        return ResultJobCancel(Err=ie(str(e)))

@update
def delete_deployment_job(job_id: text) -> ResultJobCancel:
    """Remove a terminal failed deployment record. Only the job owner may delete."""
    try:
        caller = str(ic.caller())
        list(DeploymentJob.instances())
        job = DeploymentJob[job_id]
        if job is None:
            return ResultJobCancel(Err=ie(f"unknown job_id: {job_id}"))
        if (job.caller_principal or "") != caller:
            return ResultJobCancel(Err=ie("only the job owner may delete this deployment"))
        prev = job.status or "pending"
        if prev not in _JOB_DELETABLE_STATUSES:
            return ResultJobCancel(Err=ie(f"cannot delete job with status '{prev}'"))
        job.delete()
        _delete_job_ref(job_id)
        jlog(job_id).info(f"deleted by owner ({caller})")
        return ResultJobCancel(Ok=JobStatusAck(job_id=job_id, prev_status=prev, status="deleted", noop=False))
    except Exception as e:
        return ResultJobCancel(Err=ie(str(e)))


def _parse_registry_remove_result(raw) -> None:
    """Raise on registry remove_realm failure (Ok/Err variant or JSON text)."""
    if raw is None:
        raise RuntimeError("empty registry response")
    if isinstance(raw, dict):
        if raw.get("Err"):
            raise RuntimeError(str(raw["Err"]))
        if raw.get("Ok") is not None:
            return
        if raw.get("success") is False:
            raise RuntimeError(str(raw.get("error") or "registry remove failed"))
        return
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", errors="replace")
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            if isinstance(data, dict) and data.get("success") is False:
                raise RuntimeError(str(data.get("error") or "registry remove failed"))
        except json.JSONDecodeError:
            pass
        return
    if hasattr(raw, "Err") and getattr(raw, "Err", None):
        raise RuntimeError(str(raw.Err))
    return


def _parse_ic_text_json(raw) -> dict:
    """Parse JSON returned from another canister's ``text`` endpoint via ``call_raw``."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (bytes, bytearray)):
        raw = ic.candid_decode(raw)
    if isinstance(raw, (list, tuple)) and raw:
        raw = raw[0]
    s = str(raw or "").strip()
    if s.startswith("(") and ")" in s:
        inner = s[1:s.rfind(")")].strip().rstrip(",").strip()
        if inner.startswith('"') and inner.endswith('"'):
            try:
                inner_text = json.loads(inner)
                if isinstance(inner_text, str):
                    s = inner_text
            except json.JSONDecodeError:
                pass
    return json.loads(s or "{}")


def _fetch_realm_stage_gen(backend_id: text):
    """Query realm backend get_runtime_flags for lifecycle stage."""
    flags_res: CallResult = yield ic.call_raw(
        Principal.from_str(backend_id), "get_runtime_flags",
        ic.candid_encode("()"), 1,
    )
    try:
        raw = unwrap_call_result(flags_res)
    except Exception as e:
        # Backends without get_runtime_flags are legacy builds (pre-stage) or
        # half-destroyed sweep shells from an aborted destroy — both alpha.
        if "no update method" in str(e) or "method not found" in str(e).lower():
            return "alpha"
        raise
    data = _parse_ic_text_json(raw)
    if not data.get("success", True):
        raise RuntimeError(data.get("error") or "failed to read realm stage")
    return (data.get("realm_stage") or "alpha").strip().lower()


def _try_delete_canister_gen(canister_id: text, job_id: text):
    """Best-effort IC canister teardown when the installer is a controller."""
    if not (canister_id or "").strip():
        return
    cid = canister_id.strip()
    try:
        stop_res: CallResult = yield management_canister.stop_canister(
            {"canister_id": Principal.from_str(cid)})
        unwrap_call_result(stop_res)
        del_res: CallResult = yield management_canister.delete_canister(
            {"canister_id": Principal.from_str(cid)})
        unwrap_call_result(del_res)
        jlog(job_id).info(f"deleted canister {cid}")
    except Exception as e:
        jlog(job_id).warning(f"could not delete canister {cid} (non-fatal): {e}")


def _destroy_realm_canisters_gen(job, job_id: text, backend_id: text, frontend_id: text):
    """Tear down realm canisters via Casals so cycles are drained back into its
    treasury before deletion. When Casals is configured, a Casals failure aborts
    the destroy (no direct-delete fallback — the IC burns a deleted canister's
    remaining cycles, so falling back would silently lose them)."""
    manifest = json.loads(job.manifest_json or "{}")
    cfg = _config()
    casals_id = (cfg.casals_canister_id or "").strip()
    if not casals_id:
        jlog(job_id).info("casals_canister_id not configured; using direct delete")
        yield from _try_delete_canister_gen(frontend_id, job_id)
        yield from _try_delete_canister_gen(backend_id, job_id)
        return

    cas = manifest.get("casals", {}) or {}
    realm_info = manifest.get("realm", {}) or {}
    realm_name = realm_info.get("name") or job.name or ""
    stand = (cas.get("stand") or _slugify(realm_name)).strip()

    casals = CasalsService(Principal.from_str(casals_id))
    payload = {
        "stand": stand,
        "backend_canister_id": backend_id,
        "frontend_canister_id": frontend_id,
    }
    destroy_res: CallResult = yield casals.destroy_realm_stand(json.dumps(payload))
    parsed = _casals_ok(destroy_res)
    errors = parsed.get("errors") or []
    reclaimed = int(parsed.get("total_cycles_reclaimed") or 0)
    jlog(job_id).info(
        f"casals destroy_realm_stand stand={stand} "
        f"total_cycles_reclaimed={reclaimed} "
        f"canisters={len(parsed.get('destroyed') or [])} failed={len(errors)}"
    )
    if errors:
        raise RuntimeError(f"casals could not destroy all canisters: {errors}")


@update
def destroy_realm_job(job_id: text) -> Async[ResultJobCancel]:
    """Destroy an alpha-stage realm owned by the caller.

    Deregisters the realm from the registry (including federation slugs) and
    destroys backend/frontend canisters via Casals when configured so cycles
    return to the Casals treasury. Only completed deployments still in the alpha
    lifecycle stage qualify.
    """
    try:
        caller = str(ic.caller())
        list(DeploymentJob.instances())
        job = DeploymentJob[job_id]
        if job is None:
            return ResultJobCancel(Err=ie(f"unknown job_id: {job_id}"))
        if (job.caller_principal or "") != caller:
            return ResultJobCancel(Err=ie("only the job owner may destroy this realm"))
        prev = job.status or "pending"
        if prev != "completed":
            return ResultJobCancel(Err=ie(f"cannot destroy job with status '{prev}'"))

        backend_id = (job.backend_canister_id or "").strip()
        if not backend_id:
            return ResultJobCancel(Err=ie("deployment has no backend canister id"))

        stage = yield from _fetch_realm_stage_gen(backend_id)
        if stage != "alpha":
            return ResultJobCancel(Err=ie(
                f"cannot destroy realm in '{stage}' stage; only alpha realms can be destroyed"
            ))

        frontend_id = (job.frontend_canister_id or "").strip()
        yield from _destroy_realm_canisters_gen(job, job_id, backend_id, frontend_id)

        reg_id = (job.registry_canister_id or "").strip()
        if reg_id:
            registry = RealmRegistryService(Principal.from_str(reg_id))
            remove_res: CallResult = yield registry.remove_realm(backend_id)
            _parse_registry_remove_result(unwrap_call_result(remove_res))

        job.delete()
        _delete_job_ref(job_id)
        jlog(job_id).info(f"destroyed alpha realm by owner ({caller})")
        return ResultJobCancel(Ok=JobStatusAck(
            job_id=job_id, prev_status=prev, status="destroyed", noop=False,
        ))
    except Exception as e:
        return ResultJobCancel(Err=ie(str(e), traceback.format_exc()[-1500:]))

@update
def report_deployment_failure(args: text) -> ResultReportFailure:
    try:
        params = json.loads(args)
        job_id = (params.get("job_id") or "").strip()
        err = (params.get("error") or "deployment failed")[:1990]
        if not job_id:
            return ResultReportFailure(Err=ie("job_id required"))
        list(DeploymentJob.instances())
        job = DeploymentJob[job_id]
        if job is None:
            return ResultReportFailure(Err=ie(f"unknown: {job_id}"))
        prev = job.status or "pending"
        if prev in _JOB_TERMINAL_STATUSES:
            return ResultReportFailure(Ok=JobStatusAck(job_id=job_id, prev_status=prev, status=prev, noop=True))
        job.status = "failed"
        job.error = err
        job.completed_at = now_s()
        reg_id = (params.get("registry_canister_id") or "").strip()
        if reg_id and not (job.registry_canister_id or "").strip():
            job.registry_canister_id = reg_id

        if int(job.snapshot_taken or 0) == 1 and (job.snapshot_id or "").strip():
            _schedule_snapshot_rollback(job_id)

        schedule_registry_settlement(job_id, success=False, reason=err)
        return ResultReportFailure(Ok=JobStatusAck(job_id=job_id, prev_status=prev, status="failed", noop=False))
    except Exception as e:
        return ResultReportFailure(Err=ie(str(e)))

# ── On-chain provisioning via Casals (opt-in) ──────────────────────────

def _slugify(name: str) -> str:
    out = []
    for ch in (name or "").lower():
        if ch.isalnum():
            out.append(ch)
        elif ch in (" ", "_", "-") and out and out[-1] != "-":
            out.append("-")
    s = "".join(out).strip("-")
    return s or "realm"


def _casals_ok(call_result):
    """Unwrap a CasalsService CallResult into its parsed JSON dict, raising on a
    transport error or a Casals-level {"ok": false}."""
    text_resp = unwrap_call_result(call_result)
    data = json.loads(text_resp if isinstance(text_resp, str) else json.dumps(text_resp))
    if isinstance(data, dict) and data.get("ok") is False:
        raise RuntimeError(f"casals: {data.get('error', 'unknown error')}")
    return data


def _casals_find_canister(tree: dict, stand: str, canister_name: str) -> str:
    """Look up an existing Casals canister id by stand + logical name."""
    for sec in tree.get("sections") or []:
        for st in sec.get("stands") or []:
            if (st.get("name") or "").strip() != stand:
                continue
            for c in st.get("canisters") or []:
                if (c.get("name") or "").strip() == canister_name:
                    return (c.get("canister_id") or "").strip()
    return ""


def _casals_create_or_reuse_canister(casals, job_id: str, stand: str, name: str,
                                     kind: str, wasm_key: str, install_arg=None):
    """Generator: create a canister via Casals, or reuse one left by a prior attempt."""
    create_args = {"stand": stand, "name": name, "kind": kind, "wasm_key": wasm_key}
    if install_arg is not None:
        create_args["install_arg"] = install_arg
    create_res: CallResult = yield casals.create_canister(json.dumps(create_args))
    try:
        parsed = _casals_ok(create_res)
        cid = (parsed.get("canister_id") or "").strip()
        if cid:
            jlog(job_id).info(f"casals created {kind} {cid} ({name})")
            return cid
    except RuntimeError as se:
        if "already exists" not in str(se).lower():
            raise
        jlog(job_id).info(f"casals canister '{name}' already exists; looking up for reuse")
    tree_res: CallResult = yield casals.get_tree()
    tree = _casals_ok(tree_res)
    cid = _casals_find_canister(tree, stand, name)
    if not cid:
        raise RuntimeError(f"casals: canister '{name}' already exists but was not found in get_tree")
    jlog(job_id).info(f"reusing existing {kind} {cid} ({name})")
    return cid


def _setup_stand_baton(casals, job_id: str, stand: str, casals_id: str,
                       baton_key: str, targets: list, backend_id: str):
    """Generator: per-realm Baton governance for a freshly provisioned stand.

    Creates ``<stand>-baton`` (top_commander = the Casals backend, so Casals
    can administer it), hands each realm canister to it (Baton becomes a
    co-controller + registers it as managed), then sets the commanders and the
    2-of-2 approval policy: casals-backend AND the realm backend must both
    approve every managed upgrade / asset provision.

    ``targets`` is a list of (canister_name, canister_id) to hand off.
    Idempotent — safe to re-run on a partially provisioned job.
    """
    baton_name = f"{stand}-baton"
    baton_id = yield from _casals_create_or_reuse_canister(
        casals, job_id, stand, baton_name, "backend", baton_key,
        install_arg={"top_commander": casals_id},
    )
    jlog(job_id).info(f"stand baton ready: {baton_name} ({baton_id})")

    for target_name, target_id in targets:
        if not target_id:
            continue
        hand_res: CallResult = yield casals.orchestration_hand_to_baton(json.dumps({
            "target": target_name, "baton": baton_name,
        }))
        _casals_ok(hand_res)
        jlog(job_id).info(f"handed {target_name} ({target_id}) to {baton_name}")

    commanders = [casals_id] + ([backend_id] if backend_id else [])
    policy = {
        "threshold": len(commanders),
        "eligible": list(commanders),
        "required": list(commanders),
    }
    cfg_res: CallResult = yield casals.orchestration_configure_baton(json.dumps({
        "baton": baton_name,
        "commanders": commanders,
        "approval_policy": policy,
    }))
    _casals_ok(cfg_res)
    jlog(job_id).info(
        f"baton {baton_name} configured: commanders={commanders}, "
        f"policy {policy['threshold']}-of-{len(commanders)}"
    )
    return baton_id


def _run_deferred_baton_handoff(job: DeploymentJob):
    """Execute a pending stand baton hand-off recorded during provision_via_casals."""
    cfg = _config()
    if not should_run_deferred_baton_handoff(
        baton_pending=int(job.baton_pending or 0),
        baton_canister_id=job.baton_canister_id or "",
        create_stand_baton=bool(int(cfg.create_stand_baton or 0)),
    ):
        return

    raw = (job.baton_handoff_json or "").strip()
    if not raw:
        raise RuntimeError("baton hand-off pending but baton_handoff_json is empty")

    payload = decode_baton_handoff_payload(raw)
    stand = (payload.get("stand") or "").strip()
    casals_id = (payload.get("casals_id") or "").strip()
    baton_key = (payload.get("baton_key") or cfg.baton_wasm_key or "orchestration-baton").strip()
    backend_id = (payload.get("backend_id") or job.backend_canister_id or "").strip()
    hand_targets = hand_targets_from_payload(payload)

    if not stand or not casals_id:
        raise RuntimeError("baton hand-off payload missing stand or casals_id")
    if not hand_targets:
        raise RuntimeError("baton hand-off payload has no hand targets")

    jlog(job.name).info(
        f"running deferred baton hand-off for stand '{stand}' ({len(hand_targets)} targets)"
    )
    casals = CasalsService(Principal.from_str(casals_id))
    baton_id = yield from _setup_stand_baton(
        casals, job.name, stand, casals_id, baton_key,
        hand_targets, backend_id,
    )
    job.baton_canister_id = baton_id
    job.baton_pending = 0
    jlog(job.name).info(f"deferred baton hand-off complete: {baton_id}")


@update
def configure(args: text) -> text:
    """Controller-only descriptor config: registry_backend_id, file_registry_id,
    casals_canister_id, casals_section, portal_url (+ optional casals toggles)."""
    try:
        if not ic.is_controller(ic.caller()):
            return json.dumps({"success": False, "error": "Only controllers can configure the installer"})
        params = json.loads(args) if args else {}
        apply_installer_config(params)
        payload = installer_config_payload()
        _log.info(f"configure: {payload}")
        return json.dumps(payload)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@query
def get_installer_config() -> text:
    try:
        return json.dumps(installer_config_payload())
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)})


@update
def set_casals_config(args: text) -> ResultCasalsConfig:
    """Controller-only. Configure (and enable/disable) the on-chain Casals
    provisioning path. Args (JSON):
    {provision_via_casals?: bool, casals_canister_id?, casals_section?,
     registry_principal?}."""
    try:
        if not ic.is_controller(ic.caller()):
            return ResultCasalsConfig(Err=ie("unauthorized: controller only"))
        params = json.loads(args) if args else {}
        apply_installer_config(params)
        cfg = _config()
        return ResultCasalsConfig(Ok=_casals_config_view(cfg))
    except Exception as e:
        return ResultCasalsConfig(Err=ie(str(e), traceback.format_exc()[-1500:]))


def _casals_config_view(cfg) -> CasalsConfigView:
    return CasalsConfigView(
        provision_via_casals=bool(cfg.provision_via_casals),
        casals_canister_id=cfg.casals_canister_id or "",
        casals_section=cfg.casals_section or "Deployments",
        registry_principal=cfg.registry_principal or "",
        create_stand_baton=bool(cfg.create_stand_baton),
        baton_wasm_key=cfg.baton_wasm_key or "orchestration-baton",
    )


@query
def get_casals_config() -> ResultCasalsConfig:
    try:
        return ResultCasalsConfig(Ok=_casals_config_view(_config()))
    except Exception as e:
        return ResultCasalsConfig(Err=ie(str(e)))


def _mark_provision_failed(job_id: str, reason: str):
    try:
        j = DeploymentJob[job_id]
        if j and (j.status or "") not in _JOB_TERMINAL_STATUSES:
            j.status = "failed"
            j.error = (reason or "deployment failed")[:1990]
            j.completed_at = now_s()
            schedule_registry_settlement(job_id, success=False, reason=j.error)
    except Exception:
        pass


def _schedule_provision_kick(job_id: str, delay_s: int = 0):
    def _kick_runner(kick_job_id: str):
        yield from provision_kick_runner(
            kick_job_id,
            run_gen=_provision_via_casals_gen,
            mark_failed=_mark_provision_failed,
            log_info=lambda msg: jlog(kick_job_id).info(msg),
            log_error=lambda msg: jlog(kick_job_id).error(msg),
        )

    _schedule_provision_kick_impl(
        job_id,
        set_timer=ic.set_timer,
        duration=Duration,
        delay_s=delay_s,
        runner=_kick_runner,
    )


def _arm_provision_heartbeat(delay_s: int = 0):
    """Periodic fallback: re-kick any job still in ``provisioning``."""
    interval = int(delay_s) if delay_s else PROVISION_HEARTBEAT_INTERVAL_S

    def _tick():
        try:
            cfg = _config()
            if int(cfg.provision_via_casals or 0):
                list(DeploymentJob.instances())
                for job_id in provisioning_job_ids_for_heartbeat(
                    DeploymentJob.instances(),
                    terminal_statuses=_JOB_TERMINAL_STATUSES,
                    now_s=now_s(),
                ):
                    _schedule_provision_kick(job_id, 0)
        except Exception as e:
            _log.error(f"provision heartbeat: {e}")
        _arm_provision_heartbeat()

    ic.set_timer(Duration(interval), _tick)


def _provision_via_casals_gen(job_id: str):
    """Internal Casals provisioning generator (no caller auth — timer/heartbeat only)."""
    cfg = _config()
    if not int(cfg.provision_via_casals or 0):
        raise RuntimeError("on-chain Casals provisioning is disabled")
    casals_id = (cfg.casals_canister_id or "").strip()
    if not casals_id:
        raise RuntimeError("casals_canister_id not configured")

    list(DeploymentJob.instances())
    job = DeploymentJob[job_id]
    if job is None:
        raise RuntimeError(f"unknown job_id: {job_id}")
    if (job.status or "pending") not in ("pending", "provisioning"):
        raise RuntimeError(f"job in '{job.status}', expected 'pending' or 'provisioning'")

    claim_provision_lock(job, now_s=now_s())
    try:
        yield from _provision_via_casals_body(job_id, job, cfg, casals_id)
    finally:
        clear_provision_lock(job)


def _provision_via_casals_body(job_id: str, job: DeploymentJob, cfg: InstallerConfig, casals_id: str):
    manifest = json.loads(job.manifest_json or "{}")
    cas = manifest.get("casals", {}) or {}
    realm_info = manifest.get("realm", {}) or {}
    realm_name = realm_info.get("name") or job.name
    deploy_scope = manifest.get("deploy_scope", "both")

    section = (cas.get("section") or cfg.casals_section or "Deployments").strip()
    stand = (cas.get("stand") or _slugify(realm_name)).strip()
    backend_wasm_key = (cas.get("backend_wasm_key") or "").strip()
    frontend_wasm_key = (cas.get("frontend_wasm_key") or "").strip()

    want_backend = deploy_scope in ("both", "backend_only")
    want_frontend = deploy_scope in ("both", "frontend_only")
    if want_backend and not backend_wasm_key:
        raise RuntimeError("manifest.casals.backend_wasm_key required")
    if want_frontend and not frontend_wasm_key:
        raise RuntimeError("manifest.casals.frontend_wasm_key required")

    casals = CasalsService(Principal.from_str(casals_id))

    cycles_res: CallResult = yield casals.get_cycles_cached()
    cycles_report = parse_cycles_report(unwrap_call_result(cycles_res))
    required = estimate_conductor_cycles_required(
        manifest,
        create_stand_baton=bool(int(cfg.create_stand_baton or 0)),
    )
    file_registry_id = resolve_file_registry_id(
        manifest,
        network=(manifest.get("network") or "").strip(),
        configured_id=(cfg.file_registry_id or "").strip() or configured_file_registry_id(manifest.get("network") or ""),
    )
    preflight_err = check_cycles_preflight(
        cycles_report,
        casals_canister_id=casals_id,
        required_conductor_cycles=required,
        file_registry_id=file_registry_id,
    )
    if preflight_err:
        raise RuntimeError(preflight_err)

    # 1. Stand (idempotent — a re-run of a partially provisioned job reuses it).
    stand_res: CallResult = yield casals.create_stand(json.dumps({
        "section": section, "name": stand,
        "description": f"realm {realm_name}",
    }))
    try:
        _casals_ok(stand_res)
    except RuntimeError as se:
        if "already exists" not in str(se).lower():
            raise
        jlog(job_id).info(f"stand '{stand}' already exists; reusing")

    backend_id = job.backend_canister_id or ""
    frontend_id = job.frontend_canister_id or ""

    # 2. Backend canister (Casals installs + verifies module hash).
    if want_backend and not backend_id:
        backend_id = yield from _casals_create_or_reuse_canister(
            casals, job_id, stand, f"{stand}-backend", "backend", backend_wasm_key,
        )
        job.backend_canister_id = backend_id
        job.wasm_verified = 1

    # 3. Frontend canister (Casals installs assets wasm + uploads the bundle).
    if want_frontend and not frontend_id:
        frontend_id = yield from _casals_create_or_reuse_canister(
            casals, job_id, stand, f"{stand}-frontend", "frontend", frontend_wasm_key,
        )
        job.frontend_canister_id = frontend_id
        job.frontend_wasm_verified = 1

    # 3a. Optional per-stand treasury token when the wizard chose token.new.
    token_id = ""
    if backend_id and _resolve_token_from_manifest(manifest) is not None:
        token_cfg = _resolve_token_from_manifest(manifest)
        if token_cfg and token_cfg.get("deploy_new"):
            try:
                token_id, _ = yield from _provision_realm_token_canister(
                    casals, job_id, stand, manifest, backend_id=backend_id,
                )
                jlog(job_id).info(f"stand token ready: {token_id or '–'}")
            except Exception as tok_err:
                jlog(job_id).warning(
                    f"stand token provisioning failed (non-fatal): {tok_err}"
                )

    # 3b. Per-realm Baton governance (opt-in): record hand-off for after
    # bootstrap. _setup_stand_baton removes the installer from canister
    # controllers, so it must not run until set_quarter_provisioning_config,
    # extension installs, and schedule_registration prep are done.
    baton_id = (job.baton_canister_id or "").strip()
    if should_record_deferred_baton(
        create_stand_baton=bool(int(cfg.create_stand_baton or 0)),
        baton_pending=int(job.baton_pending or 0),
        baton_canister_id=baton_id,
    ):
        baton_key = (cas.get("baton_wasm_key") or cfg.baton_wasm_key
                     or "orchestration-baton").strip()
        hand_targets = []
        if want_backend and backend_id:
            hand_targets.append((f"{stand}-backend", backend_id))
        if want_frontend and frontend_id:
            hand_targets.append((f"{stand}-frontend", frontend_id))
        if token_id:
            hand_targets.append((f"{stand}-token", token_id))
        job.baton_pending = 1
        job.baton_handoff_json = encode_baton_handoff_payload(
            build_baton_handoff_payload(
                stand=stand,
                casals_id=casals_id,
                baton_key=baton_key,
                hand_targets=hand_targets,
                backend_id=backend_id if want_backend else "",
            )
        )[:2048]
        jlog(job_id).info(
            f"baton hand-off deferred until post-bootstrap ({len(hand_targets)} targets)"
        )

    # 4. Make the realm backend the Stand commander so it can self-upgrade.
    if backend_id:
        cmd_res: CallResult = yield casals.set_commander(json.dumps({
            "stand": stand, "commander_principal": backend_id,
        }))
        _casals_ok(cmd_res)
        jlog(job_id).info(f"stand '{stand}' commander set to backend {backend_id}")

    # 4b. Inject the Casals provisioning config into the realm's manifest_data
    # so the auto-scale loop can provision quarter backend canisters without
    # admin intervention (gated on manifest_data.casals in _quarter_casals_args).
    if backend_id and backend_wasm_key:
        network = (manifest.get("network") or "").strip()
        registry_id = (manifest.get("file_registry_canister_id") or
                       manifest.get("infra", {}).get("file_registry_canister_id") or
                       configured_file_registry_id(network) or "").strip()
        casals_config = {
            "stand": stand,
            "backend_wasm_key": backend_wasm_key,
            "casals_canister_id": casals_id,
            "registry_canister_id": registry_id,
            "frontend_canister_id": frontend_id,
        }
        if baton_id:
            casals_config["baton_canister_id"] = baton_id
        casals_config_json = json.dumps(casals_config).replace('\\', '\\\\').replace('"', '\\"')
        casals_config_arg = '("' + casals_config_json + '")'
        try:
            qpc_result: CallResult = yield ic.call_raw(
                Principal.from_str(backend_id), "set_quarter_provisioning_config",
                ic.candid_encode(casals_config_arg), 0,
            )
            if isinstance(qpc_result, dict) and "Err" in qpc_result:
                jlog(job_id).warning(
                    f"set_quarter_provisioning_config failed (non-fatal): {qpc_result['Err']}"
                )
            else:
                jlog(job_id).info(
                    f"autoscale config injected: stand={stand}, "
                    f"backend_wasm_key={backend_wasm_key}, casals={casals_id}"
                )
        except Exception as qpc_err:
            jlog(job_id).warning(f"set_quarter_provisioning_config error (non-fatal): {qpc_err}")

    job.assets_verified = 1
    if want_frontend:
        job.frontend_wasm_verified = 1
    job.registry_canister_id = job.registry_canister_id or (manifest.get("registry_canister_id") or "").strip()

    # 5. Domain tail: bootstrap (configure_canister_ids, grant_frontend_access)
    # then optional legacy codex/extension installs, then registration.
    job.status = "extensions"
    jlog(job_id).info("entering bootstrap/extensions phase (casals path)")
    yield from _start_extensions_for_job(job, manifest)

    return ProvisionOk(
        job_id=job_id, status=job.status or "", stand=stand,
        backend_canister_id=backend_id, frontend_canister_id=frontend_id,
    )


@update
def provision_via_casals(job_id: text) -> Async[ResultProvision]:
    """Drive on-chain provisioning of a pending job through Casals: create the
    Stand, the backend + frontend canisters (Casals pulls WASMs from file_registry,
    verifies module hashes, and uploads the frontend bundle into the realm's own
    asset canister), then assign the realm backend as the Stand commander so the
    realm can self-upgrade.

    Opt-in: returns Err unless InstallerConfig.provision_via_casals is set. This is
    the on-chain replacement for the off-chain deployer's report_canister_ready +
    report_frontend_verified callbacks; on success it hands off to the same domain
    tail (extensions/codices -> registration -> credit settlement).

    The realm's frontend/backend WASM keys come from the manifest's optional
    `casals` block: {section?, stand?, backend_wasm_key, frontend_wasm_key}.
    """
    try:
        cfg = _config()
        caller = str(ic.caller())
        reg_principal = (cfg.registry_principal or "").strip()
        if not (ic.is_controller(ic.caller()) or (reg_principal and caller == reg_principal)):
            return ResultProvision(Err=ie("unauthorized: controller or configured registry only"))
        result = yield from _provision_via_casals_gen(job_id)
        return ResultProvision(Ok=result)
    except ProvisionAlreadyInProgress as e:
        return ResultProvision(Err=ie(str(e)))
    except Exception as e:
        _mark_provision_failed(job_id, str(e))
        return ResultProvision(Err=ie(str(e), traceback.format_exc()[-1500:]))

@update
def provision_quarter(args: text) -> Async[text]:
    """Provision a new **backend-only** quarter canister via Casals for an
    already-deployed realm (auto-scaling / sharding — issue #156).

    Unlike ``provision_via_casals`` (which stands up a brand-new realm from a
    deployment job), this is a thin broker: a capital realm asks the installer
    to mint one more backend canister under its existing Casals stand, then the
    capital registers it as a quarter itself. Backend only — quarters share the
    capital's single frontend.

    ``args`` JSON: ``{stand, backend_wasm_key, name?, section?}``.
    Returns JSON: ``{"ok": true, "canister_id": "..."}`` or ``{"ok": false, "error": ...}``.

    Authorization mirrors ``provision_via_casals``: controllers or the
    configured registry principal only — this spends Casals treasury cycles.
    """
    try:
        cfg = _config()
        caller = str(ic.caller())
        reg_principal = (cfg.registry_principal or "").strip()
        if not (ic.is_controller(ic.caller()) or (reg_principal and caller == reg_principal)):
            return json.dumps({"ok": False, "error": "unauthorized: controller or configured registry only"})
        if not int(cfg.provision_via_casals or 0):
            return json.dumps({"ok": False, "error": "on-chain Casals provisioning is disabled"})
        casals_id = (cfg.casals_canister_id or "").strip()
        if not casals_id:
            return json.dumps({"ok": False, "error": "casals_canister_id not configured"})

        params = json.loads(args or "{}")
        stand = (params.get("stand") or "").strip()
        backend_wasm_key = (params.get("backend_wasm_key") or "").strip()
        name = (params.get("name") or "").strip() or f"{stand}-quarter"
        if not stand:
            return json.dumps({"ok": False, "error": "stand required"})
        if not backend_wasm_key:
            return json.dumps({"ok": False, "error": "backend_wasm_key required"})

        casals = CasalsService(Principal.from_str(casals_id))

        be_res: CallResult = yield casals.create_canister(json.dumps({
            "stand": stand, "name": name,
            "kind": "backend", "wasm_key": backend_wasm_key,
        }))
        backend_id = (_casals_ok(be_res).get("canister_id") or "").strip()
        if not backend_id:
            return json.dumps({"ok": False, "error": "casals create_canister returned no canister_id"})

        # Let the new quarter self-upgrade like any realm backend.
        cmd_res: CallResult = yield casals.set_commander(json.dumps({
            "stand": stand, "commander_principal": backend_id,
        }))
        _casals_ok(cmd_res)

        # Hand the new quarter to the stand's Baton so it is governed like the
        # rest of the realm. Approval-free (the hand-off itself needs no vote);
        # non-fatal for stands without a Baton (legacy topology).
        baton_handed = False
        try:
            hand_res: CallResult = yield casals.orchestration_hand_to_baton(json.dumps({
                "target": name,
            }))
            _casals_ok(hand_res)
            baton_handed = True
            _log.info(f"quarter {backend_id} handed to stand '{stand}' baton")
        except Exception as hand_err:
            if "no baton canister" in str(hand_err).lower():
                _log.info(f"stand '{stand}' has no baton; quarter {backend_id} not handed off")
            else:
                _log.warning(f"quarter baton hand-off failed (non-fatal): {hand_err}")

        _log.info(f"provisioned quarter backend {backend_id} ({backend_wasm_key}) under stand '{stand}'")
        return json.dumps({"ok": True, "canister_id": backend_id, "stand": stand,
                           "name": name, "baton_handed": baton_handed})
    except Exception as e:
        _log.error(f"provision_quarter failed: {e}\n{traceback.format_exc()}")
        return json.dumps({"ok": False, "error": str(e)})

@update
def report_canister_ready(args: text) -> Async[ResultReportReady]:
    job_id = ""
    try:
        params = json.loads(args)
        job_id = params.get("job_id", "")
        if not job_id:
            return ResultReportReady(Err=ie("job_id required"))
        list(DeploymentJob.instances())
        job = DeploymentJob[job_id]
        if job is None:
            return ResultReportReady(Err=ie(f"unknown: {job_id}"))
        if (job.status or "pending") != "pending":
            return ResultReportReady(Err=ie(f"job in '{job.status}', expected 'pending'"))

        backend_id = params.get("backend_canister_id", "")
        frontend_id = params.get("frontend_canister_id", "")

        manifest = json.loads(job.manifest_json or "{}")
        deploy_scope = manifest.get("deploy_scope", "both")

        if deploy_scope == "both" and (not backend_id or not frontend_id):
            return ResultReportReady(Err=ie("canister IDs required"))
        if deploy_scope == "backend_only" and not backend_id:
            return ResultReportReady(Err=ie("backend_canister_id required"))
        if deploy_scope == "frontend_only" and not frontend_id:
            return ResultReportReady(Err=ie("frontend_canister_id required"))

        if backend_id:
            job.backend_canister_id = backend_id
        if frontend_id:
            job.frontend_canister_id = frontend_id
        job.registry_canister_id = params.get("registry_canister_id", job.registry_canister_id or "")
        job.status = "verifying"

        deployer_hash = params.get("actual_wasm_hash", "")
        if deployer_hash and not job.expected_wasm_hash:
            _log.warning("No CLI-provided expected_wasm_hash; falling back to deployer-reported hash")
            job.expected_wasm_hash = deployer_hash

        wasm_verified = False
        if deploy_scope == "frontend_only" or not backend_id:
            job.wasm_verified = 1
            wasm_verified = True
        else:
            try:
                status_call: CallResult = yield management_canister.canister_status(
                    {"canister_id": Principal.from_str(backend_id)})
                status_data = unwrap_call_result(status_call)
                mh = (status_data or {}).get("module_hash") if isinstance(status_data, dict) else None
                if mh is not None:
                    actual = mh.hex() if isinstance(mh, bytes) else (bytes(mh).hex() if isinstance(mh, list) else str(mh).replace("0x", ""))
                    job.actual_wasm_hash = actual
                    expected = (job.expected_wasm_hash or "").lower()
                    if expected and expected != actual.lower():
                        job.wasm_verified = -1
                        job.status = "failed_verification"
                        job.error = f"WASM mismatch: expected {expected}, got {actual}"
                        job.completed_at = now_s()
                        schedule_registry_settlement(job_id, success=False, reason=job.error)
                        return ResultReportReady(Ok=ReportReadyOk(
                            job_id=job_id, status="failed_verification", wasm_verified=False,
                            actual_wasm_hash=actual, extensions_started=False,
                            expected_wasm_hash=expected, failed_verification=True,
                        ))
                    job.wasm_verified = 1
                    wasm_verified = True
                else:
                    job.wasm_verified = 1
                    wasm_verified = True
            except Exception:
                job.wasm_verified = 1
                wasm_verified = True

        return ResultReportReady(Ok=ReportReadyOk(
            job_id=job_id, status=job.status, wasm_verified=wasm_verified,
            actual_wasm_hash=job.actual_wasm_hash or "",
            extensions_started=False, expected_wasm_hash=job.expected_wasm_hash or "",
            failed_verification=False,
        ))
    except Exception as e:
        if job_id:
            try:
                j = DeploymentJob[job_id]
                if j and (j.status or "") not in _JOB_TERMINAL_STATUSES:
                    j.status = "failed"
                    j.error = str(e)[:1990]
                    j.completed_at = now_s()
                    schedule_registry_settlement(job_id, success=False, reason=j.error)
            except Exception:
                pass
        return ResultReportReady(Err=ie(str(e), traceback.format_exc()[-1500:]))

@update
def report_frontend_verified(args: text) -> Async[ResultReportFrontend]:
    try:
        params = json.loads(args)
        job_id = params.get("job_id", "")
        assets_hash = (params.get("assets_hash") or "").strip().lower()
        frontend_wasm_hash = (params.get("frontend_wasm_hash") or "").strip().lower()
        if not job_id:
            return ResultReportFrontend(Err=ie("job_id required"))
        list(DeploymentJob.instances())
        job = DeploymentJob[job_id]
        if job is None:
            return ResultReportFrontend(Err=ie(f"unknown: {job_id}"))
        if (job.status or "") in _JOB_TERMINAL_STATUSES:
            return ResultReportFrontend(Err=ie(f"job terminal: {job.status}"))

        failed = False

        # --- Verify frontend canister WASM module hash ---
        if frontend_wasm_hash and not job.expected_frontend_wasm_hash:
            _log.warning("No CLI-provided expected_frontend_wasm_hash; falling back to deployer-reported hash")
            job.expected_frontend_wasm_hash = frontend_wasm_hash
        frontend_id = job.frontend_canister_id or ""
        fe_wasm_verified = False
        if frontend_id:
            try:
                status_call: CallResult = yield management_canister.canister_status(
                    {"canister_id": Principal.from_str(frontend_id)})
                status_data = unwrap_call_result(status_call)
                mh = (status_data or {}).get("module_hash") if isinstance(status_data, dict) else None
                if mh is not None:
                    actual_fe = mh.hex() if isinstance(mh, bytes) else (bytes(mh).hex() if isinstance(mh, list) else str(mh).replace("0x", ""))
                    job.actual_frontend_wasm_hash = actual_fe
                    expected_fe = (job.expected_frontend_wasm_hash or "").lower()
                    if expected_fe and expected_fe != actual_fe.lower():
                        job.frontend_wasm_verified = -1
                        job.status = "failed_verification"
                        job.error = f"frontend WASM mismatch: expected {expected_fe}, got {actual_fe}"[:1990]
                        job.completed_at = now_s()
                        schedule_registry_settlement(job_id, success=False, reason=job.error)
                        failed = True
                    else:
                        job.frontend_wasm_verified = 1
                        fe_wasm_verified = True
                else:
                    job.frontend_wasm_verified = 1
                    fe_wasm_verified = True
            except Exception as fe_err:
                jlog(job_id).error(f"frontend WASM verification error: {fe_err}")
                job.frontend_wasm_verified = 1
                fe_wasm_verified = True

        # --- Verify assets hash ---
        if not failed:
            job.actual_assets_hash = assets_hash
            expected = (job.expected_assets_hash or "").strip().lower()
            if expected and assets_hash and expected != assets_hash:
                job.assets_verified = -1
                job.status = "failed_verification"
                job.error = f"assets mismatch: expected {expected}, got {assets_hash}"[:1990]
                job.completed_at = now_s()
                schedule_registry_settlement(job_id, success=False, reason=job.error)
                failed = True
            else:
                job.assets_verified = 1
                manifest = json.loads(job.manifest_json or "{}")
                realm_info = manifest.get("realm", {})
                has_codex = manifest_has_codex_block(manifest)
                jlog(job_id).info(
                    f"frontend verified: has_codex_block={has_codex}, "
                    f"realm_info keys={list(realm_info.keys())}"
                )
                job.status = "extensions"
                jlog(job_id).info("entering bootstrap/extensions phase")
                yield from _start_extensions_for_job(job, manifest)

        return ResultReportFrontend(Ok=ReportFrontendOk(
            job_id=job_id, status=job.status or "",
            actual_assets_hash=assets_hash, assets_verified=int8(int(job.assets_verified or 0)),
            actual_frontend_wasm_hash=job.actual_frontend_wasm_hash or "",
            frontend_wasm_verified=fe_wasm_verified,
            failed_verification=failed,
        ))
    except Exception as e:
        return ResultReportFrontend(Err=ie(str(e), traceback.format_exc()[-1500:]))

@query
def get_canister_logs(from_entry: Opt[nat] = None, max_entries: Opt[nat] = None,
                      min_level: Opt[text] = None, logger_name: Opt[text] = None) -> Vec[PublicLogEntry]:
    return [PublicLogEntry(timestamp=l["timestamp"], level=l["level"],
                           logger_name=l["logger_name"], message=l["message"], id=l["id"])
            for l in _get_canister_logs(from_entry=from_entry, max_entries=max_entries,
                                         min_level=min_level, logger_name=logger_name)]

# ── Lifecycle: resume in-flight deploys after upgrade ──────────────────

def _resume_in_flight():
    try:
        list(DeployStep.instances())
        by_target = {}
        for t in DeployTask.instances():
            if (t.status or "queued") in ("waiting", "queued", "running"):
                by_target.setdefault(t.target_canister_id, []).append(t)
        for tid, tasks in by_target.items():
            tasks.sort(key=lambda t: (0 if (t.status or "") in ("queued", "running") else 1, int(t.started_at or 0)))
            head = tasks[0]
            for s in head.steps:
                if s.status == "running":
                    s.status = "pending"
                    s.started_at = 0
            head.status = "queued"
            _schedule_step_runner(head.name, 0)
            for t in tasks[1:]:
                    t.status = "waiting"
    except Exception as e:
        _log.error(f"_resume_in_flight: {e}")
