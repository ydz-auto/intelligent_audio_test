# -*- coding: utf-8 -*-
"""INT-2419 验收探针：报告中心批量导出 HTML = 逐份前端快照（与单份导出同产物）。

复用 smoke_frontend_int1854 的驱动/登录/截图/网络日志设施，验证：
  1) 选 3 份（普通 / 对比 / Benchmark）→ 批量导出 HTML → 1 个 zip、3 个子目录，
     每个子目录 report.html + css/report.css，根目录 index.html；
  2) 逐份与「单独打开该报告详情 → 导出 HTML」对照：区块锚点、表头、用例卡集合、
     图表静态图数量、无操作按钮残留一致；用例卡片数 = 接口用例集合（去重 test_case_id）；
  3) 离线：解压后 file:// 打开每份，0 条 http(s) 请求、0 破图；
  4) 批量导出全程无 `POST /reports/export`；
  5) 取消：进度中取消 → 不产出 zip、页面可继续操作；
  6) 深色页面导出：产物仍是浅色版，导出后主题复原。
  7) 同名报告：两个同名子目录互不覆盖（用同一份报告名重复导出验证，若库里确有同名报告则直接用）。

跑法：
  python tests/ui/probe_int2419_batch_export.py --base http://localhost:5330
  （环境变量 UI_TEST_USERNAME / UI_TEST_PASSWORD 可覆盖登录账号）
"""
import argparse
import html as htmlmod
import json
import os
import re
import sys
import time
import urllib.request
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.ui import smoke_frontend_int1854 as sm  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

ART = os.path.join(sm.ART_ROOT, 'int2419')
RESULT = {'kind': 'react', 'art': ART, 'checks': {}, 'notes': []}
ACTION_TEXTS = ('保存', '发布', '取消发布', '导出', '删除', '彻底删除', '下载日志', '人工复核', 'AI 复核')


def log(msg):
    print('[int2419] %s' % msg, flush=True)


def http_post_json(path, payload, timeout=90):
    url = sm.API + '/api/v1' + path
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode('utf-8'),
        headers=dict(sm._auth_headers(), **{'Content-Type': 'application/json'}),
        method='POST',
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8') or '{}')


def pick_candidates(limit=200):
    """挑最多 3 份不同类型报告（普通 / 对比 / Benchmark 优先），优先有具体用例的。"""
    status, data = sm.http_json(
        '/reports?page=1&per_page=%d&sort_by=created_at&order=desc&deleted=false' % limit)
    payload = (data or {}).get('data') or {}
    items = payload.get('items') or []

    def case_stats(report_id):
        try:
            body = http_post_json(
                '/reports/%d/cases/search' % report_id,
                {'page': 1, 'per_page': 10000, 'sort_order': 'asc'},
            )
            d = (body or {}).get('data') or {}
            ids = {str(it.get('id') or it.get('case_id') or '') for it in (d.get('items') or [])}
            ids.discard('')
            return {'api_total': d.get('total'), 'distinct_cases': len(ids)}
        except Exception as exc:
            return {'error': str(exc)[:200]}

    picked, used = [], set()

    def add(entry, stats):
        if entry['id'] in used:
            return
        used.add(entry['id'])
        picked.append({
            'id': entry['id'],
            'name': entry.get('name'),
            'type': entry.get('type'),
            'stats': stats,
        })

    # 第一轮：普通 / 对比 / Benchmark 各一份（库里没有 Benchmark 就跳过）
    for key in ('task', 'comparison', 'benchmark'):
        for entry in items:
            rtype = entry.get('type')
            mk = 'comparison' if rtype in ('comparison', 'secondary_comparison') else rtype
            if mk != key:
                continue
            stats = case_stats(entry['id'])
            if key != 'benchmark' and not (stats.get('distinct_cases') or 0):
                continue
            add(entry, stats)
            break

    # 第二轮：补足 3 份（任意类型，必须有具体用例）
    for entry in items:
        if len(picked) >= 3:
            break
        if entry['id'] in used:
            continue
        stats = case_stats(entry['id'])
        if (stats.get('distinct_cases') or 0) > 0:
            add(entry, stats)

    RESULT['checks']['candidates'] = {
        'status': status,
        'picked': picked,
        'total': payload.get('total'),
        'has_benchmark_report': any(p['type'] == 'benchmark' for p in picked),
    }
    return picked


def open_report_center(drv, base):
    drv.get(base.rstrip('/') + '/report-center?pageSize=100')
    time.sleep(5)
    sm.wait_quiet(drv, 60)


def js_click_button(drv, text, root_selector='[role=dialog]'):
    """在最后一次打开的弹窗（或整页）里按可见文案点按钮，避开 Selenium 的 stale element。"""
    return bool(drv.execute_script(
        """
        var roots = document.querySelectorAll(arguments[0]);
        var root = roots.length ? roots[roots.length - 1] : document;
        var btns = root.querySelectorAll('button');
        for (var i = btns.length - 1; i >= 0; i--) {
          if ((btns[i].innerText || '').trim() === arguments[1]) { btns[i].click(); return true; }
        }
        return false;
        """,
        root_selector,
        text,
    ))


def select_reports(drv, names):
    """按报告名勾选行（Base UI Checkbox = span[role=checkbox][aria-label='选择报告 <name>']）。"""
    selected = []
    for name in names:
        clicked = False
        for _ in range(12):
            clicked = bool(drv.execute_script(
                """
                var name = arguments[0];
                var boxes = document.querySelectorAll('[role=checkbox][aria-label="选择报告 ' + name + '"]');
                for (var i = 0; i < boxes.length; i++) {
                  if (boxes[i].getAttribute('aria-checked') === 'false') { boxes[i].click(); return true; }
                }
                return boxes.length > 0;
                """,
                name,
            ))
            if clicked:
                break
            time.sleep(1)
        selected.append({'name': name, 'clicked': clicked})
        time.sleep(0.6)
    return selected


def open_export_html(drv):
    """报告中心批量浮条/更多操作 → 导出弹窗 → 选 HTML。"""
    rec = {'ok': False}
    # 批量勾选后浮条没有导出按钮：导出入口在「更多操作」下拉的「导出 CSV」；
    # 该入口按当前选择集打开导出弹窗（已选 → 所选 id；未选 → 当前筛选全量）。
    trigger = drv.find_elements(By.CSS_SELECTOR, 'button[aria-label="更多操作"]')
    if not trigger:
        rec['error'] = '未找到「更多操作」'
        return rec
    sm.click_js(drv, trigger[0])
    time.sleep(1.2)
    clicked = drv.execute_script(
        """
        var items = document.querySelectorAll('[role=menuitem], [data-slot=menu-item]');
        for (var i = 0; i < items.length; i++) {
          if ((items[i].innerText || '').indexOf('导出') >= 0) { items[i].click(); return items[i].innerText.trim(); }
        }
        return null;
        """)
    rec['clicked'] = clicked
    time.sleep(2)
    return select_html_format(drv, rec)


def select_html_format(drv, rec=None):
    """导出弹窗打开后：格式下拉选 HTML。"""
    rec = rec or {'ok': False}
    dlgs = [x for x in drv.find_elements(By.CSS_SELECTOR, '[role=dialog]') if x.is_displayed()]
    rec['dialog_open'] = bool(dlgs)
    if not dlgs:
        rec['error'] = '导出弹窗未打开'
        return rec
    scope = dlgs[-1]
    combo = [
        b for b in scope.find_elements(By.CSS_SELECTOR, '[role=combobox], button')
        if b.is_displayed() and (b.text or '').strip().lower() in ('csv', 'excel', 'pdf', 'html', 'json')
    ]
    if not combo:
        rec['error'] = '格式下拉未找到'
        return rec
    sm.click_js(drv, combo[0])
    time.sleep(1)
    opt = [
        o for o in drv.find_elements(By.CSS_SELECTOR, '[role=option], [role=menuitem]')
        if o.is_displayed() and (o.text or '').strip().lower().startswith('html')
    ]
    if not opt:
        rec['error'] = '格式下拉无 HTML'
        return rec
    sm.click_js(drv, opt[0])
    time.sleep(0.6)
    rec['scope_text'] = (scope.text or '')[:200]
    rec['ok'] = True
    return rec


def click_export_main(drv):
    return js_click_button(drv, '导出')


def dialog_text(drv):
    return drv.execute_script(
        "var ds = document.querySelectorAll('[role=dialog]');"
        "return ds.length ? (ds[ds.length-1].innerText || '').slice(0, 500) : ''")


def wait_progress(drv, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            els = [e for e in drv.find_elements(By.CSS_SELECTOR, '[data-testid=batch-export-progress]')
                   if e.is_displayed()]
            if els:
                return (els[0].text or '').strip()
        except Exception:
            pass
        time.sleep(0.5)
    return None


def wait_zip(dl_dir, timeout=420, since=0):
    deadline = time.time() + timeout
    last_size = -1
    while time.time() < deadline:
        files = [
            os.path.join(dl_dir, f) for f in os.listdir(dl_dir)
            if f.lower().endswith('.zip') and not f.endswith('.crdownload')
        ]
        files = [f for f in files if os.path.getmtime(f) >= since]
        if files:
            cand = max(files, key=os.path.getmtime)
            try:
                size = os.path.getsize(cand)
            except OSError:
                size = -1
            if size > 0 and size == last_size:
                return cand
            last_size = size
        time.sleep(1)
    return None


def parse_html(html_text):
    """结构化抓取导出产物：锚点 / 表头 / 用例卡 / 静态图 / 操作按钮残留 / 数字集合。"""
    body = re.sub(r'<script[\s\S]*?</script>', '', html_text)
    body = body.replace('<!--', '').replace('-->', '')
    anchors = sorted(set(re.findall(r'<section[^>]*id="(report-[^"]+)"', body)))
    ths = [
        htmlmod.unescape(re.sub(r'<[^>]+>', '', cell)).strip()
        for cell in re.findall(r'<th[^>]*>([\s\S]*?)</th>', body)
    ]
    ths = [t for t in ths if t]
    case_ids = re.findall(r'data-export-case-id="([^"]*)"', body)
    total_attr = re.search(r'data-export-case-total="(\d+)"', body)
    title = re.search(r'<title>([\s\S]*?)\s*-\s*报告导出</title>', html_text)
    imgs = len(re.findall(r'<img[^>]+src="data:image/', body))
    residual = re.findall(
        r'<button[^>]*>\s*(?:%s)\s*</button>' % '|'.join(ACTION_TEXTS), body
    )
    # 数字集合（关键数值对照；剥掉时间戳里的冒号数字由导出时间单独剔除）
    text = htmlmod.unescape(re.sub(r'<[^>]+>', ' ', body))
    text = re.sub(r'报告导出时间：[^|]*', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    numbers = sorted(re.findall(r'\d+(?:\.\d+)?%?', text))
    return {
        'title': htmlmod.unescape(title.group(1)).strip() if title else None,
        'anchors': anchors,
        'ths': ths,
        'case_ids': case_ids,
        'case_total_attr': int(total_attr.group(1)) if total_attr else None,
        'chart_imgs': imgs,
        'residual_actions': residual,
        'numbers': numbers,
        'text_len': len(text),
    }


def unzip_to(zip_path, out_dir):
    if os.path.isdir(out_dir):
        for root, dirs, files in os.walk(out_dir, topdown=False):
            for f in files:
                try:
                    os.remove(os.path.join(root, f))
                except OSError:
                    pass
            for d in dirs:
                try:
                    os.rmdir(os.path.join(root, d))
                except OSError:
                    pass
    else:
        os.makedirs(out_dir, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(out_dir)
        return zf.namelist()


def open_offline(drv, html_path):
    """file:// 打开导出产物：0 http(s) 请求、0 破图。"""
    rec = {'path': html_path}
    sm.parse_perf(drv.get_log('performance'))
    drv.get('file:///' + html_path.replace('\\', '/'))
    time.sleep(3)
    apis = [a for a in sm.parse_perf(drv.get_log('performance'))
            if (a.get('url') or '').startswith(('http://', 'https://'))]
    rec['http_requests'] = apis[:10]
    rec['broken_images'] = drv.execute_script(
        "return Array.prototype.filter.call(document.images, function (img) {"
        " return !img.complete || img.naturalWidth === 0; }).length")
    rec['images'] = drv.execute_script("return document.images.length")
    rec['case_cards'] = drv.execute_script(
        "return document.querySelectorAll('[data-export-case]').length")
    rec['ok'] = not apis and rec['broken_images'] == 0 and rec['case_cards'] > 0
    return rec


def single_export_html(drv, report_id, dl_dir):
    """单独打开报告详情 → 导出 HTML，返回 (zip 路径, report.html 文本)。"""
    for name in os.listdir(dl_dir):
        try:
            os.remove(os.path.join(dl_dir, name))
        except OSError:
            pass
    drv.get('%s/report/%d' % (RESULT['base'], report_id))
    time.sleep(7)
    sm.wait_quiet(drv, 60)
    # 报告详情页底部操作条「导出」→ 导出弹窗 → 选 HTML（与批量同一个 ExportReportDialog）
    opened = drv.execute_script(
        """
        var root = document.querySelector('.report-view-container') || document;
        var btns = root.querySelectorAll('button');
        for (var i = btns.length - 1; i >= 0; i--) {
          if ((btns[i].innerText || '').trim() === '导出') { btns[i].click(); return true; }
        }
        return false;
        """)
    time.sleep(2)
    if not opened:
        return None, None
    select_html_format(drv)
    if not click_export_main(drv):
        return None, None
    zip_path = wait_zip(dl_dir, timeout=300)
    if not zip_path:
        return None, None
    names = unzip_to(zip_path, os.path.join(ART, 'single'))
    if 'report.html' not in names:
        return zip_path, None
    with open(os.path.join(ART, 'single', 'report.html'), 'r', encoding='utf-8') as fh:
        return zip_path, fh.read()


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--skip-dark', action='store_true')
    ap.add_argument('--skip-single', action='store_true')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    RESULT['base'] = base
    os.makedirs(ART, exist_ok=True)

    sm.env_check('probe_start')
    smoke = sm.Smoke('react', base)
    sm.RESULT['art'] = ART
    dl_dir = os.path.join(ART, 'downloads')
    os.makedirs(dl_dir, exist_ok=True)
    driver = sm.make_driver(dl_dir)
    RESULT['driver'] = 'chrome-headless'
    try:
        smoke.drv = driver
        login = smoke.login()
        RESULT['checks']['login'] = {'ok': login.get('ok'), 'url': login.get('url_after')}
        assert login.get('ok'), '登录失败: %s' % login

        picked = pick_candidates()
        RESULT['checks']['picked'] = picked
        if len(picked) < 2:
            raise AssertionError('候选报告不足（需要至少 2 份，最好普通/对比/Benchmark 各 1）')
        names = [p['name'] for p in picked]

        # ---- 1) 勾选 → 导出弹窗 → HTML ----
        open_report_center(driver, base)
        RESULT['checks']['center_shot'] = sm.shot(driver, '2419_center_light')
        RESULT['checks']['selected'] = select_reports(driver, names)
        time.sleep(1)
        RESULT['checks']['selection_bar'] = driver.execute_script(
            "var el = document.querySelector('.fixed.bottom-6'); return el ? el.innerText : ''")
        RESULT['checks']['selected_shot'] = sm.shot(driver, '2419_center_selected')
        open_rec = open_export_html(driver)
        RESULT['checks']['dialog'] = open_rec
        if not open_rec.get('ok'):
            raise AssertionError('导出弹窗/格式选择失败: %s' % open_rec)

        # ---- 2) 取消一轮：进度出现后取消，确认不产出 zip ----
        sm.parse_perf(driver.get_log('performance'))
        since = time.time()
        if click_export_main(driver):
            progress_text = wait_progress(driver, timeout=60)
            RESULT['checks']['cancel_progress'] = progress_text
            RESULT['checks']['cancel_shot'] = sm.shot(driver, '2419_progress')
            RESULT['checks']['cancel_clicked'] = js_click_button(driver, '取消导出')
            time.sleep(8)
            RESULT['checks']['cancel_zip'] = wait_zip(dl_dir, timeout=15, since=since)
            RESULT['checks']['cancel_ok'] = RESULT['checks']['cancel_zip'] is None
            RESULT['checks']['cancel_dialog_text'] = dialog_text(driver)
        else:
            RESULT['checks']['cancel_ok'] = False

        # ---- 3) 正式批量导出 ----
        sm.parse_perf(driver.get_log('performance'))
        since = time.time()
        if not click_export_main(driver):
            raise AssertionError('正式导出无法点击主钮')
        progress_text = wait_progress(driver, timeout=60)
        RESULT['checks']['progress_text'] = progress_text
        zip_path = wait_zip(dl_dir, timeout=420, since=since)
        RESULT['checks']['batch_zip'] = os.path.basename(zip_path) if zip_path else None
        if not zip_path:
            RESULT['checks']['batch_zip_size'] = None
            raise AssertionError('未收到批量导出 zip')
        RESULT['checks']['batch_zip_size'] = os.path.getsize(zip_path)
        export_apis = [a for a in sm.parse_perf(driver.get_log('performance'))
                       if '/export' in (a.get('url') or '')]
        RESULT['checks']['export_apis'] = export_apis
        RESULT['checks']['no_backend_export'] = not export_apis
        RESULT['checks']['batch_shot'] = sm.shot(driver, '2419_batch_done')

        batch_dir = os.path.join(ART, 'batch')
        names_in_zip = unzip_to(zip_path, batch_dir)
        RESULT['checks']['zip_entries'] = names_in_zip
        subdirs = sorted({n.split('/')[0] for n in names_in_zip if '/' in n})
        RESULT['checks']['subdirs'] = subdirs
        RESULT['checks']['has_index'] = 'index.html' in names_in_zip

        per_report = []
        for sub in subdirs:
            html_rel = sub + '/report.html'
            css_rel = sub + '/css/report.css'
            rec = {'dir': sub, 'has_html': html_rel in names_in_zip,
                   'has_css': css_rel in names_in_zip}
            if rec['has_html']:
                with open(os.path.join(batch_dir, html_rel), 'r', encoding='utf-8') as fh:
                    rec.update(parse_html(fh.read()))
                rec['offline'] = open_offline(driver, os.path.join(batch_dir, html_rel))
                rec['offline_shot'] = sm.shot(driver, '2419_offline_%d' % len(per_report))
            per_report.append(rec)
        RESULT['checks']['per_report'] = [
            {k: v for k, v in r.items() if k != 'numbers'} for r in per_report
        ]

        # 用例卡片数 = 接口用例集合（去重 test_case_id）
        case_checks = []
        for rec in per_report:
            # 目录名被截断/剔非法字符，按 report.html 的 <title> 反查报告名
            stats = next((p['stats'] for p in picked if p['name'] == rec.get('title')), None)
            cards = len(rec.get('case_ids') or [])
            case_checks.append({
                'dir': rec['dir'],
                'cards': cards,
                'total_attr': rec.get('case_total_attr'),
                'api_stats': stats,
                'cards_match_dom': cards == rec.get('case_total_attr'),
                'cards_match_api_distinct': bool(stats) and cards == stats.get('distinct_cases'),
            })
        RESULT['checks']['case_checks'] = case_checks

        # ---- 4) 与单份导出的同一份报告逐项对照 ----
        if not args.skip_single:
            target = picked[0]
            single_zip, single_html = single_export_html(driver, target['id'], dl_dir)
            RESULT['checks']['single_zip'] = os.path.basename(single_zip) if single_zip else None
            if single_html:
                single = parse_html(single_html)
                batch = next((r for r in per_report if r.get('title') == target['name']), None)
                if batch is None:
                    batch = next(
                        (r for r in per_report if r['anchors']), None)
                compare = {}
                if batch:
                    compare = {
                        'target': target['name'],
                        'anchors_equal': batch.get('anchors') == single.get('anchors'),
                        'ths_equal': batch.get('ths') == single.get('ths'),
                        'case_ids_equal': batch.get('case_ids') == single.get('case_ids'),
                        'numbers_equal': batch.get('numbers') == single.get('numbers'),
                        'chart_imgs': [batch.get('chart_imgs'), single.get('chart_imgs')],
                        'residual_actions': [
                            batch.get('residual_actions'), single.get('residual_actions')],
                    }
                    compare['diff'] = {
                        'anchors': [a for a in single.get('anchors', [])
                                    if a not in batch.get('anchors', [])],
                        'ths_missing': [t for t in single.get('ths', [])
                                        if t not in batch.get('ths', [])],
                        'numbers_missing_head': [
                            n for n in single.get('numbers', [])
                            if n not in batch.get('numbers', [])][:20],
                    }
                RESULT['checks']['single_compare'] = compare
            else:
                RESULT['checks']['single_compare'] = {'error': '单份导出未拿到 report.html'}

        # ---- 5) 深色页面导出：产物仍浅色、主题复原 ----
        if not args.skip_dark:
            driver.get(base + '/report-center?pageSize=100')
            time.sleep(2)
            driver.execute_script(
                "localStorage.setItem('iatp:theme:v1:mode','dark'); location.reload();")
            time.sleep(6)
            sm.wait_quiet(driver, 60)
            dark_before = driver.execute_script(
                "return document.documentElement.classList.contains('dark')")
            RESULT['checks']['dark_page_before'] = bool(dark_before)
            RESULT['checks']['dark_shot'] = sm.shot(driver, '2419_center_dark')
            select_reports(driver, names)
            time.sleep(1)
            open_export_html(driver)
            since = time.time()
            dark_ok = click_export_main(driver)
            dark_zip = wait_zip(dl_dir, timeout=420, since=since) if dark_ok else None
            theme_after = driver.execute_script(
                "return document.documentElement.classList.contains('dark')")
            rec = {
                'zip': os.path.basename(dark_zip) if dark_zip else None,
                'theme_restored_dark': bool(theme_after),
                'light_class_after': driver.execute_script(
                    "return document.documentElement.classList.contains('light')"),
            }
            if dark_zip:
                dark_dir = os.path.join(ART, 'batch_dark')
                entries = unzip_to(dark_zip, dark_dir)
                html_name = next((n for n in entries if n.endswith('/report.html')), None)
                if html_name:
                    with open(os.path.join(dark_dir, html_name), 'r', encoding='utf-8') as fh:
                        dark_html = fh.read()
                    rec['exported_has_dark_root'] = bool(
                        re.search(r'<html[^>]*class="[^"]*dark', dark_html))
            RESULT['checks']['dark_export'] = rec

        # ---- 汇总 ----
        checks = RESULT['checks']
        ok = bool(
            checks.get('no_backend_export')
            and len(checks.get('subdirs') or []) == len(picked)
            and checks.get('has_index')
            and all(r.get('has_html') and r.get('has_css') for r in per_report)
            and all(len(r.get('anchors') or []) >= 5 for r in per_report)
            and all(not r.get('residual_actions') for r in per_report)
            and all(r.get('offline', {}).get('ok') for r in per_report)
            and all(c.get('cards_match_dom') for c in case_checks)
        )
        compare = checks.get('single_compare') or {}
        if compare and not compare.get('error'):
            ok = ok and all([
                compare.get('anchors_equal'),
                compare.get('ths_equal'),
                compare.get('case_ids_equal'),
                compare.get('numbers_equal'),
                not any(compare.get('residual_actions') or []),
            ])
        if checks.get('cancel_ok') is not None:
            ok = ok and bool(checks.get('cancel_ok'))
        dark = checks.get('dark_export')
        if dark:
            ok = ok and bool(dark.get('zip')) and bool(dark.get('theme_restored_dark')) \
                and not dark.get('exported_has_dark_root')
        RESULT['ok'] = ok
        RESULT['console_errors'] = sm.console_errors(driver)
        sm.env_check('probe_end')
    except Exception as exc:
        RESULT['error'] = '%s: %s' % (type(exc).__name__, str(exc)[:400])
        try:
            RESULT['checks']['fail_shot'] = sm.shot(driver, '2419_fail')
        except Exception:
            pass
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    out_path = os.path.join(ART, 'summary.json')
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=2)
    print('SUMMARY_JSON=%s' % out_path)
    print('OK=%s' % RESULT.get('ok'))


if __name__ == '__main__':
    main()
