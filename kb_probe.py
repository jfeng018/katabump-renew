#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KataBump 面板探测：登录后进入服务器详情页，dump 文件管理/启动命令/端口入口（只读侦察）"""
import sys, time, json, base64, os
sys.path.insert(0, '.')
from seleniumbase import SB
import app

BASE = app.BASE_URL  # https://dashboard.katabump.com
SERVER_ID = os.environ.get("KB_SERVER_ID") or "372611"

OUT = {}

def dump_links(sb, label):
    items = []
    try:
        for a in sb.find_elements("a"):
            href = a.get_attribute("href") or ""
            text = (a.text or "").strip()
            target = "_blank" if a.get_attribute("target") == "_blank" else ""
            if href or text:
                items.append({"text": text[:60], "href": href[:160], "target": target})
    except Exception as e:
        items.append({"err": str(e)[:100]})
    OUT[label] = items

def dump_inputs(sb, label):
    items = []
    try:
        for el in sb.find_elements("input, textarea, select, button"):
            tag = el.tag_name
            typ = el.get_attribute("type") or ""
            name = el.get_attribute("name") or ""
            ident = el.get_attribute("id") or ""
            placeholder = el.get_attribute("placeholder") or ""
            text = (el.text or "")[:40]
            items.append(f"{tag} type={typ} name={name} id={ident} ph={placeholder} txt={text}")
    except Exception as e:
        items.append(str(e)[:100])
    OUT[label] = items

with SB(uc=True, headless=False) as sb:
    if not app.login(sb):
        print("LOGIN_FAIL")
        sys.exit(1)
    # cookie 名（不打印值）
    try:
        OUT["cookies"] = [c["name"] for c in sb.driver.get_cookies()]
    except Exception as e:
        OUT["cookies"] = [str(e)[:100]]

    for path, label in [
        (f"/servers/edit?id={SERVER_ID}", "server_edit"),
        (f"/servers/edit?id={SERVER_ID}&tab=files", "tab_files"),
        (f"/servers/edit?id={SERVER_ID}&tab=startup", "tab_startup"),
        (f"/servers/edit?id={SERVER_ID}&tab=console", "tab_console"),
    ]:
        try:
            sb.open(BASE + path)
            time.sleep(4)
            OUT[label + "_url"] = sb.get_current_url()
            OUT[label + "_title"] = sb.get_title() or ""
            src = (sb.get_page_source() or "")
            OUT[label + "_len"] = len(src)
            # 关键关键词出现情况
            kws = ["file", "files", "upload", "startup", "command", "console", "terminal",
                   "port", "address", "domain", "dns", "destroy", "reinstall", "restart"]
            OUT[label + "_kw"] = {k: (k in src.lower()) for k in kws}
            # 抓取含 port/address 的文本片段
            import re
            frags = set(re.findall(r'(?:port|address|domain|host)[^<]{0,80}', src[:200000], re.I))
            OUT[label + "_port_frags"] = list(frags)[:12]
            dump_links(sb, label + "_links")
            dump_inputs(sb, label + "_inputs")
            sb.save_screenshot(f"probe_{label}.png")
        except Exception as e:
            OUT[label + "_err"] = str(e)[:200]

    print(json.dumps(OUT, ensure_ascii=False, indent=1)[:6000])
    print("SCREENSHOTS_SAVED")