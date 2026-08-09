# Inventory — test.gos.earth — pre-clean-slate (2026-08-09 10:09 UTC)

All ledger default accounts verified **0 ICP**. Platform canisters will be blank-WASM wiped
(IDs + cycles preserved). Realm canisters will be deleted (cycles reclaimed to conductor treasury).
Multisig canisters are left untouched.


## PLATFORM

| name | canister_id | cycles (TC) | ICP (e8s) | module_hash |
|---|---|---|---|---|
| realm_registry_backend | yhw3g-fyaaa-aaaas-qgorq-cai | 1.93 | 0 | `0xfa47b79c88a6cd99cb113da192441d77a2f471e34c5da2cf8f512b06c6ed0043` |
| realm_registry_frontend | qtank-3qaaa-aaaaa-qhb6q-cai | 3.44 | 0 | `0xf1036e852d2d27418d7b667a9783a38ba84271f5d9730380f1f20b1494d1da82` |
| realm_installer | fltjm-tyaaa-aaaap-qunhq-cai | 6.43 | 0 | `0x18fe0993470a2674ba1d7d2356345d29da7092fa7f282a59b52d2b3efa239c68` |
| file_registry | uq2mu-kaaaa-aaaah-avqcq-cai | 0.61 | 0 | `0x87afb64c24d33dd8437969767e11c55597ac6952fa0bb60198911c8b9e971dd0` |
| file_registry_frontend | 2no7h-xqaaa-aaaad-qlxeq-cai | 3.27 | 0 | `0xf1036e852d2d27418d7b667a9783a38ba84271f5d9730380f1f20b1494d1da82` |
| casals_backend | qthgp-3yaaa-aaaae-agveq-cai | 20.03 | 0 | `0xf2e245ee4afcf195485a3cc8d0d60bab67b8d56728efc521662498c64476e664` |
| casals_frontend | qic2k-baaaa-aaaae-agvga-cai | 1.81 | 0 | `0xf1036e852d2d27418d7b667a9783a38ba84271f5d9730380f1f20b1494d1da82` |

## MULTISIG (untouched)

| name | canister_id | cycles (TC) | ICP (e8s) | module_hash |
|---|---|---|---|---|
| multisig (tree) | t2rvw-uqaaa-aaaae-agzca-cai | 1.50 | 0 | `0xe2a2006682be6b5242c12b494c3fcef1551f53dfd110b33dbac011a2f99d06d3` |
| multisig (descriptor) | 3iqx7-eyaaa-aaaae-agyxq-cai | 1.50 | 0 | `0xe2a2006682be6b5242c12b494c3fcef1551f53dfd110b33dbac011a2f99d06d3` |

## REALMS (delete candidates)

| name | canister_id | cycles (TC) | ICP (e8s) | module_hash |
|---|---|---|---|---|
| green-proof-backend | sx7ry-3yaaa-aaaae-agzfq-cai | 1.37 | 0 | `0x8734e2cc0b50e0b557b6c4654de164c8675cff3e32b4b5726860266e19a6a113` |
| green-proof-frontend | scyav-2qaaa-aaaae-agzga-cai | 1.44 | 0 | `0xf1036e852d2d27418d7b667a9783a38ba84271f5d9730380f1f20b1494d1da82` |
| launch-proof-backend | sm2n5-baaaa-aaaae-agzha-cai | 1.43 | 0 | `0x8734e2cc0b50e0b557b6c4654de164c8675cff3e32b4b5726860266e19a6a113` |
| launch-proof-frontend | sl3lj-myaaa-aaaae-agzhq-cai | 1.48 | 0 | `0xf1036e852d2d27418d7b667a9783a38ba84271f5d9730380f1f20b1494d1da82` |
| launch-proof-baton | qwgfb-7qaaa-aaaae-agzia-cai | 1.48 | 0 | `0x6ca5df4e20fa63addbd86b4a83b2c6534d493889c406d47361387d0d1127d47f` |
| smooth-proof-backend | qrhdv-siaaa-aaaae-agziq-cai | 1.43 | 0 | `0x8734e2cc0b50e0b557b6c4654de164c8675cff3e32b4b5726860266e19a6a113` |
| smooth-proof-frontend | qyeij-eaaaa-aaaae-agzja-cai | 1.47 | 0 | `0xf1036e852d2d27418d7b667a9783a38ba84271f5d9730380f1f20b1494d1da82` |
| smooth-proof-baton | q7fo5-jyaaa-aaaae-agzjq-cai | 1.48 | 0 | `0x6ca5df4e20fa63addbd86b4a83b2c6534d493889c406d47361387d0d1127d47f` |
| realmtest5-backend | y7c3n-vaaaa-aaaae-agy7a-cai | 1.18 | 0 | `0x8734e2cc0b50e0b557b6c4654de164c8675cff3e32b4b5726860266e19a6a113` |
| realmtest5-frontend | yyd5z-yyaaa-aaaae-agy7q-cai | 1.38 | 0 | `0xf1036e852d2d27418d7b667a9783a38ba84271f5d9730380f1f20b1494d1da82` |

Realm deletion reclaims ~14.14 TC to conductor treasury (qthgp-3yaaa-aaaae-agveq-cai).
Note: descriptor pins multisig 3iqx7-... but conductor tree governance stand uses t2rvw-... (both live, same hash/balance); reconcile during next gaas new.
