"""Authorization helpers for deployment manifest access."""


def can_view_deployment_manifest(*, caller: str, owner: str, is_controller: bool) -> bool:
    if is_controller:
        return True
    return (owner or "") == (caller or "")
