#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KataBump vless 清理：登录 control → 停止服务器 → 删除 vless 文件 → 验证（仅移除实例，保留部署知识）"""
import sys, time, json, os, re, base64
sys.path.insert(0, '.')
from seleniumbase import SB
import requests

CTRL = os.environ.get("KB_CTRL", "https://control.katabump.com")
KB_USERNAME = os.environ.get("KB_USERNAME", "")
KB_PASSWORD = os.environ.get("KB_PASSWORD", "")
UUID = os.environ.get("KB_SRV_UUID", "ff41b51e")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "")
TG_CHAT_ID = os.environ.get("TG_CHAT_ID", "")

FILES_TO_REMOVE = ["index.js", "config.json", "package.json"]

def tg(msg):
    if not TG_BOT_TOKEN or not TG_CHAT_ID:
        print("[TG] no token/chat, skip:", msg[:80])
        return
    try:
        r = requests.post(f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage",
                          json={"chat_id": TG_CHAT_ID, "text": msg, "disable_web_page_preview": True}, timeout=15)
        print("[TG]", r.status_code)
    except Exception as e:
        print("[TG err]", str(e)[:100])

def login_ctrl(sb):
    print("🌐 打开 control 登录页")
    sb.open(CTRL + "/auth/login")
    time.sleep(8)
    try:
        sb.wait_for_element('input[name="username"]', timeout=15)
    except Exception:
        print("❌ 无 username")
        sb.save_screenshot("cleanup_nologin.png")
        return False
    sb.type('input[name="username"]', KB_USERNAME)
    time.sleep(1)
    sb.type('input[name="password"]', KB_PASSWORD)
    time.sleep(1)
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
        if (b.text or "").strip().lower() in ("login", "sign in", "continue", "connexion"):
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
    print("登录后 URL:", cur)
    return "/auth/login" not in cur

def get_cookies(sb):
    try:
        r = sb.driver.execute_cdp_cmd('Network.getAllCookies', {})
        return {c["name"]: c["value"] for c in r.get("cookies", [])}
    except Exception as e1:
        print("CDP err:", str(e1)[:120])
        try:
            return {c["name"]: c["value"] for c in sb.driver.get_cookies()}
        except Exception as e2:
            print("get_cookies err:", str(e2)[:120])
            return {}

def make_session(sb, plain_csrf=""):
    cookies = get_cookies(sb)
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": CTRL + "/",
        "Origin": CTRL,
    })
    s.cookies.update(cookies)
    bearer = cookies.get("pterodactyl") or ""
    xsrf = cookies.get("XSRF-TOKEN") or ""
    if bearer:
        s.headers["Authorization"] = "Bearer " + bearer
    if xsrf:
        s.headers["X-XSRF-TOKEN"] = xsrf
    if plain_csrf and plain_csrf != xsrf:
        s.headers["X-CSRF-TOKEN"] = plain_csrf
    return s, cookies

def get_page_csrf(sb):
    js = r"""
    var m = document.querySelector('meta[name="csrf-token"]');
    if (m && m.content) return m.content;
    try {
      if (window.Laravel && window.Laravel.csrfToken) return window.Laravel.csrfToken;
    } catch (e) {}
    var i = document.querySelector('input[name="_token"]');
    if (i && i.value) return i.value;
    return '';
    """
    try:
        return sb.execute_script(js) or ""
    except Exception:
        return ""

def browser_api(sb, method, path, data=None, content_type=None, plain_csrf=""):
    b64 = base64.b64encode(data).decode() if data is not None else None
    js = r"""
    var m = document.cookie.match(/XSRF-TOKEN=([^;]+)/);
    var xsrfRaw = m ? m[1] : '';
    var url = arguments[0], method = arguments[1], b64 = arguments[2], ctype = arguments[3], plain = arguments[4];
    var x = new XMLHttpRequest();
    x.open(method, url, false);
    x.setRequestHeader('Accept', 'application/json');
    if (xsrfRaw) x.setRequestHeader('X-XSRF-TOKEN', xsrfRaw);
    if (plain)   x.setRequestHeader('X-CSRF-TOKEN', plain);
    if (ctype)   x.setRequestHeader('Content-Type', ctype);
    var body = null;
    if (b64 !== null && b64 !== undefined && b64 !== '') {
      var bin = atob(b64);
      var bytes = new Uint8Array(bin.length);
      for (var i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
      body = bytes.buffer;
    }
    try {
      x.send(body);
      return JSON.stringify({status: x.status, body: (x.responseText || '').slice(0, 9000)});
    } catch (e) {
      return JSON.stringify({status: -1, err: String(e).slice(0, 200)});
    }
    """
    return sb.execute_script(js, CTRL + path, method, b64, content_type, plain_csrf)

def api(s, method, path, **kw):
    try:
        r = s.request(method, CTRL + path, timeout=30, **kw)
        return {"status": r.status_code, "body": (r.text or "")[:12000]}
    except Exception as e:
        return {"err": str(e)[:150]}

OUT = {}

with SB(uc=True, headless=False) as sb:
    ok = login_ctrl(sb)
    print("LOGIN_OK" if ok else "LOGIN_FAIL")
    if not ok:
        sys.exit(1)
    s, cookies = make_session(sb)
    OUT["cookie_names"] = list(cookies.keys())
    print("COOKIES:", list(cookies.keys()))

    plain_csrf = get_page_csrf(sb)
    for page in ["/servers/files?id=372611", "/servers/control?id=372611",
                 f"/servers/files?id={UUID}", "/server/" + UUID]:
        if plain_csrf:
            break
        try:
            sb.open(CTRL + page)
            time.sleep(6)
            plain_csrf = get_page_csrf(sb)
            print("TRY_PAGE", page, "csrf_len=", len(plain_csrf or ""))
        except Exception as e:
            print("TRY_PAGE_ERR", page, str(e)[:100])
    if not plain_csrf:
        _dc = sb.execute_script("return document.cookie;") or ""
        _m2 = re.search(r'XSRF-TOKEN=([^;]+)', _dc)
        if _m2:
            plain_csrf = _m2.group(1)
            print("CSRF_FALLBACK_FROM_DOC_COOKIE", len(plain_csrf))
        else:
            plain_csrf = cookies.get("XSRF-TOKEN") or ""
            print("CSRF_FALLBACK_FROM_PY_COOKIES", len(plain_csrf))
    s, cookies = make_session(sb, plain_csrf)
    print("PLAIN_CSRF_LEN:", len(plain_csrf))

    def call(method, path, data=None, ctype=None):
        r = None
        try:
            r = json.loads(browser_api(sb, method, path, data, ctype, plain_csrf))
            if r.get("status") == 419:
                print("   browser XHR 419 → fallback requests")
                r = None
        except Exception as e:
            print("   browser_api err:", str(e)[:120])
        if r is None:
            _xsrf = cookies.get("XSRF-TOKEN") or ""
            _hdrs = {"X-XSRF-TOKEN": _xsrf} if _xsrf else {}
            if plain_csrf and plain_csrf != _xsrf:
                _hdrs["X-CSRF-TOKEN"] = plain_csrf
            if ctype:
                _hdrs["Content-Type"] = ctype
            try:
                if data is not None:
                    resp = s.request(method, CTRL + path, data=data, headers=_hdrs, timeout=30)
                else:
                    resp = s.request(method, CTRL + path, headers=_hdrs, timeout=30)
                r = {"status": resp.status_code, "body": (resp.text or "")[:12000]}
            except Exception as e:
                r = {"err": str(e)[:150]}
            print("   requests fallback:", r.get("status"), (r.get("body") or r.get("err") or "")[:150])
        return r

    # 1. 停止服务器
    p = call("POST", f"/api/client/servers/{UUID}/power", json.dumps({"signal": "stop"}).encode(), "application/json")
    OUT["power_stop"] = p
    print("POWER_STOP", p.get("status"), (p.get("body") or p.get("err") or "")[:300])

    # 2. 等停止
    state = None
    for i in range(60):
        time.sleep(2)
        r = call("GET", f"/api/client/servers/{UUID}/resources")
        try:
            state = json.loads(r["body"])["attributes"]["current_state"]
        except Exception:
            state = None
        print(f"poll {i*2}s state={state}")
        if state in ("offline", "stopped", None):
            break
    OUT["state_after_stop"] = state
    print("STATE_AFTER_STOP:", state)

    # 3. 删除 vless 文件
    body = json.dumps({"root": "/", "files": FILES_TO_REMOVE}).encode()
    d = call("POST", f"/api/client/servers/{UUID}/files/delete", body, "application/json")
    OUT["files_delete"] = d
    print("FILES_DELETE", d.get("status"), (d.get("body") or d.get("err") or "")[:300])

    # 4. 验证：列目录确认已删
    time.sleep(2)
    f = call("GET", f"/api/client/servers/{UUID}/files/list?directory=/")
    print("FILES_AFTER_STATUS", f.get("status"))
    fbody = f.get("body") or ""
    OUT["files_after"] = fbody[:3000]
    print("FILES_AFTER_BODY", fbody[:3000])
    remaining = [fn for fn in FILES_TO_REMOVE if fn in fbody]
    OUT["remaining"] = remaining
    print("REMAINING:", remaining)

    print("JSON_OUT<<")
    print(json.dumps(OUT, ensure_ascii=False, indent=1)[:12000])
    print(">>END")

    if remaining:
        tg("⚠️ KataBump vless 清理不完整：仍存在 " + ", ".join(remaining))
    else:
        tg("✅ KataBump vless 已移除（服务器 aiiiiid 已停止，vless 文件已删除）；部署方法/源码保留在本地 deploy/vless-source/")
