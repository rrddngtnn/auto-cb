"""cbai_auth.py — CodeBuddy International (codebuddy.ai) Device Flow, Keycloak direct broker URL, and 5-step Free Trial onboarding."""
from __future__ import annotations

import time
from urllib.parse import quote
import requests

CBAI_BASE = "https://www.codebuddy.ai"
CBAI_STATE_URL = f"{CBAI_BASE}/v2/plugin/auth/state?platform=CLI"
CBAI_TOKEN_URL = f"{CBAI_BASE}/v2/plugin/auth/token"
CBAI_UA = "CLI/2.108.1 CodeBuddy/2.108.1"
CBAI_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "User-Agent": CBAI_UA,
    "X-Requested-With": "XMLHttpRequest",
    "X-Domain": "codebuddy.ai",
    "X-No-Authorization": "true",
    "X-No-User-Id": "true",
    "X-Product": "SaaS",
}

# Whitelisted APAC regions from index-DkMdbZHy.js (ae/se lists)
CBAI_APAC_AREA_MAP = {
    "sg": {"Code": "65", "EnName": "Singapore", "IOS2": "SG"},
    "id": {"Code": "62", "EnName": "Indonesia", "IOS2": "ID"},
    "jp": {"Code": "81", "EnName": "Japan", "IOS2": "JP"},
    "th": {"Code": "66", "EnName": "Thailand", "IOS2": "TH"},
    "my": {"Code": "60", "EnName": "Malaysia", "IOS2": "MY"},
    "ph": {"Code": "63", "EnName": "Philippines", "IOS2": "PH"},
    "hk": {"Code": "852", "EnName": "Hong Kong, China", "IOS2": "HK"},
}


def build_cbai_area_payload(country_code: str = "sg") -> dict:
    info = CBAI_APAC_AREA_MAP.get(country_code.lower(), CBAI_APAC_AREA_MAP["sg"])
    return {
        "attributes": {
            "countryCode": [info["Code"]],
            "countryFullName": [info["EnName"]],
            "countryName": [info["IOS2"]],
        }
    }


def build_cbai_keycloak_direct_url(cli_state: str, idp_hint: str = "github") -> str:
    """Build direct Keycloak OAuth URL with kc_idp_hint to skip loading the 1.4MB /login SPA."""
    redirect_target = f"{CBAI_BASE}/login?platform=CLI&state={cli_state}"
    return (
        f"{CBAI_BASE}/auth/realms/copilot/protocol/openid-connect/auth"
        f"?client_id=console&response_type=code&redirect_uri={quote(redirect_target, safe='')}"
        f"&v=2210&product=codebuddy&kc_idp_hint={idp_hint}"
    )


def request_cbai_device_code(proxies: dict | None = None, timeout: int = 15) -> dict:
    r = requests.post(
        CBAI_STATE_URL,
        headers=CBAI_HEADERS,
        json={"platform": "CLI"},
        proxies=proxies,
        timeout=timeout,
    )
    r.raise_for_status()
    payload = r.json()
    if payload.get("code") != 0 or not payload.get("data"):
        raise RuntimeError(f"Unexpected CBAI state response: {payload}")
    data = payload["data"]
    state = data["state"]
    return {
        "provider": "codebuddy-intl",
        "state": state,
        "auth_url": data["authUrl"],
        "keycloak_github_url": build_cbai_keycloak_direct_url(state, "github"),
        "keycloak_google_url": build_cbai_keycloak_direct_url(state, "google"),
        "expires_in": 300,
        "interval": 5,
    }


def poll_cbai_token(state: str, proxies: dict | None = None, timeout: int = 15) -> dict:
    r = requests.get(
        CBAI_TOKEN_URL,
        params={"state": state},
        headers=CBAI_HEADERS,
        proxies=proxies,
        timeout=timeout,
    )
    r.raise_for_status()
    payload = r.json()
    code = payload.get("code")
    if code == 11217:
        return {"ok": False, "pending": True}
    data = payload.get("data") or {}
    if code == 0 and data.get("accessToken"):
        return {
            "ok": True,
            "pending": False,
            "access_token": data["accessToken"],
            "refresh_token": data.get("refreshToken") or "",
            "expires_in": data.get("expiresIn") or 86400,
        }
    return {"ok": False, "pending": False, "raw": payload}


def run_cbai_5step_onboarding(
    session: requests.Session,
    uid: str,
    cli_state: str,
    country_code: str = "sg",
    device_token: str = "",
) -> dict:
    """Execute the 5-step CodeBuddy International onboarding & Free Trial activation sequence."""
    hdr = {"X-Requested-With": "XMLHttpRequest", "X-Domain": "www.codebuddy.ai"}
    if device_token:
        hdr["X-Device-Token"] = device_token

    # Step 1: Complete APAC region attributes -> areaInfoComplete = true
    r1 = session.post(
        f"{CBAI_BASE}/console/login/account",
        json=build_cbai_area_payload(country_code),
        headers=hdr,
        timeout=15,
    )

    # Step 2: Overseas user register + 1500ms settle delay
    r2 = session.get(
        f"{CBAI_BASE}/auth/realms/copilot/overseas/user/register",
        params={"userId": uid},
        headers=hdr,
        timeout=15,
    )
    time.sleep(1.5)

    # Step 3: Auto-open billing account
    r3 = session.post(
        f"{CBAI_BASE}/billing/pay/get-billing-account-inner",
        json={"IsAutoOpenAccount": 1},
        headers=hdr,
        timeout=15,
    )

    # Step 4: Apply IDE Free Trial (TCACA_code_001_PqouKr6QWV)
    r4 = session.post(
        f"{CBAI_BASE}/billing/ide/trial",
        json={},
        headers=hdr,
        timeout=15,
    )

    # Step 5: Bind CLI state
    r5a = session.post(
        f"{CBAI_BASE}/console/login/enterprise",
        params={"state": cli_state},
        headers=hdr,
        timeout=15,
    )
    r5b = session.get(f"{CBAI_BASE}/console/validate/refresh-token", headers=hdr, timeout=15)
    r5c = session.get(
        f"{CBAI_BASE}/console/auth/login",
        params={"platform": "CLI", "state": cli_state, "domain": "www.codebuddy.ai"},
        headers=hdr,
        timeout=15,
    )

    return {
        "step1_area": r1.status_code,
        "step2_overseas": r2.status_code,
        "step3_billing": r3.status_code,
        "step4_trial": r4.status_code,
        "step5_enterprise": r5a.status_code,
        "step5_validate": r5b.status_code,
        "step5_cli_bind": r5c.status_code,
    }


def prepare_cbai_pairing_from_bundle(
    session_bundle: dict,
    idp_hint: str = "github",
    cli_state: str | None = None,
) -> dict:
    """Consume a standardized SessionBundle dict and prepare a CBAI pairing + 5-step onboarding plan."""
    proxy_url = session_bundle.get("proxy_url") or ""
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    country = (session_bundle.get("country") or "sg").lower()
    if cli_state:
        state = cli_state
        kc_url = build_cbai_keycloak_direct_url(state, idp_hint=idp_hint)
    else:
        dc = request_cbai_device_code(proxies=proxies)
        state = dc["state"]
        kc_url = dc["keycloak_github_url"] if idp_hint == "github" else dc["keycloak_google_url"]
    return {
        "username": session_bundle.get("username") or session_bundle.get("email") or "cbai-user",
        "email": session_bundle.get("email", ""),
        "country": country,
        "proxy_url": proxy_url,
        "storage_state_path": session_bundle.get("storage_state_path", ""),
        "state": state,
        "keycloak_direct_url": kc_url,
        "area_payload": build_cbai_area_payload(country),
    }


def _bundle_age_minutes(session_bundle: dict) -> float | None:
    import datetime

    ts = session_bundle.get("verified_at") or session_bundle.get("created_at")
    if not ts:
        return None
    try:
        dt = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        now = datetime.datetime.now(datetime.timezone.utc)
        return round((now - dt).total_seconds() / 60.0, 2)
    except Exception:
        return None


def _load_bundle_cookies(session_bundle: dict) -> dict[str, str]:
    import json
    from pathlib import Path

    cookies = dict(session_bundle.get("cookies") or {})
    st_path = session_bundle.get("storage_state_path") or ""
    if not cookies and st_path and Path(st_path).is_file():
        try:
            raw = json.loads(Path(st_path).read_text(encoding="utf-8"))
            for c in raw.get("cookies", []):
                if c.get("name") and c.get("value"):
                    cookies[c["name"]] = c["value"]
        except Exception:
            pass
    return cookies


def _extract_github_oauth_form(html: str) -> dict[str, str] | None:
    import re

    m_form = re.search(
        r'<form[^>]+action="(/login/oauth/authorize)"[^>]*>(.*?)</form>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not m_form:
        return None
    body = m_form.group(2)
    fields: dict[str, str] = {}
    for m_in in re.finditer(r"<input[^>]+>", body, re.IGNORECASE):
        tag = m_in.group(0)
        m_name = re.search(r'name="([^"]+)"', tag)
        m_val = re.search(r'value="([^"]*)"', tag)
        if m_name:
            fields[m_name.group(1)] = m_val.group(1) if m_val else ""
    fields["authorize"] = "1"
    return fields


def execute_cbai_pairing_from_bundle(
    session_bundle: dict,
    idp_hint: str = "github",
    min_age_minutes: float = 305.0,
    force_underage: bool = False,
    http_session=None,
    timeout: int = 20,
) -> dict:
    """Execute end-to-end CBAI Keycloak GitHub OAuth + 5-step Free Trial onboarding + CLI token poll."""
    age_min = _bundle_age_minutes(session_bundle)
    if not force_underage and age_min is not None and age_min < min_age_minutes:
        return {
            "ok": False,
            "error": "account_underage_for_cbai",
            "age_minutes": age_min,
            "required_minutes": min_age_minutes,
            "remaining_minutes": round(min_age_minutes - age_min, 1),
            "hint": "Wait until account age >= 305 minutes to avoid CBAI errCode=12154, or pass --force-underage",
        }

    gh_cookies = _load_bundle_cookies(session_bundle)
    if not gh_cookies.get("user_session"):
        return {
            "ok": False,
            "error": "missing_github_session_cookies",
            "hint": "Populate SessionBundle.cookies['user_session'] or storage_state_path before --execute",
            "plan": prepare_cbai_pairing_from_bundle(session_bundle, idp_hint=idp_hint),
        }

    proxy_url = session_bundle.get("proxy_url") or ""
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    country = (session_bundle.get("country") or "sg").lower()

    s = http_session or requests.Session()
    if proxies and hasattr(s, "proxies"):
        s.proxies.update(proxies)
    for k, v in gh_cookies.items():
        s.cookies.set(k, v, domain="github.com")

    dc = request_cbai_device_code(proxies=proxies, timeout=timeout)
    cli_state = dc["state"]
    kc_url = dc["keycloak_github_url"]

    r1 = s.get(kc_url, allow_redirects=False, timeout=timeout)
    gh_auth_url = r1.headers.get("location", "")
    if not gh_auth_url:
        return {"ok": False, "error": f"expected_302_from_keycloak_got_{r1.status_code}", "state": cli_state}

    r2 = s.get(gh_auth_url, allow_redirects=False, timeout=timeout)
    broker_loc = r2.headers.get("location", "")
    if r2.status_code == 200:
        form_data = _extract_github_oauth_form(r2.text)
        if not form_data:
            return {"ok": False, "error": "github_oauth_form_not_found_or_login_required", "state": cli_state}
        r2_post = s.post(
            "https://github.com/login/oauth/authorize",
            data=form_data,
            headers={"Referer": gh_auth_url, "Origin": "https://github.com"},
            allow_redirects=False,
            timeout=timeout,
        )
        broker_loc = r2_post.headers.get("location", "")

    if not broker_loc:
        return {"ok": False, "error": "missing_keycloak_broker_redirect", "state": cli_state}

    # Follow Keycloak broker callback back to www.codebuddy.ai
    r3 = s.get(broker_loc, allow_redirects=True, timeout=timeout)
    uid = session_bundle.get("username") or session_bundle.get("email") or "cbai-user"
    onboarding = run_cbai_5step_onboarding(s, uid=str(uid), cli_state=cli_state, country_code=country)
    tok = poll_cbai_token(cli_state, proxies=proxies, timeout=timeout)
    return {
        **tok,
        "username": session_bundle.get("username") or session_bundle.get("email") or "cbai-user",
        "email": session_bundle.get("email", ""),
        "state": cli_state,
        "final_url": getattr(r3, "url", ""),
        "onboarding": onboarding,
    }
