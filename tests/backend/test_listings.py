"""Listings: realms publish their own, listing publishers own listings with no canister."""

import json

import pytest

import _cdk as basilisk

from api import listings
from api.listings import (
    get_listing_details,
    list_listings,
    looks_like_principal,
    publish_listing,
)
from api.registry import register_realm_by_caller, remove_registered_realm
from core.env_config import apply_env_config
from core.models import RealmRecord

mock_ic = basilisk.ic

PUBLISHER = "62e75-t5hl5-jtm6x-nkw6a-jcykv-zr4pr-eohoq-mg53n-7meud-v7op3-fqe"
REALM = "q5b2e-vqaaa-aaaas-qhbrq-cai"
STRANGER = "2vxsx-fae"
NOW = 1_792_000_000.0
ZONE = {"h3_index": "86394600fffffff", "user_count": 40, "location_name": "Centre"}


class _Storage:
    def __init__(self):
        self.data = {}

    def get(self, key):
        return self.data.get(key)

    def insert(self, key, value):
        self.data[key] = value

    def remove(self, key):
        self.data.pop(key, None)


@pytest.fixture(autouse=True)
def _fresh():
    for realm in list(RealmRecord.instances()):
        realm.delete()
    listings.init_details(_Storage())
    apply_env_config({"listing_publishers": [PUBLISHER], "installer_id": ""})
    mock_ic.is_controller.return_value = False
    yield
    mock_ic.is_controller.return_value = False


def _register_realm(realm_id=REALM, name="València"):
    mock_ic.caller.return_value = realm_id
    result = register_realm_by_caller(name, "https://example.org")
    assert result["success"], result


def _publish(payload, caller=PUBLISHER, controller=False):
    return publish_listing(payload, caller, controller, NOW)


def test_principal_text_is_recognised_by_its_checksum():
    assert looks_like_principal(REALM)
    assert looks_like_principal(PUBLISHER)
    assert looks_like_principal(STRANGER)
    assert looks_like_principal("aaaaa-aa")
    assert not looks_like_principal("lisboa")
    assert not looks_like_principal("san-francisco")
    assert not looks_like_principal("cape-town-commons")
    assert not looks_like_principal("tokyo-yui")
    assert not looks_like_principal("seoul-dure")
    assert not looks_like_principal("2vxsx-fad")


def test_principal_shaped_words_are_valid_ids():
    assert _publish({"id": "tokyo-yui", "name": "Tokyo"})["success"]
    refused = _publish({"id": "2vxsx-fae", "name": "Squatter"})
    assert not refused["success"]


def test_publisher_creates_a_listing_without_a_canister():
    result = _publish({
        "id": "lisboa", "name": "Lisboa", "stage": "beta", "users_count": 900,
        "last_activity_at": 1_791_000_000, "manifesto": "Tejo " * 100, "zones": [ZONE],
    })
    assert result == {"success": True, "id": "lisboa", "revision": 1}

    page = list_listings(1, 50)
    (summary,) = page["listings"]
    assert summary["id"] == "lisboa"
    assert summary["canister_id"] == ""
    assert summary["url"] == ""
    assert summary["stage"] == "beta"
    assert summary["users_count"] == 900
    assert summary["revision"] == 1
    assert len(summary["manifesto_preview"]) == listings.PREVIEW_CHARS
    assert page["next"] is None

    details = get_listing_details(["lisboa"])["listings"]["lisboa"]
    assert details["manifesto"].startswith("Tejo")
    assert details["zones"] == [ZONE]


def test_listing_ids_cannot_look_like_canisters():
    result = _publish({"id": REALM, "name": "Fake València"})
    assert not result["success"]
    assert RealmRecord[REALM] is None
    assert not _publish({"id": "Lisboa!", "name": "x"})["success"]


def test_only_listing_publishers_create_listings_without_a_canister():
    result = _publish({"id": "lisboa", "name": "Lisboa"}, caller=STRANGER)
    assert not result["success"]
    assert RealmRecord["lisboa"] is None


def test_a_listing_belongs_to_its_publisher():
    _publish({"id": "lisboa", "name": "Lisboa"})
    apply_env_config({"listing_publishers": [PUBLISHER, STRANGER]})
    result = _publish({"id": "lisboa", "name": "Taken"}, caller=STRANGER)
    assert not result["success"]
    assert RealmRecord["lisboa"].name == "Lisboa"


def test_a_realm_publishes_its_own_listing():
    _register_realm()
    result = _publish({
        "name": "València", "stage": "alpha", "users_count": 127_499,
        "manifesto": "Una ciutat oberta.", "zones": [ZONE],
    }, caller=REALM)
    assert result["success"], result

    (summary,) = list_listings(1, 50)["listings"]
    assert summary["canister_id"] == REALM
    assert summary["url"] == "https://example.org"
    assert summary["users_count"] == 127_499


def test_a_realm_must_register_before_publishing():
    assert not _publish({"name": "Unregistered"}, caller=REALM)["success"]


def test_publishers_cannot_edit_a_canister_realm():
    _register_realm()
    result = _publish({"id": REALM, "users_count": 1})
    assert not result["success"]


def test_revision_moves_only_with_details():
    _publish({"id": "lisboa", "name": "Lisboa", "manifesto": "a"})
    assert _publish({"id": "lisboa", "users_count": 5})["revision"] == 1
    assert _publish({"id": "lisboa", "zones": [ZONE]})["revision"] == 2
    assert get_listing_details(["lisboa"])["listings"]["lisboa"]["manifesto"] == "a"
    assert _publish({"id": "lisboa", "manifesto": "a", "zones": [ZONE], "users_count": 6})["revision"] == 2


def test_crc32_and_base32_match_the_stdlib():
    import base64
    import zlib

    for data in (b"", b"\x00", b"realm registry", bytes(range(256))):
        assert listings._crc32(data) == zlib.crc32(data)
        text = base64.b32encode(data).decode().lower().rstrip("=")
        assert listings._b32decode(text) == data


def test_zones_append_and_cap():
    _publish({"id": "lisboa", "name": "Lisboa", "zones": [ZONE]})
    other = dict(ZONE, h3_index="86394601fffffff")
    _publish({"id": "lisboa", "zones": [other], "zones_append": True})
    zones = get_listing_details(["lisboa"])["listings"]["lisboa"]["zones"]
    assert [z["h3_index"] for z in zones] == [ZONE["h3_index"], other["h3_index"]]

    too_many = [ZONE] * (listings.ZONES_MAX + 1)
    result = _publish({"id": "lisboa", "zones": too_many})
    assert not result["success"]
    assert len(get_listing_details(["lisboa"])["listings"]["lisboa"]["zones"]) == 2


def test_rejected_publish_writes_nothing():
    result = _publish({"id": "porto", "name": "Porto", "zones": [{"h3_index": "nope"}]})
    assert not result["success"]
    assert RealmRecord["porto"] is None


def test_bad_values_are_rejected():
    assert not _publish({"id": "porto", "name": "Porto", "stage": "live"})["success"]
    assert not _publish({"id": "porto", "name": "Porto", "logo": "http://x/logo.png"})["success"]
    assert not _publish({"id": "porto", "name": "Porto", "manifesto": "x" * 8001})["success"]
    assert not _publish({"id": "porto"})["success"]


def test_pages_follow_the_cursor():
    for i in range(7):
        _publish({"id": f"city-{i}", "name": f"City {i}"})
    seen, cursor = [], 1
    while cursor is not None:
        page = list_listings(cursor, 3)
        seen += [s["id"] for s in page["listings"]]
        cursor = page["next"]
    assert seen == [f"city-{i}" for i in range(7)]


def test_details_batch_is_bounded():
    assert not get_listing_details([f"x-{i}" for i in range(11)])["success"]
    assert get_listing_details(["missing"])["listings"] == {}


def test_remove_requires_the_owner():
    _publish({"id": "lisboa", "name": "Lisboa", "zones": [ZONE]})
    mock_ic.caller.return_value = STRANGER
    assert not remove_registered_realm("lisboa")["success"]
    mock_ic.caller.return_value = PUBLISHER
    assert remove_registered_realm("lisboa")["success"]
    assert RealmRecord["lisboa"] is None
    assert listings._details.get("lisboa") is None


def test_strangers_cannot_remove_or_hijack_a_realm():
    _register_realm()
    mock_ic.caller.return_value = STRANGER
    assert not remove_registered_realm(REALM)["success"]
    result = register_realm_by_caller("Hijacked", "https://evil.example", realm_id_override=REALM)
    assert not result["success"]
    assert RealmRecord[REALM].name == "València"


def test_installer_and_controllers_may_register_for_a_realm():
    apply_env_config({"installer_id": "installer-principal"})
    mock_ic.caller.return_value = "installer-principal"
    assert register_realm_by_caller("Via installer", "", realm_id_override=REALM)["success"]
    mock_ic.caller.return_value = STRANGER
    mock_ic.is_controller.return_value = True
    assert remove_registered_realm(REALM)["success"]


def test_publishers_config_round_trip():
    apply_env_config({"listing_publishers": f"{PUBLISHER}, {STRANGER}"})
    from core.env_config import get_listing_publishers

    assert get_listing_publishers() == [PUBLISHER, STRANGER]
    with pytest.raises(ValueError):
        apply_env_config({"listing_publishers": [PUBLISHER] * 5})


def test_list_json_is_serialisable():
    _publish({"id": "lisboa", "name": "Lisboa"})
    assert json.loads(json.dumps(list_listings(1, 10)))["listings"][0]["id"] == "lisboa"
