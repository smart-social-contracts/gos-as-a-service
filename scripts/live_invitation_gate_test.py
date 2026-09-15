#!/usr/bin/env python3
"""Live test: invitation gate Request Invite button on test.gos.earth."""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from playwright.async_api import async_playwright

IDENTITY_INDEX = 5
# Canister ids live in the conductor, never here: `casals -e ic export ../gos-as-a-service/casals.json --json`.
REGISTRY_BACKEND = os.environ.get("REGISTRY_BACKEND") or sys.exit("set REGISTRY_BACKEND to the realm-registry-backend id from `casals export`")
URL = "https://test.gos.earth/deploy-gos"
TALLY_URL = "https://tally.so/r/GxQ8QL"
REPO_ROOT = Path(__file__).resolve().parents[1]


def dfx_call(method: str, arg: str, query: bool = False) -> str:
    cmd = [
        "dfx",
        "canister",
        "call",
        REGISTRY_BACKEND,
        method,
        arg,
        "--network",
        "test",
    ]
    if query:
        cmd.append("--query")
    env = {**os.environ, "TERM": "xterm", "DFX_WARNING": "-mainnet_plaintext_identity"}
    return subprocess.check_output(cmd, env=env, text=True, cwd=REPO_ROOT)


def build_auth_payload() -> tuple[str, str, str]:
    script = r"""
import { Ed25519KeyIdentity, DelegationChain } from '@dfinity/identity';

const index = Number(process.env.IDENTITY_INDEX);
const seed = new Uint8Array(32);
seed[0] = 0xed;
seed[1] = 0x57;
seed[2] = index & 0xff;
seed[3] = (index >>> 8) & 0xff;
seed[4] = (index >>> 16) & 0xff;
seed[5] = (index >>> 24) & 0xff;

const identity = Ed25519KeyIdentity.generate(seed);
const expiration = new Date(Date.now() + 7 * 24 * 60 * 60 * 1000);
const chain = await DelegationChain.create(identity, identity.getPublicKey(), expiration);

process.stdout.write(JSON.stringify({
  principal: identity.getPrincipal().toText(),
  identityJson: JSON.stringify(identity.toJSON()),
  delegationJson: JSON.stringify(chain.toJSON()),
}));
"""
    env = {**os.environ, "IDENTITY_INDEX": str(IDENTITY_INDEX)}
    out = subprocess.check_output(
        ["node", "--input-type=module", "-e", script],
        cwd=REPO_ROOT,
        env=env,
        text=True,
    )
    data = json.loads(out)
    return data["principal"], data["identityJson"], data["delegationJson"]


async def seed_auth_client(page, identity_json: str, delegation_json: str) -> None:
    await page.goto("https://test.gos.earth/", timeout=60000, wait_until="domcontentloaded")
    await page.evaluate(
        """async ({ identityJson, delegationJson }) => {
          const openDb = () => new Promise((resolve, reject) => {
            const req = indexedDB.open('auth-client-db', 1);
            req.onupgradeneeded = (event) => {
              const db = event.target.result;
              if (!db.objectStoreNames.contains('ic-keyval')) {
                db.createObjectStore('ic-keyval');
              }
            };
            req.onsuccess = () => resolve(req.result);
            req.onerror = () => reject(req.error);
          });
          const db = await openDb();
          await new Promise((resolve, reject) => {
            const tx = db.transaction('ic-keyval', 'readwrite');
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
            tx.objectStore('ic-keyval').put(identityJson, 'identity');
            tx.objectStore('ic-keyval').put(delegationJson, 'delegation');
          });
          db.close();
        }""",
        {"identityJson": identity_json, "delegationJson": delegation_json},
    )


async def main() -> None:
    principal, identity_json, delegation_json = build_auth_payload()
    print(f"Test principal: {principal}")

    activated = dfx_call("is_principal_activated", f'("{principal}")', query=True)
    print(f"is_principal_activated: {activated.strip()}")
    if "activated" in activated and "not_activated" not in activated:
        dfx_call("deactivate_principal", f'("{principal}")')
        print("Deactivated principal for clean gate test")

    dfx_call("set_invitation_mode", '("true")')
    dfx_call(
        "set_canister_config_json",
        '("{\\"test_flags\\": {\\"ii_bypass\\": false, \\"test_mode\\": true}}")',
    )
    print(f"get_invitation_mode: {dfx_call('get_invitation_mode', '()', query=True).strip()}")

    checks: dict[str, bool] = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()

        await seed_auth_client(page, identity_json, delegation_json)
        await page.goto(URL, timeout=60000, wait_until="networkidle")
        await page.wait_for_timeout(6000)

        body = await page.inner_text("body")
        invite_btn = page.locator("a.invitation-request-btn")
        await page.screenshot(path="/tmp/test_invitation_gate_logged_in.png", full_page=True)

        checks = {
            "invitation_required_heading": "Invitation Required" in body,
            "request_invite_visible": await invite_btn.count() > 0,
            "request_invite_href": (await invite_btn.get_attribute("href")) == TALLY_URL
            if await invite_btn.count()
            else False,
            "no_openchat": "OpenChat" not in body,
        }

        print("\nLive UI checks:")
        for name, ok in checks.items():
            print(f"  {name}: {'PASS' if ok else 'FAIL'}")

        if checks["request_invite_visible"] and checks["request_invite_href"]:
            async with context.expect_page() as new_page_info:
                await invite_btn.click()
            tally_page = await new_page_info.value
            await tally_page.wait_for_load_state("domcontentloaded", timeout=30000)
            tally_url = tally_page.url
            print(f"  tally_navigation: {tally_url}")
            checks["tally_navigation"] = tally_url.startswith(TALLY_URL)

        await browser.close()

    dfx_call("set_invitation_mode", '("false")')
    dfx_call(
        "set_canister_config_json",
        '("{\\"test_flags\\": {\\"ii_bypass\\": true, \\"test_mode\\": true}}")',
    )
    print("Restored test invitation_mode=false and ii_bypass=true")

    if not all(checks.values()):
        print("\nFAILED:", checks)
        sys.exit(1)
    print("\nAll live invitation-gate checks passed.")


if __name__ == "__main__":
    asyncio.run(main())
