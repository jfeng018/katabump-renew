#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KataBump Pterodactyl control 探测：登录 control 面板 + 测 client API（只读）"""
import sys, time, json, os, re
sys.path.insert(0, '.')
from seleniumbase import SB
import app as upapp

CTRL = os.environ.get("KB_CTRL", "https://control.katabump.com")
EMAIL = os.environ.get("KATABUMP_EMAIL", "")
PASSWORD = os.environ.get("KATABUMP_PASSWORD", "")

OUT = {}

def login_ctrl(sb):
    print("🌐 打开 control 登录页")
    sb.open(CTRL + "/auth/login")
    time.sleep(6)
    print("URL:", sb.get_current_url())
    src = sb.get_page_source() or ""
    print("有 email input:", 'name="email"' in src.lower() or 'type="email"' in src.lower())
    print("有 turnstile:", 'turnstile' in src.lower())
    try:
        sb.wait_for_element('input[name="email"], input[type="email"]', timeout=15)
    except Exception:
        print("❌ control 登录页无 email input")
        sb.save_screenshot("ctrl_login_noinput.png")
        return False
    upapp.js_fill_input(sb, 'input[name="email"], input[type="email"]', EMAIL)
    time.sleep(1)
    upapp.js_fill_input(sb, 'input[name="password"], input[type="password"]', PASSWORD)
    time.sleep(1)
    # 如果出现 Turnstile 也处理
    for i in range(30):
        try:
            has_ts = sb.execute_script("return !!document.querySelector('iframe[src*=\"challenges.cloudflare.com\"]') || !!document.querySelector('.cf-turnstile')")
        except Exception:
            has_ts = False
        if has_ts:
            print(f"Turnstile 出现（{i+1}s），尝试点击")
            try:
                sb.uc_gui_click_captcha()
            except Exception as e:
                print("captcha err:", str(e)[:100])
            break
        time.sleep(1)
    print("提交表单")
    try:
        sb.press_keys('input[name="password"], input[type="password"]', '\n')
    except Exception:
        try:
            sb.execute_script('document.querySelector("form").submit()')
        except Exception as e:
            print("submit err:", str(e)[:100])
    for _ in range(12):
        time.sleep(1)
        cur = sb.get_current_url() or ""
        if "/auth/login" not in cur:
            break
    cur = sb.get_current_url()
    print("登录后 URL:", cur)
    return "/auth/login" not in cur

with SB(uc=True, headless=False) as sb:
    t0 = time.time()
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

    # 关键：Pterodactyl client API（会话 cookie 即可）
    def api(sb, path):
        try:
            return sb.execute_script(
                "var x=new XMLHttpRequest();x.open('GET',arguments[0],false);"
                "x.setRequestHeader('Accept','application/json');x.send();"
                "return x.responseText.slice(0,6000)", CTRL + path)
        except Exception as e:
            return "ERR:" + str(e)[:100]

    OUT["api_client"] = api(sb, "/api/client")
    OUT["api_servers"] = api(sb, "/api/client/servers")
    # 服务器 uuid 前缀 ff41b51e -> 完整 uuid? 先试短 uuid
    OUT["api_srv_short"] = api(sb, "/api/client/servers/ff41b51e")
    OUT["api_srv_files"] = api(sb, "/api/client/servers/ff41b51e/files/list")
    OUT["api_srv_startup"] = api(sb, "/api/client/servers/ff41b51e/startup")

    print("JSON_OUT<<")
    print(json.dumps(OUT, ensure_ascii=False, indent=1)[:14000])
    print(">>END")