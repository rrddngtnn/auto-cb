"""cli.py — CLI entry point for auto-cb (CodeBuddy International Device Flow, Keycloak direct broker URL, and universal sink)."""
from __future__ import annotations

import argparse
import json
import sys

from .cbai_auth import (
    build_cbai_area_payload,
    execute_cbai_pairing_from_bundle,
    poll_cbai_token,
    prepare_cbai_pairing_from_bundle,
    request_cbai_device_code,
    run_cbai_5step_onboarding,
)
from .router_store import CredentialBundle, dispatch_credential_sink, load_dotenv_file


def cmd_init(args) -> None:
    res = request_cbai_device_code()
    print(json.dumps(res, indent=2))


def cmd_poll(args) -> None:
    res = poll_cbai_token(args.state)
    if res.get("ok") and args.sink:
        bundle = CredentialBundle(
            name=args.name,
            access_token=res["access_token"],
            refresh_token=res.get("refresh_token", ""),
            expires_in=res.get("expires_in", 86400),
        )
        res["sink_result"] = dispatch_credential_sink(bundle, sink=args.sink)
    print(json.dumps(res, indent=2))


def cmd_area_payload(args) -> None:
    print(json.dumps(build_cbai_area_payload(args.country), indent=2))


def cmd_emit_sink(args) -> None:
    bundle = CredentialBundle(
        name=args.name,
        access_token=args.access_token,
        refresh_token=args.refresh_token,
    )
    res = dispatch_credential_sink(bundle, sink=args.sink, stream=sys.stdout)
    if args.sink != "stdout":
        print(json.dumps(res, indent=2))


def main(argv: list[str] | None = None) -> int:
    load_dotenv_file()
    p = argparse.ArgumentParser(prog="auto-cb")
    sub = p.add_subparsers(dest="cmd", required=True)

    s_in = sub.add_parser("init", help="Initiate CodeBuddy International CLI state & Keycloak broker URLs")
    s_in.set_defaults(func=cmd_init)

    s_pl = sub.add_parser("poll", help="Poll CodeBuddy International CLI state for access/refresh tokens")
    s_pl.add_argument("--state", required=True)
    s_pl.add_argument("--name", default="cbai-account")
    s_pl.add_argument("--sink", default="", help="Optional sink: stdout | file:path.jsonl | http://host:port | sqlite[:path]")
    s_pl.set_defaults(func=cmd_poll)

    s_ar = sub.add_parser("area-payload", help="Generate APAC region completion payload for /console/login/account")
    s_ar.add_argument("--country", default="sg")
    s_ar.set_defaults(func=cmd_area_payload)

    s_it = sub.add_parser("sink", help="Route a CBAI token to stdout, JSONL file, HTTP gateway, or SQLite (as apikey)")
    s_it.add_argument("--name", default="cbai-account")
    s_it.add_argument("--access-token", required=True)
    s_it.add_argument("--refresh-token", default="")
    s_it.add_argument("--sink", default="stdout", help="stdout | file:tokens.jsonl | http://127.0.0.1:20128 | sqlite[:db_path]")
    s_it.set_defaults(func=cmd_emit_sink)

    s_pr = sub.add_parser("pair", help="Consume SessionBundle JSONL from --stdin or --session-file and emit CBAI pairing plans / tokens")
    s_pr.add_argument("--stdin", action="store_true", help="Read SessionBundle JSONL lines from stdin")
    s_pr.add_argument("--session-file", default="", help="Path to SessionBundle JSON/JSONL file")
    s_pr.add_argument("--idp", choices=("github", "google"), default="github")
    s_pr.add_argument("--execute", action="store_true", help="Execute Keycloak GitHub OAuth + 5-step Free Trial onboarding + token poll")
    s_pr.add_argument("--force-underage", action="store_true", help="Bypass 305-minute (5h05m) GitHub account age guard")
    s_pr.add_argument("--state", default="", help="Optional existing CLI state to poll or bind")
    s_pr.add_argument("--poll-now", action="store_true", help="Poll token for --state and route directly to --sink")
    s_pr.add_argument("--sink", default="stdout", help="Target sink when polling: stdout | file:path | http://... | sqlite[:path]")
    s_pr.set_defaults(func=cmd_pair)

    s_dr = sub.add_parser("doctor", help="Inspect declared BYOP contracts (input stream, APAC region whitelist, and output sinks)")
    s_dr.set_defaults(func=cmd_doctor)

    args = p.parse_args(argv)
    args.func(args)
    return 0


def cmd_doctor(args) -> None:
    import os

    print(
        json.dumps(
            {
                "ok": True,
                "declared_contracts": {
                    "input_contract": {
                        "format": "SessionBundle JSONL (v1.0) via --stdin or --session-file",
                        "standalone_modes": ["init", "poll", "area-payload"],
                    },
                    "apac_region_whitelist": ["sg", "id", "jp", "th", "my", "ph", "hk"],
                    "sink_driver": {
                        "supported": ["stdout", "file:<path.jsonl>", "http://<gateway>", "sqlite[:<db_path>]"],
                        "router_url": os.environ.get("ROUTER_URL", "http://127.0.0.1:20128"),
                        "encryption_key_configured": bool(os.environ.get("STORAGE_ENCRYPTION_KEY")),
                    },
                },
            },
            indent=2,
        )
    )


def _read_session_bundles(args) -> list[dict]:
    raw = ""
    if args.stdin:
        raw = sys.stdin.read().strip()
    elif args.session_file:
        with open(args.session_file, encoding="utf-8") as f:
            raw = f.read().strip()
    if not raw:
        return []
    if raw.startswith("["):
        return json.loads(raw)
    return [json.loads(ln) for ln in raw.splitlines() if ln.strip()]


def cmd_pair(args) -> None:
    bundles = _read_session_bundles(args)
    for b in bundles:
        if args.execute:
            res = execute_cbai_pairing_from_bundle(
                b, idp_hint=args.idp, force_underage=args.force_underage
            )
            if res.get("ok"):
                cred = CredentialBundle(
                    name=res["username"],
                    email=res.get("email", ""),
                    access_token=res["access_token"],
                    refresh_token=res.get("refresh_token", ""),
                    expires_in=res.get("expires_in", 86400),
                )
                sink_res = dispatch_credential_sink(cred, sink=args.sink, stream=sys.stdout)
                if args.sink != "stdout":
                    sys.stdout.write(
                        json.dumps({"ok": True, "username": res["username"], "onboarding": res.get("onboarding"), "sink_result": sink_res}) + "\n"
                    )
                    sys.stdout.flush()
            else:
                sys.stdout.write(json.dumps(res) + "\n")
                sys.stdout.flush()
            continue
        proxy_url = b.get("proxy_url") or ""
        proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
        plan = prepare_cbai_pairing_from_bundle(b, idp_hint=args.idp, cli_state=args.state or None)
        if args.poll_now:
            res = poll_cbai_token(plan["state"], proxies=proxies)
            if res.get("ok"):
                cred = CredentialBundle(
                    name=b.get("username") or b.get("email") or "cbai-account",
                    email=b.get("email", ""),
                    access_token=res["access_token"],
                    refresh_token=res.get("refresh_token", ""),
                    expires_in=res.get("expires_in", 86400),
                )
                dispatch_credential_sink(cred, sink=args.sink, stream=sys.stdout)
                continue
            plan["poll_result"] = res
        sys.stdout.write(json.dumps(plan) + "\n")
        sys.stdout.flush()


if __name__ == "__main__":
    raise SystemExit(main())
