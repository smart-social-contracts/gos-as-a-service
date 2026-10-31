"""scripts/audit_slugs.py: flags the slugs whose frontend no deployment job recorded."""

import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "audit_slugs.py"
spec = importlib.util.spec_from_file_location("audit_slugs", SCRIPT)
audit_slugs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_slugs)


def test_slug_with_an_unknown_frontend_is_flagged():
    slugs = [
        {"slug": "mine", "frontend_canister_id": "frontend-a"},
        {"slug": "hijacked", "frontend_canister_id": "attacker-frontend"},
    ]
    jobs = [{"frontend_canister_id": "frontend-a"}, {"frontend_canister_id": "frontend-b"}]
    assert audit_slugs.unverified_slugs(slugs, jobs) == [slugs[1]]


def test_every_slug_is_flagged_when_there_are_no_jobs():
    slugs = [{"slug": "mine", "frontend_canister_id": "frontend-a"}]
    assert audit_slugs.unverified_slugs(slugs, []) == slugs


def test_entities_reads_every_page_and_keeps_only_the_requested_type(monkeypatch):
    rows = [
        ("SlugRecord@1", json.dumps({"slug": "one"})),
        ("RealmRecord@x", json.dumps({"id": "x"})),
        ("SlugRecord@2", json.dumps({"slug": "two"})),
    ]
    monkeypatch.setattr(audit_slugs, "PAGE_SIZE", 2)

    def fake_browse(canister, query, network, identity):
        assert query["map"] == "storage"
        page = rows[query["offset"]:query["offset"] + query["limit"]]
        return {"result": page, "total": len(rows)}

    monkeypatch.setattr(audit_slugs, "browse", fake_browse)
    found = audit_slugs.entities("registry", "storage", "SlugRecord", "ic", None)
    assert [e["slug"] for e in found] == ["one", "two"]
