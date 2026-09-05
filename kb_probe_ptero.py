#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KataBump Pterodactyl control 探测 v3：标准 user/password 字段登录 + client API"""
import sys, time, json, os, re
sys.path.insert(0, '.')
from seleniumbase import SB

CTRL = os.environ.get("KB_CTRL", "https://control.katabump.com")
EMAIL = os.environ.get("KATABUMP_EMAIL", "")
PASSWORD = os.environ.get("KATABUMP_PASSWORD", "")

OUT = {}

def login_ctrl(sb):
    print("🌐 打开 control 登录页")
    sb.open(CTRL + "/auth/login")
    time.sleep(8)
    print("URL:", sb.get_current_url())
    src = sb.get_page_source() or ""
    print("页面含 user input:", 'name="user"' in src.lower() or 'name="email"' in src.lower() or 'type="email"' in src.lower())
    # 标准 Pterodactyl 登录：input name=user + input name=password
    found = False
    for sel in ['input[name="user"]', 'input[name="email"]', 'input[type="email"]']:
        try:
            sb.wait_for_element(sel, timeout=10)
            print("使用选择器:", sel)
            found = True
            break
        except Exception:
            continue
    if not found:
        print("❌ 未找到 user 输入框，dump body")
        html = (sb.get_page_source() or "")
        m = re.search(r"<form.*?</form>", html[:300000], re.S | re.I)
        print("FORM<<", (m.group(0)[:2000] if m else "NO_FORM"))
        sb.save_screenshot("ctrl_login_noinput.png")
        return False
    # 填表（Pterodactyl user=email）
    sb.type(sel, EMAIL)
    time.sleep(1)
    try:
        sb.type('input[name="password"], input[type="password"]', PASSWORD)
    except Exception as e:
        print("pwd fill err:", str(e)[:80])
    time.sleep(1)
    # 提交：找 submit button 或回车
    try:
        sb.press_keys('input[name="password"], input[type="password"]', '\n')
    except Exception:
        try:
            sb.click('button[type="submit"], button:has-text("Login"), button:has-text("Sign in")')
        except Exception as e:
            print("submit err:", str(e)[:100])
    for _ in range(12):
        time.sleep(1)
        cur = sb.get_current_url() or ""
        if "/auth/login" not in cur:
            break
    cur = sb.get_current_url()
    print("登录后 URL:", cur)
    OUT["after_login_url"] = cur
    return "/auth/login" not in cur

with SB(uc=True, headless=False) as sb:
    ok = login_ctrl(sb)
    print("LOGIN_OK" if ok else "LOGIN_FAIL")
    if not ok:
        try:
            sb.save_screenshot("ctrl_login_fail.png")
        except Exception:
            pass
        sys.exit(1)
    try:
        OUT["cookies"] = [c["name"] for c in sb.driver.get_cookies()]
    except Exception as e:
        OUT["cookies"] = [str(e)[:80]]

    def api(sb, path):
        try:
            return sb.execute_script(
                "var x=new XMLHttpRequest();x.open('GET',arguments[0],false);"
                "x.setRequestHeader('Accept','application/json');x.send();"
                "return x.responseText.slice(0,8000)", CTRL + path)
        except Exception as e:
            return "ERR:" + str(e)[:100]

    OUT["api_client"] = api(sb, "/api/client")
    OUT["api_servers"] = api(sb, "/api/client/servers")
    # 用 /api/client/servers 里解析的完整 uuid 前缀试
    OUT["api_srv_short"] = api(sb, "/api/client/servers/ff41b51e")
    OUT["api_srv_files"] = api(sb, "/api/client/servers/ff41b51e/files/list")
    OUT["api_srv_startup"] = api(sb, "/api/client/servers/ff41b51e/startup")
    OUT["api_srv_net"] = api(sb, "/api/client/servers/ff41b51e/network/allocation")
    OUT["api_srv_res"] = api(sb, "/api/client/servers/ff41b51e/resources")

    print("JSON_OUT<<")
    print(json.dumps(OUT, ensure_ascii=False, indent=1)[:15000])
    print(">>END")