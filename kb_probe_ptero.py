#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KataBump v5：dashboard /profil 拿账号 ID/username → 候选值试 control 登录"""
import sys, time, json, os, re
sys.path.insert(0, '.')
from seleniumbase import SB
import app as upapp

BASE = upapp.BASE_URL
CTRL = os.environ.get("KB_CTRL", "https://control.katabump.com")
EMAIL = os.environ.get("KATABUMP_EMAIL", "")
PASSWORD = os.environ.get("KATABUMP_PASSWORD", "")

OUT = {}

def login_dash(sb):
    print("🌐 dashboard 登录")
    sb.uc_open_with_reconnect(BASE + "/auth/login", reconnect_time=8)
    for i in range(40):
        src = sb.get_page_source() or ""
        if 'name="email"' in src.lower():
            break
        time.sleep(1)
    try:
        sb.wait_for_element('input[type="email"], input[name="email"]', timeout=20)
    except Exception:
        print("❌ dash 无 email")
        return False
    upapp.js_fill_input(sb, 'input[type="email"], input[name="email"]', EMAIL)
    time.sleep(1)
    upapp.js_fill_input(sb, 'input[type="password"], input[name="password"]', PASSWORD)
    time.sleep(1)
    for i in range(60):
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
    try:
        sb.press_keys('input[type="password"], input[name="password"]', '\n')
    except Exception:
        pass
    for _ in range(15):
        time.sleep(1)
        cur = sb.get_current_url() or ""
        if "/dashboard" in cur:
            break
    print("dash URL:", sb.get_current_url())
    return "/dashboard" in sb.get_current_url()

with SB(uc=True, headless=False) as sb:
    if not login_dash(sb):
        print("DASH_LOGIN_FAIL")
        sys.exit(0)
    # 读 profil 页面找 ID/username
    for path in ["/profil", "/profil/security", "/dashboard"]:
        try:
            sb.open(BASE + path)
            time.sleep(4)
            src = sb.get_page_source() or ""
            text = re.sub(r"<[^>]+>", " ", src)
            text = re.sub(r"\s+", " ", text)
            OUT["page_"+path.replace("/","_")+"_text"] = text[:1200]
            # 找数字 ID / 用户名 hint
            nums = re.findall(r"\b\d{4,9}\b", text)
            OUT["page_"+path.replace("/","_")+"_nums"] = list(dict.fromkeys(nums))[:20]
            m = re.search(r"(?:BuyerID|username|Your ID|User ID|ID)[:\s]*([A-Za-z0-9@._-]{2,40})", text, re.I)
            if m:
                OUT["page_"+path.replace("/","_")+"_idhint"] = m.group(1)
        except Exception as e:
            OUT["err_"+path] = str(e)[:120]
    # 尝试 control 登录候选
    candidates = []
    if EMAIL: candidates.append(("email", EMAIL))
    for v in OUT.values():
        if isinstance(v, dict) and "idhint" in v:
            candidates.append(("hint", v["idhint"]))
    print("候选 username:", json.dumps([c[1][:6]+"***" for c in candidates], ensure_ascii=False))
    for label, sid in candidates:
        if not sid:
            continue
        try:
            print(f"--- 尝试 control 登录 with {label}: {sid[:6]}***")
            sb.open(CTRL + "/auth/login")
            time.sleep(6)
            try:
                sb.wait_for_element('input[name="username"]', timeout=12)
            except Exception:
                print("无 username 框")
                continue
            sb.type('input[name="username"]', sid)
            sb.type('input[name="password"]', PASSWORD)
            time.sleep(1)
            btn = None
            for b in sb.find_elements('button'):
                if (b.text or "").strip().lower() in ("login", "sign in", "continue"):
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
            print(f"  结果 URL: {cur}")
            if "/auth/login" not in cur:
                OUT["ctrl_login_with"] = label + ":" + ("***" + sid[-4:] if sid[-4:].isdigit() else sid[:3]+"***")
                try:
                    OUT["cookies"] = [c["name"] for c in sb.driver.get_cookies()]
                except Exception as e:
                    OUT["cookies"] = [str(e)[:80]]
                def api(p):
                    try:
                        return sb.execute_script(
                            "var x=new XMLHttpRequest();x.open('GET',arguments[0],false);"
                            "x.setRequestHeader('Accept','application/json');x.send();"
                            "return x.responseText.slice(0,9000)", CTRL + p)
                    except Exception as e:
                        return "ERR:" + str(e)[:80]
                OUT["api_servers"] = api("/api/client/servers")
                OUT["api_files"] = api("/api/client/servers/ff41b51e/files/list")
                OUT["api_startup"] = api("/api/client/servers/ff41b51e/startup")
                OUT["api_net"] = api("/api/client/servers/ff41b51e/network/allocation")
                break
        except Exception as e:
            print(f"  {label} err: {str(e)[:120]}")

    print("JSON_OUT<<")
    print(json.dumps(OUT, ensure_ascii=False, indent=1)[:16000])
    print(">>END")