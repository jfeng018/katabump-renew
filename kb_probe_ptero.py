#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KataBump v7：dashboard 登录后，干净提取 /profil 的 username/ID/API 信息"""
import sys, time, json, os, re
sys.path.insert(0, '.')
from seleniumbase import SB
import app as upapp

BASE = upapp.BASE_URL
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

def clean_text(html):
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
    html = re.sub(r"<[^>]+>", " | ", html)
    html = re.sub(r"\s*\|\s*", " | ", html)
    html = re.sub(r"\s+", " ", html)
    return html

with SB(uc=True, headless=False) as sb:
    if not login_dash(sb):
        print("DASH_LOGIN_FAIL")
        sys.exit(0)
    for path, label in [("/profil", "profil"), ("/profil/security", "security"), ("/dashboard", "dash")]:
        try:
            sb.open(BASE + path)
            time.sleep(4)
            src = sb.get_page_source() or ""
            text = clean_text(src)
            OUT[label + "_clean"] = text[:2500]
            # input 值
            vals = re.findall(r'<input[^>]*value="([^"]+)"[^>]*>', src)
            OUT[label + "_inputvals"] = vals[:30]
            # all labels
            labels = re.findall(r'<label[^>]*>(.*?)</label>', src, re.S)
            OUT[label + "_labels"] = [re.sub(r"<[^>]+>", "", l).strip()[:60] for l in labels[:30] if re.sub(r"<[^>]+>", "", l).strip()]
        except Exception as e:
            OUT["err_" + label] = str(e)[:150]

    print("JSON_OUT<<")
    print(json.dumps(OUT, ensure_ascii=False, indent=1)[:15000])
    print(">>END")