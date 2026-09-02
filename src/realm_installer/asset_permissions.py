"""Commit-permission handling for a realm's frontend asset canister.

The realm backend needs ``Commit`` on its own asset canister to write
deployment-specific assets (branding under ``/custom/``, extension frontends
under ``/ext/``). Granting it requires ``ManagePermissions`` on that canister,
which the installer deliberately does not hold: on the Casals path the asset
canister is created and controlled by the platform provisioner (Casals) and
the governance multisig, and Casals grants ``Commit`` to the paired backend of
the stand every time it provisions the frontend bundle.

So the installer's job is to *verify* the grant, not to assume it can make it.
When it cannot verify and cannot grant, that is a real hole in the platform
topology and must be reported as such — never quietly marked done, and never
"fixed" by re-running the deployment.
"""

COMMIT = "Commit"

# Rejections that mean "you are not allowed to change permissions here", as
# opposed to a transient transport failure worth re-driving.
_DENIED_MARKERS = (
    "managepermissions",
    "is not a controller",
    "not a controller",
    "unauthorized",
    "not authorized",
    "caller does not have",
)


def list_permitted_candid(permission: str = COMMIT) -> str:
    """Candid arg for the asset canister's ``list_permitted``."""
    perm = (permission or COMMIT).strip() or COMMIT
    return "(record { permission = variant { " + perm + " } })"


def grant_permission_candid(to_principal: str, permission: str = COMMIT) -> str:
    """Candid arg for the asset canister's ``grant_permission``."""
    perm = (permission or COMMIT).strip() or COMMIT
    return (
        '(record { to_principal = principal "' + (to_principal or "").strip() + '"; '
        "permission = variant { " + perm + " } })"
    )


def principal_in_candid_vec(decoded: str, principal: str) -> bool:
    """True when a decoded ``vec principal`` response contains ``principal``."""
    text = decoded if isinstance(decoded, str) else ""
    target = (principal or "").strip()
    if not text or not target:
        return False
    return f'principal "{target}"' in text or f"principal \\\"{target}\\\"" in text


def is_permission_denied(error_text: str) -> bool:
    """True when a ``grant_permission`` rejection is an authorization refusal."""
    low = (error_text or "").strip().lower()
    if not low:
        return False
    return any(marker in low for marker in _DENIED_MARKERS)


def missing_commit_grant_error(backend_id: str, frontend_id: str, denial: str = "") -> str:
    """Precise, actionable error for an unresolvable missing Commit grant."""
    msg = (
        f"realm backend {backend_id} does not hold Commit on frontend asset canister "
        f"{frontend_id}, and the installer cannot grant it: it holds no "
        "ManagePermissions there (by design — the asset canister is controlled by "
        "the platform provisioner and the governance multisig). Casals must grant "
        "Commit to the paired stand backend when it provisions the frontend "
        "(or via grant_stand_backend_commit), or grant the installer "
        "ManagePermissions at create time. Retrying this "
        "deployment cannot change the outcome."
    )
    detail = (denial or "").strip()
    if detail:
        msg += f" Rejection: {detail}"
    return msg


def grant_frontend_access_outcome(
    *,
    permitted_before: bool,
    grant_error: str = "",
    permitted_after: bool = False,
    backend_id: str = "",
    frontend_id: str = "",
) -> tuple:
    """Decide the outcome of the ``grant_frontend_access`` step.

    Returns ``(status, note, error)`` where ``status`` is ``"completed"`` or
    ``"failed"``, ``note`` records who actually granted the permission, and
    ``error`` is the message for a failed step.
    """
    if permitted_before:
        return "completed", "already granted by the platform provisioner", ""

    denial = (grant_error or "").strip()
    if not denial:
        return "completed", "granted by the installer", ""

    if permitted_after:
        return "completed", "already granted by the platform provisioner", ""

    if is_permission_denied(denial):
        return "failed", "", missing_commit_grant_error(backend_id, frontend_id, denial)

    return "failed", "", f"grant_permission failed: {denial}"
