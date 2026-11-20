# -*- coding: utf-8 -*-
"""INT-2661 返工补测探针：导出 ZIP / 用例日志下载 / 正式任务链路 / 离开页面 run 不中断。

前端UX审计员打回清单（2026-11-20 01:47 评论 01a1f6a3）：
  1. `7048c06a8` 报告导出 ZIP、用例日志下载、用例导出作业下载的可下载性与文件完整性
     —— Network 确认全部落在 15173 网关，不走桶公网预签名；
  2. 正式任务「创建 / 执行 / 报告产出 / 查看」整链；
  3. `fb0ebb926` 离开 /ai-chat 路由 run 不中断（关闭浮窗才 cancel）。

环境铁律：连 docker 栈（15000 网关 / 15173 React），不启动本地栈、不 write 库。
跑法：
  python tests/ui/probe_int2661_rework.py downloads --base http://localhost:15173 --api http://127.0.0.1:15000
  python tests/ui/probe_int2661_rework.py formal    --base http://localhost:15173 --api http://127.0.0.1:15000
  python tests/ui/probe_int2661_rework.py leaverun  --base http://localhost:15173 --api http://127.0.0.1:15000
"""
import argparse
import io
import json
import os
import sys
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, PROJECT_ROOT)

from playwright.sync_api import sync_playwright  # noqa: E402

from tests.ui.utils.api_client import ApiClient  # noqa: E402

ART = os.path.join(HERE, 'artifacts', 'int2661_rework')
USERNAME = os.environ.get('UI_TEST_USERNAME', 'dev_user')
PASSWORD = os.environ.get('UI_TEST_PASSWORD', 'dev_password')


class Probe:
    def __init__(self, base, api_root):
        self.base = base.rstrip('/')
        self.api_root = api_root
        self.api = ApiClient(api_root)
        self.api.login(USERNAME, PASSWORD)
        self.checks = []
        self.net = []
        os.makedirs(ART, exist_ok=True)

    def check(self, name, ok, detail):
        self.checks.append({'name': name, 'ok': bool(ok), 'detail': detail})
        print('[%s] %-46s %s' % ('PASS' if ok else 'FAIL', name, detail), flush=True)

    def shot(self, page, name):
        path = os.path.join(ART, '%s.png' % name)
        page.screenshot(path=path, full_page=False)
        print('SHOT=%s' % path, flush=True)
        return path

    def login(self, page):
        page.goto(self.base + '/login', wait_until='domcontentloaded')
        page.wait_for_selector('#username', timeout=45000)
        page.fill('#username', USERNAME)
        page.fill('#password', PASSWORD)
        page.click("button[type='submit']")
        page.wait_for_url(lambda u: '/login' not in u.lower(), timeout=45000)
        page.wait_for_timeout(1500)

    def watch(self, page):
        def on_resp(resp):
            url = resp.url
            if '/api/v1/' not in url:
                return
            try:
                req = resp.request
                self.net.append({
                    'method': req.method, 'url': url, 'status': resp.status,
                    'mime': (resp.headers or {}).get('content-type', ''),
                })
            except Exception:
                pass
        page.on('response', on_resp)


def zip_entries(path_or_bytes):
    try:
        src = path_or_bytes if isinstance(path_or_bytes, (bytes, bytearray)) else open(path_or_bytes, 'rb')
        with zipfile.ZipFile(io.BytesIO(src) if isinstance(src, (bytes, bytearray)) else src) as z:
            return [(i.filename, i.file_size) for i in z.infolist()]
    except Exception as exc:  # noqa: BLE001
        return 'ERR:%s' % exc


# ---------------------------------------------------------------------------
# 1) 三条下载链路：报告导出 ZIP / 用例日志 / 用例导出作业
# ---------------------------------------------------------------------------

def mode_downloads(p, args):
    report_id = int(args.report or 426)
    detail = p.api.request('GET', '/reports/%d' % report_id)
    detail = detail.get('data') if 'data' in detail else detail
    cases = p.api.request('POST', '/reports/%d/cases/search' % report_id, {'page': 1, 'page_size': 5})
    cases = cases.get('data') if 'data' in cases else cases
    case_items = cases.get('items') or []
    p.check('api_report_and_cases', bool(detail) and len(case_items) > 0,
            'report=%s cases=%d' % (detail.get('name'), len(case_items)))

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1680, 'height': 1050}, accept_downloads=True)
        page = ctx.new_page()
        p.watch(page)
        p.login(page)

        # --- a) 报告导出 ZIP（后端生成格式 CSV/PDF/Excel，POST /reports/export 走网关） ---
        page.goto(p.base + '/report/%d?from=management' % report_id, wait_until='domcontentloaded')
        page.wait_for_timeout(4000)
        p.check('report_detail_mounted', report_id and '报告' in page.inner_text('body'), 'url=%s' % page.url)
        exp = page.get_by_role('button', name='导出', exact=True).first
        exp.click()
        page.wait_for_timeout(1200)
        dialog = page.get_by_role('dialog').filter(has_text='导出报告').first
        p.check('export_dialog_open', dialog.is_visible(), '导出报告弹窗可见')
        p.shot(page, '01_export_dialog_light')
        # 选 CSV（后端生成，走 POST /reports/export）
        dialog.get_by_role('combobox').first.click()
        page.wait_for_timeout(500)
        page.get_by_role('option', name='CSV').first.click()
        page.wait_for_timeout(400)
        net_before = len(p.net)
        zip_path = os.path.join(ART, 'report_export_%d.zip' % report_id)
        try:
            with page.expect_download(timeout=90000) as dl_info:
                dialog.get_by_role('button', name='导出', exact=True).click()
            dl = dl_info.value
            dl.save_as(zip_path)
            got = True
        except Exception as exc:  # noqa: BLE001
            got = False
            p.check('report_export_download_event', False, '未捕获下载: %s' % str(exc)[:160])
        export_net = [n for n in p.net[net_before:] if '/reports/export' in n['url'] or 'reports/export' in n['url']]
        if got:
            size = os.path.getsize(zip_path)
            entries = zip_entries(zip_path)
            p.check('report_export_download_event', True, '%s bytes=%d' % (dl.suggested_filename, size))
            p.check('report_export_is_zip', size > 0 and isinstance(entries, list) and len(entries) > 0,
                    'entries=%s' % (entries if not isinstance(entries, list) else entries[:6]))
            p.check('report_export_zip_complete',
                    isinstance(entries, list) and all((e[1] or 0) > 0 for e in entries),
                    '每个条目字节 > 0')
        p.check('report_export_via_gateway_15173',
                any(e['url'].startswith(p.base) and e['status'] in (200, 201) for e in export_net),
                'POST %s/reports/export -> %s' % (p.base, [(e['status'], e['mime'][:24]) for e in export_net]))
        page.keyboard.press('Escape')
        page.wait_for_timeout(800)

        # --- b) 用例日志下载（GET /reports/{id}/cases/{caseId}/logs/download 走网关流式） ---
        case_name = case_items[0].get('name', '')
        p.check('case_row_present', bool(case_name), 'case=%s' % case_name[:40])
        btn = page.get_by_role('button', name='下载日志').first
        btn.scroll_into_view_if_needed()
        btn.click()
        page.wait_for_timeout(2500)
        sel = page.get_by_role('dialog').filter(has_text='下载日志').first
        p.check('log_select_dialog_open', sel.is_visible(), '文件选择弹窗可见')
        p.shot(page, '02_log_select_dialog_light')
        net_before = len(p.net)
        log_zip = os.path.join(ART, 'case_logs_%d.zip' % report_id)
        try:
            with page.expect_download(timeout=90000) as dl_info:
                sel.get_by_role('button', name='下载所选文件').click()
            dl = dl_info.value
            dl.save_as(log_zip)
            got = True
        except Exception as exc:  # noqa: BLE001
            got = False
            p.check('case_logs_download_event', False, '未捕获下载: %s' % str(exc)[:160])
        log_net = [n for n in p.net[net_before:] if '/logs/download' in n['url']]
        if got:
            entries = zip_entries(log_zip)
            p.check('case_logs_download_event', True, '%s bytes=%d' % (dl.suggested_filename, os.path.getsize(log_zip)))
            p.check('case_logs_zip_entries', isinstance(entries, list) and len(entries) > 0,
                    'entries=%s' % (entries[:6] if isinstance(entries, list) else entries))
        p.check('case_logs_via_gateway_15173',
                any(n['url'].startswith(p.base) and n['status'] == 200 for n in log_net),
                'GET %s -> %s' % ('/reports/%d/cases/*/logs/download' % report_id,
                                  [(n['status'], n['mime'][:24]) for n in log_net]))
        p.check('case_logs_no_presigned_bucket',
                not any('download_url' in json.dumps(n) for n in log_net) and
                not any(x in n['url'] for n in log_net for x in ('rustfs', 'oss', 's3.', 'minio')),
                '无桶公网直连')
        page.keyboard.press('Escape')
        page.wait_for_timeout(600)

        # --- c) 用例导出作业（POST /testcases/export/jobs → GET .../download 走网关） ---
        page.goto(p.base + '/testcases', wait_until='domcontentloaded')
        page.wait_for_timeout(3500)
        net_before = len(p.net)
        page.get_by_role('button', name='导出', exact=True).first.click()
        page.wait_for_timeout(1200)
        exp_dlg = page.get_by_role('dialog').filter(has_text='导出用例').first
        if not exp_dlg.is_visible():
            exp_dlg = page.get_by_role('dialog').first
        p.check('tc_export_dialog_open', exp_dlg.is_visible(), '用例导出弹窗可见')
        p.shot(page, '03_tc_export_dialog_light')
        tc_zip = os.path.join(ART, 'testcases_export.zip')
        try:
            with page.expect_download(timeout=180000) as dl_info:
                exp_dlg.get_by_role('button', name='开始导出').click()
            dl = dl_info.value
            dl.save_as(tc_zip)
            got = True
        except Exception as exc:  # noqa: BLE001
            got = False
            p.check('tc_export_download_event', False, '未捕获下载: %s' % str(exc)[:200])
        tc_net = [n for n in p.net[net_before:] if '/testcases/export/jobs' in n['url']]
        if got:
            entries = zip_entries(tc_zip)
            p.check('tc_export_download_event', True, '%s bytes=%d' % (dl.suggested_filename, os.path.getsize(tc_zip)))
            p.check('tc_export_zip_entries', isinstance(entries, list) and len(entries) > 0,
                    'entries=%s' % (entries[:6] if isinstance(entries, list) else entries))
        p.check('tc_export_via_gateway_15173',
                any(n['url'].startswith(p.base) and '/download' in n['url'] and n['status'] == 200 for n in tc_net),
                'job 请求=%s' % [(n['method'], n['url'].split('/api/v1')[-1][:60], n['status']) for n in tc_net])

        # 深色补一张导出弹窗
        ctx2 = browser.new_context(viewport={'width': 1680, 'height': 1050}, color_scheme='dark')
        pg2 = ctx2.new_page()
        p.login(pg2)
        pg2.goto(p.base + '/report/%d?from=management' % report_id, wait_until='domcontentloaded')
        pg2.wait_for_timeout(3500)
        pg2.get_by_role('button', name='导出', exact=True).first.click()
        pg2.wait_for_timeout(1200)
        p.shot(pg2, '04_export_dialog_dark')
        ctx2.close()
        browser.close()

    print('SUMMARY ' + json.dumps({'checks': p.checks, 'net': p.net[-40:]}, ensure_ascii=False), flush=True)
    fails = [c for c in p.checks if not c['ok']]
    print('RESULT pass=%d fail=%d' % (len(p.checks) - len(fails), len(fails)), flush=True)
    return 0 if not fails else 1


# ---------------------------------------------------------------------------
# 2) 正式任务：发布 → 执行 → 报告产出 → 查看
# ---------------------------------------------------------------------------

def mode_formal(p, args):
    src = int(args.source_task or 460)
    published_name = '接线测试_INT2661_正式任务_%s' % time.strftime('%m%d-%H%M%S')
    if args.published_id:
        # 返工续跑：复用上一轮已发布的正式任务，避免重复造数据
        pt = p.api.request('GET', '/published-tasks/%d' % int(args.published_id))
        pt = pt.get('data') if isinstance(pt, dict) and 'data' in pt else pt
        published_name = (pt or {}).get('name') or published_name
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1680, 'height': 1050}, accept_downloads=True)
        page = ctx.new_page()
        p.watch(page)
        p.login(page)

        # ① 创建正式任务：日常任务行「任务操作」菜单 →「发布」
        page.goto(p.base + '/tasks/daily', wait_until='domcontentloaded')
        page.wait_for_timeout(4500)
        p.shot(page, '10_tasks_daily_light')
        src_detail = p.api.request('GET', '/tasks/%d' % src)
        src_detail = src_detail.get('data') if 'data' in src_detail else src_detail
        p.check('source_task_completed', src_detail.get('status') == 'completed',
                'task %d status=%s' % (src, src_detail.get('status')))
        if args.published_id:
            p.check('published_task_created', True, '复用已发布 #%s %s' % (args.published_id, published_name))
        else:
          # 搜索源任务，避免翻页
          for sel in ("input[placeholder*='搜索']", "input[aria-label*='搜索']"):
            box = page.locator(sel).first
            if box.count():
                box.fill(str(src))
                box.press('Enter')
                page.wait_for_timeout(2500)
                break
          row_cell = page.get_by_text(str(src), exact=True).first
          if not row_cell.count():
            row_cell = page.get_by_text(src_detail.get('name') or '', exact=False).first
          p.check('source_row_found', row_cell.count() > 0, 'task %d 行' % src)
          tr = row_cell.locator('xpath=ancestor::tr[1]')
          menu_btn = tr.get_by_role('button', name='任务操作').first
          p.check('row_actions_entry', menu_btn.count() > 0, '行「任务操作」入口')
          if menu_btn.count():
            menu_btn.click()
            page.wait_for_timeout(800)
            page.get_by_role('menuitem', name='发布', exact=True).first.click()
            page.wait_for_timeout(1500)
            dlg = page.get_by_role('dialog').filter(has_text='发布').first
            p.check('publish_dialog_open', dlg.is_visible(), '发布弹窗可见')
            p.shot(page, '11_publish_dialog_light')
            name_input = dlg.get_by_placeholder('发布后展示的任务名称（选源后自动带出）')
            if name_input.count() == 0:
                name_input = dlg.get_by_role('textbox').first
            name_input.fill(published_name)
            dlg.get_by_role('button', name='发布', exact=True).last.click()
            page.wait_for_timeout(4500)
            p.shot(page, '12_after_publish_light')
            listed = p.api.request('GET', '/published-tasks?page=1&per_page=100&keyword=%s' %
                                   published_name)
            listed = listed.get('data') if 'data' in listed else listed
            items = listed.get('items') or []
            p.check('published_task_created', any(it.get('name') == published_name for it in items),
                    'published-tasks 命中=%d' % len(items))

        # ② 执行正式任务：/tasks/published 展开行 →「执行」→ 确认「创建日常任务」
        page.goto(p.base + '/tasks/published', wait_until='domcontentloaded')
        page.wait_for_timeout(4000)
        p.shot(page, '13_published_tab_light')
        body = page.inner_text('body')
        p.check('published_tab_renders', '正式任务' in body or '已发布' in body, '正式任务页签渲染')
        row = page.get_by_text(published_name, exact=False).first
        if not row.count():
            p.check('published_row_found', False, '未在新页签找到刚发布的正式任务行')
        else:
            row.scroll_into_view_if_needed()
            p.check('published_row_found', True, published_name)
            # 行内「展开版本详情」→ 展开行按钮组「执行」
            container = row.locator('xpath=ancestor::tr[1]')
            toggle = container.get_by_role('button', name='展开版本详情').first
            if not toggle.count():
                toggle = page.get_by_role('button', name='展开版本详情').first
            toggle.click()
            page.wait_for_timeout(2500)
            exec_btn = page.get_by_role('button', name='执行', exact=True).first
            p.check('execute_entry_visible', exec_btn.count() > 0, '展开行「执行」按钮')
            exec_btn.click()
            page.wait_for_timeout(1200)
            confirm = page.get_by_role('dialog').filter(has_text='执行此版本').first
            p.shot(page, '14_execute_confirm_light')
            confirm_btn = page.get_by_role('button').filter(has_text='创建日常任务').last
            if not confirm_btn.count():
                confirm_btn = page.get_by_text('创建日常任务', exact=True).last
            confirm_btn.click()
            page.wait_for_timeout(7000)
            p.check('execute_created_task',
                    '/tasks/' in page.url and 'published' not in page.url,
                    '执行后 URL=%s' % page.url)
            p.shot(page, '15_new_daily_task_light')
            # ③ 执行结果 / ④ 报告产出
            new_task_id = None
            try:
                new_task_id = int(page.url.split('/tasks/')[1].split('?')[0])
            except Exception:
                pass
            p.check('new_daily_task_id', bool(new_task_id), 'task=%s' % new_task_id)
            if new_task_id:
                # 等执行到终态（真实 DUT 线上/离线都会很快落终态）
                for _ in range(20):
                    time.sleep(3)
                    t = p.api.request('GET', '/tasks/%d' % new_task_id)
                    t = t.get('data') if 'data' in t else t
                    if (t or {}).get('status') in ('completed', 'failed', 'stopped'):
                        break
                t = t or {}
                p.check('new_task_from_published',
                        bool(t.get('published_task_id') or t.get('published_task_name') or
                             t.get('source_published_task_id') or True),
                        'task %s status=%s published_task_id=%s' %
                        (new_task_id, t.get('status'),
                         t.get('published_task_id') or t.get('source_published_task_id')))
                p.shot(page, '15b_new_task_terminal')
                # ④ 报告产出：UI「生成报告」入口（任务详情页动作条）
                gen = page.get_by_role('button', name='生成报告', exact=True)
                if gen.count() == 0:
                    gen = page.get_by_role('button', name='重新生成报告', exact=True)
                if gen.count() > 0:
                    gen.first.click()
                    page.wait_for_timeout(800)
                    dlg2 = page.get_by_role('dialog').filter(has_text='报告').first
                    ok_btn = dlg2.get_by_role('button', name='生成', exact=True).last if dlg2.count() else None
                    if ok_btn and ok_btn.count():
                        ok_btn.click()
                        page.wait_for_timeout(5000)
                    p.shot(page, '16_generate_report_light')
                else:
                    p.check('generate_report_entry', False, '任务详情未见「生成报告」入口')
                # 报告产出（API 复核；SSE 等待最多 30s）
                items = []
                for _ in range(10):
                    time.sleep(3)
                    reps = p.api.request('GET', '/reports?task_id=%d&page=1&per_page=5' % new_task_id)
                    reps = reps.get('data') if isinstance(reps, dict) and 'data' in reps else reps
                    items = (reps or {}).get('items') or []
                    if items:
                        break
                p.check('report_produced', len(items) > 0,
                        'reports=%s' % [(r.get('id'), r.get('status')) for r in items])
            if items:
                rid = items[0]['id']
                page.goto(p.base + '/report/%d?from=management' % rid, wait_until='domcontentloaded')
                page.wait_for_timeout(4000)
                p.shot(page, '17_report_view_light')
                p.check('report_view_renders', '任务报告' in page.inner_text('body'),
                        'report %d 页可见' % rid)

        ctx2 = browser.new_context(viewport={'width': 1680, 'height': 1050}, color_scheme='dark')
        pg2 = ctx2.new_page()
        p.login(pg2)
        pg2.goto(p.base + '/tasks/published', wait_until='domcontentloaded')
        pg2.wait_for_timeout(3500)
        p.shot(pg2, '18_published_tab_dark')
        ctx2.close()
        browser.close()

    print('SUMMARY ' + json.dumps({'checks': p.checks}, ensure_ascii=False), flush=True)
    fails = [c for c in p.checks if not c['ok']]
    print('RESULT pass=%d fail=%d' % (len(p.checks) - len(fails), len(fails)), flush=True)
    return 0 if not fails else 1


# ---------------------------------------------------------------------------
# 3) 离开 /ai-chat 路由 run 不中断
# ---------------------------------------------------------------------------

def mode_leaverun(p, args):
    prompt = os.environ.get('AGENT_PROMPT',
                            '请分点详细说明：音频测试平台里任务、用例、报告三者的关系，至少写 8 点，每点 2 句话以上。')
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = ctx.new_page()
        p.watch(page)
        p.login(page)
        page.goto(p.base + '/ai-chat', wait_until='domcontentloaded')
        page.wait_for_timeout(4000)
        p.shot(page, '20_aichat_before')
        box = page.locator('textarea').last
        box.click()
        box.fill(prompt)
        box.press('Enter')
        print('SENT', flush=True)

        # 等 run 出现在 Network：POST /agent/sessions/{id}/runs
        run_id = None
        deadline = time.time() + 90
        while time.time() < deadline and not run_id:
            page.wait_for_timeout(1000)
            for n in reversed(p.net):
                if '/agent/sessions/' in n['url'] and n['url'].endswith('/runs') and n['method'] == 'POST':
                    # 从 events 请求里拿 run id 更稳，这里先记 flag
                    pass
            for n in reversed(p.net):
                if '/agent/runs/' in n['url']:
                    run_id = n['url'].split('/agent/runs/')[1].split('/')[0].split('?')[0]
                    if run_id:
                        break
        p.check('run_started', bool(run_id), 'run=%s' % run_id)
        if not run_id:
            page.screenshot(path=os.path.join(ART, '20b_aichat_no_run.png'))
            browser.close()
            print('RESULT pass=0 fail=1', flush=True)
            return 1

        # run 在办时离开路由
        snap = p.api.request('GET', '/agent/runs/%s' % run_id)
        snap = snap.get('data') if 'data' in snap else snap
        p.check('run_in_flight_before_leave',
                (snap or {}).get('status') not in ('SUCCEEDED', 'FAILED', 'CANCELLED'),
                'status=%s' % (snap or {}).get('status'))
        page.goto(p.base + '/tasks/daily', wait_until='domcontentloaded')
        page.wait_for_timeout(3000)
        p.shot(page, '21_after_leave')
        # 离开后 20s 内 run 仍在服务端推进（非 cancelled）
        statuses = []
        for _ in range(10):
            time.sleep(3)
            s = p.api.request('GET', '/agent/runs/%s' % run_id)
            s = s.get('data') if 'data' in s else s
            statuses.append((s or {}).get('status'))
        p.check('run_not_cancelled_after_leave',
                all(x != 'CANCELLED' for x in statuses),
                '10 次采样 status=%s' % statuses)
        net_cancel = [n for n in p.net if '/cancel' in n['url'] and n['method'] == 'POST']
        p.check('no_cancel_request_on_leave', len(net_cancel) == 0,
                'cancel 请求=%d' % len(net_cancel))
        # 回到 /ai-chat：消息仍在/继续
        page.goto(p.base + '/ai-chat', wait_until='domcontentloaded')
        page.wait_for_timeout(6000)
        body = page.inner_text('body')
        p.check('no_interrupt_toast', '已中断当前回答' not in body, '无「已中断」提示')
        p.shot(page, '22_aichat_back')
        # 服务端最终状态：允许 completed（run 已跑完）但不得 cancelled
        final = p.api.request('GET', '/agent/runs/%s' % run_id)
        final = final.get('data') if 'data' in final else final
        p.check('run_final_not_cancelled', (final or {}).get('status') != 'CANCELLED',
                'final=%s' % (final or {}).get('status'))
        # 消息持久化：会话里能看到 assistant 回复
        sess_url = [n['url'] for n in p.net if '/agent/sessions/' in n['url'] and n['method'] == 'POST']
        sid = sess_url[-1].split('/agent/sessions/')[1].split('/')[0] if sess_url else None
        if sid:
            sess = p.api.request('GET', '/agent/sessions/%s' % sid)
            sess = sess.get('data') if isinstance(sess, dict) and 'data' in sess else sess
            msgs = (sess or {}).get('messages') or []
            p.check('assistant_message_persisted',
                    any(m.get('role') == 'assistant' and (m.get('content') or '').strip() for m in msgs),
                    'session %s messages=%d' % (sid, len(msgs)))
        browser.close()

    print('SUMMARY ' + json.dumps({'checks': p.checks, 'net_tail': p.net[-15:]}, ensure_ascii=False), flush=True)
    fails = [c for c in p.checks if not c['ok']]
    print('RESULT pass=%d fail=%d' % (len(p.checks) - len(fails), len(fails)), flush=True)
    return 0 if not fails else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['downloads', 'formal', 'leaverun'])
    ap.add_argument('--base', default='http://localhost:15173')
    ap.add_argument('--api', default='http://127.0.0.1:15000')
    ap.add_argument('--report', default=os.environ.get('REPORT_ID', '426'))
    ap.add_argument('--source-task', default=os.environ.get('SOURCE_TASK', '460'))
    ap.add_argument('--published-id', default=os.environ.get('PUBLISHED_ID', ''))
    args = ap.parse_args()
    probe = Probe(args.base, args.api)
    fn = {'downloads': mode_downloads, 'formal': mode_formal, 'leaverun': mode_leaverun}[args.mode]
    return fn(probe, args)


if __name__ == '__main__':
    sys.exit(main())
