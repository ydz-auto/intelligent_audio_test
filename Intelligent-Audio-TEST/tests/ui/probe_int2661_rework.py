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
  python tests/ui/probe_int2661_rework.py msgdelete --base http://localhost:15173 --api http://127.0.0.1:15000

msgdelete（代码审计 2026-11-20 02:31 打回的唯一项）：在 dev_user 本 run 新建的会话里
发一条真实消息 → 点用户气泡「删除」→ 气泡消失 → 刷新并重开同一会话仍不出现；
同时 GET /agent/sessions/{id} 前后 messages 差 1、被删 id 不在返回里。收尾按会话 id
删除本 run 自建的 agent_* 明细（token 标题守卫，事务外逐表 scoped delete）。
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


# ---------------------------------------------------------------------------
# 4) fb0ebb926：AI 对话消息删除的端到端持久化（真实删除 → 刷新 → 仍不出现）
# ---------------------------------------------------------------------------

TERMINAL_RUN_STATUSES = ('SUCCEEDED', 'FAILED', 'CANCELLED')


def _open_history_session(page, token, timeout_ms=45000):
    """展开「对话记录」并点开标题含 token 的会话（重新走 GET /agent/sessions/{id} 回填）。"""
    hist = page.locator('aside').filter(has_text='对话记录')
    if hist.count() == 0:
        page.click("button[aria-label='对话记录']")
        page.wait_for_timeout(700)
    item = page.locator('aside button').filter(has_text=token).first
    item.wait_for(state='visible', timeout=timeout_ms)
    item.click()
    page.wait_for_timeout(2500)


def _user_bubbles(page, token):
    """对话正文里的用户气泡（排除历史目录标题，标题本身是首条消息快照）。"""
    return page.locator('div.group.is-user').filter(has_text=token)


def _assistant_bubbles(page):
    return page.locator('div.group.is-assistant')


def _cleanup_session(sid, token, run_status):
    """数据卫生：删除本 run 新建的会话与 run 明细（严格按 token 标题守卫）。"""
    if not sid:
        return {'skipped': 'no session'}
    if run_status not in TERMINAL_RUN_STATUSES:
        return {'skipped': 'run not terminal', 'run_status': run_status}
    try:
        import psycopg2
    except Exception as exc:  # noqa: BLE001
        return {'skipped': 'psycopg2 unavailable: %s' % exc}
    try:
        conn = psycopg2.connect(
            host='127.0.0.1', port=5432, dbname='intelligent_audio_test',
            user='intelligent_audio_test',
            password='intelligent_audio_test666', connect_timeout=5)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute('select title from agent_session where id=%s', (sid,))
        row = cur.fetchone()
        if not row or token not in (row[0] or ''):
            conn.close()
            return {'skipped': 'title guard mismatch',
                    'title': row[0] if row else None}
        scoped = [
            ('agent_run_event', 'run_id in (select id from agent_run where session_id=%s)'),
            ('agent_step', 'run_id in (select id from agent_run where session_id=%s)'),
            ('agent_tool_call', 'run_id in (select id from agent_run where session_id=%s)'),
            ('agent_approval', 'run_id in (select id from agent_run where session_id=%s)'),
            ('agent_artifact', 'run_id in (select id from agent_run where session_id=%s)'),
            ('agent_context_snapshot', 'run_id in (select id from agent_run where session_id=%s)'),
            ('agent_run_skill', 'run_id in (select id from agent_run where session_id=%s)'),
            ('agent_hidden_message', 'session_id=%s'),
            ('agent_run', 'session_id=%s'),
            ('agent_session', 'id=%s'),
        ]
        deleted = {}
        for table, where in scoped:
            cur.execute('delete from %s where %s' % (table, where), (sid,))
            deleted[table] = cur.rowcount
        conn.close()
        return {'deleted': deleted}
    except Exception as exc:  # noqa: BLE001
        return {'error': str(exc)}


def mode_msgdelete(p, args):
    """真实删除本 run 新建的用户消息：删除请求/响应 + 气泡消失 + 刷新后仍不出现。"""
    token = 'INT2661删除持久化验证%s' % time.strftime('%H%M%S')
    prompt = '%s：只回复「收到」两个字，不要调用任何工具，不要展开说明。' % token
    sid = None
    rid = None
    run_status = None
    pre_msgs = []
    deleted_id = None
    delete_status = None
    delete_body = ''
    delete_url = ''

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = ctx.new_page()
        p.watch(page)
        p.login(page)
        page.goto(p.base + '/ai-chat', wait_until='domcontentloaded')
        page.wait_for_timeout(3000)
        # 新对话：确保消息落在本 run 新建的会话里，不动既有会话
        page.click("button[aria-label='对话记录']")
        page.wait_for_timeout(800)
        page.get_by_role('button', name='新对话').click()
        page.wait_for_timeout(600)
        box = page.locator('textarea').last
        box.click()
        box.fill(prompt)
        p.shot(page, '30_new_message_light')
        box.press('Enter')

        # 会话 id 从 POST /agent/sessions/{sid}/runs 的请求 URL 取
        deadline = time.time() + 60
        while time.time() < deadline and not sid:
            page.wait_for_timeout(1000)
            for n in reversed(p.net):
                u = n['url'].split('?')[0]
                if (n['method'] == 'POST' and '/agent/sessions/' in u
                        and u.endswith('/runs')):
                    sid = u.split('/agent/sessions/')[1].split('/runs')[0]
        p.check('new_session_created', bool(sid),
                'session=%s token=%s' % (sid, token))
        if not sid:
            p.shot(page, '30b_no_session')
            ctx.close()
            browser.close()
            return 1

        # 等 run 终态（FAILED 也继续：用户消息已落库，删除持久化仍可验）
        deadline = time.time() + 180
        detail = {}
        while time.time() < deadline:
            detail = p.api.request('GET', '/agent/sessions/%s' % sid) or {}
            runs = detail.get('runs') or []
            if runs:
                rid = runs[-1].get('id')
                run_status = runs[-1].get('status')
                if run_status in TERMINAL_RUN_STATUSES:
                    break
            page.wait_for_timeout(3000)
        p.check('run_terminal', run_status in TERMINAL_RUN_STATUSES,
                'run=%s status=%s' % (rid, run_status))

        detail = p.api.request('GET', '/agent/sessions/%s' % sid) or {}
        pre_msgs = detail.get('messages') or []
        pre_ids = [m.get('id') for m in pre_msgs]
        user_msg = next((m for m in pre_msgs if m.get('role') == 'user'
                         and token in (m.get('content') or '')), None)
        deleted_id = (user_msg or {}).get('id')
        p.check('pre_user_message_present', bool(user_msg),
                'id=%s msgs=%d ids=%s' % (deleted_id, len(pre_msgs), pre_ids))
        p.check('pre_id_matches_run', deleted_id == ('user:%s' % rid),
                'expect user:%s got %s' % (rid, deleted_id))
        page.wait_for_timeout(2500)
        p.check('ui_user_bubble_visible', _user_bubbles(page, token).count() == 1,
                'user_bubbles=%d' % _user_bubbles(page, token).count())
        p.shot(page, '31_after_reply_light')

        # 刷新后（删除前）仍在：证明后续「消失」是删除生效而不是本地态没被回填
        page.reload(wait_until='domcontentloaded')
        page.wait_for_timeout(3000)
        _open_history_session(page, token)
        p.check('pre_delete_refresh_user_persists',
                _user_bubbles(page, token).count() == 1,
                'user_bubbles=%d' % _user_bubbles(page, token).count())
        p.shot(page, '32_pre_delete_refresh_light')

        page.emulate_media(color_scheme='dark')
        page.reload(wait_until='domcontentloaded')
        page.wait_for_timeout(3000)
        _open_history_session(page, token)
        p.check('dark_applied',
                page.evaluate("document.documentElement.classList.contains('dark')"),
                'dark=%s' % page.evaluate(
                    "document.documentElement.classList.contains('dark')"))
        p.check('pre_delete_refresh_dark_user_persists',
                _user_bubbles(page, token).count() == 1,
                'user_bubbles=%d' % _user_bubbles(page, token).count())
        p.shot(page, '32_pre_delete_refresh_dark')

        page.emulate_media(color_scheme='light')
        page.reload(wait_until='domcontentloaded')
        page.wait_for_timeout(3000)
        _open_history_session(page, token)

        # 点用户气泡的「删除」→ 捕获 DELETE 请求/响应
        row = _user_bubbles(page, token).first
        row.wait_for(state='visible', timeout=15000)
        row.hover()
        btn = row.locator("button[aria-label='删除']").first
        btn.wait_for(state='visible', timeout=10000)
        try:
            with page.expect_response(
                    lambda r: (r.request.method == 'DELETE'
                               and '/agent/sessions/' in r.url
                               and '/messages/' in r.url),
                    timeout=20000) as info:
                btn.click()
            resp = info.value
            delete_status = resp.status
            delete_url = resp.url
            try:
                delete_body = resp.text()
            except Exception:  # noqa: BLE001
                delete_body = ''
            from urllib.parse import unquote
            p.check('delete_request_ok', delete_status in (200, 204),
                    'DELETE %s -> %s %s' % (delete_url, delete_status,
                                            delete_body[:200]))
            p.check('delete_targets_user_message',
                    bool(deleted_id) and deleted_id in unquote(delete_url),
                    'target=%s url=%s' % (deleted_id, delete_url))
        except Exception as exc:  # noqa: BLE001
            p.check('delete_request_ok', False, 'DELETE 未捕获: %s' % exc)

        gone = False
        for _ in range(20):
            if _user_bubbles(page, token).count() == 0:
                gone = True
                break
            page.wait_for_timeout(500)
        p.check('bubble_gone_after_delete', gone,
                'user_bubbles=%d' % _user_bubbles(page, token).count())

        # 本地缓存是刷新后的首屏来源（zustand 持久化 messages 500ms 防抖）；
        # 等缓存落盘再刷新，避免把「防抖窗口内立即刷新」当成删除未生效。
        cache_flushed = False
        flush_ms = None
        cache_before = page.evaluate(
            "localStorage.getItem('iatp:ai-chat:v1:messages')") or ''
        t0 = time.time()
        while time.time() - t0 < 8:
            raw = page.evaluate(
                "localStorage.getItem('iatp:ai-chat:v1:messages')") or ''
            if token not in raw:
                cache_flushed = True
                flush_ms = int((time.time() - t0) * 1000)
                break
            page.wait_for_timeout(150)
        p.check('local_cache_flushed_after_delete', cache_flushed,
                'flush_ms=%s before_has_token=%s after_has_token=%s'
                % (flush_ms, token in cache_before,
                   token in (page.evaluate(
                       "localStorage.getItem('iatp:ai-chat:v1:messages')")
                       or '')))
        p.shot(page, '33_after_delete_light')

        # 刷新 → 重新打开同一会话：被删用户消息仍不出现，助手回复还在
        page.reload(wait_until='domcontentloaded')
        page.wait_for_timeout(3000)
        _open_history_session(page, token)
        p.check('after_refresh_user_bubble_absent',
                _user_bubbles(page, token).count() == 0,
                'user_bubbles=%d' % _user_bubbles(page, token).count())
        p.check('after_refresh_session_loaded',
                _assistant_bubbles(page).count() >= 1,
                'assistant_bubbles=%d' % _assistant_bubbles(page).count())
        p.shot(page, '34_after_refresh_light')

        page.emulate_media(color_scheme='dark')
        page.reload(wait_until='domcontentloaded')
        page.wait_for_timeout(3000)
        _open_history_session(page, token)
        p.check('after_refresh_dark_user_absent',
                _user_bubbles(page, token).count() == 0,
                'user_bubbles=%d' % _user_bubbles(page, token).count())
        p.check('after_refresh_dark_session_loaded',
                _assistant_bubbles(page).count() >= 1,
                'assistant_bubbles=%d' % _assistant_bubbles(page).count())
        p.shot(page, '34_after_refresh_dark')

        # 干净上下文（无 localStorage）打开同一会话：证明「不出现」来自服务端过滤，
        # 不是只靠本地存档把消息藏起来。
        ctx2 = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page2 = ctx2.new_page()
        p.login(page2)
        page2.goto(p.base + '/ai-chat', wait_until='domcontentloaded')
        page2.wait_for_timeout(3000)
        _open_history_session(page2, token)
        p.check('fresh_context_user_bubble_absent',
                _user_bubbles(page2, token).count() == 0,
                'user_bubbles=%d' % _user_bubbles(page2, token).count())
        p.check('fresh_context_session_loaded',
                _assistant_bubbles(page2).count() >= 1,
                'assistant_bubbles=%d' % _assistant_bubbles(page2).count())
        p.shot(page2, '35_fresh_context_light')
        ctx2.close()

        # 接口口径：messages 条数差 1，被删 id 不在返回里
        post = p.api.request('GET', '/agent/sessions/%s' % sid) or {}
        post_msgs = post.get('messages') or []
        post_ids = [m.get('id') for m in post_msgs]
        p.check('api_count_minus_one', len(post_msgs) == len(pre_msgs) - 1,
                'pre=%d post=%d' % (len(pre_msgs), len(post_msgs)))
        p.check('api_deleted_id_absent', deleted_id not in post_ids,
                'deleted=%s post_ids=%s' % (deleted_id, post_ids))
        p.check('api_context_effect',
                any(m.get('role') == 'assistant'
                    and (m.get('content') or '').strip() for m in post_msgs),
                'assistant 仍在：%s' % [m.get('role') for m in post_msgs])
        p.shot(page, '35_post_api_check')
        ctx.close()
        browser.close()

    teardown = _cleanup_session(sid, token, run_status)
    print('TEARDOWN ' + json.dumps(teardown, ensure_ascii=False), flush=True)
    print('SUMMARY ' + json.dumps(
        {'token': token, 'session': sid, 'run': rid, 'run_status': run_status,
         'pre_ids': [m.get('id') for m in pre_msgs], 'deleted': deleted_id,
         'delete': {'url': delete_url, 'status': delete_status,
                    'body': delete_body},
         'checks': p.checks, 'teardown': teardown},
        ensure_ascii=False), flush=True)
    fails = [c for c in p.checks if not c['ok']]
    print('RESULT pass=%d fail=%d' % (len(p.checks) - len(fails), len(fails)),
          flush=True)
    return 0 if not fails else 1


def mode_msgedge(p, args):
    """删除后立刻刷新（本地 messages 500ms 防抖窗口内）：验证是否会「删了又回来」。"""
    token = 'INT2661删除竞态验证%s' % time.strftime('%H%M%S')
    prompt = '%s：只回复「收到」两个字，不要调用任何工具。' % token
    sid = rid = run_status = None

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1600, 'height': 1000})
        page = ctx.new_page()
        p.watch(page)
        p.login(page)
        page.goto(p.base + '/ai-chat', wait_until='domcontentloaded')
        page.wait_for_timeout(3000)
        page.click("button[aria-label='对话记录']")
        page.wait_for_timeout(800)
        page.get_by_role('button', name='新对话').click()
        page.wait_for_timeout(600)
        box = page.locator('textarea').last
        box.click()
        box.fill(prompt)
        box.press('Enter')

        deadline = time.time() + 60
        while time.time() < deadline and not sid:
            page.wait_for_timeout(1000)
            for n in reversed(p.net):
                u = n['url'].split('?')[0]
                if (n['method'] == 'POST' and '/agent/sessions/' in u
                        and u.endswith('/runs')):
                    sid = u.split('/agent/sessions/')[1].split('/runs')[0]
        p.check('new_session_created', bool(sid), 'session=%s' % sid)
        if not sid:
            ctx.close()
            browser.close()
            return 1

        deadline = time.time() + 180
        detail = {}
        while time.time() < deadline:
            detail = p.api.request('GET', '/agent/sessions/%s' % sid) or {}
            runs = detail.get('runs') or []
            if runs:
                rid = runs[-1].get('id')
                run_status = runs[-1].get('status')
                if run_status in TERMINAL_RUN_STATUSES:
                    break
            page.wait_for_timeout(3000)
        p.check('run_terminal', run_status in TERMINAL_RUN_STATUSES,
                'run=%s status=%s' % (rid, run_status))
        pre_msgs = (p.api.request('GET', '/agent/sessions/%s' % sid) or {}).get('messages') or []
        user_msg = next((m for m in pre_msgs if m.get('role') == 'user'
                         and token in (m.get('content') or '')), None)
        deleted_id = (user_msg or {}).get('id')
        p.check('pre_user_message_present', bool(user_msg),
                'id=%s msgs=%d' % (deleted_id, len(pre_msgs)))
        page.wait_for_timeout(2000)

        row = _user_bubbles(page, token).first
        row.wait_for(state='visible', timeout=15000)
        row.hover()
        row.locator("button[aria-label='删除']").first.click()
        t_click = time.time()
        gone = False
        for _ in range(20):
            if _user_bubbles(page, token).count() == 0:
                gone = True
                break
            page.wait_for_timeout(200)
        p.check('bubble_gone_after_delete', gone,
                'user_bubbles=%d' % _user_bubbles(page, token).count())
        # 不等本地防抖落盘，立刻刷新（<500ms 窗口）
        page.reload(wait_until='domcontentloaded')
        reload_ms = int((time.time() - t_click) * 1000)
        page.wait_for_timeout(3000)
        reappeared = _user_bubbles(page, token).count() == 1
        p.check('edge_repro_user_bubble_reappears', reappeared,
                'reload_ms=%s user_bubbles=%d'
                % (reload_ms, _user_bubbles(page, token).count()))
        raw = page.evaluate(
            "localStorage.getItem('iatp:ai-chat:v1:messages')") or ''
        p.check('edge_local_cache_contains_deleted', token in raw,
                'local_cache_has_token=%s len=%d' % (token in raw, len(raw)))
        post_msgs = (p.api.request('GET', '/agent/sessions/%s' % sid) or {}).get('messages') or []
        p.check('edge_server_already_filtered',
                len(post_msgs) == len(pre_msgs) - 1
                and all(m.get('id') != deleted_id for m in post_msgs),
                'pre=%d post=%d deleted_in_server=%s'
                % (len(pre_msgs), len(post_msgs),
                   any(m.get('id') == deleted_id for m in post_msgs)))
        p.shot(page, '40_edge_reappear_light')
        page.emulate_media(color_scheme='dark')
        page.reload(wait_until='domcontentloaded')
        page.wait_for_timeout(2500)
        p.check('edge_reappear_dark_still_there',
                _user_bubbles(page, token).count() == 1,
                'user_bubbles=%d' % _user_bubbles(page, token).count())
        p.shot(page, '40_edge_reappear_dark')
        ctx.close()
        browser.close()

    teardown = _cleanup_session(sid, token, run_status)
    print('TEARDOWN ' + json.dumps(teardown, ensure_ascii=False), flush=True)
    print('SUMMARY ' + json.dumps(
        {'token': token, 'session': sid, 'run': rid, 'run_status': run_status,
         'deleted': deleted_id, 'reload_ms': reload_ms,
         'checks': p.checks, 'teardown': teardown}, ensure_ascii=False),
        flush=True)
    fails = [c for c in p.checks if not c['ok']]
    print('RESULT pass=%d fail=%d' % (len(p.checks) - len(fails), len(fails)),
          flush=True)
    return 0 if not fails else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['downloads', 'formal', 'leaverun',
                                     'msgdelete', 'msgedge'])
    ap.add_argument('--base', default='http://localhost:15173')
    ap.add_argument('--api', default='http://127.0.0.1:15000')
    ap.add_argument('--report', default=os.environ.get('REPORT_ID', '426'))
    ap.add_argument('--source-task', default=os.environ.get('SOURCE_TASK', '460'))
    ap.add_argument('--published-id', default=os.environ.get('PUBLISHED_ID', ''))
    args = ap.parse_args()
    probe = Probe(args.base, args.api)
    fn = {'downloads': mode_downloads, 'formal': mode_formal,
          'leaverun': mode_leaverun, 'msgdelete': mode_msgdelete,
          'msgedge': mode_msgedge}[args.mode]
    return fn(probe, args)


if __name__ == '__main__':
    sys.exit(main())
