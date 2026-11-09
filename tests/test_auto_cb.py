import io
import json
import os
import sqlite3
import tempfile

from auto_cb.cbai_auth import (
    build_cbai_area_payload,
    build_cbai_keycloak_direct_url,
    execute_cbai_pairing_from_bundle,
    prepare_cbai_pairing_from_bundle,
)
from auto_cb.router_store import (
    CredentialBundle,
    decrypt_field,
    dispatch_credential_sink,
    encrypt_field,
)

TEST_SECRET = "0000000000000000000000000000000000000000000000000000000000000001"


def test_area_and_keycloak_url():
    p = build_cbai_area_payload("sg")
    assert p["attributes"]["countryCode"] == ["65"]
    u = build_cbai_keycloak_direct_url("state-123", "github")
    assert "kc_idp_hint=github" in u and "state-123" in u


def test_encryption_and_universal_sinks():
    enc = encrypt_field("cbai-jwt-token", secret=TEST_SECRET)
    assert enc.startswith("enc:v1:")
    assert decrypt_field(enc, secret=TEST_SECRET) == "cbai-jwt-token"

    bundle = CredentialBundle(
        name="cbai-unit",
        access_token="eyJ_cbai_test_access",
        refresh_token="eyJ_cbai_test_refresh",
    )

    buf = io.StringIO()
    r_out = dispatch_credential_sink(bundle, sink="stdout", stream=buf)
    assert r_out["ok"] and json.loads(buf.getvalue())["provider"] == "codebuddy-intl"

    with tempfile.TemporaryDirectory() as tmp:
        jpath = os.path.join(tmp, "cbai.jsonl")
        r_file = dispatch_credential_sink(bundle, sink=f"file:{jpath}")
        assert r_file["ok"] and os.path.isfile(jpath)

        db_path = os.path.join(tmp, "router.sqlite")
        con = sqlite3.connect(db_path)
        con.execute(
            """
            CREATE TABLE provider_connections (
                id TEXT PRIMARY KEY, provider TEXT, auth_type TEXT, name TEXT,
                api_key TEXT, access_token TEXT, refresh_token TEXT,
                is_active INTEGER, test_status TEXT, created_at TEXT, updated_at TEXT
            )
            """
        )
        con.commit()
        con.close()
        r_db = dispatch_credential_sink(bundle, sink=f"sqlite:{db_path}", secret=TEST_SECRET)
        assert r_db["ok"] and r_db["connection_id"]


def test_session_bundle_pairing_plan():
    plan = prepare_cbai_pairing_from_bundle(
        {"username": "dev-zen-200", "email": "zen@beta.example.test", "country": "id", "proxy_url": "http://127.0.0.1:8080"},
        idp_hint="github",
        cli_state="fixed-state-001",
    )
    assert plan["username"] == "dev-zen-200"
    assert plan["state"] == "fixed-state-001"
    assert "kc_idp_hint=github" in plan["keycloak_direct_url"]
    assert plan["area_payload"]["attributes"]["countryCode"] == ["62"]

    # Verify 305-minute age guard blocks newly created GitHub accounts from hitting errCode=12154
    import datetime

    fresh_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    underage = execute_cbai_pairing_from_bundle(
        {"username": "dev-zen-200", "created_at": fresh_iso, "cookies": {"user_session": "s123"}}
    )
    assert not underage["ok"] and underage["error"] == "account_underage_for_cbai"


if __name__ == "__main__":
    test_area_and_keycloak_url()
    test_encryption_and_universal_sinks()
    test_session_bundle_pairing_plan()
    print("[PASS] auto-cb offline suite passed (3/3)")
