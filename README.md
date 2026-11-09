# auto-cb

Universal CodeBuddy International (`www.codebuddy.ai`) OAuth & onboarding toolkit: CLI Device Flow (`state` generator & token poller), direct Keycloak identity broker URL builder (`kc_idp_hint=github|google`), 5-step Free Trial onboarding runner (`/billing/ide/trial`), and pluggable credential sink (`stdout`, `file`, `http`, `sqlite`).

## Modules

| Module | Path | Responsibility |
|---|---|---|
| `cbai_auth` | `packages/auto_cb/cbai_auth.py` | CLI state creation (`request_cbai_device_code`), token polling (`poll_cbai_token`), direct Keycloak broker URLs (`build_cbai_keycloak_direct_url`), APAC region payload (`build_cbai_area_payload`), and 5-step onboarding (`run_cbai_5step_onboarding`) |
| `router_store` | `packages/auto_cb/router_store.py` | `CredentialBundle` schema, `scrypt` + `AES-256-GCM` (`enc:v1:`) cipher, and `dispatch_credential_sink` (`stdout`, `file:<path>`, `http://<host>:<port>`, `sqlite:<db_path>`) |
| `cli` | `packages/auto_cb/cli.py` | CLI (`init`, `poll`, `area-payload`, `sink`, `pair --stdin`, `doctor`) |

## Quickstart

```bash
cp .env.example .env
make test
make hygiene
make init
make area-payload CC=sg
```
