#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""KataBump vless deploy: 登录 control → 页面上下文 fetch 上传 → 启动 → websocket 抓日志 → TG 通知"""
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

FULL_UUID = "ff41b51e-0808-4d8b-aafb-96d591677e97"

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
        sb.save_screenshot("deploy_nologin.png")
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
    # 只有当 plain_csrf 是真正的明文 token（≠ 加密 cookie 值）时才设 X-CSRF-TOKEN
    if plain_csrf and plain_csrf != xsrf:
        s.headers["X-CSRF-TOKEN"] = plain_csrf
    return s, cookies


def get_page_csrf(sb):
    """取页面里的明文 session CSRF token（Laravel 布局注入）"""
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
    """已登录页面上下文里用同步 XHR 打 client API：
    X-CSRF-TOKEN = 明文 session token；X-XSRF-TOKEN = 加密 cookie 原值"""
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

    # 登录后 dump cookies 诊断 CSRF 可用性
    import re as _re
    _dc = sb.execute_script("return document.cookie;") or ""
    print("DOC_COOKIE_AFTER_LOGIN:", _dc[:300])
    _m = _re.search(r'XSRF-TOKEN=([^;]+)', _dc)
    print("DOC_COOKIE_XSRF_LEN:", len(_m.group(1)) if _m else 0)

    # 登录后落到 SPA 外壳页（无 Laravel 布局），先导航到真实服务器页取明文 csrf token
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
        # SPA 无明文 token → 从 document.cookie 取加密 XSRF-TOKEN（Laravel 会解密比对）
        _m2 = _re.search(r'XSRF-TOKEN=([^;]+)', _dc)
        if _m2:
            plain_csrf = _m2.group(1)
            print("CSRF_FALLBACK_FROM_DOC_COOKIE", len(plain_csrf))
        else:
            plain_csrf = cookies.get("XSRF-TOKEN") or ""
            print("CSRF_FALLBACK_FROM_PY_COOKIES", len(plain_csrf))
    s, cookies = make_session(sb, plain_csrf)
    print("PLAIN_CSRF_LEN:", len(plain_csrf))

    def call(method, path, data=None, ctype=None):
        """浏览器 XHR 优先；419 时 fallback 到 requests（X-XSRF-TOKEN 走加密 cookie）"""
        r = None
        try:
            r = json.loads(browser_api(sb, method, path, data, ctype, plain_csrf))
            if r.get("status") == 419:
                print("   browser XHR 419 → fallback requests")
                r = None
        except Exception as e:
            print("   browser_api err:", str(e)[:120])
        if r is None:
            # requests fallback：X-XSRF-TOKEN = 加密 cookie 原值（Laravel 服务端解密）
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

    # 1. 验证文件已由 SFTP 上传到位（GET 不需要 CSRF）
    f = call("GET", f"/api/client/servers/{UUID}/files/list?directory=/")
    print("FILES_STATUS", f.get("status"))
    fbody = f.get("body") or ""
    OUT["files_before"] = fbody[:3000]
    print("FILES_BODY", fbody[:3000])
    has_index = "index.js" in fbody
    has_config = "config.json" in fbody
    print("HAS_INDEX_JS", has_index, "HAS_CONFIG", has_config)
    if not (has_index and has_config):
        # SFTP 未到位，尝试 API 写入兜底
        for fname in ["index.js", "config.json", "package.json"]:
            if not os.path.exists(fname):
                continue
            with open(fname, "rb") as fh:
                data = fh.read()
            r = call("POST", f"/api/client/servers/{UUID}/files/write?file={fname}", data, "application/octet-stream")
            print("WRITE", fname, r.get("status"), (r.get("body") or r.get("err") or "")[:200])
            OUT.setdefault("writes", []).append({"file": fname, "status": r.get("status"),
                                                  "body": (r.get("body") or r.get("err") or "")[:200]})
        print("WRITES_DONE")

    # 2. 启动（必须带 Content-Type: application/json，否则 Laravel 不解析 signal）
    p = call("POST", f"/api/client/servers/{UUID}/power", json.dumps({"signal": "start"}).encode(), "application/json")
    OUT["power_start"] = p
    print("POWER_START", p.get("status"), (p.get("body") or p.get("err") or "")[:300])

    # 3. 轮询 running
    state = None
    for i in range(90):
        time.sleep(2)
        r = call("GET", f"/api/client/servers/{UUID}/resources")
        try:
            state = json.loads(r["body"])["attributes"]["current_state"]
        except Exception:
            state = None
        print(f"poll {i*2}s state={state}")
        if state == "running":
            break
    OUT["final_state"] = state
    if state != "running":
        tx = "KataBump vless 部署失败：服务器未进入 running（state=%s）" % state
        print("FAIL", tx)
        tg(tx)
        sys.exit(2)

    # 4. websocket 抓日志（最多 80s，等 sing-box 下载+启动+打印链接）
    ws_lines = []
    try:
        import websocket  # websocket-client
        w = call("GET", f"/api/client/servers/{UUID}/websocket")
        wd = json.loads(w["body"])["data"][0]
        token = wd["token"]
        sock = wd["socket"]
        ws = websocket.create_connection(sock + f"?token={token}&permissions=*&server_id={UUID}", timeout=10)
        ws.send(json.dumps({"event": "auth", "args": [token]}))
        time.sleep(2)
        ws.send(json.dumps({"event": "send logs", "args": [""]}))
        deadline = time.time() + 80
        while time.time() < deadline:
            try:
                ws.settimeout(5)
                msg = ws.recv()
                data = json.loads(msg)
                if data.get("event") == "console output":
                    line = data.get("args", [""])[0]
                    ws_lines.append(line)
                    print("[WS]", line[:200])
                    if "vless://" in line:
                        break
            except Exception:
                # 每 10s 重新请求日志
                try:
                    ws.send(json.dumps({"event": "send logs", "args": [""]}))
                except Exception:
                    pass
        ws.close()
    except Exception as e:
        print("[WS err]", str(e)[:150])

    OUT["ws_lines_tail"] = ws_lines[-40:]

    # 5. 提取 vless 链接
    full = "\n".join(ws_lines)
    links = re.findall(r"vless://[^\s#\"]+", full)
    links = list(dict.fromkeys(links))[:6]
    OUT["links"] = links
    print("LINKS:", json.dumps(links, ensure_ascii=False, indent=1))
    print("JSON_OUT<<")
    print(json.dumps(OUT, ensure_ascii=False, indent=1)[:16000])
    print(">>END")

    if links:
        tg("🚀 KataBump vless 已部署上线（服务器 aiiiiid / 51.75.118.171:20275）\n\n" + "\n".join(links))
    else:
        tg("⚠️ KataBump vless 服务器已 running，但未抓到节点链接（日志可能未刷出）。稍后手动抓 logs。")