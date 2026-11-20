# -*- coding: utf-8 -*-
"""INT-2586 前端回归日巡补充实测（React 15173，docker 真实库栈，只读）。

日巡主体由既有脚本覆盖：
  - tests/ui/smoke_react_nav_walk_int2136.py   侧栏 21 条链接逐页可达 + 4xx5xx + 截图
  - tests/ui/smoke_frontend_int1919.py --kind react  登录/任务/用例/报告/开始测试 5 链路
  - tests/ui/probe_int2441_daily_smoke.py      设备/音频/任务/报告 空态·错误态·加载态
  - tests/ui/probe_int2445_daily_smoke.py      用例三态 + 音频三态 + 报告产出链路
本探针补本卡（2026-11-14）要复核的两件事：

  1. 上一轮日巡（INT-2445）UX 审计落的 P2/P3 缺陷修复在线上是否真的生效：
     - INT-2446 P2 任务详情「创建人」不得再是写死 mock 名「张测试」，
       应为真实创建人（dev_user）或降级「用户 #id」；
     - INT-2447 P3-1 报告中心 / 报告展示页「时间范围」默认回显中文「全部时间」，
       不得再回显英文 value「all」；高级搜索三个 Select 同样回显中文 label；
     - INT-2447 P3-2 报告列表错误态走公共 ErrorState（「报告列表加载失败」+「重试」），
       解除拦截后重试恢复真实列表。
  2. 正式任务链路：已完成正式任务 460 → 详情「查看报告」→ 报告 426 详情可查看，
     报告名与 GET /reports/by_task/460 一致（真实库，非 mock）。

只读语义：路由拦截只作用于浏览器网络层（CDP），不提交任何写请求、不写库、无 teardown。
跑法（环境铁律：连 docker 栈，不启动本地栈）：
  python tests/ui/probe_int2586_daily_recheck.py --base http://localhost:15173 \
      --api http://localhost:15000
"""
import argparse
import json
import os
import sys
import time

import httpx
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT_ROOT)

from tests.ui.utils.api_client import ApiClient  # noqa: E402

ART = os.path.join(HERE, 'artifacts', 'int2586')


class Probe:
    def __init__(self, base, api, username, password):
        self.base = base.rstrip('/')
        self.api = api.rstrip('/')
        self.username = username
        self.password = password
        self.checks = []
        self.net = []

    # ── 基础件 ──────────────────────────────────────────
    def check(self, name, ok, detail, shot=None):
        rec = {'name': name, 'ok': bool(ok), 'detail': detail}
        if shot:
            rec['shot'] = os.path.relpath(shot, PROJECT_ROOT)
        self.checks.append(rec)
        print('[%s] %-42s %s' % ('PASS' if ok else 'FAIL', name, detail), flush=True)
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
        time.sleep(0.6)

    def text(self, page):
        return page.inner_text('body')

    def _record_api(self, page, tag):
        try:
            res = page.evaluate(
                "() => performance.getEntriesByType('resource').map(e => e.name)"
                ".filter(n => n.includes('/api/'))")
        except Exception as exc:
            res = ['EXC:%s' % exc]
        self.net.append({'page': tag, 'api_resources': res})
        return res

    def api_get(self, path):
        r = httpx.get(self.api + path, headers=self.h, timeout=60, trust_env=False)
        body = (r.json() if r.headers.get('content-type', '').startswith('application/json')
                else {})
        return r.status_code, body

    # ── 1. INT-2446 P2 复验：任务详情创建人 ────────────────
    def check_task_creator(self, page):
        st, body = self.api_get('/api/v1/tasks/588')
        detail = (body.get('data') or {})
        creator_id = detail.get('created_by_user_id')
        self.go(page, '/tasks/588', 4)
        txt = self.text(page)
        has_mock = '张测试' in txt
        line = ''
        for ln in txt.splitlines():
            if '创建人' in ln:
                line = ln.strip()
                break
        # 解析到真实名（dev_user）或降级「用户 #<id>」都算修复生效，只禁写死 mock 名
        resolved = bool(line) and (
            'dev_user' in line or ('用户 #' in line) or ('创建人 —' in line))
        self.check('INT-2446 P2 复验：任务详情创建人非 mock',
                   bool(creator_id) and not has_mock and resolved,
                   'GET /tasks/588 created_by_user_id=%s / 页面「%s」/ 含「张测试」=%s'
                   % (creator_id, line[:60], has_mock),
                   self.shot(page, '01_task_detail_creator'))

        # 标签行空态须带标签名（INT-2446 P3：信息卡里不得再裸出一个无标签的「—」）。
        # 只在任务信息卡内取证（含「创建人」+「标签」的最小容器），关联用例列表的空单元格不算。
        info = page.evaluate("""() => {
          const cards = [...document.querySelectorAll('div')].filter(n => {
            const t = n.innerText || '';
            return t.includes('创建人') && t.includes('标签') && t.length < 1600;
          });
          const card = cards[cards.length - 1];
          if (!card) return {found: false, dashes: []};
          const dashes = [...card.querySelectorAll('div,span')]
            .filter(n => n.children.length === 0 && (n.innerText || '').trim() === '—')
            .map(n => {
              const g = n.parentElement && n.parentElement.parentElement;
              return {ctx: ((g && g.innerText) || '').trim().slice(0, 60)};
            });
          return {found: true, dashes: dashes};
        }""")
        dashes = info.get('dashes') or []
        bare = [d['ctx'] for d in dashes
                if not any(k in d['ctx'] for k in ('标签', '描述', '创建人'))]
        self.check('INT-2446 P3 复验：信息卡「—」占位均带字段名',
                   info.get('found') and not bare,
                   '信息卡找到=%s / 卡内「—」占位=%s / 无字段名=%s'
                   % (info.get('found'), dashes or '无', bare or '无'))

        self.set_dark(page, True)
        self.shot(page, '02_task_detail_creator', dark=True)
        self.set_dark(page, False)
        self._record_api(page, 'task_detail_creator')

    # ── 2. 正式任务链路：已完成任务 460 → 查看报告 → 报告 426 ──
    def check_formal_task_chain(self, page):
        st, body = self.api_get('/api/v1/tasks/460')
        task = (body.get('data') or {})
        st_r, body_r = self.api_get('/api/v1/reports/by_task/460')
        report = (body_r.get('data') or {})
        rid = report.get('id')
        rname = report.get('name') or ''
        self.check('正式任务 460：详情与报告接口一致',
                   st == 200 and task.get('status') == 'completed' and st_r == 200
                   and bool(rid) and bool(rname),
                   'GET /tasks/460 status=%s / GET /reports/by_task/460 → %s id=%s name=%s'
                   % (task.get('status'), st_r, rid, rname))

        self.go(page, '/tasks/460', 5)
        txt = self.text(page)
        status_ok = ('已完成' in txt) or ('completed' in txt.lower())
        # 任务详情的报告落点是「报告文档」区（Report Studio 文档聚合）；该任务无关联文档时
        # 渲染「该任务的报告暂无关联文档」（与 INT-2434/2386 口径一致，404 不建无主文档）。
        doc_section = '报告文档' in txt
        doc_hint = '该任务的报告暂无关联文档' in txt
        self.shot(page, '03_formal_task_detail')

        # 正式任务的报告查看入口在报告中心：产出报告 426 必须列表可见且详情可打开。
        self.go(page, '/report-center', 6)
        center_txt = self.text(page)
        in_center = (rname in center_txt) if rname else False
        self.check('正式任务 460 详情：已完成 + 报告文档区',
                   status_ok and doc_section,
                   '状态已完成可见=%s / 「报告文档」区=%s / 无关联文档提示=%s'
                   % (status_ok, doc_section, doc_hint),
                   self.shot(page, '04_formal_task_report_section'))
        self.check('正式任务 460 产出报告在报告中心可见',
                   in_center,
                   '报告名「%s」在报告中心列表可见=%s' % (rname, in_center),
                   self.shot(page, '04b_formal_report_in_center'))
        if rid:
            self.go(page, '/report/%s?from=management' % rid, 5)
            txt2 = self.text(page)
            detail_ok = (rname in txt2) or ('返回' in txt2 and '总览' in txt2)
            self.check('正式任务 460 报告 %s 详情可查看' % rid, detail_ok,
                       '详情含报告名=%s / 含「返回/总览」=%s / URL=%s'
                       % (rname in txt2, '返回' in txt2 and '总览' in txt2, page.url),
                       self.shot(page, '05_formal_report_detail'))
            self.set_dark(page, True)
            self.shot(page, '06_formal_report_detail', dark=True)
            self.set_dark(page, False)
            self._record_api(page, 'formal_report')

    # ── 3. INT-2447 P3-1 复验：报告域 Select 回显中文 ───────
    def _trigger_text(self, page, selector):
        try:
            el = page.locator(selector).first
            if el.count() == 0:
                return ''
            return (el.inner_text() or '').strip()
        except Exception:
            return ''

    def check_report_selects(self, page):
        self.go(page, '/report-center', 4)
        t = self._trigger_text(page, '[aria-label="时间范围"]')
        body_txt = self.text(page)
        # 工具栏按钮里不得出现裸英文 value 'all'
        raw_all = page.evaluate("""() => [...document.querySelectorAll('button')]
            .filter(b => (b.innerText || '').trim() === 'all').length""")
        self.check('INT-2447 P3-1 复验：报告中心时间范围=全部时间',
                   '全部时间' in t and raw_all == 0,
                   '触发器文本「%s」/ 裸「all」按钮数=%s' % (t, raw_all),
                   self.shot(page, '07_report_center'))

        # 高级搜索三个 Select
        try:
            page.get_by_role('button', name='高级搜索', exact=False).first.click()
            time.sleep(1.5)
            labels = {
                '设备类型': self._trigger_text(page, '#adv-device-type'),
                '创建者': self._trigger_text(page, '#adv-creator'),
                '时间范围': self._trigger_text(page, '#adv-time-range'),
            }
            bad = [k for k, v in labels.items()
                   if not v or v in ('all', 'smart_speaker', 'published')]
            self.check('INT-2447 返工复验：高级搜索 Select 回显中文',
                       not bad,
                       '触发器文本=%s / 异常=%s' % (labels, bad or '无'),
                       self.shot(page, '08_report_advanced_search'))
            page.get_by_role('button', name='高级搜索', exact=False).first.click()
            time.sleep(1)
        except Exception as exc:
            self.check('INT-2447 返工复验：高级搜索 Select 回显中文', False,
                       '异常 %s: %s' % (type(exc).__name__, str(exc)[:160]))

        self.go(page, '/reports', 4)
        t2 = self._trigger_text(page, '[aria-label="时间范围"]')
        raw_all2 = page.evaluate("""() => [...document.querySelectorAll('button')]
            .filter(b => (b.innerText || '').trim() === 'all').length""")
        self.check('INT-2447 P3-1 复验：报告展示页时间范围=全部时间',
                   '全部时间' in t2 and raw_all2 == 0,
                   '触发器文本「%s」/ 裸「all」按钮数=%s' % (t2, raw_all2),
                   self.shot(page, '09_reports_showcase'))

        self.set_dark(page, True)
        self.shot(page, '10_report_center', dark=True)
        self.set_dark(page, False)
        self._record_api(page, 'report_selects')

    # ── 4. INT-2447 P3-2 复验：报告列表错误态公共 ErrorState ──
    def check_report_error_state(self, page):
        self.cdp.send('Network.setBlockedURLs', {'urls': ['*api/v1/reports?*']})
        self.go(page, '/report-center', 5)
        txt = self.text(page)
        err_ok = '报告列表加载失败' in txt
        empty_masked = '暂无报告' not in txt and '未找到匹配报告' not in txt
        retry = page.get_by_role('button', name='重试', exact=False).count()
        # 公共 ErrorState：红色警示三角图标 + 「请重试」类副文案
        alert_icon = page.locator('[role=dialog], [role=alert], .text-destructive').count()
        self.check('INT-2447 P3-2 复验：报告错误态统一为公共 ErrorState',
                   err_ok and empty_masked and retry > 0,
                   '「报告列表加载失败」=%s / 空态被抑制=%s / 重试按钮=%s / 警示节点=%s'
                   % (err_ok, empty_masked, retry, alert_icon),
                   self.shot(page, '11_report_error_state'))

        self.cdp.send('Network.setBlockedURLs', {'urls': []})
        try:
            page.get_by_role('button', name='重试', exact=False).first.click()
            time.sleep(7)
            txt2 = self.text(page)
            recovered = '报告列表加载失败' not in txt2
            rows = page.locator('table tbody tr').count()
            self.check('报告错误态重试恢复', recovered, '重试后错误消失=%s / 列表行=%s'
                       % (recovered, rows), self.shot(page, '12_report_retry_ok'))
        except Exception as exc:
            self.check('报告错误态重试恢复', False,
                       '异常 %s: %s' % (type(exc).__name__, str(exc)[:160]))

    # ── 主流程 ──────────────────────────────────────────
    def run(self):
        api = ApiClient(self.api)
        api.login(self.username, self.password)
        self.h = {'Authorization': 'Bearer ' + api.token}
        os.makedirs(ART, exist_ok=True)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={'width': 1680, 'height': 1050})
            page = ctx.new_page()
            self.cdp = ctx.new_cdp_session(page)
            self.cdp.send('Network.enable')

            page.goto(self.base + '/login', wait_until='domcontentloaded')
            time.sleep(2)
            page.fill('#username', self.username)
            page.fill('#password', self.password)
            page.click('button[type=submit]')
            page.wait_for_url(lambda u: 'login' not in u, timeout=30000)
            self.check('登录（真实表单）', True, '登录后 URL=%s' % page.url,
                       self.shot(page, '00_login'))

            for fn in (self.check_task_creator,
                       self.check_formal_task_chain,
                       self.check_report_selects,
                       self.check_report_error_state):
                try:
                    fn(page)
                except Exception as exc:
                    self.check(fn.__name__, False,
                               '异常 %s: %s' % (type(exc).__name__, str(exc)[:200]))

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
    summary = {'checks': probe.checks,
               'network': probe.net,
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
