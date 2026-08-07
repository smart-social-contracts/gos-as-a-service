from core.models import RealmRecord, SlugRecord
from _cdk import ic
from ic_python_logging import get_logger

logger = get_logger("registry")


def list_registered_realms() -> list:
    try:
        realms = [r.to_dict() for r in RealmRecord.instances()]
        realms.sort(key=lambda r: r.get("created_at", 0), reverse=True)
        return realms
    except Exception as e:
        logger.error(f"Error listing realms: {e}")
        return []


def register_realm_by_caller(
    name: str, url: str = "", logo: str = "", backend_url: str = "",
    frontend_canister_id: str = "", realm_id_override: str = "",
) -> dict:
    realm_id = realm_id_override.strip() if realm_id_override else str(ic.caller())
    if not name or not name.strip():
        return {"success": False, "error": "Realm name cannot be empty"}
    try:
        existing = RealmRecord[realm_id]
        if existing:
            existing.name = name.strip()
            if url:
                existing.url = url.strip()
            if backend_url:
                existing.backend_url = backend_url.strip()
            if logo:
                existing.logo = logo.strip()
            if frontend_canister_id:
                existing.frontend_canister_id = frontend_canister_id.strip()
            return {"success": True, "message": f"Realm '{realm_id}' updated"}

        RealmRecord(
            id=realm_id, name=name.strip(),
            url=url.strip(), backend_url=backend_url.strip(),
            logo=logo.strip(),
            created_at=float(ic.time() / 1_000_000_000),
            frontend_canister_id=frontend_canister_id.strip(),
        )
        return {"success": True, "message": f"Realm '{realm_id}' registered"}
    except Exception as e:
        logger.error(f"Error registering realm {realm_id}: {e}")
        return {"success": False, "error": str(e)}


def get_registered_realm(realm_id: str) -> dict:
    try:
        realm = RealmRecord[realm_id]
        if realm is None:
            return {"success": False, "error": f"Realm '{realm_id}' not found"}
        return {"success": True, "realm": realm.to_dict()}
    except Exception as e:
        return {"success": False, "error": str(e)}


def remove_registered_realm(realm_id: str) -> dict:
    try:
        realm = RealmRecord[realm_id]
        if realm is None:
            return {"success": False, "error": f"Realm '{realm_id}' not found"}
        for slug_rec in list(SlugRecord.instances()):
            if (slug_rec.realm_id or "") == realm_id:
                slug_rec.delete()
        realm.delete()
        return {"success": True, "message": f"Realm '{realm_id}' removed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def count_registered_realms() -> int:
    try:
        return len(list(RealmRecord.instances()))
    except Exception:
        return 0
