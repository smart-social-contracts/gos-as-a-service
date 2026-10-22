"""Realm listings: what the registry directory and globe show about each realm.

A realm canister publishes its own listing (the listing id is its principal).
A listing with no canister behind it is published by a principal named in the
``listing_publishers`` config and belongs to that publisher.

A listing's summary lives on its ``RealmRecord``; its details (manifesto and
zones) live in a separate stable map keyed by listing id, read one listing at
a time, and carry a revision so readers only fetch them again when it changes.
"""

import json

from core.env_config import get_installer_id, get_listing_publishers
from core.models import RealmRecord

STAGES = ("alpha", "beta", "production", "deprecation", "terminated")
PAGE_MAX = 50
DETAILS_BATCH_MAX = 10
PREVIEW_CHARS = 280
MANIFESTO_MAX = 8000
ZONES_MAX = 1000
_TEXT_MAX = {"name": 128, "logo": 512}
_ZONE_TEXT_MAX = {"name": 80, "location_name": 80, "zone_type": 32}
_ID_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789")
_HEX_CHARS = frozenset("0123456789abcdef")


# No regular expressions: the canister's frozen stdlib has no `re`.
def _is_listing_id(value: str) -> bool:
    """Lowercase words of letters and digits joined by single dashes."""
    return all(part and set(part) <= _ID_CHARS for part in value.split("-"))


def _is_h3_index(value: str) -> bool:
    return 15 <= len(value) <= 16 and set(value) <= _HEX_CHARS

_details = None


def init_details(storage) -> None:
    """Use *storage* (a StableBTreeMap[str, str] on the canister) for listing details."""
    global _details
    _details = storage


def looks_like_principal(value: str) -> bool:
    """True for principal text: base32 groups of five whose first four bytes are
    the CRC32 of the rest. "tokyo-yui" has the shape of one but not the checksum."""
    parts = value.split("-")
    if len(parts) < 2 or any(len(p) != 5 for p in parts[:-1]) or not 1 <= len(parts[-1]) <= 5:
        return False
    raw = _b32decode("".join(parts))
    return raw is not None and len(raw) >= 4 and _crc32(raw[4:]) == int.from_bytes(raw[:4], "big")


# Hand-rolled: the canister's frozen base64 has no b32decode, and zlib is not there.
_B32 = {c: i for i, c in enumerate("abcdefghijklmnopqrstuvwxyz234567")}
_CRC_TABLE = []
for _n in range(256):
    _c = _n
    for _ in range(8):
        _c = (_c >> 1) ^ 0xEDB88320 if _c & 1 else _c >> 1
    _CRC_TABLE.append(_c)


def _b32decode(text: str):
    bits = nbits = 0
    out = bytearray()
    for ch in text:
        if ch not in _B32:
            return None
        bits = (bits << 5) | _B32[ch]
        nbits += 5
        if nbits >= 8:
            nbits -= 8
            out.append((bits >> nbits) & 0xFF)
    return bytes(out)


def _crc32(data: bytes) -> int:
    crc = 0xFFFFFFFF
    for byte in data:
        crc = (crc >> 8) ^ _CRC_TABLE[(crc ^ byte) & 0xFF]
    return crc ^ 0xFFFFFFFF


def _load_details(listing_id: str) -> dict:
    raw = _details.get(listing_id)
    if not raw:
        return {"revision": 0, "manifesto": "", "zones": []}
    return json.loads(raw)


def _clean_zone(zone) -> dict:
    if not isinstance(zone, dict):
        raise ValueError("each zone must be an object")
    h3_index = str(zone.get("h3_index") or "").strip().lower()
    if not _is_h3_index(h3_index):
        raise ValueError(f"invalid h3_index {h3_index!r}")
    user_count = int(zone.get("user_count") or 0)
    if user_count < 0:
        raise ValueError("user_count must not be negative")
    clean = {"h3_index": h3_index, "user_count": user_count}
    for key, limit in _ZONE_TEXT_MAX.items():
        value = str(zone.get(key) or "").strip()
        if value:
            clean[key] = value[:limit]
    return clean


def _caller_may_manage(record, caller: str, is_controller: bool) -> bool:
    if is_controller:
        return True
    if record.publisher:
        return caller == record.publisher
    installer = get_installer_id()
    return caller == record.id or (bool(installer) and caller == installer)


def caller_may_manage(listing_id: str, caller: str, is_controller: bool) -> bool:
    record = RealmRecord[listing_id]
    return record is not None and _caller_may_manage(record, caller, is_controller)


def publish_listing(payload: dict, caller: str, is_controller: bool, now: float) -> dict:
    """Create or update a listing; see the module docstring for who may publish what."""
    listing_id = str(payload.get("id") or caller).strip()
    record = RealmRecord[listing_id]

    if listing_id == caller:
        if record is None:
            return {"success": False, "error": "Register the realm before publishing its listing"}
    else:
        if not (is_controller or caller in get_listing_publishers()):
            return {"success": False, "error": "Caller may not publish listings for other ids"}
        if looks_like_principal(listing_id) or not _is_listing_id(listing_id) or not 3 <= len(listing_id) <= 48:
            return {
                "success": False,
                "error": "A listing without a canister needs an id of lowercase words joined by dashes",
            }
        if record is not None and not _caller_may_manage(record, caller, is_controller):
            return {"success": False, "error": f"Listing '{listing_id}' belongs to another publisher"}

    try:
        stage = str(payload.get("stage") or "").strip().lower()
        if stage and stage not in STAGES:
            raise ValueError(f"stage must be one of {', '.join(STAGES)}")
        texts = {}
        for key, limit in _TEXT_MAX.items():
            if key in payload:
                value = str(payload.get(key) or "").strip()
                if len(value) > limit:
                    raise ValueError(f"{key} is longer than {limit} characters")
                texts[key] = value
        if record is None and not texts.get("name"):
            raise ValueError("name is required")
        if texts.get("logo") and not texts["logo"].startswith("https://"):
            raise ValueError("logo must be an https URL")
        manifesto = None
        if "manifesto" in payload:
            manifesto = str(payload.get("manifesto") or "").strip()
            if len(manifesto) > MANIFESTO_MAX:
                raise ValueError(f"manifesto is longer than {MANIFESTO_MAX} characters")
        details = None
        if manifesto is not None or "zones" in payload:
            stored = _load_details(listing_id)
            details = dict(stored)
            if manifesto is not None:
                details["manifesto"] = manifesto
            if "zones" in payload:
                if not isinstance(payload["zones"], list):
                    raise ValueError("zones must be a list")
                zones = [_clean_zone(z) for z in payload["zones"]]
                details["zones"] = details["zones"] + zones if payload.get("zones_append") else zones
                if len(details["zones"]) > ZONES_MAX:
                    raise ValueError(f"A listing has at most {ZONES_MAX} zones")
            if details["manifesto"] == stored["manifesto"] and details["zones"] == stored["zones"]:
                details = None
            else:
                details["revision"] = int(stored.get("revision") or 0) + 1
        users_count = max(0, int(payload.get("users_count") or 0))
        last_activity_at = max(0, int(payload.get("last_activity_at") or 0))
    except (TypeError, ValueError) as e:
        return {"success": False, "error": str(e)}

    if record is None:
        record = RealmRecord(
            id=listing_id, name=texts["name"], url="", backend_url="", logo="",
            created_at=now, frontend_canister_id="", listing_status="live",
            publisher=caller,
        )
    for key, value in texts.items():
        if key == "name" and not value:
            continue
        setattr(record, key, value)
    if stage:
        record.stage = stage
    if "users_count" in payload:
        record.users_count = users_count
    if "last_activity_at" in payload:
        record.last_activity_at = last_activity_at
    if details is not None:
        _details.insert(listing_id, json.dumps(details, separators=(",", ":")))
        record.revision = details["revision"]
        if manifesto is not None:
            record.manifesto_preview = manifesto[:PREVIEW_CHARS]

    return {"success": True, "id": listing_id, "revision": record.revision or 0}


def remove_listing_details(listing_id: str) -> None:
    if _details is not None:
        _details.remove(listing_id)


def listing_summary(record) -> dict:
    return {
        "id": record.id,
        "name": record.name or "",
        "logo": record.logo or "",
        "url": record.url or "",
        "frontend_canister_id": record.frontend_canister_id or "",
        "canister_id": "" if record.publisher else record.id,
        "stage": record.stage or "",
        "users_count": record.users_count or 0,
        "last_activity_at": record.last_activity_at or 0,
        "manifesto_preview": record.manifesto_preview or "",
        "revision": record.revision or 0,
        "created_at": record.created_at or 0.0,
        "listing_status": record.effective_listing_status(),
    }


def list_listings(from_id: int, count: int) -> dict:
    """One page of listing summaries in id order; ``next`` is the cursor for the following page."""
    count = max(1, min(int(count or PAGE_MAX), PAGE_MAX))
    from_id = max(1, int(from_id or 1))
    page = RealmRecord.load_some(from_id, count)
    next_id = None
    if len(page) == count:
        candidate = int(page[-1]._id) + 1
        if candidate <= RealmRecord.max_id():
            next_id = candidate
    return {
        "success": True,
        "listings": [listing_summary(r) for r in page],
        "next": next_id,
    }


def get_listing_details(ids: list) -> dict:
    """Manifesto and zones for up to DETAILS_BATCH_MAX listings."""
    if not isinstance(ids, list) or len(ids) > DETAILS_BATCH_MAX:
        return {"success": False, "error": f"Pass a list of at most {DETAILS_BATCH_MAX} ids"}
    found = {}
    for listing_id in ids:
        listing_id = str(listing_id)
        if RealmRecord[listing_id] is not None:
            found[listing_id] = _load_details(listing_id)
    return {"success": True, "listings": found}
