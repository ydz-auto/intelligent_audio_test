# -*- coding: utf-8 -*-
"""INT-2447 复测探针：报告中心 / 报告展示页 时间范围筛选中文标签 + 列表错误态对齐公共 ErrorState。

前置：镜像 docker 栈常驻（网关 http://localhost:15000，真实库 intelligent_audio_test），
本卡改动跑在 React dev server 上（默认 5374，代理 /api → 15000），不启动任何本地后端栈。

覆盖（全部真实数据、真实接口，只读）：
  P3-1  /report-center 与 /reports 的 `[aria-label=时间范围]` 触发器显示「全部时间」
        （修复前为英文 value `all`）；下拉选「今日」后回显「今日」，再切回「全部时间」；
        报告展示页顶部 Badge 也不再回显英文 value。
  P3-1 残余  /report-center「高级搜索」折叠区 设备类型 / 创建者 / 时间范围 三个 Select
        默认显示「全部 / 全部 / 全部时间」（修复前 `all` / `all` / `all`），切换后回显中文
        （智能音箱 / 今日），与 Hero 的 timeRange 同 state 保持一致；重置后复原。
  同根因扫描  报告中心可达弹窗里的裸 SelectValue：导出弹窗「格式」= CSV（非 `csv`）、
        对比弹窗「对比维度」= 测试用例 / 「对比方式」= 横向对比（同指标多主体）（非 `test_cases` / `horizontal`）。
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

    # ── 高级搜索（P3-1 残余）───────────────────────────
    def adv_trigger(self, page, sel):
        loc = page.locator('#adv-%s' % sel)
        return loc.first

    def adv_text(self, page, sel):
        loc = self.adv_trigger(page, sel)
        return loc.inner_text().strip() if loc.count() and loc.is_visible() else ''

    def ensure_adv_open(self, page):
        if not self.adv_trigger(page, 'device-type').count() or not self.adv_trigger(page, 'device-type').first.is_visible():
            page.locator('button:has-text("高级搜索")').first.click()
            time.sleep(0.8)

    def adv_pick(self, page, sel, option):
        self.ensure_adv_open(page)
        self.adv_trigger(page, sel).click()
        time.sleep(1.0)
        try:
            page.get_by_role('option', name=option, exact=True).first.click(timeout=5000)
        except Exception:
            page.get_by_text(option, exact=True).first.click(timeout=5000)
        time.sleep(2.0)

    def check_advanced_search(self, page):
        """高级搜索三个 Select：默认中文 + 切换后中文 + 重置复原（修复前为 all/all/all）。"""
        self.ensure_adv_open(page)
        dev, cre, rng = (self.adv_text(page, 'device-type'),
                         self.adv_text(page, 'creator'),
                         self.adv_text(page, 'time-range'))
        panel = page.inner_text('body')
        raw_present = any(tok in panel for tok in ('smart_speaker', 'car_voice', 'demo_admin'))
        self.check('高级搜索：默认显示「全部 / 全部 / 全部时间」',
                   dev == '全部' and cre == '全部' and rng == '全部时间' and not raw_present,
                   '设备类型=%r 创建者=%r 时间范围=%r 面板含英文原始值=%s（修复前 all/all/all）'
                   % (dev, cre, rng, raw_present),
                   self.shot(page, '12_adv_search_light'))
        self.set_dark(page, True)
        self.ensure_adv_open(page)
        dark_rng = self.adv_text(page, 'time-range')
        self.check('高级搜索：深色下文案仍为中文', dark_rng == '全部时间', 'deep 时间范围=%r' % dark_rng,
                   self.shot(page, '12b_adv_search_dark'))
        self.set_dark(page, False)

        # 切换：设备类型=智能音箱、时间范围=今日 → 触发器与 Hero 同步回显中文
        self.adv_pick(page, 'device-type', '智能音箱')
        after_dev = self.adv_text(page, 'device-type')
        self.check('高级搜索：选「智能音箱」后回显中文（非 smart_speaker）',
                   after_dev == '智能音箱', '回显=%r' % after_dev,
                   self.shot(page, '13_adv_device_picked'))

        self.adv_pick(page, 'time-range', '今日')
        after_rng = self.adv_text(page, 'time-range')
        hero_rng = self.time_trigger(page).inner_text().strip()
        total_text = page.inner_text('body')
        self.check('高级搜索：选「今日」后回显「今日」，Hero 同 state 同步',
                   after_rng == '今日' and hero_rng == '今日' and 'today' not in total_text,
                   '高级搜索时间范围=%r Hero=%r 页面含英文 today=%s'
                   % (after_rng, hero_rng, 'today' in total_text),
                   self.shot(page, '14_adv_time_today'))

        # 重置高级搜索 → 三个控件复原
        try:
            page.get_by_role('button', name='重置高级搜索', exact=True).first.click(timeout=5000)
            time.sleep(2.2)
        except Exception:
            pass
        self.ensure_adv_open(page)
        r_dev, r_cre, r_rng = (self.adv_text(page, 'device-type'),
                               self.adv_text(page, 'creator'),
                               self.adv_text(page, 'time-range'))
        self.check('高级搜索：重置后复原「全部 / 全部 / 全部时间」',
                   r_dev == '全部' and r_cre == '全部' and r_rng == '全部时间',
                   '设备类型=%r 创建者=%r 时间范围=%r' % (r_dev, r_cre, r_rng),
                   self.shot(page, '15_adv_reset'))

    # ── 同根因扫描：报告中心可达弹窗的裸 SelectValue ──────
    def check_dialog_selects(self, page):
        # 导出弹窗「格式」：修前回显英文 value csv
        try:
            page.get_by_role('button', name='更多操作', exact=True).first.click(timeout=5000)
            time.sleep(1.0)
            page.get_by_role('menuitem', name='导出 CSV', exact=True).first.click(timeout=5000)
            time.sleep(2.0)
            dialog = page.locator('[role=dialog]').first
            fmt = dialog.locator('[data-slot=select-trigger]').first.inner_text().strip()
            self.check('导出弹窗：格式回显「CSV」（非英文 value csv）',
                       fmt.upper().startswith('CSV'), '格式触发器=%r' % fmt,
                       self.shot(page, '16_export_dialog_format'))
            page.keyboard.press('Escape')
            time.sleep(1.0)
        except Exception as exc:  # noqa: BLE001 - 探针：打开失败也要留记录
            self.check('导出弹窗：格式回显「CSV」', False, '打开/读取失败：%r' % exc)

        # 对比弹窗「对比维度 / 对比方式」：修前回显 test_cases / horizontal
        try:
            rows = page.locator('tbody tr')
            boxes = page.locator('tbody tr [role=checkbox]')
            for i in range(min(2, boxes.count())):
                boxes.nth(i).click(timeout=5000)
                time.sleep(0.6)
            page.get_by_role('button', name='批量对比', exact=True).first.click(timeout=8000)
            time.sleep(2.0)
            # 对比维度 / 对比方式在「对比配置」页签（默认停在「基于任务」）
            page.get_by_role('tab', name='对比配置', exact=True).first.click(timeout=5000)
            time.sleep(1.2)
            dialog = page.locator('[role=dialog]').first
            selects = dialog.locator('[data-slot=select-trigger]')
            dim = selects.nth(0).inner_text().strip() if selects.count() > 0 else ''
            mode = selects.nth(1).inner_text().strip() if selects.count() > 1 else ''
            self.check('对比弹窗：对比维度 / 对比方式回显中文 label',
                       dim == '测试用例' and mode.startswith('横向对比'),
                       '对比维度=%r 对比方式=%r（修复前 test_cases / horizontal）' % (dim, mode),
                       self.shot(page, '17_compare_dialog_selects'))
            page.keyboard.press('Escape')
            time.sleep(1.0)
        except Exception as exc:  # noqa: BLE001
            self.check('对比弹窗：对比维度 / 对比方式回显中文 label', False,
                       '打开/读取失败：%r' % exc)

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

            # 2b) P3-1 残余：高级搜索三个 Select（本轮打回项）
            self.check_advanced_search(page)

            # 2c) 同根因扫描：报告中心可达弹窗的裸 SelectValue（导出 / 对比）
            self.check_dialog_selects(page)

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
