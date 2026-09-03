"""Resume planning for the installer's bootstrap / extension deploy task.

A deployment whose canisters already exist must never be re-driven from step
zero. ``enter_setup`` and ``configure_canister_ids`` are one-shot on a live
stand: replaying them turns one recoverable failure (say, a missing
asset-canister permission) into a task where every step fails, and the realm
is left half-built with no way forward. A second pass therefore resumes the
existing task from its first unfinished step and leaves completed steps alone.
"""

import hashlib
import json

# A step left ``running`` for longer than this lost its runner (a trap, a
# canister upgrade, or a dropped timer) and may be re-driven.
STALE_RUNNING_S = 15 * 60

# Steps that configure the realm once. They cannot be replayed against a live
# stand, which is why a completed one is never reset.
ONE_SHOT_STEP_KINDS = ("enter_setup", "configure_canister_ids")

# Steps the realm cannot live without, whatever happens to extensions.
BOOTSTRAP_STEP_KINDS = (
    "enter_setup",
    "configure_canister_ids",
    "grant_frontend_access",
    "codex",
    "codex_init",
)

# Task statuses the step runner will not pick up again (mirrors
# main._TERMINAL_TASK_STATUSES).
TERMINAL_TASK_STATUSES = ("completed", "partial", "failed", "cancelled")

# Statuses a step may be reset from on a resume pass.
_RESETTABLE_STATUSES = ("failed", "running")

# enter_setup markers that mean "the realm is already where this step wanted
# it", i.e. a previous pass got through even though its bookkeeping was lost.
# Deliberately narrow: anything else stays a failure.
_ALREADY_IN_SETUP_MARKERS = (
    "already in setup",
    "already_in_setup",
    "already entered setup",
    "already in_setup",
    "setup already",
    "already bootstrapped",
    "already initialized",
    "already initialised",
    "already has a founder",
    "founder already",
)

_MAX_TASK_ID_LEN = 64

# A job sitting in ``extensions`` with nothing driving it for this long is
# stranded, not working. Four live jobs on test.gos.earth sat like that for
# hours while their cards animated at 42%.
EXTENSIONS_STALL_S = 30 * 60


def deploy_task_id(job_id: str) -> str:
    """Task id for a job's bootstrap/extension task.

    Derived from the job id so it is stable across passes (a resume finds the
    same task) and unique per job. The previous ``"deploy_%d" % ic.time()``
    scheme collided: IC time is the same for every message in a round, so two
    jobs provisioned together minted the same task name and the second job
    adopted the first realm's steps.
    """
    jid = (job_id or "").strip()
    if not jid:
        return ""
    candidate = f"deploy_{jid}"
    if len(candidate) <= _MAX_TASK_ID_LEN:
        return candidate
    digest = hashlib.sha256(jid.encode()).hexdigest()
    return ("deploy_" + digest)[:_MAX_TASK_ID_LEN]


def _status_of(step) -> str:
    return (getattr(step, "status", None) or "pending").strip().lower()


def _idx_of(step) -> int:
    return int(getattr(step, "idx", 0) or 0)


def _kind_of(step) -> str:
    return (getattr(step, "kind", None) or "").strip()


def _started_at_of(step) -> int:
    return int(getattr(step, "started_at", 0) or 0)


def completed_step_kinds(steps) -> list:
    """Kinds of the steps a previous pass finished, in step order."""
    done = [s for s in (steps or []) if _status_of(s) == "completed"]
    return [_kind_of(s) for s in sorted(done, key=_idx_of)]


def task_has_progress(steps) -> bool:
    """True when a previous pass completed at least one step."""
    return any(_status_of(s) == "completed" for s in (steps or []))


def steps_to_reset(steps, *, now_s: int, stale_running_s: int = STALE_RUNNING_S) -> list:
    """Indices of the steps a resume pass may re-drive.

    Failed steps always qualify. A ``running`` step qualifies only once its
    runner is provably gone (older than ``stale_running_s``), so a resume can
    never race a pass that is still in flight. Completed steps are never
    returned — that is the whole point.
    """
    out = []
    for step in sorted(steps or [], key=_idx_of):
        status = _status_of(step)
        if status not in _RESETTABLE_STATUSES:
            continue
        if status == "running":
            started = _started_at_of(step)
            if started and (int(now_s) - started) < int(stale_running_s):
                continue
        out.append(_idx_of(step))
    return out


def plan_resume(steps, *, now_s: int, stale_running_s: int = STALE_RUNNING_S) -> dict:
    """Plan a second pass over an existing task.

    ``resume`` is True whenever the task has steps at all: its steps were built
    from this job's manifest, so re-using them is always more correct than
    minting a duplicate task. ``reset_idx`` lists the steps to put back to
    ``pending``; ``keep_completed`` is what the pass will skip.
    """
    all_steps = list(steps or [])
    reset_idx = steps_to_reset(all_steps, now_s=now_s, stale_running_s=stale_running_s)
    pending_idx = [_idx_of(s) for s in sorted(all_steps, key=_idx_of) if _status_of(s) == "pending"]
    return {
        "resume": bool(all_steps),
        "reset_idx": reset_idx,
        "pending_idx": pending_idx,
        "keep_completed": completed_step_kinds(all_steps),
        "has_progress": task_has_progress(all_steps),
    }


def describe_resume(plan: dict) -> str:
    """One-line log summary of a resume plan."""
    keep = plan.get("keep_completed") or []
    reset = plan.get("reset_idx") or []
    pending = plan.get("pending_idx") or []
    return (
        f"keeping {len(keep)} completed step(s) [{', '.join(keep) or '–'}], "
        f"re-driving idx {reset or '–'}, pending idx {pending or '–'}"
    )


def bootstrap_already_started(backend_canister_id: str, ext_deploy_task_id: str) -> bool:
    """True when a pass already created canisters and started the bootstrap task.

    Provisioning (stand, canisters, commander, autoscale config) all runs
    before the task is created, so an existing task id means every Casals call
    of the first pass succeeded. A second pass must not repeat them.
    """
    return bool((backend_canister_id or "").strip() and (ext_deploy_task_id or "").strip())


def failed_bootstrap_step_kinds(steps) -> list:
    """Kinds of the failed bootstrap steps, in step order.

    A failed bootstrap step is not a partial success. A realm that never
    entered setup, never learned its canister IDs, or whose backend cannot
    write to its own frontend is not deployed — registering it (and capturing
    the credits) would bury the problem in a "completed with errors" card.
    """
    failed = [
        s for s in (steps or [])
        if _status_of(s) == "failed" and _kind_of(s) in BOOTSTRAP_STEP_KINDS
    ]
    return [_kind_of(s) for s in sorted(failed, key=_idx_of)]


def task_belongs_to_job(task_target_canister_id: str, job_backend_canister_id: str) -> bool:
    """True when a recorded task really is this job's.

    Guards against a task id minted by the old wall-clock scheme, where two
    jobs in one round shared a name: resuming that task would drive another
    realm's steps against another realm's canisters.
    """
    return (task_target_canister_id or "").strip() == (job_backend_canister_id or "").strip()


def _completed_count(task) -> int:
    return sum(1 for s in (getattr(task, "steps", None) or []) if _status_of(s) == "completed")


def best_owned_task(tasks, backend_canister_id: str):
    """The job's own task among rows a name collision orphaned.

    Two jobs that minted the same task name left two task rows: the alias
    resolves to whichever was written last, so a job can end up pointing at
    another realm's steps while its own row sits unreachable. Rows are still
    enumerable, so a job can find its own by target canister. Prefers the row
    that got furthest, then the most recent.
    """
    backend = (backend_canister_id or "").strip()
    if not backend:
        return None
    owned = [
        t for t in (tasks or [])
        if task_belongs_to_job(getattr(t, "target_canister_id", ""), backend)
    ]
    if not owned:
        return None
    return sorted(
        owned,
        key=lambda t: (_completed_count(t), int(getattr(t, "started_at", 0) or 0)),
    )[-1]


def completed_step_signatures(steps) -> list:
    """``(kind, label)`` of every completed step — a step's identity across tasks."""
    out = []
    for step in sorted(steps or [], key=_idx_of):
        if _status_of(step) != "completed":
            continue
        out.append((_kind_of(step), (getattr(step, "label", None) or "").strip()))
    return out


def steps_satisfied_by_prior_task(new_steps, prior_signatures) -> list:
    """Indices of freshly built steps a previous task of this realm completed.

    A rebuild happens when the recorded task is gone or was shadowed by a name
    collision. The realm still carries the effects of whatever ran, so the
    rebuild must not replay them: `enter_setup` on a realm already in setup and
    `configure_canister_ids` on a configured one both fail.
    """
    remaining = list(prior_signatures or [])
    out = []
    for step in sorted(new_steps or [], key=_idx_of):
        sig = (_kind_of(step), (getattr(step, "label", None) or "").strip())
        if sig in remaining:
            remaining.remove(sig)
            out.append(_idx_of(step))
    return out


def task_owner_job(jobs, task_name: str, task_target_canister_id: str):
    """The job a finished task actually belongs to.

    Matching on ``ext_deploy_task_id`` alone painted one realm's failed steps
    onto another realm's card (and settled the wrong job) whenever two jobs
    shared a task name. The task's target canister decides.
    """
    name = (task_name or "").strip()
    candidates = [
        j for j in (jobs or []) if (getattr(j, "ext_deploy_task_id", "") or "").strip() == name
    ]
    owners = [
        j for j in candidates
        if task_belongs_to_job(task_target_canister_id, getattr(j, "backend_canister_id", ""))
    ]
    if not owners:
        return None
    if len(owners) == 1:
        return owners[0]
    return sorted(owners, key=lambda j: int(getattr(j, "created_at", 0) or 0))[-1]


def extensions_stall_reason(
    *,
    task,
    backend_canister_id: str,
    recorded_task_id: str,
    now_s: int,
    last_activity_s: int,
    stall_s: int = EXTENSIONS_STALL_S,
) -> str:
    """Why a job stuck in ``extensions`` can no longer make progress, or "".

    Reporting this is not a retry: it replaces an animated progress card with
    the truth, releases the credit hold, and makes the job eligible for an
    explicit resume. Nothing here re-drives a bootstrap.
    """
    if int(now_s) - int(last_activity_s or 0) < int(stall_s):
        return ""
    recorded = (recorded_task_id or "").strip()
    if not recorded:
        return "stuck in the extensions phase with no deploy task recorded"
    if task is None:
        return f"deploy task {recorded} no longer exists"
    target = (getattr(task, "target_canister_id", "") or "").strip()
    if not task_belongs_to_job(target, backend_canister_id):
        return (
            f"deploy task {recorded} belongs to another realm "
            f"(it targets {target or 'nothing'}, this realm is "
            f"{(backend_canister_id or '').strip() or 'unknown'}) — a task id collision, "
            "so this realm's bootstrap never ran"
        )
    status = (getattr(task, "status", None) or "").strip().lower()
    if status in TERMINAL_TASK_STATUSES:
        return f"deploy task {recorded} finished as '{status}' but the job was never settled"
    if status in ("queued", "waiting") and not _completed_count(task):
        return f"deploy task {recorded} never started"
    return ""


def coerce_realm_json(raw):
    """Unwrap candid ``text`` / one-element tuples into a JSON object when possible."""
    if raw is None:
        return None
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode("utf-8")
        except Exception:
            return raw
    while isinstance(raw, (list, tuple)) and len(raw) == 1:
        raw = raw[0]
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return raw
    s = raw.strip()
    if not s:
        return None
    if s[0] in "{[":
        try:
            return json.loads(s)
        except Exception:
            return s
    start, end = s.find("{"), s.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(s[start : end + 1])
        except Exception:
            return s
    return s


def install_step_in_progress(parsed) -> bool:
    """True when a realm install call advanced but needs another update."""
    parsed = coerce_realm_json(parsed)
    return (
        isinstance(parsed, dict)
        and parsed.get("success") is True
        and parsed.get("status") == "in_progress"
    )


def realm_json_response_failed(parsed) -> tuple[bool, str]:
    """Return ``(is_failure, error_message)`` for realm JSON text endpoints.

    Fail only on an explicit rejection (``ok``/``success`` false, or ``error``).
    Unparseable candid leftovers are not treated as failure.
    """
    parsed = coerce_realm_json(parsed)
    if not isinstance(parsed, dict):
        return False, ""
    if parsed.get("status") == "in_progress":
        return False, ""
    if parsed.get("ok") is False or parsed.get("success") is False:
        return True, str(parsed.get("error") or parsed.get("err") or parsed.get("Err") or "realm call rejected")
    err = parsed.get("error") or parsed.get("err")
    if err is None and parsed.get("Err") is not None:
        err = parsed["Err"]
    if err:
        return True, str(err)
    return False, ""


def enter_setup_already_satisfied(error_text: str) -> bool:
    """True when an ``enter_setup`` rejection means the realm is already in setup.

    Only reached when the step record was lost (so resume could not skip it).
    The realm is in the state the step wanted, so treating this as satisfied is
    truthful — the step result records that it was not this pass that did it.
    """
    low = (error_text or "").strip().lower()
    if not low:
        return False
    return any(marker in low for marker in _ALREADY_IN_SETUP_MARKERS)
