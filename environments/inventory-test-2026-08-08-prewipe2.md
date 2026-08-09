# test.gos.earth Canister Inventory Snapshot

| Field | Value |
|-------|-------|
| **Date** | 2026-08-08 (pre-wipe #2, before clean-slate `gaas new` rehearsal) |
| **Identity** | `deployer` (`ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`) |
| **Network** | IC mainnet |

## Table 1: Platform Canisters + Multisig (to be blank-WASM wiped, IDs preserved)

| Name | Canister ID | Status | Cycles | Module Hash |
|------|-------------|--------|--------|-------------|
| realm_registry_backend | `yhw3g-fyaaa-aaaas-qgorq-cai` | Running | 1,963,763,795,360 | `0xebf9ddbfd0beb8754ff070c22a1448c6d0a8d34a81b8a735a1761c2480465a72` |
| realm_registry_frontend | `qtank-3qaaa-aaaaa-qhb6q-cai` | Running | 3,458,973,104,620 | `0xf1036e852d2d27418d7b667a9783a38ba84271f5d9730380f1f20b1494d1da82` |
| realm_installer | `fltjm-tyaaa-aaaap-qunhq-cai` | Running | 6,507,988,999,551 | `0x7ea0e0130b6ce630841ddcf27748060c7340a6d6798d1f0c7ef3d2cb7859fed6` |
| file_registry | `uq2mu-kaaaa-aaaah-avqcq-cai` | Running | 2,066,642,050,630 | `0x25bada97e8e7d4e838896148c2ab9e17eaed3fa50236e10c387681d1c7407134` |
| file_registry_frontend | `2no7h-xqaaa-aaaad-qlxeq-cai` | Running | 3,279,178,547,607 | `0xf1036e852d2d27418d7b667a9783a38ba84271f5d9730380f1f20b1494d1da82` |
| casals_backend | `qthgp-3yaaa-aaaae-agveq-cai` | Running | 15,499,993,241,644 | `0x14b856c0d4f866c78d511664d6b3a1e72a2b89f1bce201ba68083d6a2a14e433` |
| casals_frontend | `qic2k-baaaa-aaaae-agvga-cai` | Running | 1,829,167,532,306 | `0xf1036e852d2d27418d7b667a9783a38ba84271f5d9730380f1f20b1494d1da82` |
| multisig_backend | `3iqx7-eyaaa-aaaae-agyxq-cai` | Running | 1,497,814,569,142 | `0xe2a2006682be6b5242c12b494c3fcef1551f53dfd110b33dbac011a2f99d06d3` |

## Table 2: RealmTest5 (KEPT — user's setup-wizard preview; not touched by wipe)

| Name | Canister ID | Status | Cycles | Module Hash |
|------|-------------|--------|--------|-------------|
| realmtest5-backend | `y7c3n-vaaaa-aaaae-agy7a-cai` | Running | 1,251,242,751,771 | `0xacf20f096f50c7fcae18e25d23d3fb65ac2f41a6f664b4728fd28fdab195f673` |
| realmtest5-frontend | `yyd5z-yyaaa-aaaae-agy7q-cai` | Running | 1,450,676,313,535 | `0xf1036e852d2d27418d7b667a9783a38ba84271f5d9730380f1f20b1494d1da82` |
| realmtest5-baton | `tgvph-dqaaa-aaaae-agzaa-cai` | Running | 1,476,503,378,211 | `0x8f664bf7fb99c407f54960f632a3105ff8d64f62866dc74249a409db63d976f1` |

## Table 3: Deleted for cycle reclaim on 2026-08-08 (user-approved: old realms only)

Cycles withdrawn to deployer cycles wallet via `dfx canister delete` (13.9T reclaimed).

| Name | Canister ID | Approx. cycles reclaimed |
|------|-------------|--------------------------|
| gaas-smoke-backend | `zhloo-3aaaa-aaaae-agy3a-cai` | ~1.46T |
| gaas-smoke-frontend | `zaki2-wyaaa-aaaae-agy3q-cai` | ~1.49T |
| gaas-smoke-baton | `ynemu-zqaaa-aaaae-agy4a-cai` | ~1.48T |
| realmtest2-backend | `ykfka-uiaaa-aaaae-agy4q-cai` | ~1.46T |
| realmtest2-frontend | `ydgb4-caaaa-aaaae-agy5a-cai` | ~1.49T |
| realmtest4-backend | `yrawf-oqaaa-aaaae-agy6a-cai` | ~1.48T |
| realmtest4-frontend | `ywbqr-diaaa-aaaae-agy6q-cai` | ~1.49T |
| e2e-proof-backend | `tbujt-oiaaa-aaaae-agzaq-cai` | ~2T |
| e2e-proof-frontend | `tixcp-yaaaa-aaaae-agzba-cai` | ~2T |
| e2e-proof-baton | `tpwe3-vyaaa-aaaae-agzbq-cai` | ~2T |
