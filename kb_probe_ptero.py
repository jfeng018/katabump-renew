#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KataBump v6：dashboard → 点 Access server (SSO?) → control 是否带会话 → 然后试 client API"""
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
    OUT["dash_cookies"] = [c["name"] for c in sb.driver.get_cookies()]
    # 打开服务器编辑页，找 Access server / Go to server 链接
    try:
        sb.open(BASE + "/servers/edit?id=372611")
        time.sleep(5)
        link = None
        for a in sb.find_elements("a"):
            href = a.get_attribute("href") or ""
            t = (a.text or "").strip()
            if "control.katabump.com" in href or "access" in t.lower():
                link = a
                print(f"找到链接: text={t} href={href}")
                break
        if link is None:
            print("❌ 未找到 Access server 链接")
            for a in sb.find_elements("a"):
                if "server" in (a.get_attribute("href") or ""):
                    print("  候选:", (a.text or "")[:40], a.get_attribute("href")[:120])
        else:
            href = link.get_attribute("href")
            # 直接导航看是否 SSO
            print("导航到 control:", href)
            sb.open(href)
            time.sleep(8)
            OUT["sso_url"] = sb.get_current_url()
            OUT["sso_title"] = sb.get_title() or ""
            OUT["sso_cookies"] = [c["name"] for c in sb.driver.get_cookies()]
            src = sb.get_page_source() or ""
            OUT["sso_len"] = len(src)
            text = re.sub(r"<[^>]+>", " ", src)
            text = re.sub(r"\s+", " ", text)
            OUT["sso_text"] = text[:500]
            if "/auth/login" not in sb.get_current_url():
                print("✅ SSO 成功！control 已带会话")
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
            else:
                print("❌ SSO 失败：control 仍要登录")
                # 尝试把 dashboard 的 PHPSESSID 复制给 control？
                print("dash cookie 不跨域，无法复制")
    except Exception as e:
        OUT["err"] = str(e)[:300]

    print("JSON_OUT<<")
    print(json.dumps(OUT, ensure_ascii=False, indent=1)[:16000])
    print(">>END")