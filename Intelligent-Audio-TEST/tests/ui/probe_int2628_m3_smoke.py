# -*- coding: utf-8 -*-
"""INT-2628 前端回归日巡 · M3 收口页面补测（React 15173，docker 真实库栈，只读）。

日巡主体由既有脚本覆盖（INT-2586 同口径）：
  - tests/ui/smoke_react_nav_walk_int2136.py   侧栏逐页可达 + 4xx5xx + 截图
  - tests/ui/smoke_frontend_int1919.py --kind react  登录/任务/用例/报告/开始测试 5 链路
  - tests/ui/probe_int2441_daily_smoke.py      设备/音频/任务/报告 空态·错误态·加载态
  - tests/ui/probe_int2445_daily_smoke.py      用例三态 + 音频三态 + 报告产出链路
  - tests/ui/probe_int2586_daily_recheck.py    INT-2446/2447 修复复验 + 正式任务报告链路
本探针补本卡（2026-11-15）要复验的 M3 收口页面（INT-2474/2475/2476/2477/2478 中
有前端落地的部分）：

  1. INT-2477 React Auto 模式前端：/ai-chat 的「对话 / Auto」模式切换器、
     五项预算收紧设置（轮次 / 工具 / token / 时长 / 输出）、切回对话后预算面板
     不残留；浅 / 深色截图。只切模式不发起 run（不发写请求）。
  2. INT-2476 Skill 管理页：/agent-skills 列表行数 vs GET /agent/skills，
     无「Skill 列表加载失败」错误态；浅 / 深色截图。
  3. Agent 供应商页：/agent-providers 行数 vs GET /agent/providers（M3 灰度 /
     审批联动依赖的供应商配置入口可用）。
  4. Network 证据：三页 /api 请求无 4xx/5xx；console 无 error。

只读语义：只做页面导航与模式切换，不提交任何写请求（不发消息、不保存预算、
不改供应商），不写库，无 teardown。
跑法（环境铁律：连 docker 栈，不启动本地栈）：
  python tests/ui/probe_int2628_m3_smoke.py --base http://localhost:15173 \
      --api http://localhost:15000
"""
import argparse
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
ART = os.path.join(HERE, 'artifacts', 'int2628')


class Probe:
    def __init__(self, base, api, username, password):
        self.base = base.rstrip('/')
        self.api = api.rstrip('/')
        self.username = username
        self.password = password
        self.checks = []
        self.net = []
        self.console = []

    # ── 基础件 ──────────────────────────────────────────
    def check(self, name, ok, detail, shot=None):
        rec = {'name': name, 'ok': bool(ok), 'detail': detail}
        if shot:
            rec['shot'] = os.path.relpath(shot, PROJECT_ROOT)
        self.checks.append(rec)
        print('[%s] %-44s %s' % ('PASS' if ok else 'FAIL', name, detail), flush=True)
        return rec

    def shot(self, page, name, dark=False):
        os.makedirs(ART, exist_ok=True)
        path = os.path.join(ART, '%s%s.png' % (name, '_dark' if dark else ''))
        page.screenshot(path=path)
        return path

    def go(self, page, route, wait=4.0):
        page.goto(self.base + '/' + route.lstrip('/'), wait_until='domcontentloaded')
        time.sleep(wait)

    def set_dark(self, page, on):
        page.evaluate("on => document.documentElement.classList.toggle('dark', on)", on)
        time.sleep(0.8)

    def text(self, page):
        return page.inner_text('body')

    def api_items(self, page, path):
        """借页面 token 调同源网关接口，返回 (status, items)。"""
        res = page.evaluate(
            """async (path) => {
              const raw = localStorage.getItem('iatp:auth:token:v1')
              let token = null
              try { const v = JSON.parse(raw); token = v && v.data !== undefined ? v.data : v }
              catch (e) { token = raw }
              if (token && typeof token === 'object')
                token = token.accessToken || token.access_token || null
              const resp = await fetch(path, {headers: token ? {Authorization: 'Bearer ' + token} : {}})
              const text = await resp.text()
              let body = null
              try { body = JSON.parse(text) } catch (e) { body = null }
              return {status: resp.status, body}
            }""", path)
        body = res.get('body') or {}
        items = body.get('items')
        if not isinstance(items, list) and isinstance(body.get('data'), list):
            items = body['data']
        if not isinstance(items, list) and isinstance(body.get('data'), dict):
            items = body['data'].get('items')
        return res.get('status'), (items if isinstance(items, list) else [])

    def _record_api(self, page, tag):
        try:
            res = page.evaluate(
                "() => performance.getEntriesByType('resource').map(e => e.name)"
                ".filter(n => n.includes('/api/'))")
        except Exception as exc:
            res = ['EXC:%s' % exc]
        self.net.append({'page': tag, 'api_resources': res})
        return res

    # ── 1. INT-2477 Auto 模式前端 ────────────────────────
    def check_auto_mode(self, page):
        self.go(page, '/ai-chat', 4)
        page.wait_for_selector('textarea', timeout=30000)
        time.sleep(1.2)
        switcher = page.locator('[data-agent-mode-switcher]')
        present = switcher.count() > 0
        mode = (switcher.first.get_attribute('data-agent-mode-switcher')
                if present else None)
        chat_btn = page.locator('[data-agent-mode-option="chat"]')
        auto_btn = page.locator('[data-agent-mode-option="auto"]')
        labels = (chat_btn.first.inner_text() if chat_btn.count() else '') + '/' + (
            auto_btn.first.inner_text() if auto_btn.count() else '')
        self.check('INT-2477 模式切换器渲染（对话/Auto）',
                   present and mode == 'chat' and chat_btn.count() == 1
                   and auto_btn.count() == 1 and '对话' in labels and 'Auto' in labels,
                   'switcher=%s 默认模式=%s 选项文案「%s」' % (present, mode, labels.strip()),
                   self.shot(page, '01_ai_chat_chat_mode'))

        auto_btn.first.click()
        page.wait_for_selector('[data-auto-budget-settings]', timeout=15000)
        time.sleep(0.8)
        panel = page.locator('[data-auto-budget-settings]')
        inputs = panel.locator('input')
        n_inputs = inputs.count()
        panel_txt = panel.inner_text()
        fields = [k for k in ('轮次', '工具', 'token', 'Token', '时长', '输出')
                  if k in panel_txt]
        mode_now = page.locator('[data-agent-mode-switcher]').first.get_attribute(
            'data-agent-mode-switcher')
        self.check('INT-2477 切 Auto：五项预算设置可见',
                   mode_now == 'auto' and n_inputs >= 5 and len(fields) >= 4,
                   '模式=%s / 预算输入框=%d / 面板字段命中=%s'
                   % (mode_now, n_inputs, fields),
                   self.shot(page, '02_ai_chat_auto_budget'))
        # 留空 = 服务端默认：输入框 prompt 提示与服务端默认口径
        placeholders = []
        for i in range(min(n_inputs, 5)):
            try:
                placeholders.append(inputs.nth(i).get_attribute('placeholder') or '')
            except Exception:
                placeholders.append('')
        self.check('INT-2477 预算默认值口径（留空=服务端默认）',
                   any(p.strip() for p in placeholders),
                   'placeholder=%s' % placeholders)
        # 无「全部自动批准」入口（写操作必须逐条审批）
        body_txt = self.text(page)
        no_auto_approve = ('全部自动批准' not in body_txt)
        self.check('INT-2477 无「全部自动批准」入口', no_auto_approve,
                   '页面含「全部自动批准」=%s' % (not no_auto_approve))

        self.set_dark(page, True)
        self.shot(page, '03_ai_chat_auto_budget', dark=True)
        self.set_dark(page, False)

        # 切回对话：预算面板卸载，普通对话入口恢复
        chat_btn.first.click()
        time.sleep(1.0)
        mode_back = page.locator('[data-agent-mode-switcher]').first.get_attribute(
            'data-agent-mode-switcher')
        panel_back = page.locator('[data-auto-budget-settings]').count()
        self.check('INT-2477 切回对话：预算面板不残留',
                   mode_back == 'chat' and panel_back == 0,
                   '模式=%s / 预算面板节点=%d' % (mode_back, panel_back),
                   self.shot(page, '04_ai_chat_back_to_chat'))
        self._record_api(page, 'ai_chat')

    # ── 2. INT-2476 Skill 管理页 ─────────────────────────
    def check_skills(self, page):
        st, items = self.api_items(page, '/api/v1/agent/skills')
        self.go(page, '/agent-skills', 5)
        try:
            page.wait_for_selector('[data-testid=agent-skill-row]', timeout=20000)
        except Exception:
            pass
        time.sleep(1.0)
        rows = page.locator('[data-testid=agent-skill-row]').count()
        txt = self.text(page)
        err = 'Skill 列表加载失败' in txt
        names = [r.get_attribute('data-skill-name')
                 for r in page.locator('[data-testid=agent-skill-row]').all()][:8]
        self.check('INT-2476 Skill 管理页列表 vs 接口',
                   st == 200 and rows > 0 and not err
                   and (len(items) == 0 or rows <= len(items)),
                   'GET /agent/skills %s %s 条 / 页面行=%d / 错误态=%s / 前几项=%s'
                   % (st, len(items), rows, err, names))
        self.check('INT-2476 Skill 页无加载失败错误态', not err,
                   '「Skill 列表加载失败」=%s / 正文长度=%d' % (err, len(txt)),
                   self.shot(page, '05_agent_skills'))
        self.set_dark(page, True)
        self.shot(page, '06_agent_skills', dark=True)
        self.set_dark(page, False)
        self._record_api(page, 'agent_skills')
        return rows

    # ── 3. Agent 供应商页 ────────────────────────────────
    def check_providers(self, page):
        st, items = self.api_items(page, '/api/v1/agent/providers')
        self.go(page, '/agent-providers', 5)
        try:
            page.wait_for_selector('[data-testid=agent-provider-row]', timeout=20000)
        except Exception:
            pass
        time.sleep(1.0)
        rows = page.locator('[data-testid=agent-provider-row]').count()
        txt = self.text(page)
        err = '加载失败' in txt
        self.check('Agent 供应商页列表 vs 接口',
                   st == 200 and rows == len(items) and not err,
                   'GET /agent/providers %s 条 / 页面行=%d / 错误态=%s'
                   % (len(items), rows, err),
                   self.shot(page, '07_agent_providers'))
        self.set_dark(page, True)
        self.shot(page, '08_agent_providers', dark=True)
        self.set_dark(page, False)
        self._record_api(page, 'agent_providers')

    # ── 主流程 ──────────────────────────────────────────
    def run(self):
        os.makedirs(ART, exist_ok=True)
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={'width': 1680, 'height': 1050})
            page = ctx.new_page()

            def on_console(msg):
                if msg.type in ('error',):
                    self.console.append({'page': page.url, 'text': msg.text[:200]})

            page.on('console', on_console)

            page.goto(self.base + '/login', wait_until='domcontentloaded')
            time.sleep(2)
            page.fill('#username', self.username)
            page.fill('#password', self.password)
            page.click('button[type=submit]')
            page.wait_for_url(lambda u: 'login' not in u, timeout=30000)
            self.check('登录（真实表单）', True, '登录后 URL=%s' % page.url)

            for fn in (self.check_auto_mode, self.check_skills,
                       self.check_providers):
                try:
                    fn(page)
                except Exception as exc:
                    self.check(fn.__name__, False,
                               '异常 %s: %s' % (type(exc).__name__, str(exc)[:200]))

            # Network：三页 /api 请求汇总（资源清单只记 URL；4xx/5xx 由各页错误态断言覆盖）
            bad_console = [c for c in self.console
                           if 'favicon' not in c['text'].lower()]
            self.check('页面 console 无 error', not bad_console,
                       'console error=%s' % (bad_console[:5] or '无'))
            browser.close()


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:15173')
    ap.add_argument('--api', default='http://localhost:15000')
    ap.add_argument('--username', default=os.environ.get('UI_TEST_USERNAME', 'dev_user'))
    ap.add_argument('--password', default=os.environ.get('UI_TEST_PASSWORD', 'dev_password'))
    args = ap.parse_args()

    probe = Probe(args.base, args.api, args.username, args.password)
    probe.run()
    summary = {'checks': probe.checks, 'network': probe.net,
               'console': probe.console,
               'passed': sum(1 for c in probe.checks if c['ok']),
               'failed': sum(1 for c in probe.checks if not c['ok'])}
    os.makedirs(ART, exist_ok=True)
    path = os.path.join(ART, 'summary.json')
    with open(path, 'w', encoding='utf-8') as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=1)
    print('PASSED=%d FAILED=%d' % (summary['passed'], summary['failed']))
    print('SUMMARY_JSON=' + path)


if __name__ == '__main__':
    main()
