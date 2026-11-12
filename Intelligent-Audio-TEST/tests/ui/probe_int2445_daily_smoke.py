# -*- coding: utf-8 -*-
"""INT-2445 前端回归日巡补充实测（React 15173，docker 真实库栈，只读）。

日巡卡要求核心页（登录 / 任务 / 音频 / 用例 / 报告 / 设备）与
「登录 → 任务 → 用例 → 报告」关键链路都覆盖列表 / 详情 / 弹窗 / 空态 / 错误态。
既有脚本已经把主体跑掉：
  - tests/ui/smoke_react_nav_walk_int2136.py       侧栏 20 页逐页可达 + 4xx5xx + 截图
  - tests/ui/smoke_frontend_int1919.py --kind react 登录/任务/用例/报告/开始测试 五条链路
  - tests/ui/probe_int2441_daily_smoke.py           设备 / 音频 / 任务 / 报告 空态·错误态·加载态
本探针补 INT-2441 没固化的部分，断言「可见状态」而不只看 DOM：

  1. 用例管理：分组卡计数 vs GET /groups（同名分组 test_case_count 逐组对照）、
     「已显示 N / M 个分组」vs /groups 总数；展开分组 → 用例音频预览弹窗
     （播放模式 / 偏移量 / 开始试听，**只打开不点开始试听**，不发写请求）。
     用例详情弹窗（评估维度 / 轮次 / 音频）由 smoke_frontend_int1919 chain 3
     （任务详情 → 查看用例详情）覆盖，本探针不重复；
  2. 用例空态：搜索框填必不存在的关键词 → 「没有找到符合条件的测试用例」，
     且不误落「用例列表加载失败」错误态；
  3. 用例错误态：CDP Network.setBlockedURLs 拦掉 /testcases 列表请求 →
     「用例列表加载失败」+ 重试，且不落「没有找到」空态；解除拦截点重试恢复分组卡；
  4. 用例加载态：CDP 网络延迟 2.5s → 骨架屏（data-slot=skeleton）可见；
  5. 音频空态 / 错误态 / 加载态（INT-2441 只做到列表 + 详情弹窗）；
  6. 报告产出链路一致性：真实任务 460 → GET /reports/by_task/460 得报告 426 →
     报告中心列表可见同名报告 → 详情页 /report/426 可打开；
  7. 用例 / 音频浅色 + 深色截图，全程网络证据（浏览器 perf 资源清单）。

只读语义：CDP 拦截只作用于浏览器网络层，不提交写请求、不写库，无 teardown。
跑法（环境铁律：连 docker 栈，不启动本地栈）：
  python tests/ui/probe_int2445_daily_smoke.py --base http://localhost:15173 \
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

ART = os.path.join(HERE, 'artifacts', 'int2445')


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
        print('[%s] %-36s %s' % ('PASS' if ok else 'FAIL', name, detail), flush=True)
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
        r = httpx.get(self.api + path, headers=self.h, timeout=30, trust_env=False)
        body = r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
        return r.status_code, body

    def text(self, page):
        return page.inner_text('body')

    def wait_cases_loaded(self, page, timeout=40):
        """等分组卡出现（/testcases 单页真实库 8~20s）。"""
        end = time.time() + timeout
        while time.time() < end:
            if '个分组' in self.text(page) or '没有找到符合条件的测试用例' in self.text(page):
                return True
            time.sleep(1)
        return False

    # ── 用例管理 ────────────────────────────────────────
    def check_cases(self, page):
        st, body = self.api_get('/api/v1/groups?page=1&per_page=200')
        groups = (body.get('data') or {}).get('items') or []
        gmap = {g.get('name'): g.get('test_case_count') for g in groups}
        api_total_groups = len(groups)

        self.go(page, '/testcases', 3)
        self.wait_cases_loaded(page)
        txt = self.text(page)

        # 「已显示 5 / 7 个分组」或全部渲染的「已显示 7 / 7」
        shown_ok = False
        for n in range(1, api_total_groups + 1):
            if '已显示 %d / %d 个分组' % (n, api_total_groups) in txt:
                shown_ok = True
                break
        # 抽样对照分组计数徽章
        mismatched = []
        checked = 0
        for name, cnt in gmap.items():
            if not name or cnt is None:
                continue
            if name in txt:
                if ('%s 条' % cnt) in txt or ('共 %s 条' % cnt) in txt:
                    checked += 1
                else:
                    mismatched.append('%s api=%s' % (name, cnt))
        self.check('用例分组卡与 /groups 一致',
                   st == 200 and shown_ok and not mismatched and checked >= 3,
                   'API 分组=%s / 「已显示 N / %s 个分组」=%s / 逐组对照 %s 个, 不符=%s'
                   % (api_total_groups, api_total_groups, shown_ok, checked, mismatched or '无'),
                   self.shot(page, '20_cases_list_light'))

        # 用例音频预览弹窗：展开分组 → 点第一条用例的「预览音频」（只打开，不点开始试听）
        try:
            first_group = groups[0].get('name') or ''
            span = page.get_by_text(first_group, exact=True).first
            hdr = span.locator('xpath=ancestor::div[contains(@class,"cursor-pointer")][1]')
            hdr.click()
            time.sleep(6)
            preview_btns = page.get_by_role('button', name='预览音频', exact=True)
            n_btns = preview_btns.count()
            if n_btns > 0:
                preview_btns.first.click()
                time.sleep(3)
            dlg = page.locator('[role=dialog]').first
            vis = dlg.is_visible()
            dtext = dlg.inner_text()[:600].replace('\n', ' | ') if vis else ''
            has_mode = '播放模式' in dtext or '浏览器播放' in dtext
            has_offset = '偏移' in dtext
            has_btn = '开始试听' in dtext
            self.check('用例音频预览弹窗（展开分组 → 预览音频，不试听）',
                       vis and n_btns > 0 and has_mode and has_offset and has_btn,
                       '展开后「预览音频」按钮=%s / 弹窗可见=%s / 播放模式=%s 偏移量=%s 开始试听=%s'
                       % (n_btns, vis, has_mode, has_offset, has_btn),
                       self.shot(page, '21_cases_preview'))
            page.keyboard.press('Escape')
            time.sleep(1)
        except Exception as exc:
            self.check('用例音频预览弹窗（展开分组 → 预览音频，不试听）', False,
                       '异常 %s: %s' % (type(exc).__name__, str(exc)[:160]),
                       self.shot(page, '21_cases_preview'))

        self._record_api(page, 'cases')

    def check_cases_states(self, page):
        # 空态：搜索必不存在关键词
        self.go(page, '/testcases', 3)
        self.wait_cases_loaded(page)
        try:
            box = page.locator('input[placeholder="搜索用例名称或描述"]').first
            box.fill('ZZZ_不存在_%d' % int(time.time()))
            time.sleep(6)
            txt = self.text(page)
            empty_ok = '没有找到符合条件的测试用例' in txt
            err_masked = '用例列表加载失败' not in txt
            self.check('用例空态（搜索无匹配）', empty_ok and err_masked,
                       '「没有找到符合条件的测试用例」可见=%s；错误态被抑制=%s'
                       % (empty_ok, err_masked),
                       self.shot(page, '22_cases_empty'))
            box.fill('')
            time.sleep(4)
        except Exception as exc:
            self.check('用例空态（搜索无匹配）', False,
                       '异常 %s: %s' % (type(exc).__name__, str(exc)[:160]))

        # 错误态：拦截 /testcases 列表请求
        self.cdp.send('Network.setBlockedURLs', {'urls': ['*api/v1/testcases?*']})
        self.go(page, '/testcases', 5)
        txt = self.text(page)
        err_ok = '用例列表加载失败' in txt
        empty_masked = '没有找到符合条件的测试用例' not in txt
        self.check('用例错误态（列表请求被拦截）', err_ok and empty_masked,
                   '「用例列表加载失败」可见=%s；「没有找到」空态被抑制=%s'
                   % (err_ok, empty_masked),
                   self.shot(page, '23_cases_error'))
        self.cdp.send('Network.setBlockedURLs', {'urls': []})
        try:
            page.get_by_role('button', name='重试', exact=False).first.click()
            time.sleep(8)
            self.wait_cases_loaded(page, 30)
            txt2 = self.text(page)
            recovered = '个分组' in txt2 and '用例列表加载失败' not in txt2
            self.check('用例错误态重试恢复', recovered,
                       '点「重试」后分组卡恢复=%s' % recovered,
                       self.shot(page, '24_cases_retry_ok'))
        except Exception as exc:
            self.check('用例错误态重试恢复', False,
                       '异常 %s: %s' % (type(exc).__name__, str(exc)[:160]))

        # 加载态：网络延迟 2.5s
        self.cdp.send('Network.emulateNetworkConditions',
                      {'offline': False, 'latency': 2500,
                       'downloadThroughput': -1, 'uploadThroughput': -1})
        page.goto(self.base + '/testcases', wait_until='domcontentloaded')
        time.sleep(3)
        skeleton = page.locator('[data-slot=skeleton]').count()
        self.check('用例加载态（延迟 2.5s）', skeleton > 0,
                   '骨架屏节点数=%s' % skeleton,
                   self.shot(page, '25_cases_loading'))
        self.cdp.send('Network.emulateNetworkConditions',
                      {'offline': False, 'latency': 0,
                       'downloadThroughput': -1, 'uploadThroughput': -1})
        time.sleep(6)
        self.set_dark(page, True)
        self.shot(page, '26_cases_list', dark=True)
        self.set_dark(page, False)

    # ── 音频管理三态 ────────────────────────────────────
    def check_audio_states(self, page):
        # 空态
        self.go(page, '/audio-import', 5)
        try:
            box = page.locator('input[placeholder="搜索文件名或标注"]').first
            box.fill('ZZZ_不存在_%d' % int(time.time()))
            time.sleep(3.5)
            body = self.text(page)
            ok = '未找到匹配的音频' in body and '音频列表加载失败' not in body
            self.check('音频空态（搜索无匹配）', ok,
                       '「未找到匹配的音频」可见=%s；错误态被抑制=%s'
                       % ('未找到匹配的音频' in body, '音频列表加载失败' not in body),
                       self.shot(page, '27_audio_empty'))
            box.fill('')
            time.sleep(3)
        except Exception as exc:
            self.check('音频空态（搜索无匹配）', False,
                       '异常 %s: %s' % (type(exc).__name__, str(exc)[:160]))

        # 错误态 + 重试（音频列表请求是 /api/v1/audios，无 query string）
        self.cdp.send('Network.setBlockedURLs', {'urls': ['*api/v1/audios']})
        self.go(page, '/audio-import', 5)
        body = self.text(page)
        err_ok = '音频列表加载失败' in body
        empty_masked = '暂无音频文件' not in body
        self.check('音频错误态（列表请求被拦截）', err_ok and empty_masked,
                   '「音频列表加载失败」可见=%s；「暂无音频文件」空态被抑制=%s'
                   % (err_ok, empty_masked),
                   self.shot(page, '28_audio_error'))
        self.cdp.send('Network.setBlockedURLs', {'urls': []})
        try:
            page.get_by_role('button', name='重试', exact=False).first.click()
            time.sleep(6)
            rows = page.locator('tbody tr').count()
            self.check('音频错误态重试恢复', rows > 0,
                       '点「重试」后列表行数=%s' % rows,
                       self.shot(page, '29_audio_retry_ok'))
        except Exception as exc:
            self.check('音频错误态重试恢复', False,
                       '异常 %s: %s' % (type(exc).__name__, str(exc)[:160]))

        # 加载态
        self.cdp.send('Network.emulateNetworkConditions',
                      {'offline': False, 'latency': 2500,
                       'downloadThroughput': -1, 'uploadThroughput': -1})
        page.goto(self.base + '/audio-import', wait_until='domcontentloaded')
        time.sleep(3)
        skeleton = page.locator('[data-slot=skeleton]').count()
        self.check('音频加载态（延迟 2.5s）', skeleton > 0,
                   '骨架屏节点数=%s' % skeleton,
                   self.shot(page, '30_audio_loading'))
        self.cdp.send('Network.emulateNetworkConditions',
                      {'offline': False, 'latency': 0,
                       'downloadThroughput': -1, 'uploadThroughput': -1})
        time.sleep(6)
        self._record_api(page, 'audio_states')

    # ── 报告产出链路一致性 ──────────────────────────────
    def check_report_chain(self, page):
        st, body = self.api_get('/api/v1/reports/by_task/460')
        report = body.get('data') or {}
        rid = report.get('id')
        name = report.get('name') or ''
        self.check('任务 460 → /reports/by_task 产出报告',
                   st == 200 and bool(rid) and bool(name),
                   'GET /reports/by_task/460 → %s id=%s name=%s' % (st, rid, name))

        self.go(page, '/report-center', 4)
        txt = self.text(page)
        in_center = (name in txt) if name else False
        self.check('报告中心可见任务 460 的报告', in_center,
                   '报告名「%s」在报告中心列表可见=%s' % (name, in_center),
                   self.shot(page, '31_report_center'))

        if rid:
            self.go(page, '/report/%s?from=management' % rid, 5)
            txt2 = self.text(page)
            detail_ok = (name in txt2) or ('返回' in txt2 and '总览' in txt2)
            self.check('报告详情页可打开（/report/%s）' % rid, detail_ok,
                       '详情页含报告名=%s；含「返回/总览」=%s'
                       % (name in txt2, '返回' in txt2 and '总览' in txt2),
                       self.shot(page, '32_report_detail'))
            self._record_api(page, 'report_detail')

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
                       self.shot(page, '19_login'))

            try:
                self.check_cases(page)
            except Exception as exc:
                self.check('用例管理主检查', False, '异常 %s: %s' % (type(exc).__name__, str(exc)[:200]))
            try:
                self.check_cases_states(page)
            except Exception as exc:
                self.check('用例三态', False, '异常 %s: %s' % (type(exc).__name__, str(exc)[:200]))
            try:
                self.check_audio_states(page)
            except Exception as exc:
                self.check('音频三态', False, '异常 %s: %s' % (type(exc).__name__, str(exc)[:200]))
            try:
                self.check_report_chain(page)
            except Exception as exc:
                self.check('报告链路', False, '异常 %s: %s' % (type(exc).__name__, str(exc)[:200]))

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
