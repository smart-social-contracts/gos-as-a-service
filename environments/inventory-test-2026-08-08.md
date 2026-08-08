# test.gos.earth Canister Inventory Snapshot

| Field | Value |
|-------|-------|
| **Date** | 2026-08-08 |
| **Purpose** | Pre-wipe inventory before gaas CLI redeploy of test.gos.earth |
| **Identity** | `deployer` (`ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`) |
| **Network** | IC mainnet (`--network ic`) |
| **Sources** | `environments/test.json`, `realms/canister_ids.json` |

---

## Table 1: Platform Canisters (6)

From `environments/test.json`.

| Name | Canister ID | Status | Module Hash | Memory Size | Controllers | Cycles Balance |
|------|-------------|--------|-------------|-------------|-------------|----------------|
| realm_registry_backend | `yhw3g-fyaaa-aaaas-qgorq-cai` | Running | `0x19c9020863941dbf5f5135eb0d897fa86b6c6c94d7a94032e9f992a8732954cb` | 114,339,952 B (~109 MB) | `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` | 2,282,769,213,438 |
| realm_registry_frontend | `qtank-3qaaa-aaaaa-qhb6q-cai` | Running | `0x330e10d6e268d7031ce2573563d9308529759d94584c4768f9cf86938e00ccf4` | 59,541,781 B (~57 MB) | `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` | 3,553,376,832,792 |
| realm_installer | `fltjm-tyaaa-aaaap-qunhq-cai` | Running | `0xaca99c827a05ed76c9c6672ea24ba5ace604422dd245823dd8c441b39628b059` | 121,812,846 B (~116 MB) | `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` | 6,887,449,657,335 |
| file_registry | `uq2mu-kaaaa-aaaah-avqcq-cai` | Running | `0x2bb80d9dcdf2974d255db181bdb8bb6674358c936513c0971e3cfeae20e59fb7` | 312,953,087 B (~299 MB) | `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` | 604,230,190,561 |
| file_registry_frontend | `2no7h-xqaaa-aaaad-qlxeq-cai` | Running | `0xf1036e852d2d27418d7b667a9783a38ba84271f5d9730380f1f20b1494d1da82` | 2,239,076 B (~2 MB) | `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` | 3,311,368,582,519 |
| casals_conductor | `qthgp-3yaaa-aaaae-agveq-cai` | Running | `0x5d3f694b463607353af7434a75a8afda0cbdb12128271d73f4c31dd2b4a13eaa` | 160,257,453 B (~153 MB) | `3itd6-2sx7g-vefdk-xhebm-fucot-llay5-lhqd6-pkjac-m7mkf-vhwqq-fqe`, `7ligz-kvvkj-iezxe-fbwfv-4zipu-6zvfb-taw3d-mi7ni-ysp27-cme2n-eqe`, `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `jku4b-fiyac-636ba-q2hmj-22lrq-drtrz-lqatd-ooccj-wzwxo-ox6py-gae` | 5,557,355,684,942 |

---

## Table 2: Realms Test-Network Canisters (16)

From `realms/canister_ids.json` — every entry with a `"test"` network ID.

| Name | Canister ID | Status | Module Hash | Memory Size | Controllers | Cycles Balance |
|------|-------------|--------|-------------|-------------|-------------|----------------|
| casals_frontend | `qic2k-baaaa-aaaae-agvga-cai` | Running | `0x04e565b3425fe7510ee16b02adcfe3f01abc9a2725c82a21cb08969241debd62` | 7,567,094 B (~7 MB) | `7ligz-kvvkj-iezxe-fbwfv-4zipu-6zvfb-taw3d-mi7ni-ysp27-cme2n-eqe`, `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae` | 1,894,398,870,959 |
| casals_backend | `qthgp-3yaaa-aaaae-agveq-cai` | Running | `0x5d3f694b463607353af7434a75a8afda0cbdb12128271d73f4c31dd2b4a13eaa` | 160,257,453 B (~153 MB) | `3itd6-2sx7g-vefdk-xhebm-fucot-llay5-lhqd6-pkjac-m7mkf-vhwqq-fqe`, `7ligz-kvvkj-iezxe-fbwfv-4zipu-6zvfb-taw3d-mi7ni-ysp27-cme2n-eqe`, `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `jku4b-fiyac-636ba-q2hmj-22lrq-drtrz-lqatd-ooccj-wzwxo-ox6py-gae` | 5,557,355,684,942 |
| file_registry | `uq2mu-kaaaa-aaaah-avqcq-cai` | Running | `0x2bb80d9dcdf2974d255db181bdb8bb6674358c936513c0971e3cfeae20e59fb7` | 312,953,087 B (~299 MB) | `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` | 604,230,190,561 |
| file_registry_frontend | `2no7h-xqaaa-aaaad-qlxeq-cai` | Running | `0xf1036e852d2d27418d7b667a9783a38ba84271f5d9730380f1f20b1494d1da82` | 2,239,076 B (~2 MB) | `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` | 3,311,368,582,519 |
| marketplace_backend | `2wldc-niaaa-aaaad-qlxga-cai` | Running | `0xbc9ce986654c759c5095cb2cc10dcc89b8b7c7e5380cc76674ec96e22545635d` | 58,020,354 B (~55 MB) | `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` | 2,746,703,406,575 |
| marketplace_frontend | `mxyd5-3qaaa-aaaao-ba2xq-cai` | Running | `0x330e10d6e268d7031ce2573563d9308529759d94584c4768f9cf86938e00ccf4` | 16,812,249 B (~16 MB) | `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` | 3,710,604,561,267 |
| nft_backend | `eelas-yyaaa-aaaao-qps7a-cai` | Running | `0xabea08d97de800d4e299545be786dd02c9c6a7d93aaccc3770a08c213dfa484b` | 31,793,715 B (~30 MB) | `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` | 3,819,847,649,597 |
| nft_frontend | `ysrkl-eqaaa-aaaas-qgosa-cai` | Running | *(none — empty asset canister)* | 13,356 B | `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` | 3,928,025,168,924 |
| platform_dashboard_frontend | `em2mz-rqaaa-aaaag-ayt7q-cai` | Running | `0x330e10d6e268d7031ce2573563d9308529759d94584c4768f9cf86938e00ccf4` | 3,894,301 B (~4 MB) | `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` | 2,824,667,411,073 |
| realm_backend | `ku6cv-2iaaa-aaaab-agrpa-cai` | Running | `0x21e4ae4d169c822df9f313a8283100284717a5501bb3cc58a6a159da3786d3a9` | 142,400,008 B (~136 MB) | `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` | 674,106,145,178 |
| realm_frontend | `pqwsi-vyaaa-aaaau-agrbq-cai` | Running | `0x330e10d6e268d7031ce2573563d9308529759d94584c4768f9cf86938e00ccf4` | 15,035,451 B (~14 MB) | `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` | 2,418,473,699,422 |
| realm_installer | `fltjm-tyaaa-aaaap-qunhq-cai` | Running | `0xaca99c827a05ed76c9c6672ea24ba5ace604422dd245823dd8c441b39628b059` | 121,812,846 B (~116 MB) | `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` | 6,887,449,657,335 |
| realm_registry_backend | `yhw3g-fyaaa-aaaas-qgorq-cai` | Running | `0x19c9020863941dbf5f5135eb0d897fa86b6c6c94d7a94032e9f992a8732954cb` | 114,339,952 B (~109 MB) | `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` | 2,282,769,213,438 |
| realm_registry_frontend | `qtank-3qaaa-aaaaa-qhb6q-cai` | Running | `0x330e10d6e268d7031ce2573563d9308529759d94584c4768f9cf86938e00ccf4` | 59,541,781 B (~57 MB) | `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` | 3,553,376,832,792 |
| token_backend | `nusyl-jiaaa-aaaae-qj6mq-cai` | Running | `0xa1734ad2ec260ce85e541f860dbcaf8c846423709177587c7e5f70adc47e461a` | 31,692,349 B (~30 MB) | `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` | 3,804,566,095,882 |
| token_frontend | `33mmr-pyaaa-aaaam-ai47q-cai` | Running | *(none — empty asset canister)* | 13,356 B | `ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae`, `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` | 3,929,696,617,717 |

> **Note:** Six entries in Table 2 share IDs with Table 1 (platform canisters). Unique canister IDs across both tables: **16**.

---

## Live Registry Contents (realm_registry_backend)

Canister: `yhw3g-fyaaa-aaaas-qgorq-cai`

### `list_realms` (raw)

```
(
  vec {
    record {
      id = "shzd3-6yaaa-aaaae-agvkq-cai";
      url = "https://test.gos.earth/r/testrealmssyntropia1";
      logo = "https://3gs2x-7iaaa-aaaae-agywq-cai.icp0.io/custom/logo.png";
      name = "TestRealmsSyntropia1";
      created_at = 1786136307.9025347 : float64;
      backend_url = "https://shzd3-6yaaa-aaaae-agvkq-cai.icp0.io";
      frontend_canister_id = "3gs2x-7iaaa-aaaae-agywq-cai";
      users_count = 0 : nat64;
    };
    record {
      id = "m2wv3-uaaaa-aaaah-quoiq-cai";
      url = "https://2dmsp-maaaa-aaaad-qlxfq-cai.icp0.io";
      logo = "logo.png";
      name = "Syntropia";
      created_at = 1781068073.9054646 : float64;
      backend_url = "https://m2wv3-uaaaa-aaaah-quoiq-cai.icp0.io";
      frontend_canister_id = "2dmsp-maaaa-aaaad-qlxfq-cai";
      users_count = 0 : nat64;
    };
    record {
      id = "rnghe-haaaa-aaaak-qyxyq-cai";
      url = "https://pqwsi-vyaaa-aaaau-agrbq-cai.icp0.io";
      logo = "logo.png";
      name = "Agora";
      created_at = 1781068069.228808 : float64;
      backend_url = "https://rnghe-haaaa-aaaak-qyxyq-cai.icp0.io";
      frontend_canister_id = "pqwsi-vyaaa-aaaau-agrbq-cai";
      users_count = 0 : nat64;
    };
    record {
      id = "ku6cv-2iaaa-aaaab-agrpa-cai";
      url = "https://2enu3-byaaa-aaaad-qlxfa-cai.icp0.io";
      logo = "logo.png";
      name = "Dominion";
      created_at = 1781068055.2718413 : float64;
      backend_url = "https://ku6cv-2iaaa-aaaab-agrpa-cai.icp0.io";
      frontend_canister_id = "2enu3-byaaa-aaaad-qlxfa-cai";
      users_count = 0 : nat64;
    };
  },
)
```

### `realm_count` (raw)

```
(4 : nat64)
```

### `list_pending_pretty_hostnames` / slugs (raw)

```
(
  "{\"success\":true,\"slugs\":[{\"slug\":\"testrealmssyntropia1\",\"realm_id\":\"shzd3-6yaaa-aaaae-agvkq-cai\",\"frontend_canister_id\":\"3gs2x-7iaaa-aaaae-agywq-cai\",\"claimed_by\":\"fltjm-tyaaa-aaaap-qunhq-cai\",\"claimed_at\":1786136310.432734,\"portal_url\":\"https://test.gos.earth/r/testrealmssyntropia1\",\"pretty_hostname\":\"testrealmssyntropia1.test.gos.earth\",\"pretty_hostname_status\":\"pending\",\"gos_implementation\":\"realms-gos\",\"gos_version\":\"\",\"ggg_conformance\":\"1.0\",\"loader_profile\":\"realms-iframe-v1\",\"created_at\":1786136310.432734,\"updated_at\":1786174844.4027982}]}",
)
```

### `status` (raw)

```
(
  variant {
    Ok = record {
      python_version = "3.13.0 (tags/v3.13.0-dirty:60403a5, May 16 2026, 08:41:41) [Clang 18.1.2-wasi-sdk (https://github.com/llvm/llvm-project 26a1d6601d727a96f43";
      status = "ok";
      realms_count = 4 : nat64;
      version = "0.3.2";
      dependencies = vec {
        "ic-basilisk==BASILISK_0.3.2";
        "ic-python-db==IC_PYTHON_DB_0.3.2";
        "ic-python-logging==IC_PYTHON_LOGGING_0.3.2";
      };
      commit = "15c2f04";
      commit_datetime = "2026-08-08 10:20:09";
    }
  },
)
```

**Summary:** 4 realms registered, 1 slug (`testrealmssyntropia1`, pretty-hostname status: `pending`).

---

## File Registry Namespaces (file_registry)

Canister: `uq2mu-kaaaa-aaaah-avqcq-cai`

### `list_namespaces` (raw)

```
(
  "[{\"namespace\":\"branding-testrealmssyntropia1-d27b4118\",\"file_count\":2,\"total_bytes\":1150342,\"created\":1786131416848969170,\"owner\":\"svg6i-ii3xk-qrwvk-3shub-2cuk6-vm5py-ckzub-w32aw-zhqqp-tsdpe-4ae\",\"description\":\"\"},{\"namespace\":\"ext/access_manager/1.8.1\",\"file_count\":3,\"total_bytes\":230033,\"created\":1786134679452506706,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/admin_dashboard/1.3.0\",\"file_count\":4,\"total_bytes\":90163,\"created\":1786137577878310816,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/codex_viewer/1.0.6\",\"file_count\":4,\"total_bytes\":109094,\"created\":1786137594737424403,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/department_docs/1.1.0\",\"file_count\":4,\"total_bytes\":86276,\"created\":1786134693786211762,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/import_export/1.0.2\",\"file_count\":4,\"total_bytes\":113298,\"created\":1786137612865126423,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/justice_litigation/0.5.0\",\"file_count\":4,\"total_bytes\":142764,\"created\":1786134707260507342,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/land_registry/1.3.5\",\"file_count\":6,\"total_bytes\":1251458,\"created\":1786134721824004797,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/managed_services/0.2.0\",\"file_count\":3,\"total_bytes\":102359,\"created\":1786134774829241744,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/member_dashboard/1.1.2\",\"file_count\":4,\"total_bytes\":137520,\"created\":1786137633574455291,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/member_manager/1.0.5\",\"file_count\":4,\"total_bytes\":97740,\"created\":1786134785670706570,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/metrics/1.1.2\",\"file_count\":2,\"total_bytes\":115962,\"created\":1786134802428460673,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/mundus_explorer/1.0.0\",\"file_count\":4,\"total_bytes\":85850,\"created\":1786137652474450716,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/notifications/1.1.3\",\"file_count\":4,\"total_bytes\":85390,\"created\":1786134813532935771,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/package_manager/0.3.1\",\"file_count\":2,\"total_bytes\":143610,\"created\":1786134827269357121,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/passport_verification/1.0.6\",\"file_count\":4,\"total_bytes\":98060,\"created\":1786134837116951233,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/procurement/0.3.0\",\"file_count\":4,\"total_bytes\":125212,\"created\":1786134851411714613,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/public_dashboard/1.3.9\",\"file_count\":2,\"total_bytes\":114638,\"created\":1786137670265922723,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/realm_settings/1.10.0\",\"file_count\":4,\"total_bytes\":216381,\"created\":1786137683455644485,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/role_manager/1.3.3\",\"file_count\":4,\"total_bytes\":258846,\"created\":1786134865718376589,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/syntropia/0.8.9\",\"file_count\":28,\"total_bytes\":208436,\"created\":1786134597892409699,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/system_info/1.0.3\",\"file_count\":4,\"total_bytes\":90512,\"created\":1786134882883641536,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/task_monitor/1.0.6\",\"file_count\":4,\"total_bytes\":168420,\"created\":1786134898982890168,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/vault/0.2.7\",\"file_count\":10,\"total_bytes\":143046,\"created\":1786137706013576178,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/voting/1.3.1\",\"file_count\":4,\"total_bytes\":230003,\"created\":1786137749772629015,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"ext/zone_selector/1.3.9\",\"file_count\":6,\"total_bytes\":1241512,\"created\":1786134917386679726,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"frontend/realm-assets/main.1786133825.33772de\",\"file_count\":120,\"total_bytes\":5204696,\"created\":1786134051672939641,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"frontend/realm-assets/main.1786175945.9ad2094\",\"file_count\":120,\"total_bytes\":5204844,\"created\":1786176078380378634,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"frontend/realm-assets/main.1786178668.f8e017e\",\"file_count\":120,\"total_bytes\":5204863,\"created\":1786178798651534970,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"frontend/registry-assets/0.3.2\",\"file_count\":91,\"total_bytes\":3671319,\"created\":1786184584115282215,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"frontend/registry-assets/main.1785786698.c364d98\",\"file_count\":90,\"total_bytes\":3626844,\"created\":1785786801504206646,\"owner\":\"7ligz-kvvkj-iezxe-fbwfv-4zipu-6zvfb-taw3d-mi7ni-ysp27-cme2n-eqe\",\"description\":\"\"},{\"namespace\":\"frontend/registry-assets/main.1785787283.6f05169\",\"file_count\":90,\"total_bytes\":3627407,\"created\":1785787385187934191,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"frontend/registry-assets/main.1785789219.6f051696\",\"file_count\":90,\"total_bytes\":3627530,\"created\":1785789223884890318,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"wasm/installer-backend/0.1.0\",\"file_count\":1,\"total_bytes\":1719493,\"created\":1786184337948108907,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"wasm/installer-backend/0.3.2\",\"file_count\":1,\"total_bytes\":1719494,\"created\":1786184271815889102,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"wasm/realm-assetstorage/main.1786133825.33772de\",\"file_count\":1,\"total_bytes\":380263,\"created\":1786134515078004097,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"wasm/realm-assetstorage/main.1786175945.9ad2094\",\"file_count\":1,\"total_bytes\":380263,\"created\":1786176634709018820,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"wasm/realm-assetstorage/main.1786178668.f8e017e\",\"file_count\":1,\"total_bytes\":380263,\"created\":1786179445897367619,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"wasm/realm-backend/main.1786133825.33772de\",\"file_count\":1,\"total_bytes\":3252731,\"created\":1786134039952076402,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"wasm/registry-assetstorage/0.3.2\",\"file_count\":1,\"total_bytes\":600971,\"created\":1786185277257014418,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"wasm/registry-assetstorage/main.1785787283.6f05169\",\"file_count\":1,\"total_bytes\":465918,\"created\":1785787813960676830,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"wasm/registry-assetstorage/main.1785789219.6f051696\",\"file_count\":1,\"total_bytes\":465918,\"created\":1785789613952210388,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"wasm/registry-backend/0.3.2\",\"file_count\":1,\"total_bytes\":1682847,\"created\":1786184572533041437,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"},{\"namespace\":\"wasm/registry-backend/main.1785786698.c364d98\",\"file_count\":1,\"total_bytes\":1670665,\"created\":1785786790146536590,\"owner\":\"7ligz-kvvkj-iezxe-fbwfv-4zipu-6zvfb-taw3d-mi7ni-ysp27-cme2n-eqe\",\"description\":\"\"},{\"namespace\":\"wasm/registry-backend/main.1785787283.6f05169\",\"file_count\":1,\"total_bytes\":1785329,\"created\":1785787375344388010,\"owner\":\"ah6ac-cc73l-bb2zc-ni7bh-jov4q-roeyj-6k2ob-mkg5j-pequi-vuaa6-2ae\",\"description\":\"\"}]",
)
```

**Summary:** 44 namespaces total (1 branding, 25 extensions, 7 frontend asset versions, 11 wasm artifacts).

---

## Footer

| Metric | Value |
|--------|-------|
| **Platform canister entries (Table 1)** | 6 |
| **Realms test canister entries (Table 2)** | 16 |
| **Unique canister IDs (deduplicated)** | **16** |
| **Combined cycles balance (unique IDs)** | ~52.4 TC (52,412,550,501,452 cycles) |
| **All canisters Running?** | Yes — all 16 |
| **Status failures for deployer** | None |

### Controller visibility (deployer identity)

The `deployer` principal (`ah6ac-cc73l-…`) is a **controller of all 16 canisters**. No `dfx canister status` calls failed.

Additional non-deployer controllers present on some canisters:

| Canister | Extra controllers (beyond deployer) |
|----------|-------------------------------------|
| casals_conductor / casals_backend | `3itd6-…`, `7ligz-…`, `jku4b-…` |
| casals_frontend | `7ligz-…` |
| All other platform + realms test canisters | `cpbhu-5iaaa-aaaad-aalta-cai`, `qthgp-3yaaa-aaaae-agveq-cai` |

### Notable observations

- **`nft_frontend` and `token_frontend`** have no module hash and minimal memory (13 KB) — empty asset canisters, not yet populated.
- **`file_registry`** has the lowest cycles balance among platform canisters (~604B cycles / ~0.6 TC).
- **Registry lists 4 realms** but several realm backend/frontend canister IDs (`shzd3-…`, `3gs2x-…`, `m2wv3-…`, `2dmsp-…`, `rnghe-…`, `2enu3-…`) are **not** in `canister_ids.json` — these are dynamically provisioned realm stands beyond the static test template IDs.
- **1 slug** registered: `testrealmssyntropia1` (pretty-hostname status: `pending`).

> **Reinstall note:** A `dfx canister install --mode reinstall` (or equivalent gaas redeploy) **preserves canister IDs and existing cycles balances**. This inventory captures both so they can be verified post-redeploy.
