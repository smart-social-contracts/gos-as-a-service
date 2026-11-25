"""A small simulated Internet Computer for the installer's real code.

The installer's job state machine is driven by timers and inter-canister
calls, so a race in it cannot be seen by calling one function. This module
loads ``src/realm_installer/main.py`` unchanged, replaces the IC (timers,
``yield``-ed calls, the clock) with a virtual-time scheduler, and answers the
calls the installer makes from a fake Casals conductor, realm backend and
registry. Nothing in the installer is stubbed except the cycles preflight.

The registry is the real one: settlement calls reach ``core.env_config`` and
its credit holds, so a test can follow a realm's credits from request to
capture. Everything runs in virtual seconds, so a 4-minute provisioning takes
milliseconds and is deterministic.
"""

import heapq
import importlib.util
import inspect
import json
import os
import sys

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "src", "realm_installer"))

BASE_TIME_S = 1_800_000_000  # any plausible wall clock; only differences matter

INSTALLER_ID = "installer-principal"
REGISTRY_ID = "registry-principal"
CASALS_ID = "casals-principal"
FILE_REGISTRY_ID = "file-registry-principal"
FOUNDER = "founder-principal"
STARTING_CREDITS = 20
DEPLOYMENT_COST = 5


_installer = None


def load_installer():
    """The installer's main.py as a plain module (Basilisk is only a stub here), imported once."""
    global _installer
    if _installer is None:
        _installer = _import_installer()
    return _installer


def empty_databases(installer):
    """Remove every installer and registry row, so a test starts from nothing."""
    from realm_registry_backend.core import models

    for entity in (
        installer.DeploymentJob, installer.DeploymentJobRef, installer.DeployTask, installer.DeployStep,
        installer.InstallerConfig, models.UserCredits, models.DeploymentCreditHold,
        models.CreditTransaction, models.RegistryConfig,
    ):
        for row in list(entity.instances()):
            row.delete()


def _import_installer():
    import basilisk

    sys.path.insert(0, _SRC)

    class Variant(dict):
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

    class Record(dict):
        def __init_subclass__(cls, **kwargs):
            super().__init_subclass__()

    # In stub mode basilisk's Record/Variant reject the keyword arguments the
    # installer's candid types pass; swap them only while main.py is imported.
    saved = {name: getattr(basilisk, name) for name in ("Record", "Variant")}
    basilisk.Record, basilisk.Variant = Record, Variant
    try:
        spec = importlib.util.spec_from_file_location("realm_installer_main", os.path.join(_SRC, "main.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for name, value in saved.items():
            setattr(basilisk, name, value)
    return module


class Call:
    """One inter-canister call an installer generator yielded."""

    def __init__(self, target, method, args):
        self.target, self.method, self.args = str(target), method, args


class _FakeService:
    """Stands in for a Basilisk ``Service``: every method returns the call it would make."""

    def __init__(self, principal):
        self._principal = principal

    def __getattr__(self, method):
        return lambda *args: Call(self._principal, method, args)


class _FakePrincipal(str):
    @staticmethod
    def from_str(value):
        return _FakePrincipal(value)

    def to_str(self):
        return str(self)


class SimulatedIC:
    """Virtual-time scheduler that stands in for ``basilisk.ic`` and answers the installer's calls."""

    CALL_LATENCY_S = 2
    REALM_LATENCY_S = 3
    STAND_BUILD_S = 100  # the conductor needs this long to build a declared stand

    def __init__(self, installer):
        self.main = installer
        self.t = 0
        self._events = []
        self._seq = 0
        self.stands = {}  # stand -> time it was declared
        self.caller_id = REGISTRY_ID  # who the installer sees; a test sets it to act as a user
        self.registry_down = False  # calls to the registry are rejected while True
        self.settlements = {}  # job_id -> ["failed" | "succeeded" | "retried", ...]; "(refused)" if not accepted
        self.history = {}  # job_id -> [(time, status)] every distinct status a poller would see
        self.traps = []
        self.observe = True  # record every status a poller would see (reads every job after each event)
        self.provision_kicks = []  # job ids the installer armed a provision kick for

    # -- the ic.* surface the installer uses --------------------------------
    def time(self):
        return (BASE_TIME_S + self.t) * 1_000_000_000

    def set_timer(self, delay, callback):
        self.at(self.t + int(delay), lambda: self.run(callback()))

    def caller(self):
        return self.caller_id

    def is_controller(self, _principal):
        return False

    def id(self):
        return _FakePrincipal(INSTALLER_ID)

    def call_raw(self, target, method, args, _cycles):
        return Call(target, method, args)

    @staticmethod
    def candid_encode(value):
        return value

    @staticmethod
    def candid_decode(value):
        return value

    # -- scheduler -----------------------------------------------------------
    def at(self, when, action):
        self._seq += 1
        heapq.heappush(self._events, (when, self._seq, action))

    def run(self, result):
        if inspect.isgenerator(result):
            self._advance(result, None)

    def _advance(self, generator, reply):
        try:
            call = generator.send(reply)
        except StopIteration:
            return
        except Exception as error:  # a real canister traps; the pass is simply over
            self.traps.append((self.t, repr(error)))
            return
        latency = self.REALM_LATENCY_S if call.target.startswith("realm") else self.CALL_LATENCY_S
        self.at(self.t + latency, lambda: self._advance(generator, self._answer(call)))

    def run_until(self, until_s):
        while self._events and self._events[0][0] <= until_s:
            when, _seq, action = heapq.heappop(self._events)
            self.t = when
            action()
            self._observe()
        self.t = until_s
        self._observe()

    def _observe(self):
        if not self.observe:
            return
        for job in self.main.DeploymentJob.instances():
            seen = self.history.setdefault(job.name, [])
            if not seen or seen[-1][1] != job.status:
                seen.append((self.t, job.status))

    # -- the world the installer talks to -----------------------------------
    def _answer(self, call):
        if call.target == CASALS_ID:
            return {"Ok": json.dumps(self._casals(call))}
        if call.target == REGISTRY_ID:
            if self.registry_down:
                return {"Err": "IC0508: canister is stopped"}
            return {"Ok": self._registry(call)}
        if call.method == "list_permitted":  # the realm's frontend asset canister
            backend = call.target.replace("-frontend", "-backend")
            return {"Ok": f'(vec {{ principal "{backend}" }})'}
        if call.method == "read" and call.args[0] == "status":
            return {"Ok": json.dumps({"ok": True, "status": "setup"})}
        return {"Ok": json.dumps({"ok": True})}

    def _casals(self, call):
        if call.method == "stand_create":
            stand = json.loads(call.args[0])["name"]
            created = stand not in self.stands
            self.stands.setdefault(stand, self.t)
            return {"ok": True, "created": created}
        if call.method == "orchestra_get":
            return self._orchestra(json.loads(call.args[0])["stand"])
        return {"ok": True}

    def _orchestra(self, stand):
        declared_at = self.stands.get(stand)
        if declared_at is None:
            return {"ok": True, "canisters": [], "stands": []}
        built = self.t - declared_at >= self.STAND_BUILD_S
        members = [
            {"name": f"{stand}-{kind}", "stand": stand, "canister_id": f"realm-{stand}-{kind}", "status": "ready"}
            for kind in ("backend", "frontend")
        ] if built else []
        return {"ok": True, "canisters": members, "stands": [{"name": stand, "built_at": self.t if built else 0}]}

    def _registry(self, call):
        from realm_registry_backend.core import env_config

        job_id = call.args[0]
        settle = {
            "deployment_failed": ("failed", lambda: env_config.settle_deployment_failed(job_id, call.args[1], INSTALLER_ID)),
            "deployment_succeeded": ("succeeded", lambda: env_config.settle_deployment_succeeded(job_id, INSTALLER_ID)),
            "deployment_retried": ("retried", lambda: env_config.settle_deployment_retried(job_id, INSTALLER_ID)),
        }.get(call.method)
        if settle is None:
            return "ok"  # register_realm, claim_slug
        outcome, run = settle
        reply = run()
        self.settlements.setdefault(job_id, []).append(outcome if reply["success"] else f"{outcome} (refused)")
        return json.dumps(reply)


def simulate(installer, *, realms, request_gap_s=3, heartbeat_phase_s=None, run_s=900, setup=None, kick_passes=True):
    """Request ``realms`` a few seconds apart and let the installer run; return the simulated IC.

    ``heartbeat_phase_s`` places the installer's first provision heartbeat
    (it was armed when the canister last started, so its phase against a
    request is arbitrary). ``setup(sim)`` may schedule extra events with
    ``sim.at(seconds, action)`` before the run starts. ``kick_passes=False``
    records the provision kicks the installer arms (``sim.provision_kicks``)
    without running the passes, to look at the heartbeat alone.
    """
    sim = SimulatedIC(installer)
    installer.ic = sim
    installer.Duration = lambda seconds: seconds
    installer.Principal = _FakePrincipal
    installer.CasalsService = installer.RealmRegistryService = installer.RealmTargetService = _FakeService
    installer.FileRegistryService = _FakeService
    installer._cycles_preflight_gen = lambda manifest, cfg: iter(())  # not under test: no Casals cycles report
    installer.check_cycles_preflight = lambda *args, **kwargs: None
    installer.parse_cycles_report = lambda raw: raw
    if not hasattr(installer, "_real_schedule_provision_kick"):
        installer._real_schedule_provision_kick = installer._schedule_provision_kick
    real_kick = installer._real_schedule_provision_kick  # never the wrapper of an earlier simulation
    def schedule_kick(job_id, delay_s=0):
        sim.provision_kicks.append(job_id)
        if kick_passes:
            real_kick(job_id, delay_s)

    installer._schedule_provision_kick = schedule_kick

    from realm_registry_backend.api import credits
    from realm_registry_backend.core import env_config

    env_config.apply_env_config({"installer_id": INSTALLER_ID, "can_test_mode": False})
    for number in range(realms):
        credits.add_user_credits(f"{FOUNDER}-{number}", STARTING_CREDITS)

    installer.apply_installer_config({
        "provision_via_casals": True,
        "casals_canister_id": CASALS_ID,
        "registry_principal": REGISTRY_ID,
        "file_registry_id": FILE_REGISTRY_ID,
    })
    installer._arm_provision_heartbeat(heartbeat_phase_s or 0)

    for number in range(realms):
        sim.at(number * request_gap_s, lambda number=number: sim.run(_request_deployment(installer, number)))
    if setup:
        setup(sim)
    sim.run_until(run_s)
    return sim


def _request_deployment(installer, number):
    """What the registry's request_deployment does: enqueue the job, then hold the credits for it."""
    from realm_registry_backend.api import credits

    founder = f"{FOUNDER}-{number}"
    manifest = {
        "network": "local",
        "realm": {"name": f"realm {number}"},
        "casals": {"section": "Deployments"},
        "registry_canister_id": REGISTRY_ID,
        "file_registry_canister_id": FILE_REGISTRY_ID,
        "requesting_principal": f"{FOUNDER}-{number}",
        "founder": f"{FOUNDER}-{number}",
    }
    result = yield from installer.enqueue_deployment(json.dumps(manifest))
    held = credits.create_deployment_hold(founder, result["Ok"]["job_id"], DEPLOYMENT_COST, "Realm deployment")
    assert held["success"], held
