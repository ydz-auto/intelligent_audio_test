# -*- coding: utf-8 -*-
"""INT-2441 前端回归日巡补充实测（React 15173，docker 真实库栈，只读）。

日巡卡要求核心页含「列表 / 详情 / 弹窗 / 空态 / 错误态」，登录 → 任务 → 用例 →
报告 关键链路与全站导航由既有脚本覆盖：
  - tests/ui/smoke_react_nav_walk_int2136.py（20 页侧栏逐页）
  - tests/ui/smoke_frontend_int1919.py --kind react（登录/任务/用例/报告/开始测试 5 链路）
本探针补它们没固化的部分（Playwright，断言「可见状态」而不只看 DOM）：

  1. 设备管理：列表行数 vs GET /test-devices total；行菜单 → 详情弹窗；
     添加设备弹窗；编辑抽屉（弹窗族）；
  2. 设备管理空态：搜索框填必不存在的关键词 → 「未找到匹配的设备」空态可见
     （真实库里 6 台设备清不掉，0 条空库状态无法在不写库的前提下构造，故用筛选
     无匹配这一同类空态；两者共用同一 Empty 组件分支）；
  3. 设备管理错误态：CDP Network.setBlockedURLs 拦掉列表请求 → 「设备列表加载失败」
     + 重试，解除拦截后点重试恢复真实列表；
  4. 设备管理加载态：CDP 网络延迟 2.5s → 骨架屏（data-slot=skeleton）可见；
  5. 音频管理：列表行数 / 「共 N 个」vs GET /audios total；行菜单 → 详情编辑弹窗；
  6. 任务 / 报告中心：可见计数 vs 接口 total（真实库一致性）；
  7. 报告中心错误态（列表请求被拦截 → 「报告列表加载失败」不落「暂无报告」）、
     报告中心空态（筛选无匹配 → 「未找到匹配报告」）、任务页错误态（列表被拦截
     → 「任务列表加载失败」）；
  8. 设备 + 音频浅色 / 深色截图，全程 Network 证据（浏览器 perf 资源清单）。

只读语义：路由拦截只作用于浏览器网络层（CDP），不提交任何写请求，不写库，
无 teardown 清理。跑法（环境铁律：连 docker 栈，不启动本地栈）：
  python tests/ui/probe_int2441_daily_smoke.py --base http://localhost:15173 \
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

ART = os.path.join(HERE, 'artifacts', 'int2441')


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
        print('[%s] %-38s %s' % ('PASS' if ok else 'FAIL', name, detail))
        return rec

    def shot(self, page, name, dark=False):
        os.makedirs(ART, exist_ok=True)
        path = os.path.join(ART, '%s%s.png' % (name, '_dark' if dark else ''))
        page.screenshot(path=path)
        return path

    def go(self, page, route, wait=3.5):
        page.goto(self.base + '/' + route.lstrip('/'), wait_until='domcontentloaded')
        time.sleep(wait)

    def set_dark(self, page, on):
        page.evaluate("on => document.documentElement.classList.toggle('dark', on)", on)
        time.sleep(0.6)

    def _record_api(self, page, tag):
        """记录当前文档真实发出的 /api 资源（证明走真实网关、无 mock）。"""
        try:
            res = page.evaluate(
                "() => performance.getEntriesByType('resource').map(e => e.name)"
                ".filter(n => n.includes('/api/'))")
        except Exception as exc:
            res = ['EXC:%s' % exc]
        self.net.append({'page': tag, 'api_resources': res})
        return res

    def api_get(self, path):
        r = httpx.get(self.api + path, headers=self.h, timeout=30, trust_env=False)
        return r.status_code, (r.json() if r.headers.get('content-type', '').startswith('application/json') else {})

    @staticmethod
    def _visible(page, text, timeout=8):
        try:
            page.get_by_text(text, exact=False).first.wait_for(state='visible', timeout=timeout * 1000)
            return True
        except Exception:
            return False

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

            # 1) 登录
            page.goto(self.base + '/login', wait_until='domcontentloaded')
            time.sleep(2)
            page.fill('#username', self.username)
            page.fill('#password', self.password)
            page.click('button[type=submit]')
            page.wait_for_url(lambda u: 'login' not in u, timeout=30000)
            self.check('登录（真实表单）', True, '登录后 URL=%s' % page.url,
                       self.shot(page, '01_login'))

            self.check_devices(page)
            self.check_audio(page)
            self.check_counts(page)
            self.check_states_extra(page)
            browser.close()

    # ── 设备管理 ────────────────────────────────────────
    def check_devices(self, page):
        self._cur_page = 'devices'
        st, body = self.api_get('/api/v1/test-devices?page=1&per_page=1000')
        api_total = (body.get('data') or {}).get('total')
        self.go(page, '/devices', 4)
        rows = page.locator('tbody tr').count()
        page_text = page.inner_text('body')
        self.check('设备列表：行数与接口一致',
                   st == 200 and rows == api_total and str(api_total) in page_text,
                   'API total=%s / 页面行数=%s / 页脚「共 %s 条」=%s'
                   % (api_total, rows, api_total, ('共 %s 条' % api_total) in page_text),
                   self.shot(page, '02_devices_list_light'))

        # 详情弹窗
        page.locator('button[aria-label^="操作 "]').first.click()
        time.sleep(0.8)
        page.get_by_role('menuitem', name='详情', exact=True).first.click()
        time.sleep(1.5)
        dlg = page.locator('[role=dialog]').first
        dlg_visible = dlg.is_visible()
        dlg_text = dlg.inner_text()[:300].replace('\n', ' | ') if dlg_visible else ''
        self.check('设备详情弹窗', dlg_visible and len(dlg_text) > 10,
                   '弹窗可见=%s 内容=%s' % (dlg_visible, dlg_text[:160]),
                   self.shot(page, '03_devices_detail'))
        page.keyboard.press('Escape')
        time.sleep(0.8)

        # 添加设备弹窗（只打开不提交）
        page.get_by_role('button', name='添加设备', exact=True).first.click()
        time.sleep(1.5)
        add_dlg = page.locator('[role=dialog]').first
        add_visible = add_dlg.is_visible()
        add_text = add_dlg.inner_text()[:200].replace('\n', ' | ') if add_visible else ''
        self.check('添加设备弹窗（不提交）', add_visible and len(add_text) > 10,
                   '弹窗可见=%s 内容=%s' % (add_visible, add_text[:140]),
                   self.shot(page, '04_devices_add_modal'))
        page.keyboard.press('Escape')
        time.sleep(0.8)

        # 编辑抽屉
        page.locator('button[aria-label^="操作 "]').first.click()
        time.sleep(0.8)
        page.get_by_role('menuitem', name='编辑', exact=True).first.click()
        time.sleep(1.5)
        edit_open = page.locator('[role=dialog]').first.is_visible() or page.locator('[data-slot=sheet-content]').first.is_visible()
        edit_text = ''
        if edit_open:
            loc = page.locator('[role=dialog]').first if page.locator('[role=dialog]').first.is_visible() else page.locator('[data-slot=sheet-content]').first
            edit_text = loc.inner_text()[:200].replace('\n', ' | ')
        self.check('设备编辑抽屉（不提交）', edit_open and len(edit_text) > 10,
                   '抽屉可见=%s 内容=%s' % (edit_open, edit_text[:140]),
                   self.shot(page, '05_devices_edit'))
        page.keyboard.press('Escape')
        time.sleep(0.8)

        # 深色截图
        self.set_dark(page, True)
        self.shot(page, '06_devices_list', dark=True)
        self.set_dark(page, False)

        # 空态：搜索一个必不存在的关键词（同类 Empty 分支）
        search = page.locator('input[placeholder="搜索设备名称或型号"]').first
        search.fill('ZZZ_不存在_%d' % int(time.time()))
        time.sleep(2.5)
        empty_ok = page.get_by_text('未找到匹配的设备', exact=False).first.is_visible()
        empty_rows = page.locator('tbody tr').count()
        self.check('设备空态（筛选无匹配）', empty_ok and empty_rows == 0,
                   '「未找到匹配的设备」可见=%s；行数=%s' % (empty_ok, empty_rows),
                   self.shot(page, '07_devices_empty'))
        search.fill('')
        time.sleep(2)

        # 错误态 + 重试恢复（CDP 拦截列表请求，模拟接口不可用）
        self.cdp.send('Network.setBlockedURLs', {'urls': ['*api/v1/test-devices?*']})
        self.go(page, '/devices/test', 4)
        err_ok = page.get_by_text('设备列表加载失败', exact=False).first.is_visible()
        empty_masked = not page.get_by_text('暂无设备', exact=True).first.is_visible()
        self.check('设备错误态（列表请求被拦截）', err_ok and empty_masked,
                   '「设备列表加载失败」可见=%s；空态被抑制=%s' % (err_ok, empty_masked),
                   self.shot(page, '08_devices_error'))
        self.cdp.send('Network.setBlockedURLs', {'urls': []})
        page.get_by_role('button', name='重试', exact=False).first.click()
        time.sleep(4)
        recovered = page.locator('tbody tr').count()
        self.check('设备错误态重试恢复', recovered == api_total,
                   '点「重试」后行数=%s（API total=%s）' % (recovered, api_total),
                   self.shot(page, '09_devices_retry_ok'))

        # 加载态（CDP 网络延迟 2.5s）
        self.cdp.send('Network.emulateNetworkConditions',
                      {'offline': False, 'latency': 2500,
                       'downloadThroughput': -1, 'uploadThroughput': -1})
        page.goto(self.base + '/devices/test', wait_until='domcontentloaded')
        time.sleep(3)
        skeleton = page.locator('[data-slot=skeleton]').count()
        self.check('设备加载态（延迟 2.5s）', skeleton > 0,
                   '骨架屏节点数=%s' % skeleton,
                   self.shot(page, '10_devices_loading'))
        self.cdp.send('Network.emulateNetworkConditions',
                      {'offline': False, 'latency': 0,
                       'downloadThroughput': -1, 'uploadThroughput': -1})
        time.sleep(4)
        self._record_api(page, 'devices')
        self._cur_page = ''

    # ── 音频管理 ────────────────────────────────────────
    def check_audio(self, page):
        self._cur_page = 'audio'
        st, body = self.api_get('/api/v1/audios?page=1&per_page=20')
        data = body.get('data') or {}
        api_total = data.get('total')
        self.go(page, '/audio-import', 4.5)
        rows = page.locator('tbody tr').count()
        text = page.inner_text('body')
        count_ok = ('共 %s 个' % api_total) in text
        self.check('音频列表：总数与接口一致',
                   st == 200 and count_ok and rows > 0,
                   'API total=%s / 页面「共 %s 个」=%s / 行数=%s'
                   % (api_total, api_total, count_ok, rows),
                   self.shot(page, '11_audio_list_light'))

        page.locator('button[aria-label^="音频 "]').first.click()
        time.sleep(0.8)
        page.get_by_role('menuitem', name='详情 / 编辑元数据', exact=True).first.click()
        time.sleep(2)
        dlg = page.locator('[role=dialog]').first
        vis = dlg.is_visible()
        txt = dlg.inner_text()[:300].replace('\n', ' | ') if vis else ''
        self.check('音频详情 / 编辑弹窗', vis and len(txt) > 10,
                   '弹窗可见=%s 内容=%s' % (vis, txt[:160]),
                   self.shot(page, '12_audio_detail'))
        page.keyboard.press('Escape')
        time.sleep(0.8)
        self.set_dark(page, True)
        self.shot(page, '13_audio_list', dark=True)
        self.set_dark(page, False)
        self._record_api(page, 'audio')
        self._cur_page = ''

    # ── 任务 / 报告中心计数 ─────────────────────────────
    def check_counts(self, page):
        self._cur_page = 'counts'
        st, body = self.api_get('/api/v1/tasks?page=1&per_page=5')
        total = (body.get('data') or {}).get('total')
        self.go(page, '/tasks', 4)
        text = page.inner_text('body')
        ok = st == 200 and total is not None and ('%s' % total) in text
        self.check('任务页计数与接口一致', ok,
                   'API total=%s / 页面含该数字=%s' % (total, ok),
                   self.shot(page, '14_tasks_list'))

        st2, body2 = self.api_get('/api/v1/reports?page=1&per_page=5')
        total2 = (body2.get('data') or {}).get('total')
        self.go(page, '/report-center', 4)
        text2 = page.inner_text('body')
        ok2 = st2 == 200 and total2 is not None and ('%s' % total2) in text2
        self.check('报告中心计数与接口一致', ok2,
                   'API total=%s / 页面含该数字=%s' % (total2, ok2),
                   self.shot(page, '15_report_center'))
        self._record_api(page, 'report_center')
        self._cur_page = ''

    # ── 报告中心 / 任务页 空态与错误态 ──────────────────
    def check_states_extra(self, page):
        self._cur_page = 'states_extra'
        # 报告中心错误态
        self.cdp.send('Network.setBlockedURLs', {'urls': ['*api/v1/reports?*']})
        self.go(page, '/report-center', 4)
        body = page.inner_text('body')
        ok = '报告列表加载失败' in body and '暂无报告' not in body
        self.check('报告中心错误态（列表被拦截）', ok,
                   '「报告列表加载失败」可见=%s；空态被抑制=%s'
                   % ('报告列表加载失败' in body, '暂无报告' not in body),
                   self.shot(page, '16_report_center_error'))
        self.cdp.send('Network.setBlockedURLs', {'urls': []})

        # 报告中心空态（筛选无匹配）
        self.go(page, '/report-center', 4)
        search = page.locator('input[placeholder*="搜索"]').first
        search.fill('ZZZ_不存在_%d' % int(time.time()))
        time.sleep(2.5)
        body2 = page.inner_text('body')
        ok2 = '未找到匹配报告' in body2
        self.check('报告中心空态（筛选无匹配）', ok2,
                   '「未找到匹配报告」可见=%s' % ok2,
                   self.shot(page, '17_report_center_empty'))

        # 任务页错误态
        self.cdp.send('Network.setBlockedURLs', {'urls': ['*api/v1/tasks?*']})
        self.go(page, '/tasks', 4)
        body3 = page.inner_text('body')
        ok3 = '任务列表加载失败' in body3
        self.check('任务页错误态（列表被拦截）', ok3,
                   '「任务列表加载失败」可见=%s' % ok3,
                   self.shot(page, '18_tasks_error'))
        self.cdp.send('Network.setBlockedURLs', {'urls': []})
        self._cur_page = ''


def main():
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
