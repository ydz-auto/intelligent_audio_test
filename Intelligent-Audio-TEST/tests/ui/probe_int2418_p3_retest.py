# -*- coding: utf-8 -*-
"""INT-2418 前端UX审计打回项的复测探针（测试工程师）。

只复测审计失败清单里的两项（§2.3 打回后只复测失败项）：

- P3-1 对比报告导出物里两张纯控制卡只剩空壳（「报告保存」/「选择要对比的设备和API」）；
        期望：导出物整块移除、无空框、无 data-export-hide 残留，页面照常显示可操作。
- P3-2 导出内「具体用例」同屏两个计数口径（区块头「共 N 条结果」vs 工具条「总计 N 条结果」）；
        期望：工具条改「个用例」口径，数值 = 用例卡张数。

附带主链路回归：HTML 导出仍为前端快照（无 POST /reports/export）、zip 结构不变。
"""
import json
import os
import re
import sys
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.ui import smoke_frontend_int1854 as sm  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

ART = os.path.join(sm.ART_ROOT, 'int2418_p3_retest')
RESULT = {'checks': {}, 'notes': []}

CARD_SAVE = '报告保存'
CARD_SELECT = '选择要对比的设备和API'


def log(msg):
    print('[p3retest] %s' % msg, flush=True)


def login(d, base):
    d.get(base + '/login')
    time.sleep(3)
    u = [e for e in d.find_elements(By.CSS_SELECTOR, 'input')
         if e.get_attribute('type') in (None, 'text', 'email') and e.is_displayed()][0]
    p = [e for e in d.find_elements(By.CSS_SELECTOR, 'input[type=password]') if e.is_displayed()][0]
    u.clear()
    u.send_keys(sm.USERNAME)
    p.clear()
    p.send_keys(sm.PASSWORD)
    btns = [b for b in d.find_elements(By.TAG_NAME, 'button')
            if b.is_displayed() and b.text.strip() in ('登 录', '登录')]
    sm.click_js(d, btns[-1])
    time.sleep(5)
    return d.current_url


def set_theme(d, mode):
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)
    d.refresh()
    time.sleep(8)
    return bool(d.execute_script(
        "return document.documentElement.classList.contains('dark')"))


def open_export_dialog_and_click(d):
    exp = sm.find_buttons(d, texts=('导出', '导出报告', 'HTML 导出')) or \
        sm.find_buttons(d, contains=('导出',))
    assert exp, '无导出按钮'
    sm.click_js(d, exp[0])
    time.sleep(2.5)
    dlgs = [x for x in d.find_elements(By.CSS_SELECTOR, '[role=dialog]') if x.is_displayed()]
    scope = dlgs[-1] if dlgs else d
    combo = [b for b in scope.find_elements(By.CSS_SELECTOR, '[role=combobox], button')
             if b.is_displayed() and (b.text or '').strip().lower() in
             ('csv', 'excel', 'pdf', 'html', 'json')]
    assert combo, '导出弹窗无格式下拉'
    sm.click_js(d, combo[0])
    time.sleep(1.2)
    opts = [e for e in d.find_elements(By.CSS_SELECTOR, '[role=option], [role=menuitem]')
            if e.is_displayed() and (e.text or '').strip().lower().startswith('html')]
    assert opts, '无 HTML 选项'
    sm.click_js(d, opts[0])
    time.sleep(0.8)
    mains = [b for b in scope.find_elements(By.TAG_NAME, 'button')
             if b.is_displayed() and (b.text or '').strip() == '导出']
    assert mains, '无主导出按钮'
    sm.click_js(d, mains[-1])


def wait_zip(dl_dir, timeout=240):
    deadline = time.time() + timeout
    last = -1
    while time.time() < deadline:
        files = [f for f in os.listdir(dl_dir) if f.lower().endswith('.zip')]
        if files:
            p = os.path.join(dl_dir, files[0])
            try:
                size = os.path.getsize(p)
            except OSError:
                size = -1
            if size > 0 and size == last:
                return p
            last = size
        time.sleep(1)
    return None


def export_report(d, base, report_id, tag):
    dl = os.path.join(ART, 'downloads_' + tag)
    os.makedirs(dl, exist_ok=True)
    for f in os.listdir(dl):
        os.remove(os.path.join(dl, f))
    d.execute_cdp_cmd('Page.setDownloadBehavior',
                      {'behavior': 'allow', 'downloadPath': dl})
    d.get_log('performance')
    open_export_dialog_and_click(d)
    z = wait_zip(dl)
    assert z, '%s 未下载到 zip' % tag
    out = os.path.join(ART, 'exported_' + tag)
    os.makedirs(out, exist_ok=True)
    with zipfile.ZipFile(z) as zf:
        names = zf.namelist()
        zf.extractall(out)
    apis = sm.parse_perf(d.get_log('performance'))
    return {
        'zip': os.path.basename(z),
        'zip_size': os.path.getsize(z),
        'zip_names': sorted(names),
        'export_requests': [a.get('url') for a in apis
                            if '/reports/export' in (a.get('url') or '')],
        'out': out,
    }


# ── P3-1：两张纯控制卡 ────────────────────────────────────
PAGE_CARD_JS = """
return (function(){
  var all = Array.prototype.slice.call(document.querySelectorAll('div'));
  function findCard(title){
    for (var i=0;i<all.length;i++){
      var el = all[i];
      var p = el.querySelector(':scope > p, :scope > div > p');
      if (p && (p.textContent||'').trim() === title) return el;
    }
    return null;
  }
  function info(title){
    var el = findCard(title);
    if (!el) return {found:false};
    var r = el.getBoundingClientRect();
    return {
      found: true,
      visible: r.width>0 && r.height>0,
      inputs: el.querySelectorAll('input, textarea').length,
      buttons: Array.prototype.map.call(el.querySelectorAll('button'),
        function(b){return (b.textContent||'').trim();}),
      text: (el.innerText||'').replace(/\\s+/g,' ').trim().slice(0,200)
    };
  }
  return {save: info('%(save)s'), select: info('%(select)s'),
          hasDataExportHide: document.querySelectorAll('[data-export-hide]').length};
})()
""" % {'save': CARD_SAVE, 'select': CARD_SELECT}

EMPTY_GRID_JS = """
return (function(){
  var bad = [];
  var els = document.querySelectorAll('div');
  for (var i=0;i<els.length;i++){
    var el = els[i];
    var cls = el.className || '';
    if (typeof cls === 'string' && cls.indexOf('sm:grid-cols-2') >= 0
        && el.children.length === 0) {
      bad.push((el.outerHTML||'').slice(0,160));
    }
  }
  return bad;
})()
"""


def part_p31(base, d):
    rec = {}
    d.get(base + '/report/395')
    time.sleep(10)
    sm.wait_quiet(d, 45)
    rec['page'] = d.execute_script(PAGE_CARD_JS)
    rec['page_body_has_save_title'] = CARD_SAVE in sm.body_text(d)
    rec['page_body_has_select_title'] = CARD_SELECT in sm.body_text(d)
    rec['shot_page_light'] = sm.shot(d, 'p3r_page_light_top')
    # 页面不应被 data-export-hide 影响显示
    rec['ok_page'] = bool(rec['page'].get('save', {}).get('found')) and \
        bool(rec['page'].get('select', {}).get('found')) and \
        rec['page']['save'].get('visible') and rec['page']['select'].get('visible') and \
        rec['page']['save'].get('inputs', 0) >= 2 and \
        any('保存' in b for b in rec['page']['save'].get('buttons', [])) and \
        rec['page']['select'].get('buttons', []) != []

    exp = export_report(d, base, 395, 'p31')
    rec['zip'] = exp['zip']
    rec['zip_size'] = exp['zip_size']
    rec['zip_names'] = exp['zip_names']
    rec['export_requests'] = exp['export_requests']
    html_path = os.path.join(exp['out'], 'report.html')
    with open(html_path, encoding='utf-8') as fh:
        html = fh.read()
    rec['html_size'] = len(html)
    rec['html_has_save_title'] = CARD_SAVE in html
    rec['html_has_select_title'] = CARD_SELECT in html
    rec['html_has_export_hide_attr'] = 'data-export-hide' in html
    rec['html_empty_grid_count'] = len(re.findall(
        r'<div class="[^"]*sm:grid-cols-2[^"]*"></div>', html))
    # 信息未丢：设备/API 名单仍在「设备与API统计」区块（从详情接口取真名，避免受控制卡移除影响）
    rec['html_has_device_section'] = '设备与API' in html
    page_dev = []
    try:
        st, detail = sm.http_json('/reports/%d' % 395)
        detail = (detail or {}).get('data') or detail or {}
        summary = detail.get('summary') or {}
        for key in ('devices', 'apis'):
            for item in (summary.get(key) or []):
                nm = (item or {}).get('name')
                if nm and nm not in page_dev:
                    page_dev.append(nm)
    except Exception as exc:  # noqa: BLE001
        RESULT['notes'].append('report detail api failed: %s' % exc)
    rec['api_device_names'] = page_dev
    missing = [n for n in page_dev if n not in html]
    rec['device_names_missing_in_export'] = missing[:8]
    rec['device_name_occurrences'] = {
        n: html.count(n) for n in page_dev}
    # 打开导出物截图 + 空框扫描
    fpath = html_path.replace('\\', '/')
    d.get('file:///' + fpath)
    time.sleep(3)
    rec['export_empty_grids'] = d.execute_script(EMPTY_GRID_JS)
    rec['export_body_has_save_title'] = CARD_SAVE in sm.body_text(d)
    rec['export_body_has_select_title'] = CARD_SELECT in sm.body_text(d)
    rec['export_export_hide_nodes'] = d.execute_script(
        "return document.querySelectorAll('[data-export-hide]').length")
    rec['shot_export_top'] = sm.shot(d, 'p3r_export_top')
    d.execute_script("window.scrollTo(0,0);")
    time.sleep(0.5)
    rec['ok_export'] = (not rec['html_has_save_title']) and \
        (not rec['html_has_select_title']) and \
        (rec['html_has_export_hide_attr'] is False) and \
        rec['html_empty_grid_count'] == 0 and \
        rec['export_empty_grids'] == [] and \
        (not rec['export_body_has_save_title']) and \
        (not rec['export_body_has_select_title']) and \
        rec['export_export_hide_nodes'] == 0
    rec['ok_info_kept'] = rec['html_has_device_section'] and \
        (not missing if page_dev else True)
    rec['ok_p3_1'] = rec['ok_page'] and rec['ok_export'] and rec['ok_info_kept']
    RESULT['checks']['p3_1'] = rec
    return rec


# ── P3-2：具体用例计数口径 ────────────────────────────────
CASE_COUNT_JS = """
return (function(){
  var sec = document.getElementById('report-specific-cases');
  if (!sec) return {found:false};
  var txt = (sec.innerText || '').replace(/\\s+/g,' ');
  var info = document.getElementById('export-case-pageinfo');
  var cards = sec.querySelectorAll('[data-case-index]');
  var m1 = txt.match(/共\\s*(\\d+)\\s*条结果/);
  var m2 = info ? (info.textContent||'').match(/总计\\s*(\\d+)\\s*个用例/) : null;
  var m2b = info ? (info.textContent||'').match(/总计\\s*(\\d+)\\s*条结果/) : null;
  return {
    found: true,
    section_header_total: m1 ? parseInt(m1[1],10) : null,
    toolbar_text: info ? (info.textContent||'').trim() : null,
    toolbar_total_cases: m2 ? parseInt(m2[1],10) : null,
    toolbar_total_rows_style: m2b ? parseInt(m2b[1],10) : null,
    case_cards: cards.length,
    visible_cards: Array.prototype.filter.call(cards, function(c){
      return c.style.display !== 'none';
    }).length,
    toolbar_in_section: !!(info && sec.contains(info))
  };
})()
"""


def part_p32(base, d, report_id, tag):
    rec = {}
    d.get(base + '/report/%d' % report_id)
    time.sleep(10)
    sm.wait_quiet(d, 45)
    exp = export_report(d, base, report_id, tag)
    rec['zip'] = exp['zip']
    rec['zip_size'] = exp['zip_size']
    rec['export_requests'] = exp['export_requests']
    html_path = os.path.join(exp['out'], 'report.html')
    fpath = html_path.replace('\\', '/')
    d.get('file:///' + fpath)
    time.sleep(3)
    rec['counts'] = d.execute_script(CASE_COUNT_JS)
    c = rec['counts']
    rec['ok_count_style'] = bool(c.get('found')) and c.get('toolbar_total_cases') is not None \
        and c.get('toolbar_total_rows_style') is None
    rec['ok_count_value'] = bool(c.get('found')) and \
        c.get('toolbar_total_cases') == c.get('case_cards') and \
        (c.get('case_cards') or 0) > 0
    # 翻到第 2 页 / 点卡片展开（导出交互未回归）
    if (c.get('case_cards') or 0) > 10:
        d.execute_script("document.getElementById('export-case-next').click();")
        time.sleep(1)
        rec['page2_visible'] = d.execute_script(
            "var s=document.getElementById('report-specific-cases');"
            "return Array.prototype.filter.call("
            "s.querySelectorAll('[data-case-index]'),function(x){"
            "return x.style.display!=='none';}).length")
        rec['page2_toolbar'] = d.execute_script(
            "var i=document.getElementById('export-case-pageinfo');"
            "return i?(i.textContent||'').trim():null")
        rec['ok_page2'] = rec['page2_visible'] == 10
    d.execute_script(
        "var s=document.getElementById('report-specific-cases');"
        "if(s) s.scrollIntoView({block:'start'});")
    time.sleep(1)
    rec['shot_export_cases'] = sm.shot(d, 'p3r_export_cases_%s' % tag)
    rec['ok_p3_2'] = rec['ok_count_style'] and rec['ok_count_value'] and \
        rec.get('ok_page2', True)
    RESULT['checks']['p3_2_%s' % tag] = rec
    return rec


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--only', default=None, choices=['p31', 'p32', 'dark'])
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ART, exist_ok=True)
    sm.env_check('p3retest_start')
    smoke = sm.Smoke('react', base)
    sm.RESULT['art'] = ART
    driver = sm.make_driver(ART)
    try:
        smoke.drv = driver
        login(driver, base)
        if args.only in (None, 'p31'):
            part_p31(base, driver)
            log('p31 done')
        if args.only in (None, 'p32'):
            part_p32(base, driver, 395, '395')
            part_p32(base, driver, 426, '426')
            log('p32 done')
        if args.only in (None, 'dark'):
            # 回到站点（此刻浏览器停在 file:// 导出物，localStorage 跨协议不生效）
            driver.get(base + '/report/395')
            time.sleep(8)
            dark = set_theme(driver, 'dark')
            time.sleep(6)
            sm.wait_quiet(driver, 45)
            RESULT['checks']['dark'] = {'dark': dark,
                                        'shot': sm.shot(driver, 'p3r_page_dark_top')}
            RESULT['checks']['dark']['shot_report'] = sm.shot(driver, 'p3r_page_dark_report')
            RESULT['checks']['dark']['cards_in_dark'] = driver.execute_script(PAGE_CARD_JS)
            log('dark done')
        RESULT['console_errors'] = sm.console_errors(driver)
        sm.env_check('p3retest_end')
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    summary_path = os.path.join(ART, 'p3retest_summary.json')
    merged = {'checks': {}, 'notes': []}
    if os.path.exists(summary_path):
        try:
            with open(summary_path, encoding='utf-8') as fh:
                merged = json.load(fh)
        except Exception:
            pass
    merged.setdefault('checks', {}).update(RESULT.get('checks', {}))
    merged.setdefault('notes', []).extend(RESULT.get('notes', []))
    merged['env'] = sm.RESULT.get('env', {})
    merged['console_errors'] = RESULT.get('console_errors', [])
    with open(summary_path, 'w', encoding='utf-8') as fh:
        json.dump(merged, fh, ensure_ascii=False, indent=2)
    print('P3RETEST_JSON=%s' % summary_path)


if __name__ == '__main__':
    main()
