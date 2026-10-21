# -*- coding: utf-8 -*-
"""
INT-1105 返工实机验证（P2：驱动关键字下拉为空 + 控制台 TypeError）
复测项：设备 test 添加/编辑弹窗「驱动关键字」下拉加载真实选项 + 控制台零报错。
连本 run dev server :5525（常驻后端 :5000，AUTH_MODE=off）。
产出：浅/深 弹窗截图 + 关键字下拉选项证据 + Network 证据截图。
"""
import json, os, time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5525"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots", "int1105-r2")
os.makedirs(OUT, exist_ok=True)


class Net:
    """请求/响应捕获：按 URL+seq 记录 method/status/url/resBody。"""

    def __init__(self):
        self.entries = []
        self.seq = 0

    def attach(self, page):
        def on_req(req):
            if "/api/v1/" not in req.url:
                return
            self.seq += 1
            entry = {"seq": self.seq, "method": req.method, "url": req.url,
                     "status": None, "resBody": None, "ts": time.time()}
            self.entries.append(entry)

        def on_res(res):
            if "/api/v1/" not in res.url:
                return
            cand = [e for e in self.entries if e["url"] == res.url and e["status"] is None]
            if cand:
                cand[-1]["status"] = res.status
                try:
                    body = res.body().decode("utf-8", "replace")
                    cand[-1]["resBody"] = body[:800]
                except Exception:
                    pass
        page.on("request", on_req)
        page.on("response", on_res)


def build_net_html(net, path):
    rows = []
    t0 = min((e["ts"] for e in net.entries), default=0)
    for e in net.entries:
        url = e["url"].replace(BASE, "").replace("http://127.0.0.1:5000", "")
        rel = "+%.1fs" % (e["ts"] - t0)
        res = (e["resBody"] or "").replace("<", "&lt;").replace(">", "&gt;")
        rows.append(
            "<tr>"
            f"<td>{e['seq']}</td><td>{rel}</td><td>{e['method']}</td><td class='u'>{url}</td>"
            f"<td>{e['status'] or ''}</td><td class='b'>{res}</td>"
            "</tr>"
        )
    html = (
        "<html><head><meta charset='utf-8'><style>"
        "body{font-family:Consolas,monospace;background:#fff;color:#222;margin:16px}"
        "table{border-collapse:collapse;width:100%;font-size:12px}"
        "th,td{border:1px solid #ccc;padding:4px 6px;text-align:left;vertical-align:top;word-break:break-all}"
        "th{background:#f0f0f0}.u{color:#08c}.b{color:#666;white-space:pre-wrap}"
        "</style></head><body><h3>INT-1105 返工 Network 证据</h3><table>"
        "<tr><th>seq</th><th>t</th><th>method</th><th>url</th><th>status</th><th>resBody</th></tr>"
        + "".join(rows)
        + "</table></body></html>"
    )
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


def wait_for(page, expr, timeout_ms=20000, what=""):
    start = time.time()
    while time.time() - start < timeout_ms / 1000.0:
        try:
            if page.evaluate(expr):
                return
        except Exception:
            pass
        time.sleep(0.3)
    raise TimeoutError("timeout waiting: " + what)


def keywords_options(page):
    """返回 #field-keywords 下拉全部 option 的 {value,label} 列表（不含占位）。"""
    return page.evaluate("""() => {
      const sel = document.querySelector('#field-keywords')
      if (!sel) return null
      return Array.from(sel.options).map(o => ({ value: o.value, label: o.textContent.trim() }))
    }""")


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1440, "height": 900})

    net = Net()
    console_errors = []
    page = context.new_page()
    net.attach(page)
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append("[pageerror] " + str(e)))

    # ===== 浅色：添加测试设备弹窗 =====
    page.goto(BASE + "/#/devices", wait_until="domcontentloaded", timeout=60000)
    wait_for(page, "document.body.innerText.includes('设备管理') && document.body.innerText.includes('测试设备列表')", 30000, "devices page")
    # 确保 测试设备 tab 激活
    act = page.evaluate("document.querySelector('.tab-btn.active')?.getAttribute('data-device-type')")
    if act != "test":
        page.locator('.tab-btn[data-device-type="test"]').first.click()
        time.sleep(1)
    # 打开 添加测试设备
    page.locator(".header-right .btn.btn-primary").first.click()
    wait_for(page, "!!document.querySelector('#field-keywords')", 20000, "add modal keywords field")
    # 等待驱动关键字真实选项加载
    wait_for(page, """(() => {
      const sel = document.querySelector('#field-keywords')
      return sel && Array.from(sel.options).filter(o => o.value !== '').length >= 5
    })()""", 20000, "keywords options loaded")
    time.sleep(1)
    opts_light = keywords_options(page)
    print("[light] keywords options:", json.dumps(opts_light, ensure_ascii=False))
    page.screenshot(path=os.path.join(OUT, "add-test-modal-keywords-light.png"))
    print("[shot] add-test-modal-keywords-light.png")

    # 关闭添加弹窗
    page.locator(".modal-close").first.click()
    time.sleep(0.8)

    # ===== 浅色：编辑已有测试设备弹窗（pura90小艺） =====
    card_edit = page.locator(".device-card button.btn.btn-secondary", has_text="编辑").first
    if card_edit.count() > 0:
        card_edit.click()
        wait_for(page, "!!document.querySelector('#field-keywords')", 20000, "edit modal keywords field")
        wait_for(page, """(() => {
          const sel = document.querySelector('#field-keywords')
          return sel && Array.from(sel.options).filter(o => o.value !== '').length >= 5
        })()""", 20000, "edit keywords options loaded")
        time.sleep(1)
        opts_edit = keywords_options(page)
        print("[edit] keywords options:", json.dumps(opts_edit, ensure_ascii=False))
        # 编辑态回显：已存关键字 harmony.base.v1 应命中选项值
        sel_val = page.evaluate("document.querySelector('#field-keywords')?.value")
        print("[edit] field-keywords current value:", repr(sel_val))
        page.screenshot(path=os.path.join(OUT, "edit-test-modal-keywords-light.png"))
        print("[shot] edit-test-modal-keywords-light.png")
        page.locator(".modal-close").first.click()
        time.sleep(0.8)

    # ===== 深色：添加测试设备弹窗 =====
    page.evaluate("localStorage.setItem('iatp:theme:v1', 'dark')")
    page.reload(wait_until="domcontentloaded")
    wait_for(page, "document.body.innerText.includes('设备管理') && document.body.innerText.includes('测试设备列表')", 30000, "devices page dark")
    dark_on = page.evaluate("document.documentElement.classList.contains('dark')")
    print("[dark] html.dark =", dark_on)
    page.locator(".header-right .btn.btn-primary").first.click()
    wait_for(page, "!!document.querySelector('#field-keywords')", 20000, "add modal keywords field dark")
    wait_for(page, """(() => {
      const sel = document.querySelector('#field-keywords')
      return sel && Array.from(sel.options).filter(o => o.value !== '').length >= 5
    })()""", 20000, "keywords options loaded dark")
    time.sleep(1)
    opts_dark = keywords_options(page)
    print("[dark] keywords options:", json.dumps(opts_dark, ensure_ascii=False))
    page.screenshot(path=os.path.join(OUT, "add-test-modal-keywords-dark.png"))
    print("[shot] add-test-modal-keywords-dark.png")

    # ===== 控制台零报错断言 =====
    kw_errors = [e for e in console_errors if "加载驱动关键字失败" in e or "join is not a function" in e or "TypeError" in e]
    print("[console] total errors:", len(console_errors))
    for e in console_errors:
        print("[console] ", e[:200])
    if kw_errors:
        raise AssertionError("驱动关键字相关控制台报错: " + "; ".join(kw_errors)[:400])

    # ===== Network 证据 =====
    net_path = build_net_html(net, os.path.join(OUT, "network.html"))
    np = browser.new_page(viewport={"width": 1440, "height": 1000})
    np.goto("file:///" + net_path.replace("\\", "/"), wait_until="domcontentloaded")
    np.screenshot(path=os.path.join(OUT, "network-evidence.png"), full_page=True)
    print("[shot] network-evidence.png")
    kw_calls = [e for e in net.entries if "driver-keywords" in e["url"]]
    print("[network] driver-keywords calls:", json.dumps(kw_calls, ensure_ascii=False))

    browser.close()

print("VERIFY OK")
