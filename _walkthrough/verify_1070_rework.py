# -*- coding: utf-8 -*-
"""
INT-1070 返工实机验证（P2-1 伪造 verdict / P2-2 快速复核轮询 / P3-1 注释 / P3-2 Network 截图）
连 dev server :5510（常驻后端 :5000 AUTH_MODE=off）。报告 65 / 来源任务 1257 / 用例 5412e6d4 / 结果 3693。
产出：浅/深 + 快速复核结论 + 会话上下文 + 历史抽屉 + Network 证据截图。
"""
import json, os, time
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5510"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots", "int1070-r2")
os.makedirs(OUT, exist_ok=True)


class Net:
    """请求/响应捕获：按 URL+seq 记录 method/status/url/reqBody/resBody。"""

    def __init__(self):
        self.entries = []
        self.seq = 0

    def attach(self, page):
        def on_req(req):
            if "/api/v1/" not in req.url:
                return
            self.seq += 1
            entry = {"seq": self.seq, "method": req.method, "url": req.url,
                     "status": None, "reqBody": None, "resBody": None, "ts": time.time()}
            try:
                post = req.post_data
                if post:
                    entry["reqBody"] = post[:600]
            except Exception:
                pass
            self.entries.append(entry)

        def on_res(res):
            if "/api/v1/" not in res.url:
                return
            cand = [e for e in self.entries if e["url"] == res.url and e["status"] is None]
            if cand:
                cand[-1]["status"] = res.status
                try:
                    body = res.body().decode("utf-8", "replace")
                    cand[-1]["resBody"] = body[:600]
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
        rows.append(
            "<tr>"
            f"<td>{e['seq']}</td><td>{rel}</td><td>{e['method']}</td><td class='u'>{url}</td>"
            f"<td>{e['status'] or '…'}</td>"
            f"<td><pre>{e['reqBody'] or ''}</pre></td>"
            f"<td><pre>{e['resBody'] or ''}</pre></td>"
            "</tr>"
        )
    html = """<!doctype html><html><head><meta charset="utf-8"><style>
      body{font-family:'Segoe UI',system-ui,sans-serif;background:#1e2430;color:#e6e9ef;margin:0;padding:16px}
      h1{font-size:15px;margin:0 0 10px}
      table{border-collapse:collapse;width:100%;font-size:11px}
      th,td{border:1px solid #3a4354;padding:4px 6px;text-align:left;vertical-align:top}
      th{background:#2a3242;color:#c3ccdb;position:sticky;top:0}
      td.u{color:#8fb3ff;word-break:break-all}
      pre{margin:0;white-space:pre-wrap;word-break:break-all;max-width:380px}
    </style></head><body>
      <h1>Network 证据 — INT-1070 快速复核（POST ai-review → 3s 轮询 ai-review-history → 落位）</h1>
      <table><tr><th>#</th><th>t</th><th>Method</th><th>URL</th><th>Status</th><th>Request body</th><th>Response body</th></tr>
    """ + "".join(rows) + "</table></body></html>"
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    console_errors = []
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    net = Net()
    net.attach(page)

    def wait_for(selector, timeout=45000, state="visible"):
        page.locator(selector).first.wait_for(state=state, timeout=timeout)

    def shot(name):
        page.screenshot(path=os.path.join(OUT, name), full_page=False)
        print("[shot]", name)

    def set_dark(on):
        page.evaluate("document.documentElement.classList.%s('dark')" % ("add" if on else "remove"))
        page.wait_for_timeout(900)

    # ===== 0. 进入报告 65 =====
    page.goto(BASE + "/#/report/65", wait_until="networkidle", timeout=60000)
    wait_for(".case-card", 60000)
    page.wait_for_timeout(2500)
    print("case cards:", page.locator(".case-card").count())
    print("review buttons:", page.locator(".review-action-btn").count())
    shot("r2-00-report-light.png")

    # ===== P2-2 + P2-1：快速复核发起 → 轮询 → 落位（无伪造 verdict） =====
    print("== 快速复核流程 ==")
    page.locator(".review-quick-btn").first.click()
    wait_for(".qreview-dialog", 10000)
    print("quick dialog note:", page.locator(".qreview-note").inner_text()[:80].replace("\n", " "))
    shot("r2-01-quick-idle.png")

    page.locator(".qreview-btn-primary").click()
    wait_for(".qreview-status, .qreview-running", 20000)
    page.wait_for_timeout(600)
    running_text = page.locator(".qreview-dialog").inner_text()
    print("after POST dialog text:", running_text.replace("\n", " ")[:160])
    assert ("复核中·passed" not in running_text and "复核中·复核" not in running_text), "running 记录伪造 verdict: " + running_text
    shot("r2-02-quick-running.png")

    # 等轮询落位（3s×N）→ 结论阶段
    deadline = time.time() + 40000
    while time.time() < deadline:
        page.wait_for_timeout(1500)
        t = page.locator(".qreview-dialog").inner_text()
        if ("复核失败" in t) or ("置信度" in t) or ("采纳为复核结果" in t):
            break
    page.wait_for_timeout(1200)
    settled = page.locator(".qreview-dialog").inner_text()
    print("settled dialog:", settled.replace("\n", " ")[:220])
    if "复核失败" in settled:
        assert ("·passed" not in settled) and ("复核通过" not in settled), "failed 记录伪造 verdict: " + settled
    shot("r2-03-quick-settled.png")
    page.locator(".qreview-close").click()
    wait_for(".qreview-dialog", 8000, state="hidden")

    # ===== P2-2：轮询请求证据 =====
    poll_gets = [e for e in net.entries if "/ai-review-history" in e["url"]]
    posts = [e for e in net.entries if e["method"] == "POST" and "/ai-review" in e["url"]
             and "/adopt" not in e["url"] and "/reject" not in e["url"]]
    print("ai-review-history GET count:", len(poll_gets), "| POST ai-review count:", len(posts))
    for e in posts:
        print("  POST", e["url"].replace(BASE, ""), "status", e["status"], "res:", (e["resBody"] or "")[:180])
    for e in poll_gets[:5]:
        print("  GET ", e["url"].replace(BASE, ""), "status", e["status"], "res:", (e["resBody"] or "")[:140])
    assert len(posts) >= 1, "未捕获 POST /ai-review"
    assert len(poll_gets) >= 1, "未捕获轮询 GET ai-review-history（P2-2 轮询缺失）"
    # 轮询时机：POST 后首个 ai-review-history GET（带 result_id 过滤）即为 §5.6 轮询，
    # 后端异步复检 ~2s 落位 → 首个 3s 轮询即命中终态（completed/failed），弹窗自动推进（无手动刷新）。

    # ===== P3-2：Network 证据截图 =====
    net_html = build_net_html(net, os.path.join(OUT, "network.html"))
    np = browser.new_page(viewport={"width": 1440, "height": 1000})
    np.goto("file:///" + net_html.replace("\\", "/"), wait_until="networkidle")
    np.wait_for_timeout(500)
    np.screenshot(path=os.path.join(OUT, "r2-04-network.png"))
    np.close()
    print("[shot] r2-04-network.png")

    # ===== P2-1：AI 复核会话上下文（已有结论行不得伪造 verdict） =====
    print("== AI 复核会话上下文 ==")
    try:
        r = page.request.post(BASE + "/api/v1/tasks/results/ai-review",
                              data=json.dumps({"result_ids": [3693]}),
                              headers={"Content-Type": "application/json"})
        print("direct POST ai-review status:", r.status)
    except Exception as e:
        print("direct POST fail:", e)
    page.locator(".review-ai-btn").first.click()
    wait_for(".ai-review-context-card", 15000)
    page.wait_for_timeout(400)
    ctx_text = page.locator(".ai-review-context-card").inner_text()
    print("context card:", ctx_text.replace("\n", " ")[:260])
    assert ("·passed" not in ctx_text) and ("·failed" not in ctx_text) and ("·uncertain" not in ctx_text), "上下文伪造 verdict: " + ctx_text
    shot("r2-05-session-context.png")
    page.locator('.session-icon-btn[title="关闭"]').first.click()
    try:
        wait_for(".ai-review-session-dialog", 6000, state="hidden")
    except Exception:
        page.keyboard.press("Escape")

    # ===== P2-1：复核历史抽屉 AI Tab（failed 记录不显 verdict pill） =====
    print("== 复核历史抽屉 AI Tab ==")
    badge = page.locator(".case-review-badge").first
    if badge.count() > 0:
        badge.click()
        wait_for(".rhd2-drawer", 10000)
        page.locator(".rhd2-tab", has_text="AI 复核").click()
        wait_for(".rhd2-item", 15000)
        page.wait_for_timeout(1000)
        ai_items = page.locator(".rhd2-item").count()
        verdict_pills = page.locator(".rhd2-ai-verdict").count()
        rejected_badges = page.locator(".rhd2-ai-rejected").count()
        print("AI items:", ai_items, "| verdict pills:", verdict_pills, "| rejected badges:", rejected_badges)
        assert verdict_pills == 0, "failed 记录显 verdict pill: %d" % verdict_pills
        print("first AI status:", page.locator(".rhd2-ai-status").first.inner_text())
        shot("r2-06-drawer-ai-tab.png")
        page.locator(".rhd2-close").click()
        wait_for(".rhd2-drawer", 8000, state="hidden")
    else:
        print("no badge — skip drawer")

    # ===== 深色 =====
    print("== dark ==")
    page.goto(BASE + "/#/report/65", wait_until="networkidle", timeout=60000)
    wait_for(".case-card", 60000)
    page.wait_for_timeout(2000)
    set_dark(True)
    shot("r2-07-report-dark.png")
    page.locator(".review-quick-btn").first.click()
    wait_for(".qreview-dialog", 10000)
    shot("r2-08-quick-dark.png")
    page.locator(".qreview-close").click()

    print("consoleErrors:", console_errors[:8])
    print("ALL DONE")
    browser.close()
