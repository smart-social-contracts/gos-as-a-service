"""Tests for immediate Casals provision kick scheduling."""

import os
import sys

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src/realm_installer"))

from provision_kick import (
    PROVISION_HEARTBEAT_INTERVAL_S,
    provisioning_job_ids_for_heartbeat,
    schedule_provision_kick,
    should_kick_provision_on_enqueue,
)


class _FakeJob:
    def __init__(self, name: str, status: str):
        self.name = name
        self.status = status


def test_should_kick_when_casals_manifest_and_flag_enabled():
    assert should_kick_provision_on_enqueue(casals_manifest=True, provision_via_casals=True)
    assert not should_kick_provision_on_enqueue(casals_manifest=True, provision_via_casals=False)
    assert not should_kick_provision_on_enqueue(casals_manifest=False, provision_via_casals=True)


def test_schedule_provision_kick_uses_zero_delay_timer():
    timer_calls = []
    ran = []

    def fake_set_timer(duration, callback):
        timer_calls.append((duration, callback))

    def fake_runner(job_id: str):
        ran.append(job_id)
        if False:
            yield

    schedule_provision_kick(
        "job_test_1",
        set_timer=fake_set_timer,
        duration=lambda s: s,
        delay_s=0,
        runner=fake_runner,
    )

    assert len(timer_calls) == 1
    duration, callback = timer_calls[0]
    assert duration == 0
    list(callback())
    assert ran == ["job_test_1"]


def test_heartbeat_interval_is_ten_minutes():
    assert PROVISION_HEARTBEAT_INTERVAL_S == 600


def test_provisioning_job_ids_for_heartbeat():
    jobs = [
        _FakeJob("job_a", "provisioning"),
        _FakeJob("job_b", "pending"),
        _FakeJob("job_c", "failed"),
        _FakeJob("job_d", "provisioning"),
    ]
    ids = provisioning_job_ids_for_heartbeat(jobs, terminal_statuses=("failed", "completed"))
    assert ids == ["job_a", "job_d"]
