#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KataBump v8：control 登录（username=账号ID）+ client API 探测"""
import sys, time, json, os, re
sys.path.insert(0, '.')
from seleniumbase import SB

CTRL = os.environ.get("KB_CTRL", "https://control.katabump.com")
KB_USERNAME = os.environ.get("KB_USERNAME", "")
KB_PASSWORD = os.environ.get("KB_PASSWORD", "")

OUT = {}

def login_ctrl(sb):
    print("🌐 打开 control 登录页")
    sb.open(CTRL + "/auth/login")
    time.sleep(8)
    print("URL:", sb.get_current_url())
    try:
        sb.wait_for_element('input[name="username"]', timeout=15)
        print("✅ 找到 username 输入框")
    except Exception:
        print("❌ 无 username")
        sb.save_screenshot("ctrl_login_noinput.png")
        return False
    print("填 username:", KB_USERNAME)
    sb.type('input[name="username"]', KB_USERNAME)
    time.sleep(1)
    sb.type('input[name="password"]', KB_PASSWORD)
    time.sleep(1)
    # 如果有 turnstile 处理
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
        t = (b.text or "").strip().lower()
        if t in ("login", "sign in", "continue", "connexion"):
            btn = b
            break
    if btn:
        print("点按钮:", btn.text)
        btn.click()
    else:
        print("无 login 按钮，回车")
        sb.press_keys('input[name="password"]', '\n')
    time.sleep(3)
    for _ in range(12):
        time.sleep(1)
        if "/auth/login" not in sb.get_current_url():
            break
    cur = sb.get_current_url()
    print("登录后 URL:", cur)
    if "/auth/login" in cur:
        try:
            src = sb.get_page_source() or ""
            txt = re.sub(r"<[^>]+>", " ", src)
            txt = re.sub(r"\s+", " ", txt)
            for kw in ["incorrect", "invalid", "wrong", "no user", "not found", "password", "找不到", "错误"]:
                i = txt.lower().find(kw)
                if i >= 0:
                    print(f"提示[{kw}]:", txt[max(0,i-100):i+200])
                    break
        except Exception as e:
            print("读提示 err:", str(e)[:80])
        sb.save_screenshot("ctrl_login_fail.png")
        return False
    return True

with SB(uc=True, headless=False) as sb:
    ok = login_ctrl(sb)
    print("LOGIN_OK" if ok else "LOGIN_FAIL")
    if not ok:
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
                "return x.responseText.slice(0,12000)", CTRL + path)
        except Exception as e:
            return "ERR:" + str(e)[:100]

    OUT["api_client"] = api(sb, "/api/client")
    OUT["api_servers"] = api(sb, "/api/client/servers")
    OUT["api_srv_files"] = api(sb, "/api/client/servers/ff41b51e/files/list")
    OUT["api_srv_startup"] = api(sb, "/api/client/servers/ff41b51e/startup")
    OUT["api_srv_net"] = api(sb, "/api/client/servers/ff41b51e/network/allocation")
    OUT["api_srv_res"] = api(sb, "/api/client/servers/ff41b51e/resources")

    print("JSON_OUT<<")
    print(json.dumps(OUT, ensure_ascii=False, indent=1)[:18000])
    print(">>END")