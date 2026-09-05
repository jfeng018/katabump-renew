#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KataBump v9：control 登录成功 → CDP 导 cookie → requests 打 Pterodactyl client API"""
import sys, time, json, os, re
sys.path.insert(0, '.')
from seleniumbase import SB
import requests

CTRL = os.environ.get("KB_CTRL", "https://control.katabump.com")
KB_USERNAME = os.environ.get("KB_USERNAME", "")
KB_PASSWORD = os.environ.get("KB_PASSWORD", "")
UUID = os.environ.get("KB_SRV_UUID", "ff41b51e")

OUT = {}

def login_ctrl(sb):
    print("🌐 打开 control 登录页")
    sb.open(CTRL + "/auth/login")
    time.sleep(8)
    try:
        sb.wait_for_element('input[name="username"]', timeout=15)
        print("✅ 找到 username 输入框")
    except Exception:
        print("❌ 无 username")
        sb.save_screenshot("ctrl_login_noinput.png")
        return False
    sb.type('input[name="username"]', KB_USERNAME)
    time.sleep(1)
    sb.type('input[name="password"]', KB_PASSWORD)
    time.sleep(1)
    for i in range(30):
        try:
            has_ts = sb.execute_script("return !!document.querySelector('iframe[src*=\"challenges.cloudflare.com\"]') || !!document.querySelector('.cf-turnstile')")
        except Exception:
            has_ts = False
        if has_ts:
            print(f"Turnstile（{i+1}s）")
            try:
                sb.uc_gui_click_captcha()
            except Exception as e:
                print("captcha:", str(e)[:80])
            break
        time.sleep(1)
    btn = None
    for b in sb.find_elements('button'):
        if (b.text or "").strip().lower() in ("login", "sign in", "continue", "connexion"):
            btn = b
            break
    if btn:
        btn.click()
    else:
        sb.press_keys('input[name="password"]', '\n')
    time.sleep(3)
    for _ in range(12):
        time.sleep(1)
        if "/auth/login" not in sb.get_current_url():
            break
    cur = sb.get_current_url()
    print("登录后 URL:", cur)
    return "/auth/login" not in cur

def get_cookies(sb):
    """优先 CDP，其次 driver.get_cookies"""
    try:
        r = sb.driver.execute_cdp_cmd('Network.getAllCookies', {})
        cks = r.get("cookies", [])
        OUT["cookie_names"] = [c["name"] for c in cks]
        return {c["name"]: c["value"] for c in cks}
    except Exception as e1:
        print("CDP err:", str(e1)[:120])
        try:
            cks = sb.driver.get_cookies()
            OUT["cookie_names"] = [c["name"] for c in cks]
            return {c["name"]: c["value"] for c in cks}
        except Exception as e2:
            print("get_cookies err:", str(e2)[:120])
            return {}

with SB(uc=True, headless=False) as sb:
    ok = login_ctrl(sb)
    print("LOGIN_OK" if ok else "LOGIN_FAIL")
    if not ok:
        sys.exit(1)
    cookies = get_cookies(sb)
    OUT["has_session_cookie"] = any("sess" in n.lower() or "pterodactyl" in n.lower() for n in OUT.get("cookie_names", []))
    if not cookies:
        print("NO_COOKIES")
        sys.exit(1)

    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": CTRL + "/",
    })
    s.cookies.update(cookies)

    def api(path):
        try:
            r = s.get(CTRL + path, timeout=30)
            return {"status": r.status_code, "body": (r.text or "")[:15000]}
        except Exception as e:
            return {"err": str(e)[:150]}

    OUT["api_client"] = api("/api/client")
    OUT["api_servers"] = api("/api/client/servers")
    OUT["api_srv_files"] = api(f"/api/client/servers/{UUID}/files/list")
    OUT["api_srv_startup"] = api(f"/api/client/servers/{UUID}/startup")
    OUT["api_srv_net"] = api(f"/api/client/servers/{UUID}/network/allocation")
    OUT["api_srv_res"] = api(f"/api/client/servers/{UUID}/resources")
    OUT["api_acct"] = api("/api/client/account")

    print("JSON_OUT<<")
    print(json.dumps(OUT, ensure_ascii=False, indent=1)[:22000])
    print(">>END")