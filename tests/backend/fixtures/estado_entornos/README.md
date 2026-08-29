# Fixtures de `estado_entornos`

Mundo enlatado para el dry-run del informe "estado de los entornos" — sin IC en
vivo:

```bash
./scripts/estado_entornos.sh --fixtures tests/backend/fixtures/estado_entornos
```

Los ids de canister son los reales de `environments/*.json` (son públicos y
están en este repo); las respuestas son inventadas. Un fichero ausente simula
un fallo del CLI (p.ej. identidad que no es controller del canister).

Layout por entorno (`test/`, `staging/`, `demo/`):

| Ruta | Simula |
|---|---|
| `status/<canister_id>.txt` | salida de `dfx canister status` |
| `call/<canister_id>/<method>.txt` | respuesta candid de una query sin argumentos |
| `call/<canister_id>/list_files__<ns-slug>.txt` | `list_files` por namespace (`/`-→`_`) |
| `http/<host>.html` | GET `https://<host>/` (meta tags del frontend) |
| `objects/<namespace>/<path>.b64` | objeto del file_registry (base64) para `get_file_size` / `get_file_chunk` |

El objeto wasm de prueba es el módulo vacío `(module)` gzipeado con
`mtime=0`; su module hash es
`93a44bbb96c751218e4c00d479e4c14358122a389acca16205b1e4d0dc5f9476`
(sha256 de los 8 bytes `\0asm\1\0\0\0`), que es lo que el job de deploy del
fixture reporta como `actual_wasm_hash` — así el mapa module_hash → versión
casa de verdad.
