# -*- coding: utf-8 -*-
"""INT-2447 复测探针：报告中心 / 报告展示页 时间范围筛选中文标签 + 列表错误态对齐公共 ErrorState。

前置：镜像 docker 栈常驻（网关 http://localhost:15000，真实库 intelligent_audio_test），
本卡改动跑在 React dev server 上（默认 5374，代理 /api → 15000），不启动任何本地后端栈。

覆盖（全部真实数据、真实接口，只读）：
  P3-1  /report-center 与 /reports 的 `[aria-label=时间范围]` 触发器显示「全部时间」
        （修复前为英文 value `all`）；下拉选「今日」后回显「今日」，再切回「全部时间」；
        报告展示页顶部 Badge 也不再回显英文 value。
  P3-2  列表请求被 CDP 拦截 → 报告中心（表格 / 卡片视图）与报告展示页（列表 / 卡片视图）
        都渲染公共 ErrorState：红色 AlertTriangle + 「报告列表加载失败」+ 「重试」，
        不再出现排序图标 ↑↓ 与「请重试」；解除拦截后点「重试」恢复真实列表。
  证据  浅色 / 深色截图 + Network 证据（CDP responseReceived 渲染成表格截屏）。

跑法：python tests/ui/probe_int2447_report_filter_error.py \
          --base http://localhost:5374 --api http://localhost:15000
"""
import argparse
import html
import json
import os
import sys
import time

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT_ROOT)

from tests.ui.utils.api_client import ApiClient  # noqa: E402

ART = os.path.join(HERE, 'artifacts', 'int2447')


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
        print('[%s] %-44s %s' % ('PASS' if ok else 'FAIL', name, detail))
        return rec

    def shot(self, page, name, dark=False):
        os.makedirs(ART, exist_ok=True)
        path = os.path.join(ART, '%s%s.png' % (name, '_dark' if dark else ''))
        page.screenshot(path=path)
        return path

    def go(self, page, route, wait=3.5):
        page.goto(self.base + '/' + route.lstrip('/'), wait_until='domcontentloaded')
        time.sleep(wait)

    def reload(self, page, wait=4):
        """保留当前 URL（含 ?view=card 等查询参数）重载。"""
        page.goto(page.url, wait_until='domcontentloaded')
        time.sleep(wait)

    def set_dark(self, page, on):
        page.evaluate("on => document.documentElement.classList.toggle('dark', on)", on)
        time.sleep(0.6)

    def block(self, urls):
        self.cdp.send('Network.setBlockedURLs', {'urls': urls})

    def api_get(self, path):
        import httpx
        r = httpx.get(self.api + path, headers=self.h, timeout=30, trust_env=False)
        body = r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
        return r.status_code, body

    # ── 时间范围控件 ────────────────────────────────────
    def time_trigger(self, page):
        return page.locator('[aria-label="时间范围"]').first

    def check_time_range_label(self, page, tag, shot_light, shot_dark):
        trg = self.time_trigger(page)
        visible = trg.count() > 0 and trg.is_visible()
        text = trg.inner_text().strip() if visible else ''
        self.check('%s：时间范围默认显示中文「全部时间」' % tag,
                   visible and text == '全部时间',
                   '触发器可见=%s innerText=%r（修复前为 english `all`）' % (visible, text),
                   self.shot(page, shot_light))
        self.set_dark(page, True)
        self.check('%s：深色下文案仍为「全部时间」' % tag,
                   self.time_trigger(page).inner_text().strip() == '全部时间',
                   'deep innerText=%r' % self.time_trigger(page).inner_text().strip(),
                   self.shot(page, shot_dark))
        self.set_dark(page, False)

    def check_time_range_options(self, page, tag):
        """下拉选「今日」→ 回显「今日」；再切回「全部时间」——证明 label 解析对任意 value 生效。"""
        self.time_trigger(page).click()
        time.sleep(1.0)
        popup_text = page.locator('[role=listbox]').first.inner_text() if page.locator('[role=listbox]').count() else ''
        try:
            page.get_by_role('option', name='今日', exact=True).first.click(timeout=5000)
        except Exception:
            page.get_by_text('今日', exact=True).first.click(timeout=5000)
        time.sleep(1.8)
        after = self.time_trigger(page).inner_text().strip()
        self.check('%s：选中「今日」后回显「今日」' % tag, after == '今日',
                   'options=%r → 回显=%r' % (popup_text.replace('\n', '/'), after),
                   self.shot(page, '05_time_range_today'))

        self.time_trigger(page).click()
        time.sleep(1.0)
        try:
            page.get_by_role('option', name='全部时间', exact=True).first.click(timeout=5000)
        except Exception:
            page.get_by_text('全部时间', exact=True).first.click(timeout=5000)
        time.sleep(1.8)
        back = self.time_trigger(page).inner_text().strip()
        self.check('%s：切回「全部时间」' % tag, back == '全部时间', '回显=%r' % back)

    # ── 错误态 ──────────────────────────────────────────
    def check_error_state(self, page, tag, shot_name, expect_rows=True):
        """列表请求已被拦截的状态下检查错误态；返回 body 文本。"""
        body_text = page.inner_text('body')
        has_title = '报告列表加载失败' in body_text
        has_retry_btn = page.get_by_role('button', name='重试', exact=True).count() > 0
        no_old_button = page.get_by_role('button', name='请重试', exact=True).count() == 0
        icon_cls = ''
        if page.locator('[data-slot=empty-icon] svg').count():
            icon_cls = page.locator('[data-slot=empty-icon] svg').first.get_attribute('class') or ''
        is_alert = 'lucide-triangle-alert' in icon_cls or 'lucide-alert-triangle' in icon_cls
        self.check('%s：错误态 = 公共 ErrorState（红色 AlertTriangle + 标题 + 重试）' % tag,
                   has_title and has_retry_btn and no_old_button and is_alert,
                   '标题=%s 按钮「重试」=%s 旧按钮「请重试」=%s 图标class=%r'
                   % (has_title, has_retry_btn, not no_old_button, icon_cls),
                   self.shot(page, shot_name))
        self.set_dark(page, True)
        self.check('%s：深色错误态一致' % tag,
                   '报告列表加载失败' in page.inner_text('body')
                   and any(k in (page.locator('[data-slot=empty-icon] svg').first.get_attribute('class') or '')
                           for k in ('lucide-triangle-alert', 'lucide-alert-triangle')),
                   'deep 标题与图标同上', self.shot(page, shot_name + '_dark'))
        self.set_dark(page, False)
        return body_text

    def recover(self, page, tag):
        self.block([])
        page.get_by_role('button', name='重试', exact=True).first.click()
        time.sleep(3.5)
        body = page.inner_text('body')
        rows = page.locator('tbody tr').count()
        cards = page.locator('[data-slot=card]').count()
        ok = '报告列表加载失败' not in body and '暂无报告' not in body
        self.check('%s：解除拦截后点「重试」恢复真实列表' % tag,
                   ok, '列表行=%s 卡片=%s 仍报错=%s' % (rows, cards, '报告列表加载失败' in body),
                   self.shot(page, '09_recover_after_retry'))

    def switch_view(self, page, label):
        """切换 表格 / 卡片 视图（工具栏按钮）。"""
        try:
            page.get_by_role('button', name=label).first.click(timeout=5000)
            time.sleep(2.2)
            return True
        except Exception:
            return False

    # ── 主流程 ──────────────────────────────────────────
    def run(self):
        api = ApiClient(self.api)
        api.login(self.username, self.password)
        self.h = {'Authorization': 'Bearer ' + api.token}
        st, body = self.api_get('/api/v1/reports?page=1&per_page=20')
        api_total = (body.get('data') or {}).get('total')
        print('真实库 GET /api/v1/reports total=%s (HTTP %s)' % (api_total, st))
        os.makedirs(ART, exist_ok=True)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(viewport={'width': 1680, 'height': 1050})
            page = ctx.new_page()
            self.cdp = ctx.new_cdp_session(page)
            self.cdp.send('Network.enable')
            responses = []

            def on_resp(ev):
                try:
                    url = ev['response']['url']
                    if '/api/v1/' in url and not url.endswith('.map'):
                        responses.append((ev['response'].get('status'), ev['type'], url))
                except Exception:
                    pass
            self.cdp.on('Network.responseReceived', on_resp)

            # 1) 登录（真实表单 → 真实网关）
            page.goto(self.base + '/login', wait_until='domcontentloaded')
            time.sleep(2)
            page.fill('#username', self.username)
            page.fill('#password', self.password)
            page.click('button[type=submit]')
            page.wait_for_url(lambda u: 'login' not in u, timeout=30000)
            self.check('登录（dev_user 真实表单）', True, 'URL=%s' % page.url,
                       self.shot(page, '01_login'))

            # 2) 报告中心：默认文案 + 下拉回显 + 浅/深截图
            self.go(page, '/report-center', 4)
            page_text = page.inner_text('body')
            rows = page.locator('tbody tr').count()
            self.check('报告中心：列表真实数据渲染', rows > 0 and str(api_total) in page_text,
                       'API total=%s / 表格行=%s / 页面计数可见=%s'
                       % (api_total, rows, str(api_total) in page_text),
                       self.shot(page, '02_report_center_light_raw'))
            self.check_time_range_label(page, '报告中心', '02_report_center_light',
                                        '03_report_center_dark')
            self.check_time_range_options(page, '报告中心')

            # 3) 报告展示页 /reports：同款控件 + 顶部 Badge
            self.go(page, '/reports', 4)
            self.check_time_range_label(page, '报告展示页', '04_reports_light', '04_reports_dark')
            self.check_time_range_options(page, '报告展示页')
            self.time_trigger(page).click()
            time.sleep(1.0)
            try:
                page.get_by_role('option', name='今日', exact=True).first.click(timeout=5000)
            except Exception:
                page.get_by_text('今日', exact=True).first.click(timeout=5000)
            time.sleep(1.8)
            badge_text = page.inner_text('body')
            self.check('报告展示页：顶部 Badge 不回显英文 value',
                       '今日' in badge_text and 'today' not in badge_text,
                       'Badge/页面含「今日」=%s 含英文「today」=%s' % ('今日' in badge_text, 'today' in badge_text),
                       self.shot(page, '06_reports_badge_today'))
            self.time_trigger(page).click()
            time.sleep(1.0)
            try:
                page.get_by_role('option', name='全部时间', exact=True).first.click(timeout=5000)
            except Exception:
                page.get_by_text('全部时间', exact=True).first.click(timeout=5000)
            time.sleep(1.8)

            # 4) P3-2 错误态：报告中心（表格）
            self.block(['*api/v1/reports*'])
            self.go(page, '/report-center', 4)
            self.check_error_state(page, '报告中心（表格）', '07_report_center_error')
            self.recover(page, '报告中心（表格）')

            # 5) P3-2 错误态：报告中心（卡片视图；切视图后按当前 URL 重载，保证仍是卡片态）
            if self.switch_view(page, '卡片'):
                self.block(['*api/v1/reports*'])
                self.reload(page)
                self.check_error_state(page, '报告中心（卡片）', '07b_report_center_card_error')
                self.recover(page, '报告中心（卡片）')
                self.switch_view(page, '表格')
            else:
                self.check('报告中心：切换到卡片视图', False, '未找到卡片视图按钮')

            # 6) P3-2 错误态：报告展示页（列表 + 卡片）
            self.block(['*api/v1/reports*'])
            self.go(page, '/reports', 4)
            self.check_error_state(page, '报告展示页（列表）', '08_reports_error')
            self.recover(page, '报告展示页（列表）')

            if self.switch_view(page, '卡片'):
                self.block(['*api/v1/reports*'])
                self.reload(page)
                self.check_error_state(page, '报告展示页（卡片）', '08b_reports_card_error')
                self.recover(page, '报告展示页（卡片）')
            else:
                self.check('报告展示页：切换到卡片视图', False, '未找到卡片视图按钮')

            # 7) Network 证据截图
            self.save_network_evidence(responses, browser)
            browser.close()

        print('\nRESULT %d/%d passed' % (sum(1 for c in self.checks if c['ok']), len(self.checks)))
        with open(os.path.join(ART, 'summary.json'), 'w', encoding='utf-8') as fh:
            json.dump({'checks': self.checks, 'net': self.net, 'api_total': api_total},
                      fh, ensure_ascii=False, indent=2)
        return 0 if all(c['ok'] for c in self.checks) else 1

    def save_network_evidence(self, responses, browser):
        os.makedirs(ART, exist_ok=True)
        seen, rows_html = set(), []
        for status, rtype, url in responses:
            key = (status, url)
            if key in seen:
                continue
            seen.add(key)
            short = url.split('15000')[-1] if '15000' in url else url
            short = short.split('5374')[-1] if '5374' in short else short
            color = '#0a7' if 200 <= (status or 0) < 300 else '#c33'
            rows_html.append(
                '<tr><td style="color:%s;font-weight:600">%s</td><td>%s</td>'
                '<td style="font-family:monospace;font-size:12px">%s</td></tr>'
                % (color, status, html.escape(rtype), html.escape(short[:170])))
        doc = ('<html><head><meta charset="utf-8"></head>'
               '<body style="font-family:Segoe UI,sans-serif;padding:16px;background:#fff">'
               '<h3 style="margin:0 0 4px">INT-2447 Network 证据（CDP Network.responseReceived）</h3>'
               '<p style="margin:0 0 10px;color:#666;font-size:12px">'
               'React dev server :5374 → /api 代理 → docker 网关 :15000（真实库 intelligent_audio_test）</p>'
               '<table cellspacing="0" cellpadding="5" style="border-collapse:collapse;font-size:13px">'
               '<tr style="background:#eee"><th>status</th><th>type</th><th>url</th></tr>'
               + ''.join(rows_html) + '</table></body></html>')
        path = os.path.join(ART, 'net_evidence.html')
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(doc)
        pg = browser.new_page(viewport={'width': 1500, 'height': min(60 + 26 * len(rows_html), 1400)})
        pg.goto('file:///' + path.replace('\\', '/'))
        time.sleep(0.6)
        pg.screenshot(path=os.path.join(ART, '10_network_evidence.png'))
        pg.close()
        self.net.append({'api_response_count': len(seen)})
        self.check('Network 证据：真实 /api 响应已记录', len(seen) > 0,
                   '%d 条唯一 /api/v1 响应 → 10_network_evidence.png' % len(seen))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5374')
    ap.add_argument('--api', default='http://localhost:15000')
    ap.add_argument('--username', default=os.environ.get('UI_TEST_USERNAME', 'dev_user'))
    ap.add_argument('--password', default=os.environ.get('UI_TEST_PASSWORD', 'dev_password'))
    a = ap.parse_args()
    sys.exit(Probe(a.base, a.api, a.username, a.password).run())
