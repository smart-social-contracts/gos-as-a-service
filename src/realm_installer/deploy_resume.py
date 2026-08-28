"""Resume planning for the installer's bootstrap / extension deploy task.

A deployment whose canisters already exist must never be re-driven from step
zero. ``enter_setup`` and ``configure_canister_ids`` are one-shot on a live
stand: replaying them turns one recoverable failure (say, a missing
asset-canister permission) into a task where every step fails, and the realm
is left half-built with no way forward. A second pass therefore resumes the
existing task from its first unfinished step and leaves completed steps alone.
"""

import hashlib

# A step left ``running`` for longer than this lost its runner (a trap, a
# canister upgrade, or a dropped timer) and may be re-driven.
STALE_RUNNING_S = 15 * 60

# Steps that configure the realm once. They cannot be replayed against a live
# stand, which is why a completed one is never reset.
ONE_SHOT_STEP_KINDS = ("enter_setup", "configure_canister_ids")

# Steps the realm cannot live without, whatever happens to extensions.
BOOTSTRAP_STEP_KINDS = ("enter_setup", "configure_canister_ids", "grant_frontend_access")

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
