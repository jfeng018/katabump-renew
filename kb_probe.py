#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KataBump 面板探测 v2：稳健登录 + dump 服务器管理页（找文件上传/启动命令/端口）"""
import sys, time, json, os, re
sys.path.insert(0, '.')
from seleniumbase import SB
import app as upapp

BASE = upapp.BASE_URL
SERVER_ID = os.environ.get("KB_SERVER_ID") or "372611"
EMAIL = os.environ.get("KATABUMP_EMAIL", "")
PASSWORD = os.environ.get("KATABUMP_PASSWORD", "")

EXISTS_JS = "return !!document.querySelector('input[name=\"cf-turnstile-response\"]') || !!document.querySelector('.cf-turnstile') || !!document.querySelector('iframe[src*=\"challenges.cloudflare.com\"]')"

def robust_login(sb):
    """复刻 app.login 但 Turnstile 检测 60s + 多条件 + 提交前确认 token"""
    print("🌐 打开登录页")
    sb.uc_open_with_reconnect(BASE + "/auth/login", reconnect_time=8)
    # 等 email 表单（CF 底部检查通过）
    print("⏳ 等待登录表单（CF 检查）...")
    for i in range(40):
        src = sb.get_page_source() or ""
        if 'name="email"' in src.lower() or 'input[type="email"]' in src.lower():
            print(f"✅ 表单出现（{i+1}s）")
            break
        time.sleep(1)
    try:
        sb.wait_for_element('input[type="email"], input[name="email"]', timeout=20)
    except Exception:
        print("❌ 无 email 输入框，截图")
        sb.save_screenshot("probe_nologin.png")
        print("PAGE_SNIP:", (sb.get_page_source() or "")[:500])
        return False
    # 填表（用 upapp 的 js_fill_input）
    print("📧 填邮箱/密码")
    upapp.js_fill_input(sb, 'input[type="email"], input[name="email"]', EMAIL)
    time.sleep(1)
    upapp.js_fill_input(sb, 'input[type="password"], input[name="password"]', PASSWORD)
    time.sleep(1)
    # Turnstile 检测：60s 周期轮询
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
            print(f"uc_gui_click_captcha: {str(e)[:120]}")
        time.sleep(2)
        # 检查 token
        try:
            tok = sb.execute_script('return document.querySelector("input[name=\\"cf-turnstile-response\\"]")?.value || ""')
            print(f"token_len={len(tok or '')}")
        except Exception as e:
            print("token check err", str(e)[:80])
    else:
        print("⚠️ 60s 未检测到 Turnstile，仍尝试提交")
    # 提交
    print("🖱️ 提交表单")
    try:
        sb.press_keys('input[type="password"], input[name="password"]', '\n')
    except Exception:
        try:
            sb.execute_script('document.querySelector("form").submit()')
        except Exception as e:
            print("submit err", str(e)[:100])
    # 等跳转
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

def dump_links(sb, label):
    items = []
    try:
        for a in sb.find_elements("a"):
            href = a.get_attribute("href") or ""
            text = (a.text or "").strip()
            if href or text:
                items.append({"t": text[:50], "h": href[:150]})
    except Exception as e:
        items.append({"err": str(e)[:80]})
    OUT[label] = items[:60]

def dump_inputs(sb, label):
    items = []
    try:
        for el in sb.find_elements("input, textarea, select, button"):
            tag = el.tag_name
            typ = el.get_attribute("type") or ""
            nm = el.get_attribute("name") or ""
            vid = el.get_attribute("id") or ""
            ph = el.get_attribute("placeholder") or ""
            txt = (el.text or "")[:40]
            items.append(f"{tag} t={typ} n={nm} id={vid} ph={ph} txt={txt}")
    except Exception as e:
        items.append(str(e)[:80])
    OUT[label] = items[:60]

with SB(uc=True, headless=False) as sb:
    ok = robust_login(sb)
    if not ok:
        print("LOGIN_FAIL")
        try:
            src = (sb.get_page_source() or "")
            if "error=captcha" in sb.get_current_url():
                print("CAPTCHA_ERROR_URL")
                print("URL:", sb.get_current_url())
        except Exception:
            pass
        sys.exit(1)
    try:
        OUT["cookies"] = [c["name"] for c in sb.driver.get_cookies()]
    except Exception as e:
        OUT["cookies"] = [str(e)[:80]]

    # 服务器详情页主页面
    for path, label in [
        (f"/servers/edit?id={SERVER_ID}", "edit"),
        (f"/servers/files?id={SERVER_ID}", "files"),
        (f"/servers/filemanager?id={SERVER_ID}", "filemanager"),
    ]:
        try:
            sb.open(BASE + path)
            time.sleep(5)
            OUT[label + "_url"] = sb.get_current_url()
            OUT[label + "_title"] = sb.get_title() or ""
            src = (sb.get_page_source() or "")
            OUT[label + "_len"] = len(src)
            kws = ["file", "upload", "startup", "command", "console", "terminal",
                   "port", "address", "domain", "restart", "start", "stop", "delete"]
            OUT[label + "_kw"] = {k: (k in src.lower()) for k in kws}
            frags = set(re.findall(r'(?:port|address|domain|host)[^<]{0,80}', src[:300000], re.I))
            OUT[label + "_port_frags"] = list(frags)[:15]
            dump_links(sb, label + "_links")
            dump_inputs(sb, label + "_inputs")
            sb.save_screenshot(f"probe_{label}.png")
        except Exception as e:
            OUT[label + "_err"] = str(e)[:200]

    print("JSON_OUT<<")
    print(json.dumps(OUT, ensure_ascii=False, indent=1)[:9000])
    print(">>END")