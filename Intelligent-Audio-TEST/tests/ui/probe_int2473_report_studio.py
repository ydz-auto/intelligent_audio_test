# -*- coding: utf-8 -*-
"""INT-2473 Report Studio 前端实测（docker 真实库栈，React 5350 → 网关 15000）。

链路（真实请求，不用 mock）：
  报告取数上下文 → 报告工作模式 → 起草 / 载入文档 → 编辑保存新版本
  → 历史版本恢复（内容回到目标版本）→ 导出 MD（进度 → 完成 → 下载产物可打开）
  → 导出 PDF（后端未部署渲染器时失败态可见）→ 浅色 / 深色截图 + Network 请求记录

跑法（环境铁律：连 docker 栈，不启动本地栈）：
  <conda python> tests/ui/probe_int2473_report_studio.py \
      --base http://localhost:5350 --api http://localhost:15000 --report-id 426

产出：tests/ui/artifacts/int2473/summary.json + 截图 + downloads/。
写数据纪律：只动本卡「接线测试_INT2473」文档；不改真实报告记录。
"""
import argparse
import json
import os
import re
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402
from selenium.webdriver.support import expected_conditions as EC  # noqa: E402
from selenium.webdriver.support.ui import WebDriverWait  # noqa: E402

from tests.ui.smoke_frontend_int1854 import (  # noqa: E402
    RESULT,
    body_text,
    console_errors,
    log,
    make_driver,
    parse_perf,
    shot,
    wait_quiet,
)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ART = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int2473')
RESULT['art'] = ART

SUMMARY = {'env': [], 'steps': [], 'requests': [], 'console': [], 'artifacts': []}


def step(name, ok, detail=None):
    rec = {'step': name, 'ok': bool(ok), 'detail': detail or {}}
    SUMMARY['steps'].append(rec)
    log('STEP %s -> %s %s' % (name, 'PASS' if ok else 'FAIL', json.dumps(detail or {}, ensure_ascii=False)[:300]))
    return rec


def env_check(tag, api):
    import urllib.request
    with urllib.request.urlopen(api.rstrip('/') + '/health', timeout=20) as resp:
        health = json.loads(resp.read().decode('utf-8'))
    rec = {'tag': tag, 'health': health}
    SUMMARY['env'].append(rec)
    log('ENV[%s] database=%s' % (tag, health.get('database')))
    assert health.get('database') == 'intelligent_audio_test', '环境串库: %s' % health
    return rec


def click_button(drv, contains=None, exact=None):
    for b in drv.find_elements(By.TAG_NAME, 'button'):
        try:
            if not b.is_displayed() or not b.is_enabled():
                continue
        except Exception:
            continue
        text = (b.text or '').strip()
        if exact and text == exact:
            return b
        if contains and contains in text:
            return b
    return None


def click_aria(drv, label):
    for b in drv.find_elements(By.CSS_SELECTOR, '[aria-label]'):
        try:
            if b.get_attribute('aria-label') == label and b.is_displayed():
                return b
        except Exception:
            continue
    return None


def open_work_mode(drv, timeout=30):
    btn = wait_for(drv, lambda: click_button(drv, contains='报告工作模式'), timeout, 0.4)
    if btn is None:
        return False
    drv.execute_script('arguments[0].click()', btn)
    wait_quiet(drv, timeout=40)
    time.sleep(1.0)
    return bool(drv.find_elements(By.CSS_SELECTOR, "[data-testid='studio-document-panel']"))


def ensure_work_mode(drv, timeout=30):
    """已开着就不再点（按钮此时是「关闭文档预览」，再点会关掉面板）。"""
    if drv.find_elements(By.CSS_SELECTOR, "[data-testid='studio-document-panel']"):
        return True
    return open_work_mode(drv, timeout)


def close_dialog(drv, testid):
    """关闭指定对话框：先找「关闭」按钮，找不到（只有右上角 X）就发 ESC。

    版本链弹窗没有文字「关闭」按钮，旧实现静默失败 → 后续窄屏截图上还压着弹窗。
    """
    sel = "[data-testid='%s']" % testid
    els = drv.find_elements(By.CSS_SELECTOR, sel)
    if not els:
        return True
    # 首选弹窗自带的关闭钮（DialogContent 的 X，文案在 sr-only 里，b.text 取不到）
    for x in els[0].find_elements(By.CSS_SELECTOR, "[data-slot='dialog-close']"):
        try:
            drv.execute_script('arguments[0].click()', x)
            if wait_for(drv, lambda: not drv.find_elements(By.CSS_SELECTOR, sel), 8, 0.2):
                return True
        except Exception:
            continue
    for b in els[0].find_elements(By.TAG_NAME, 'button'):
        try:
            if (b.text or '').strip() == '关闭':
                drv.execute_script('arguments[0].click()', b)
                if wait_for(drv, lambda: not drv.find_elements(By.CSS_SELECTOR, sel), 8, 0.2):
                    return True
                break
        except Exception:
            continue
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    return bool(wait_for(
        drv, lambda: not drv.find_elements(By.CSS_SELECTOR, sel), 8, 0.2))


def cleanup_studio_rows(report_ids, title_like='%INT2473%', since=None):
    """删掉本 run 建的 Studio 测试行（Studio 无删除接口；只按 doc_id 精确删）。

    `since` = 本 run 开工时间（东八区 naive，与后端 utc8now 落库口径一致）：
    只删本 run 之后建的行，避免把共享库里别人/历史 run 的文档一起清掉。
    """
    import psycopg2

    conn = psycopg2.connect(
        host=os.environ.get('STUDIO_DB_HOST', 'localhost'),
        port=int(os.environ.get('STUDIO_DB_PORT', '5432')),
        dbname=os.environ.get('STUDIO_DB_NAME', 'intelligent_audio_test'),
        user=os.environ.get('STUDIO_DB_USER', 'intelligent_audio_test'),
        password=os.environ.get('STUDIO_DB_PASSWORD', 'intelligent_audio_test666'),
        connect_timeout=10,
    )
    try:
        with conn.cursor() as cur:
            sql = ('select doc_id from report_studio_documents '
                   'where (report_id = any(%s) or title like %s)')
            params = [list(report_ids), title_like]
            if since is not None:
                sql += ' and created_at >= %s'
                params.append(since)
            cur.execute(sql, tuple(params))
            ids = [row[0] for row in cur.fetchall()]
            if ids:
                for table in ('report_studio_export_jobs',
                              'report_studio_chart_specs',
                              'report_studio_document_versions',
                              'report_studio_documents'):
                    try:
                        cur.execute(
                            'delete from %s where doc_id = any(%%s)' % table, (ids,))
                    except Exception:
                        conn.rollback()
                        raise
        conn.commit()
    finally:
        conn.close()
    return ids


def login(drv, base, username, password):
    drv.get(base + '/login')
    try:
        WebDriverWait(drv, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type=password]')))
    except Exception:
        drv.execute_script('window.localStorage.clear()')
        drv.get(base + '/login')
        WebDriverWait(drv, 45).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, 'input[type=password]')))
    time.sleep(1.0)
    u = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input')
         if e.get_attribute('type') in (None, 'text', 'email') and e.is_displayed()][0]
    p = [e for e in drv.find_elements(By.CSS_SELECTOR, 'input[type=password]')
         if e.is_displayed()][0]
    u.clear(); u.send_keys(username)
    p.clear(); p.send_keys(password)
    btns = [b for b in drv.find_elements(By.TAG_NAME, 'button')
            if b.is_displayed() and b.text.strip() in ('登 录', '登录')]
    if not btns:
        btns = [b for b in drv.find_elements(By.CSS_SELECTOR, 'button[type=submit]')
                if b.is_displayed()]
    drv.execute_script('arguments[0].click()', btns[0])
    WebDriverWait(drv, 45).until(lambda d: '/login' not in d.current_url)
    time.sleep(2.0)


def wait_for(drv, predicate, timeout=30, interval=0.3):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            value = predicate()
            if value:
                return value
        except Exception:
            pass
        time.sleep(interval)
    return None


def panel_text(drv):
    els = drv.find_elements(By.CSS_SELECTOR, "[data-testid='studio-document-panel']")
    return els[0].text if els else ''


def find_versions(drv):
    return drv.find_elements(By.CSS_SELECTOR, "[data-testid='studio-version-list'] li[data-version]")


def render_network_page(requests, path):
    rows = ''.join(
        '<tr><td>%s</td><td class="u">%s</td><td class="%s">%s</td></tr>'
        % (r.get('method'), (r.get('url') or '').replace('http://localhost:5350', ''),
           'ok' if (r.get('status') or 0) < 400 else 'bad', r.get('status'))
        for r in requests)
    html = """<!doctype html><meta charset="utf-8"><title>INT-2473 Network</title>
<style>body{font:12px/1.5 "Segoe UI",sans-serif;padding:16px;background:#fff;color:#111}
h1{font-size:15px;margin:0 0 8px}table{border-collapse:collapse;width:100%%}
td,th{border-bottom:1px solid #e5e5e5;padding:4px 6px;text-align:left;vertical-align:top}
th{background:#f5f5f5;position:sticky;top:0}.u{word-break:break-all;font-family:Consolas,monospace}
.ok{color:#1a7f37;font-weight:600}.bad{color:#cf222e;font-weight:600}</style>
<h1>INT-2473 Report Studio 实测 · 真实 API 请求记录（/api/v1）</h1>
<table><thead><tr><th>方法</th><th>URL</th><th>状态</th></tr></thead><tbody>%s</tbody></table>""" % rows
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(html)
    return path


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5350')
    ap.add_argument('--api', default='http://localhost:15000')
    ap.add_argument('--username', default='dev_user')
    ap.add_argument('--password', default='dev_password')
    ap.add_argument('--report-id', type=int, default=426)
    ap.add_argument('--empty-report-id', type=int, default=425)
    # 任务上下文两例：451 = 已完成任务但无报告（by_task 404）；460 = 已完成任务且有报告 426
    ap.add_argument('--task-without-report-id', type=int, default=451)
    ap.add_argument('--task-with-report-id', type=int, default=460)
    args = ap.parse_args()

    # 本 run 开工时间：清理只删这之后建的行（后端 created_at 用东八区 naive）
    run_start = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None)

    os.makedirs(ART, exist_ok=True)
    downloads = os.path.join(ART, 'downloads')
    os.makedirs(downloads, exist_ok=True)
    # 只清本目录历史下载，确保「新产物落盘」判定不被上一轮文件干扰
    for name in os.listdir(downloads):
        path = os.path.join(downloads, name)
        if os.path.isfile(path):
            os.remove(path)

    env_check('start', args.api)
    drv = make_driver(downloads)
    base = args.base.rstrip('/')
    try:
        login(drv, base, args.username, args.password)
        step('login', '/login' not in drv.current_url, {'url': drv.current_url})

        # 1. 报告取数上下文（URL 契约 + 真实名称解析）
        drv.get('%s/ai-chat?report=%d' % (base, args.report_id))
        wait_quiet(drv, timeout=40)
        time.sleep(1.0)
        text = body_text(drv)
        badge_ok = ('#%d' % args.report_id) in text or ('报告 #%d' % args.report_id) in text
        step('context_badge', badge_ok, {'snippet': text[:240]})
        shot(drv, '01_context_light')

        # 选择器打开：真实报告 / 任务列表 + 来源 ID
        trigger = None
        for b in drv.find_elements(By.CSS_SELECTOR, "button[role='combobox']"):
            if b.is_displayed():
                trigger = b
                break
        if trigger is not None:
            drv.execute_script('arguments[0].click()', trigger)
            time.sleep(2.5)
            pop_text = body_text(drv)
            step('context_selector', ('来源：报告 #' in pop_text) or ('测试报告' in pop_text),
                 {'has_source_id': '来源：报告 #' in pop_text})
            shot(drv, '02_context_selector_light')
            drv.execute_script('arguments[0].click()', trigger)
            time.sleep(0.8)
        else:
            step('context_selector', False, {'reason': 'combobox not found'})

        # 2. 报告工作模式
        btn = click_button(drv, contains='报告工作模式')
        if btn is None:
            raise AssertionError('报告工作模式按钮未找到')
        drv.execute_script('arguments[0].click()', btn)
        wait_quiet(drv, timeout=40)
        time.sleep(1.0)
        panel = panel_text(drv)
        step('work_mode_open', bool(panel), {'panel': panel[:300]})
        shot(drv, '03_panel_light')

        # 3. 文档载入 / 起草
        draft_btn = None
        deadline = time.time() + 25
        while time.time() < deadline:
            panel = panel_text(drv)
            if '版本' in panel or '该报告还没有 Studio 文档' in panel:
                break
            time.sleep(0.5)
        if '该报告还没有 Studio 文档' in panel:
            draft_btn = drv.find_element(By.CSS_SELECTOR, "[data-testid='studio-draft-button']")
            drv.execute_script('arguments[0].click()', draft_btn)
            wait_quiet(drv, timeout=40)
            time.sleep(1.2)
            panel = panel_text(drv)
        doc_loaded = '版本' in panel and '取数来源' in panel
        step('document_loaded', doc_loaded, {'panel': panel[:300]})
        shot(drv, '04_document_light')

        # 编辑前记录「当前版本号 + 正文渲染文本」：恢复后逐字比对，不依赖起草模板字面量
        # （旧脚本断言出现「初始内容 v1」，而 V10.11.2 模板是「数据来源：报告 #N…」→ 干净库必挂）
        base_version = 1
        version_match = re.search(r'版本\s*(\d+)', panel)
        if version_match:
            base_version = int(version_match.group(1))
        baseline_text = ''
        content_els = drv.find_elements(By.CSS_SELECTOR, "[data-testid='studio-document-content']")
        if content_els:
            baseline_text = content_els[0].text.strip()
        step('capture_baseline', bool(baseline_text), {
            'version': base_version, 'content': baseline_text[:160],
        })

        # 4. 编辑保存 = 新版本（真实 PUT，乐观锁）
        edit_btn = click_aria(drv, '编辑文档')
        if edit_btn is None:
            raise AssertionError('编辑按钮未找到')
        drv.execute_script('arguments[0].click()', edit_btn)
        editor = wait_for(drv, lambda: drv.find_element(By.CSS_SELECTOR, "[data-testid='studio-document-editor']"), 15)
        marker = '接线测试_INT2473 编辑于 %s' % time.strftime('%H:%M:%S')
        new_content = '# 接线测试 Report Studio\n\n%s\n\n- 取数来源：报告 #%d\n' % (marker, args.report_id)
        # React 受控 textarea：走原生 value setter + input 事件（send_keys 在受控组件里偶发丢值）
        drv.execute_script(
            "const el=arguments[0];"
            "const setter=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;"
            "setter.call(el, arguments[1]);"
            "el.dispatchEvent(new Event('input',{bubbles:true}));",
            editor, new_content)
        time.sleep(0.6)
        value_ok = drv.execute_script("return arguments[0].value;", editor) == new_content
        save_btn = wait_for(
            drv,
            lambda: drv.find_element(By.CSS_SELECTOR, "[data-testid='studio-document-save']")
            if drv.find_element(By.CSS_SELECTOR, "[data-testid='studio-document-save']").is_enabled()
            else None,
            10)
        if save_btn is None:
            raise AssertionError('保存按钮未启用（编辑值未进入受控状态）')
        drv.execute_script('arguments[0].click()', save_btn)
        wait_quiet(drv, timeout=40)
        time.sleep(1.2)
        content_text = ''
        content_els = drv.find_elements(By.CSS_SELECTOR, "[data-testid='studio-document-content']")
        if content_els:
            content_text = content_els[0].text
        panel_after = panel_text(drv)
        step('edit_save_new_version', value_ok and marker in content_text, {
            'value_ok': value_ok,
            'content': content_text[:160],
            'panel': panel_after[:160],
        })
        shot(drv, '05_after_save_light')

        # 5. 历史版本 → 恢复到 v1，内容回到 v1
        hist = click_aria(drv, '历史版本')
        drv.execute_script('arguments[0].click()', hist)
        time.sleep(2.5)
        versions = find_versions(drv)
        version_numbers = [v.get_attribute('data-version') for v in versions]
        step('version_list', len(versions) >= 2, {'versions': version_numbers})
        shot(drv, '06_version_list_light')
        # 恢复到编辑前的那个版本（干净库即 v1；有历史版本时也不会误恢复更早的快照）
        target = next(
            (v for v in versions if v.get_attribute('data-version') == str(base_version)),
            None)
        if target is None:
            target = sorted(versions, key=lambda v: int(v.get_attribute('data-version') or 0))[0]
        restore_btn = target.find_element(By.CSS_SELECTOR, 'button')
        drv.execute_script('arguments[0].click()', restore_btn)
        wait_for(drv, lambda: not drv.find_elements(By.CSS_SELECTOR, "[data-testid='studio-version-list']"), 20)
        wait_quiet(drv, timeout=40)
        time.sleep(1.2)
        restored_text = ''
        content_els = drv.find_elements(By.CSS_SELECTOR, "[data-testid='studio-document-content']")
        if content_els:
            restored_text = content_els[0].text.strip()
        step('restore_baseline', (restored_text == baseline_text) and (marker not in restored_text), {
            'restored_version': base_version,
            'matches_baseline': restored_text == baseline_text,
            'content': restored_text[:160],
            'baseline': baseline_text[:160],
        })
        shot(drv, '07_after_restore_light')

        # 6. 导出 MD：进度态 → 完成 → 下载
        export_btn = click_aria(drv, '导出')
        drv.execute_script('arguments[0].click()', export_btn)
        time.sleep(1.5)
        shot(drv, '08_export_panel_light')
        md_btn = click_button(drv, exact='Markdown')
        if md_btn is None:
            raise AssertionError('Markdown 格式按钮未找到')
        drv.execute_script('arguments[0].click()', md_btn)
        start_btn = drv.find_element(By.CSS_SELECTOR, "[data-testid='studio-export-start']")
        drv.execute_script('arguments[0].click()', start_btn)
        # 进度态可见（快速作业可能一闪而过，允许未捕获）
        progress_seen = bool(wait_for(drv, lambda: drv.find_elements(By.CSS_SELECTOR, "[data-testid='studio-export-progress']"), 3, 0.1))
        wait_for(drv, lambda: drv.find_elements(By.CSS_SELECTOR, "[data-testid='studio-export-download']"), 30)
        done_ok = bool(drv.find_elements(By.CSS_SELECTOR, "[data-testid='studio-export-done']"))
        shot(drv, '09_export_done_light')
        # 按钮防重复：完成态下没有「再次导出」起点按钮
        dup = drv.find_elements(By.CSS_SELECTOR, "[data-testid='studio-export-start']")
        step('export_md', done_ok, {'progress_seen': progress_seen, 'duplicate_button': len(dup)})
        download_btn = drv.find_element(By.CSS_SELECTOR, "[data-testid='studio-export-download']")
        before = set(os.listdir(downloads))
        drv.execute_script('arguments[0].click()', download_btn)

        def new_download():
            fresh = [
                f for f in (set(os.listdir(downloads)) - before)
                if not f.endswith('.crdownload')
            ]
            return fresh or None

        downloaded = wait_for(drv, new_download, 30)
        artifact = None
        if downloaded:
            name = max(downloaded, key=lambda f: os.path.getmtime(os.path.join(downloads, f)))
            artifact = os.path.join(downloads, name)
            size = os.path.getsize(artifact)
            with open(artifact, 'rb') as fh:
                head = fh.read(200).decode('utf-8', 'replace')
            step('export_artifact', size > 0, {'file': name, 'size': size, 'head': head[:120]})
        else:
            step('export_artifact', False, {'reason': 'no new download'})

        # 7. 导出 PDF：当前后端（未合 INT-2471 渲染器）失败态可见
        time.sleep(1.0)
        pdf_btn = click_button(drv, exact='PDF')
        if pdf_btn is not None:
            drv.execute_script('arguments[0].click()', pdf_btn)
            time.sleep(0.6)
            start_btn = wait_for(drv, lambda: drv.find_element(By.CSS_SELECTOR, "[data-testid='studio-export-start']"), 10, 0.2)
            if start_btn is None:
                raise AssertionError('切换 PDF 后未回到可导出态')
            drv.execute_script('arguments[0].click()', start_btn)
            failed = wait_for(drv, lambda: drv.find_elements(By.CSS_SELECTOR, "[data-testid='studio-export-error']"), 40)
            err_text = failed[0].text if failed else ''
            step('export_pdf_failure_state', bool(failed), {'error': err_text[:200]})
            shot(drv, '10_export_pdf_failed_light')
        else:
            step('export_pdf_failure_state', False, {'reason': 'PDF button missing'})
        # 关闭导出面板（只点对话框内的「关闭」）
        close_dialog(drv, 'studio-export-panel')
        time.sleep(0.8)

        # 8. 深色截图（同一面板）
        drv.execute_cdp_cmd('Emulation.setEmulatedMedia', {
            'features': [{'name': 'prefers-color-scheme', 'value': 'dark'}]
        })
        time.sleep(1.5)
        shot(drv, '11_panel_dark')
        hist = click_aria(drv, '历史版本')
        if hist is not None:
            drv.execute_script('arguments[0].click()', hist)
            time.sleep(2.0)
            shot(drv, '12_version_list_dark')
            close_dialog(drv, 'studio-version-list')
            time.sleep(0.5)
        else:
            step('dark_version_list', False, {'reason': 'history button missing'})

        # 8a. 复位浅色（CDP emulated media 会话级生效，不复位后面 14/15/16 会被标成浅色实为深色）
        drv.execute_cdp_cmd('Emulation.setEmulatedMedia', {
            'features': [{'name': 'prefers-color-scheme', 'value': 'light'}]
        })
        time.sleep(1.0)

        # 8b. 窄屏（<1024px）报告工作模式：文档面板以覆盖式抽屉呈现，不再是死按钮（UX 审计 P2-1）
        close_dialog(drv, 'studio-version-list')
        close_dialog(drv, 'studio-export-panel')
        drv.set_window_size(900, 900)
        time.sleep(1.2)
        ensure_work_mode(drv, 15)
        panels = drv.find_elements(By.CSS_SELECTOR, "[data-testid='studio-document-panel']")
        visible = [p for p in panels if p.is_displayed()]
        rect = visible[0].rect if visible else {}
        dialogs_open = [
            d for d in drv.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']")
            if d.is_displayed()]
        in_viewport = bool(visible) and rect.get('width', 0) >= 320 and rect.get('x', -1) >= 0
        step('work_mode_narrow_900', in_viewport and not dialogs_open, {
            'panels': len(panels), 'visible': len(visible), 'rect': rect,
            'dialogs_open': len(dialogs_open),
            'panel': panel_text(drv)[:160],
        })
        shot(drv, '18_workmode_900w_light')
        drv.set_window_size(1680, 1050)
        time.sleep(1.0)

        # 9. 加载态：CDP 网络延迟下截取「正在加载」中间态（真实请求仍发往网关）
        drv.execute_cdp_cmd('Network.enable', {})
        drv.execute_cdp_cmd('Network.emulateNetworkConditions', {
            'offline': False, 'latency': 2500,
            'downloadThroughput': -1, 'uploadThroughput': -1,
            'connectionType': 'cellular3g',
        })
        drv.get('%s/ai-chat?report=%d' % (base, args.report_id))
        time.sleep(1.2)
        toggle = wait_for(drv, lambda: click_button(drv, contains='报告工作模式'), 20, 0.3)
        if toggle is not None:
            drv.execute_script('arguments[0].click()', toggle)
            loading_seen = wait_for(
                drv,
                lambda: '正在加载报告文档' in panel_text(drv) or '正在加载文档正文' in panel_text(drv),
                12, 0.2)
            step('loading_state', bool(loading_seen), {'panel': panel_text(drv)[:120]})
            shot(drv, '16_loading_state_light')
        else:
            step('loading_state', False, {'reason': 'work-mode toggle missing'})
        drv.execute_cdp_cmd('Network.emulateNetworkConditions', {
            'offline': False, 'latency': 0,
            'downloadThroughput': -1, 'uploadThroughput': -1,
            'connectionType': 'none',
        })
        wait_quiet(drv, timeout=40)

        # 10. 空态：另一份真实报告（无 Studio 文档）
        drv.get('%s/ai-chat?report=%d' % (base, args.empty_report_id))
        wait_quiet(drv, timeout=40)
        time.sleep(1.0)
        opened = open_work_mode(drv)
        empty_text = panel_text(drv)
        step('empty_state', opened and '该报告还没有 Studio 文档' in empty_text, {
            'panel': empty_text[:160],
        })
        shot(drv, '14_empty_state_light')

        # 10b. 空态「起草文档」按钮：真实 POST /documents 建 v1 草稿
        draft_btn = drv.find_elements(By.CSS_SELECTOR, "[data-testid='studio-draft-button']")
        if draft_btn:
            drv.execute_script('arguments[0].click()', draft_btn[0])
            drafted = wait_for(drv, lambda: '版本 1' in panel_text(drv), 25, 0.4)
            step('draft_button', bool(drafted), {'panel': panel_text(drv)[:180]})
            shot(drv, '17_draft_created_light')
        else:
            step('draft_button', False, {'reason': 'draft button missing'})

        # 10. 错误态：CDP 阻断 report-studio 文档接口（不用 route mock，页面仍走真实实现）
        drv.execute_cdp_cmd('Network.enable', {})
        drv.execute_cdp_cmd('Network.setBlockedURLs', {
            'urls': ['*report-studio/documents*']
        })
        drv.refresh()
        wait_quiet(drv, timeout=40)
        time.sleep(1.0)
        opened = open_work_mode(drv)
        error_ready = wait_for(
            drv,
            lambda: '文档列表加载失败' in panel_text(drv) or '文档正文加载失败' in panel_text(drv),
            25, 0.4)
        step('error_state', bool(error_ready), {'panel': panel_text(drv)[:160]})
        shot(drv, '15_error_state_light')
        drv.execute_cdp_cmd('Network.setBlockedURLs', {'urls': []})

        # 10c. 任务上下文三态（UX 审计 P2-2）：
        #   解析中 → 「正在解析任务关联报告…」（不闪「未绑定报告上下文」）；
        #   解析完无报告（by_task 404）→ 「该任务暂无关联报告」；
        #   解析出报告 → 面板载入该报告文档，来源卡「任务 #y → 报告 #x」。
        drv.execute_cdp_cmd('Network.enable', {})
        drv.execute_cdp_cmd('Network.emulateNetworkConditions', {
            'offline': False, 'latency': 2500,
            'downloadThroughput': -1, 'uploadThroughput': -1,
            'connectionType': 'cellular3g',
        })
        drv.get('%s/ai-chat?task=%d' % (base, args.task_without_report_id))
        time.sleep(2.0)
        toggle = wait_for(drv, lambda: click_button(drv, contains='报告工作模式'), 40, 0.3)
        if toggle is not None:
            drv.execute_script('arguments[0].click()', toggle)
            resolving = wait_for(
                drv, lambda: '正在解析任务关联报告' in panel_text(drv), 15, 0.2)
            step('task_context_resolving', bool(resolving), {
                'panel': panel_text(drv)[:160]})
            shot(drv, '21_task_resolving_light')
        else:
            step('task_context_resolving', False, {'reason': 'work-mode toggle missing'})
        drv.execute_cdp_cmd('Network.emulateNetworkConditions', {
            'offline': False, 'latency': 0,
            'downloadThroughput': -1, 'uploadThroughput': -1,
            'connectionType': 'none',
        })
        # 延迟复位后同一页面：by_task 404 落「该任务暂无关联报告」
        no_report_ready = wait_for(
            drv, lambda: '该任务暂无关联报告' in panel_text(drv), 30, 0.3)
        panel_task_missing = panel_text(drv)
        step('task_context_no_report',
             bool(no_report_ready) and '未绑定报告上下文' not in panel_task_missing,
             {'panel': panel_task_missing[:220]})
        shot(drv, '19_task_no_report_light')

        drv.get('%s/ai-chat?task=%d' % (base, args.task_with_report_id))
        wait_quiet(drv, timeout=40)
        time.sleep(1.0)
        opened = ensure_work_mode(drv)
        wait_for(drv, lambda: '取数来源' in panel_text(drv), 25, 0.3)
        panel_task_with = panel_text(drv)
        step('task_context_with_report',
             opened and ('→ 报告 #%d' % args.report_id) in panel_task_with,
             {'panel': panel_task_with[:260]})
        shot(drv, '20_task_with_report_light')

        # 10d. 同一报告多文档切换（UX 审计 P3-1）：用页面内登录态再建一份，
        #      头部文档名变成切换器，可切回另一份（旧实现只显示最新一份、无法切换）
        second_title = '接线测试_INT2473 第二份文档'
        created = drv.execute_async_script(
            """
            const done = arguments[arguments.length - 1];
            const body = arguments[0];
            const token = window.localStorage.getItem('iatp:auth:token:v1');
            fetch('/api/v1/report-studio/documents', {
              method: 'POST',
              headers: {'Content-Type': 'application/json',
                        'Authorization': 'Bearer ' + (token || '')},
              body: JSON.stringify(body)
            }).then(async r => done({status: r.status, data: await r.json()}))
              .catch(e => done({status: -1, error: String(e)}));
            """,
            {
                'report_id': args.report_id,
                'title': second_title,
                'markdown_content': '# 第二份文档\n\n接线测试_INT2473 多文档切换\n',
            })
        SUMMARY['second_doc'] = created
        step('multi_doc_created', created.get('status') in (200, 201), {
            'status': created.get('status')})
        drv.get('%s/ai-chat?report=%d' % (base, args.report_id))
        wait_quiet(drv, timeout=40)
        time.sleep(1.0)
        ensure_work_mode(drv)
        tabs = wait_for(
            drv,
            lambda: drv.find_elements(By.CSS_SELECTOR, "[data-testid='studio-doc-tab']"),
            25, 0.3) or []
        labels = [(tab.text or '').strip() for tab in tabs]
        step('multi_doc_switcher', len(tabs) >= 2, {'tabs': labels})
        shot(drv, '22_doc_switcher_light')
        draft_tab = next((tab for tab in tabs if '草稿' in (tab.text or '')), None)
        if draft_tab is not None:
            # 这排页签在 overflow-x-auto 容器里，WebDriver 原生 click 实测不派发 click 事件；
            # 统一走 JS 点击（本脚本其他按钮同理）
            drv.execute_script('arguments[0].click()', draft_tab)
            time.sleep(1.2)
        title_el = drv.find_elements(By.CSS_SELECTOR, "[data-testid='studio-doc-title']")
        title_text = title_el[0].text.strip() if title_el else ''
        # 断言头部标题（页签行里仍会有两份文档的名字，不能拿整块面板文本比）
        switched = ('草稿' in title_text) and (second_title not in title_text)
        step('multi_doc_switch', bool(switched), {
            'title': title_text, 'panel': panel_text(drv)[:200]})
        shot(drv, '23_doc_switched_light')

        # 11. 真实请求记录（/api/v1）
        apis = parse_perf(drv.get_log('performance'))
        studio_reqs = [r for r in apis if '/api/v1/' in (r.get('url') or '')]
        SUMMARY['requests'] = studio_reqs
        html_path = render_network_page(studio_reqs, os.path.join(ART, '13_network_requests.html'))
        drv.get('file:///' + html_path.replace('\\', '/'))
        time.sleep(1.0)
        shot(drv, '13_network_requests')

        studio_only = [r for r in studio_reqs if '/report-studio/' in (r.get('url') or '') or '/ai-chat' in (r.get('url') or '')]
        errors = [r for r in studio_reqs if isinstance(r.get('status'), int) and r['status'] >= 400]
        step('network_studio_calls', len(studio_only) >= 6, {
            'studio_calls': len(studio_only),
            'api_errors': errors[:10],
        })
        SUMMARY['console'] = console_errors(drv)
        # 「该任务没有报告」是本轮要验的业务事实（by_task 404），浏览器必然记一条资源 SEVERE；
        # 只排除这条预期内 404，其他 SEVERE 仍判失败。
        expected_404 = '/reports/by_task/%d' % args.task_without_report_id
        expected_hits = [c for c in SUMMARY['console'] if expected_404 in c]
        unexpected_hits = [c for c in SUMMARY['console'] if expected_404 not in c]
        step('console_clean', not unexpected_hits, {
            'errors': unexpected_hits[:5],
            'expected_404_ignored': len(expected_hits),
        })

        # 12. 清理本 run 建的 Studio 测试行（报告 425 起草件 + 报告 426 编辑件，只删本 run 之后建的）
        try:
            removed = cleanup_studio_rows(
                [args.empty_report_id, args.report_id],
                title_like='%INT2473%', since=run_start)
            SUMMARY['cleanup_doc_ids'] = removed
            step('cleanup', True, {'doc_ids': removed, 'since': run_start.isoformat()})
        except Exception as exc:
            step('cleanup', False, {'error': str(exc)[:300]})

    except Exception:
        SUMMARY['error'] = traceback.format_exc()
        try:
            shot(drv, '99_failure')
        except Exception:
            pass
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    with open(os.path.join(ART, 'summary.json'), 'w', encoding='utf-8') as fh:
        json.dump(SUMMARY, fh, ensure_ascii=False, indent=1)
    failed = [s for s in SUMMARY['steps'] if not s['ok']]
    log('DONE failed_steps=%d/%d' % (len(failed), len(SUMMARY['steps'])))
    for item in failed:
        log('  FAILED: %s %s' % (item['step'], json.dumps(item['detail'], ensure_ascii=False)[:200]))
    sys.exit(0 if not failed and not SUMMARY.get('error') else 1)


if __name__ == '__main__':
    main()
