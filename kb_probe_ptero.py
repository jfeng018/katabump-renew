#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KataBump Pterodactyl control 探测 v4：username 字段登录（"Your ID"）+ client API"""
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
    try:
        sb.wait_for_element('input[name="username"]', timeout=15)
        print("✅ 找到 username 输入框")
    except Exception:
        print("❌ 无 username 输入框")
        sb.save_screenshot("ctrl_login_noinput.png")
        return False
    # username 可能是 email 或 ID；先用 email
    sid = os.environ.get("KB_USERNAME", EMAIL)
    print("用 username 值（前若干字符）:", sid[:6] + "***")
    sb.type('input[name="username"]', sid)
    time.sleep(1)
    sb.type('input[name="password"]', PASSWORD)
    time.sleep(1)
    # 找提交按钮
    try:
        btns = sb.find_elements('button[type="submit"], button')
        submit = None
        for b in btns:
            t = (b.text or "").strip()
            if t and any(k in t.lower() for k in ["login", "sign in", "continue", "submit", "connexion"]):
                submit = b
                break
        if submit:
            print("点按钮:", submit.text)
            submit.click()
        else:
            print("无 submit 按钮，回车")
            sb.press_keys('input[name="password"]', '\n')
    except Exception as e:
        print("submit err:", str(e)[:100])
        sb.press_keys('input[name="password"]', '\n')
    time.sleep(3)
    for _ in range(12):
        time.sleep(1)
        cur = sb.get_current_url() or ""
        if "/auth/login" not in cur:
            break
    cur = sb.get_current_url()
    print("登录后 URL:", cur)
    # 若还停在 login，读 alert/错误
    if "/auth/login" in cur:
        try:
            src = sb.get_page_source() or ""
            m = re.search(r'(?:alert|error|danger)[^>]*>([^<]{5,300})', src, re.I)
            if m:
                print("错误提示:", m.group(1)[:300])
            else:
                # 找含"incorrect"/"invalid"/"password"的文本
                txt = re.sub(r"<[^>]+>", " ", src)
                txt = re.sub(r"\s+", " ", txt)
                for kw in ["incorrect", "invalid", "wrong", "not find", "no user", "密码", "不存在"]:
                    i = txt.lower().find(kw)
                    if i >= 0:
                        print(f"提示[{kw}]:", txt[max(0,i-80):i+150])
                        break
        except Exception as e:
            print("读错误提示 err:", str(e)[:80])
        sb.save_screenshot("ctrl_login_fail.png")
        return False
    return True

with SB(uc=True, headless=False) as sb:
    ok = login_ctrl(sb)
    print("LOGIN_OK" if ok else "LOGIN_FAIL")
    if not ok:
        sys.exit(0)
    try:
        OUT["cookies"] = [c["name"] for c in sb.driver.get_cookies()]
    except Exception as e:
        OUT["cookies"] = [str(e)[:80]]

    def api(sb, path):
        try:
            return sb.execute_script(
                "var x=new XMLHttpRequest();x.open('GET',arguments[0],false);"
                "x.setRequestHeader('Accept','application/json');x.send();"
                "return x.responseText.slice(0,10000)", CTRL + path)
        except Exception as e:
            return "ERR:" + str(e)[:100]

    OUT["api_client"] = api(sb, "/api/client")
    OUT["api_servers"] = api(sb, "/api/client/servers")
    OUT["api_srv_files"] = api(sb, "/api/client/servers/ff41b51e/files/list")
    OUT["api_srv_startup"] = api(sb, "/api/client/servers/ff41b51e/startup")
    OUT["api_srv_net"] = api(sb, "/api/client/servers/ff41b51e/network/allocation")

    print("JSON_OUT<<")
    print(json.dumps(OUT, ensure_ascii=False, indent=1)[:16000])
    print(">>END")