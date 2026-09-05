#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KataBump control 面板探测：进入 control.katabump.com/server/<uuid>，找文件管理/console/startup"""
import sys, time, json, os, re
sys.path.insert(0, '.')
from seleniumbase import SB
import app as upapp

BASE = upapp.BASE_URL
CTRL = os.environ.get("KB_CTRL", "https://control.katabump.com/server/ff41b51e")
EMAIL = os.environ.get("KATABUMP_EMAIL", "")
PASSWORD = os.environ.get("KATABUMP_PASSWORD", "")

EXISTS_JS = "return !!document.querySelector('input[name=\"cf-turnstile-response\"]') || !!document.querySelector('.cf-turnstile') || !!document.querySelector('iframe[src*=\"challenges.cloudflare.com\"]')"

def robust_login(sb):
    print("🌐 打开登录页")
    sb.uc_open_with_reconnect(BASE + "/auth/login", reconnect_time=8)
    print("⏳ 等待登录表单（CF 检查）...")
    for i in range(40):
        src = sb.get_page_source() or ""
        if 'name="email"' in src.lower():
            break
        time.sleep(1)
    try:
        sb.wait_for_element('input[type="email"], input[name="email"]', timeout=20)
    except Exception:
        print("❌ 无 email 输入框")
        sb.save_screenshot("probe_nologin.png")
        return False
    upapp.js_fill_input(sb, 'input[type="email"], input[name="email"]', EMAIL)
    time.sleep(1)
    upapp.js_fill_input(sb, 'input[type="password"], input[name="password"]', PASSWORD)
    time.sleep(1)
    print("⏳ 等待 Turnstile widget（最长 60s）...")
    ts_found = False
    for i in range(60):
        try:
            if sb.execute_script(EXISTS_JS):
                ts_found = True
                print(f"✅ Turnstile 出现（{i+1}s）")
                break
        except Exception:
            pass
        time.sleep(1)
    if ts_found:
        print("🖱️ 调用 uc_gui_click_captcha")
        try:
            sb.uc_gui_click_captcha()
        except Exception as e:
            print(f"uc_gui_click_captcha err: {str(e)[:120]}")
        time.sleep(2)
    print("🖱️ 提交表单")
    try:
        sb.press_keys('input[type="password"], input[name="password"]', '\n')
    except Exception:
        try:
            sb.execute_script('document.querySelector("form").submit()')
        except Exception as e:
            print("submit err", str(e)[:100])
    for _ in range(15):
        time.sleep(1)
        cur = (sb.get_current_url() or "")
        if "/dashboard" in cur or "Dashboard | KataBump" in (sb.get_title() or ""):
            break
    cur = sb.get_current_url()
    title = sb.get_title() or ""
    print(f"登录后 URL: {cur}  TITLE: {title}")
    return "/dashboard" in cur or "Dashboard" in title

OUT = {}

def save_snapshot(sb, label, wait=6):
    try:
        sb.open(CTRL)
    except Exception as e:
        print(f"open {label} err: {str(e)[:100]}")
    time.sleep(wait)
    src = (sb.get_page_source() or "")
    OUT[label + "_url"] = sb.get_current_url()
    OUT[label + "_title"] = sb.get_title() or ""
    OUT[label + "_len"] = len(src)
    kws = ["file", "upload", "startup", "command", "console", "terminal", "sftp",
           "port", "network", "allocation", "setting", "docker", "restart", "start",
           "jsdelivr", "npm", "node"]
    OUT[label + "_kw"] = {k: (k in src.lower()) for k in kws}
    # 页面可见文本片段（取 body 前 4000 字符，去 HTML 标签）
    text = re.sub(r"<[^>]+>", " ", src)
    text = re.sub(r"\s+", " ", text)[:3000]
    OUT[label + "_text"] = text
    # links
    items = []
    try:
        for a in sb.find_elements("a"):
            href = a.get_attribute("href") or ""
            t = (a.text or "").strip()
            if href or t:
                items.append({"t": t[:40], "h": href[:160]})
    except Exception as e:
        items.append({"err": str(e)[:80]})
    OUT[label + "_links"] = items[:50]
    try:
        sb.save_screenshot(f"snap_{label}.png")
    except Exception:
        pass

with SB(uc=True, headless=False) as sb:
    if not robust_login(sb):
        print("LOGIN_FAIL")
        sys.exit(1)
    try:
        OUT["cookies"] = [c["name"] for c in sb.driver.get_cookies()]
    except Exception as e:
        OUT["cookies"] = [str(e)[:80]]

    # control 根
    save_snapshot(sb, "ctrl_home")
    # 常见路径
    for sub in ["files", "console", "startup", "settings", "network", "database", "schedules", "terminal", "app"]:
        try:
            sb.open(CTRL + "/" + sub)
            time.sleep(4)
            src = (sb.get_page_source() or "")
            OUT["sub_" + sub + "_url"] = sb.get_current_url()
            OUT["sub_" + sub + "_title"] = sb.get_title() or ""
            OUT["sub_" + sub + "_len"] = len(src)
            OUT["sub_" + sub + "_kw"] = {k: (k in src.lower()) for k in ["file", "upload", "command", "start", "log"]}
            text = re.sub(r"<[^>]+>", " ", src)
            text = re.sub(r"\s+", " ", text)[:600]
            OUT["sub_" + sub + "_text"] = text
        except Exception as e:
            OUT["sub_" + sub + "_err"] = str(e)[:120]

    print("JSON_OUT<<")
    print(json.dumps(OUT, ensure_ascii=False, indent=1)[:12000])
    print(">>END")