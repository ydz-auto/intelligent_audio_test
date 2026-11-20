# -*- coding: utf-8 -*-
"""INT-2418 返工复测探针（测试工程师）：只复测上一轮失败的 P2-1 / P3-2 / P3-3。

- P2-1：对比表格列头资源名在导出 HTML 中不再丢失（页面 th 文本集合 ⊆ 导出 th 文本集合，空 th = 0）
- P3-2：页面处于「柱状图」视图时，导出 HTML 里图表静态化为内联 PNG（canvas → data:image/png），
        不是静默退化成表格；file:// 打开无破图
- P3-3：导出 HTML 不再残留分组/标签对比的空筛选卡骨架（无 role=checkbox、无筛选 label 文本）
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

ART = os.path.join(sm.ART_ROOT, 'int2418_retest')
RESULT = {'checks': {}, 'notes': []}


def log(msg):
    print('[retest2418] %s' % msg, flush=True)


def login(d, base):
    d.get(base + '/login')
    time.sleep(3)
    u = [e for e in d.find_elements(By.CSS_SELECTOR, 'input')
         if e.get_attribute('type') in (None, 'text', 'email') and e.is_displayed()][0]
    p = [e for e in d.find_elements(By.CSS_SELECTOR, 'input[type=password]') if e.is_displayed()][0]
    u.clear(); u.send_keys(sm.USERNAME)
    p.clear(); p.send_keys(sm.PASSWORD)
    btns = [b for b in d.find_elements(By.TAG_NAME, 'button')
            if b.is_displayed() and b.text.strip() in ('登 录', '登录')]
    sm.click_js(d, btns[-1])
    time.sleep(5)
    return d.current_url


def open_export_dialog_and_click(d):
    exp = sm.find_buttons(d, texts=('导出', '导出报告', 'HTML 导出')) or sm.find_buttons(d, contains=('导出',))
    assert exp, '无导出按钮'
    sm.click_js(d, exp[0])
    time.sleep(2.5)
    dlgs = [x for x in d.find_elements(By.CSS_SELECTOR, '[role=dialog]') if x.is_displayed()]
    scope = dlgs[-1] if dlgs else d
    combo = [b for b in scope.find_elements(By.CSS_SELECTOR, '[role=combobox], button')
             if b.is_displayed() and (b.text or '').strip().lower() in ('csv', 'excel', 'pdf', 'html', 'json')]
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
    """打开报告 → 导出 HTML → 返回 (zip 路径, 解压目录)。"""
    dl = os.path.join(ART, 'downloads_' + tag)
    os.makedirs(dl, exist_ok=True)
    for f in os.listdir(dl):
        os.remove(os.path.join(dl, f))
    d.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': dl})
    sm.parse_perf(d.get_log('performance'))
    open_export_dialog_and_click(d)
    z = wait_zip(dl)
    assert z, '%s 未下载到 zip' % tag
    out = os.path.join(ART, 'exported_' + tag)
    os.makedirs(out, exist_ok=True)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(out)
    apis = sm.parse_perf(d.get_log('performance'))
    return z, out, [a.get('url') for a in apis if '/reports/export' in (a.get('url') or '')]


TH_JS = """
return (function(){
  var out = {};
  ['report-case-category','report-case-tag'].forEach(function(id){
    var s = document.getElementById(id);
    if (!s) { out[id] = null; return; }
    out[id] = Array.prototype.map.call(s.querySelectorAll('table th'), function(t){
      return (t.textContent || '').replace(/\\s+/g,' ').trim();
    });
  });
  return out;
})()
"""


def part_p21(base, d):
    """P2-1：对比表格列头资源名。"""
    rec = {}
    d.get(base + '/report/395')
    time.sleep(10)
    sm.wait_quiet(d, 45)
    page = d.execute_script(TH_JS) or {}
    rec['page_th'] = {k: (len(v) if v else 0) for k, v in page.items()}
    rec['page_th_empty'] = {k: len([x for x in (v or []) if not x]) for k, v in page.items()}
    rec['page_th_sample'] = {k: (v or [])[:6] for k, v in page.items()}
    rec['shot_page'] = sm.shot(d, 'retest_p21_page_headers')
    z, out, export_reqs = export_report(d, base, 395, 'p21')
    rec['zip'] = os.path.basename(z)
    rec['zip_size'] = os.path.getsize(z)
    rec['export_requests'] = export_reqs
    fpath = os.path.join(out, 'report.html').replace('\\', '/')
    d.get('file:///' + fpath)
    time.sleep(3)
    exp = d.execute_script(TH_JS) or {}
    rec['export_th'] = {k: (len(v) if v else 0) for k, v in exp.items()}
    rec['export_th_empty'] = {k: len([x for x in (v or []) if not x]) for k, v in exp.items()}
    rec['export_th_sample'] = {k: (v or [])[:6] for k, v in exp.items()}
    # 页面非空列头必须全部出现在导出里
    missing = {}
    for sec, texts in page.items():
        page_set = set([x for x in (texts or []) if x])
        exp_set = set([x for x in (exp.get(sec) or []) if x])
        miss = sorted(page_set - exp_set)
        missing[sec] = miss[:10]
    rec['headers_missing_in_export'] = missing
    rec['shot_export'] = sm.shot(d, 'retest_p21_export_headers')
    rec['ok_p2_1'] = all(v == 0 for v in rec['export_th_empty'].values()) and \
        (rec['export_th'].get('report-case-category') or 0) > 0 and \
        not any(missing.values())
    RESULT['checks']['p2_1'] = rec
    return rec


def part_p32_p33(base, d):
    """P3-2：柱状图视图导出为静态图；P3-3：空筛选卡骨架不残留。"""
    rec = {}
    d.get(base + '/report/426')
    time.sleep(10)
    sm.wait_quiet(d, 45)
    # 在「按用例分组对比」卡里切到柱状图（第一个可见的「柱状图」视图按钮）
    rec['switch_chart'] = d.execute_script(
        "var s=document.getElementById('report-case-category');"
        "if(!s)return 'no-section';"
        "var b=Array.prototype.filter.call(s.querySelectorAll('button'),"
        "function(x){return (x.textContent||'').trim()==='柱状图';});"
        "if(!b.length)return 'no-bar-button';"
        "b[0].click();return 'clicked';")
    time.sleep(4)
    rec['page_canvases'] = d.execute_script("return document.querySelectorAll('canvas').length")
    rec['page_tables_in_section'] = d.execute_script(
        "var s=document.getElementById('report-case-category');"
        "return s?s.querySelectorAll('table').length:null")
    rec['shot_page'] = sm.shot(d, 'retest_p32_page_bar_chart')
    z, out, export_reqs = export_report(d, base, 426, 'p32')
    rec['zip'] = os.path.basename(z)
    rec['export_requests'] = export_reqs
    fpath = os.path.join(out, 'report.html').replace('\\', '/')
    d.get('file:///' + fpath)
    time.sleep(3)
    rec['export_canvases'] = d.execute_script("return document.querySelectorAll('canvas').length")
    rec['export_imgs_total'] = d.execute_script("return document.images.length")
    rec['export_imgs_data_png'] = d.execute_script(
        "return Array.prototype.filter.call(document.images,"
        "function(i){return (i.getAttribute('src')||'').indexOf('data:image/png')===0;}).length")
    rec['export_imgs_broken'] = d.execute_script(
        "return Array.prototype.filter.call(document.images,"
        "function(i){return i.complete && i.naturalWidth===0;}).length")
    rec['export_imgs_sizes'] = d.execute_script(
        "return Array.prototype.slice.call(document.images,0,8).map(function(i){"
        "return {w:i.naturalWidth,h:i.naturalHeight,src:(i.getAttribute('src')||'').slice(0,22)};})")
    rec['export_tables_in_section'] = d.execute_script(
        "var s=document.getElementById('report-case-category');"
        "return s?s.querySelectorAll('table').length:null")
    rec['offline_http'] = [a.get('url') for a in sm.parse_perf(d.get_log('performance'))
                           if (a.get('url') or '').startswith(('http://', 'https://'))]
    rec['shot_export'] = sm.shot(d, 'retest_p32_export_bar_chart')
    rec['ok_p3_2'] = (rec['page_canvases'] or 0) > 0 and \
        (rec['export_canvases'] == 0) and \
        (rec['export_imgs_data_png'] or 0) >= (rec['page_canvases'] or 0) and \
        rec['export_imgs_broken'] == 0
    # P3-3：空筛选卡骨架
    rec['p33_inputs'] = d.execute_script("return document.querySelectorAll('input').length")
    rec['p33_checkboxes'] = d.execute_script(
        "return document.querySelectorAll('[role=checkbox]').length")
    # 只看分组/标签对比两个区块（总览里的「评估维度」是统计卡标签，属正常内容）
    rec['p33_labels'] = d.execute_script(
        "var secs=['report-case-category','report-case-tag'].map(function(id){"
        "var s=document.getElementById(id);return s?(s.innerText||''):'';}).join('\\n');"
        "return {use_case_name:(secs.match(/用例名称/g)||[]).length,"
        "eval_dim:(secs.match(/评估维度/g)||[]).length,"
        "apply_btn:(secs.match(/应用筛选/g)||[]).length};")
    rec['p33_input_types'] = d.execute_script(
        "return Array.prototype.map.call(document.querySelectorAll('input'),"
        "function(i){return (i.type||'')+':'+(i.id||i.getAttribute('name')||'');}).slice(0,10)")
    rec['ok_p3_3'] = rec['p33_checkboxes'] == 0 and \
        rec['p33_labels']['use_case_name'] == 0 and \
        rec['p33_labels']['eval_dim'] == 0 and \
        rec['p33_labels']['apply_btn'] == 0
    RESULT['checks']['p3_2_p3_3'] = rec
    return rec


SHOT_JS_SCROLL = """
return (function(id){
  var s = document.getElementById(id);
  if (!s) return 'no-section';
  s.scrollIntoView({block:'start'});
  return Math.round(window.scrollY);
})('%s')
"""


def part_shots(base, d):
    """补充证据截图：页面柱状图视图 / 导出 HTML 同区块 / 对比表格列头。"""
    rec = {}
    # 页面（426，切柱状图）
    d.get(base + '/report/426')
    time.sleep(10)
    sm.wait_quiet(d, 45)
    d.execute_script(
        "var s=document.getElementById('report-case-category');"
        "Array.prototype.filter.call(s.querySelectorAll('button'),"
        "function(x){return (x.textContent||'').trim()==='柱状图';})[0].click();")
    time.sleep(4)
    rec['page_y'] = d.execute_script(SHOT_JS_SCROLL % 'report-case-category')
    time.sleep(0.8)
    rec['shot_page_chart'] = sm.shot(d, 'retest_shot_page_chart')
    # 导出（复用 p32 已解压产物）
    fpath = os.path.join(ART, 'exported_p32', 'report.html').replace('\\', '/')
    d.get('file:///' + fpath)
    time.sleep(3)
    rec['export_y'] = d.execute_script(SHOT_JS_SCROLL % 'report-case-category')
    time.sleep(0.8)
    rec['shot_export_chart'] = sm.shot(d, 'retest_shot_export_chart')
    # 对比表格列头（导出 p21）
    fpath2 = os.path.join(ART, 'exported_p21', 'report.html').replace('\\', '/')
    d.get('file:///' + fpath2)
    time.sleep(3)
    rec['p21_y'] = d.execute_script(SHOT_JS_SCROLL % 'report-case-category')
    time.sleep(0.8)
    rec['shot_export_headers'] = sm.shot(d, 'retest_shot_export_headers')
    RESULT['checks']['shots'] = rec
    return rec


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--only', default=None, choices=['p21', 'p32', 'shots'])
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ART, exist_ok=True)
    sm.env_check('retest_start')
    smoke = sm.Smoke('react', base)
    sm.RESULT['art'] = ART
    driver = sm.make_driver(ART)
    try:
        smoke.drv = driver
        login(driver, base)
        if args.only in (None, 'p21'):
            part_p21(base, driver)
            log('p21 done')
        if args.only in (None, 'p32'):
            part_p32_p33(base, driver)
            log('p32/p33 done')
        if args.only in (None, 'shots'):
            part_shots(base, driver)
            log('shots done')
        sm.env_check('retest_end')
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    # 分次运行时合并已有结果，避免只跑 --only 时把其它部分覆盖掉
    summary_path = os.path.join(ART, 'retest_summary.json')
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
    with open(summary_path, 'w', encoding='utf-8') as fh:
        json.dump(merged, fh, ensure_ascii=False, indent=2)
    print('RETEST_JSON=%s' % summary_path)


if __name__ == '__main__':
    main()
