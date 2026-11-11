# -*- coding: utf-8 -*-
"""INT-2418 复测探针（第二部分）：状态复原 + 区块数值一致性。"""
import json
import os
import re
import sys
import time
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.ui import smoke_frontend_int1854 as sm  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

ART = os.path.join(sm.ART_ROOT, 'int2418_verify2')
RESULT = {'checks': {}}


def log(m):
    print('[verify2] %s' % m, flush=True)


def login(d, base):
    d.get(base + '/login'); time.sleep(3)
    u = [e for e in d.find_elements(By.CSS_SELECTOR, 'input')
         if e.get_attribute('type') in (None, 'text', 'email') and e.is_displayed()][0]
    p = [e for e in d.find_elements(By.CSS_SELECTOR, 'input[type=password]') if e.is_displayed()][0]
    u.clear(); u.send_keys(sm.USERNAME)
    p.clear(); p.send_keys(sm.PASSWORD)
    b = [x for x in d.find_elements(By.TAG_NAME, 'button')
         if x.is_displayed() and x.text.strip() in ('登 录', '登录')]
    sm.click_js(d, b[-1]); time.sleep(5)


def export_flow(d, dl):
    os.makedirs(dl, exist_ok=True)
    for f in os.listdir(dl):
        os.remove(os.path.join(dl, f))
    d.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': dl})
    exp = sm.find_buttons(d, texts=('导出', '导出报告', 'HTML 导出')) or sm.find_buttons(d, contains=('导出',))
    sm.click_js(d, exp[0]); time.sleep(2.5)
    dlgs = [x for x in d.find_elements(By.CSS_SELECTOR, '[role=dialog]') if x.is_displayed()]
    scope = dlgs[-1] if dlgs else d
    combo = [b for b in scope.find_elements(By.CSS_SELECTOR, '[role=combobox], button')
             if b.is_displayed() and (b.text or '').strip().lower() in ('csv', 'excel', 'pdf', 'html', 'json')]
    sm.click_js(d, combo[0]); time.sleep(1.2)
    opts = [e for e in d.find_elements(By.CSS_SELECTOR, '[role=option], [role=menuitem]')
            if e.is_displayed() and (e.text or '').strip().lower().startswith('html')]
    sm.click_js(d, opts[0]); time.sleep(0.8)
    mains = [b for b in scope.find_elements(By.TAG_NAME, 'button')
             if b.is_displayed() and (b.text or '').strip() == '导出']
    sm.click_js(d, mains[-1])
    deadline = time.time() + 200
    last = -1
    while time.time() < deadline:
        fs = [f for f in os.listdir(dl) if f.lower().endswith('.zip')]
        if fs:
            p = os.path.join(dl, fs[0])
            try:
                sz = os.path.getsize(p)
            except OSError:
                sz = -1
            if sz > 0 and sz == last:
                return p
            last = sz
        time.sleep(1)
    return None


SECTION_JS = ("return (function(){var o={};"
              "['report-overview','report-resource-stats','report-conclusion',"
              "'report-case-category','report-case-tag','report-documents'].forEach(function(id){"
              "var s=document.getElementById(id);if(s)o[id]=(s.innerText||'').replace(/\\s+/g,' ').trim();});"
              "return o;})()")


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ART, exist_ok=True)
    sm.env_check('verify2_start')
    smoke = sm.Smoke('react', base)
    sm.RESULT['art'] = ART
    d = sm.make_driver(ART)
    rec = {}
    try:
        smoke.drv = d
        login(d, base)
        d.get(base + '/report/426'); time.sleep(9); sm.wait_quiet(d, 45)

        # 页面区块文本（导出前）
        rec['page_sections'] = d.execute_script(SECTION_JS)
        # 折叠「分析结论」分区
        rec['collapse_before'] = d.execute_script(
            "var ts=Array.from(document.querySelectorAll('[data-slot=\"collapsible-trigger\"]'));"
            "var b=ts.find(function(x){return x.textContent.indexOf('分析结论')>=0;});"
            "if(!b)return 'no-trigger';b.click();return 'clicked';")
        time.sleep(1)
        rec['collapse_after_click'] = d.execute_script(
            "var ts=Array.from(document.querySelectorAll('[data-slot=\"collapsible-trigger\"]'));"
            "var b=ts.find(function(x){return x.textContent.indexOf('分析结论')>=0;});"
            "var h=b?b.closest('[data-slot=\"collapsible\"]'):null;"
            "var p=h?h.querySelector('[data-slot=\"collapsible-content\"],[data-slot=\"collapsible-panel\"]'):null;"
            "return p?{disp:p.style.display,hidden:p.hasAttribute('hidden'),h:p.offsetHeight}:null")
        # 滚动内层容器
        rec['scroll_set'] = d.execute_script(
            "var c=document.querySelector('.report-view-container');"
            "if(!c)return 'no-container';c.scrollTop=800;return c.scrollTop;")
        time.sleep(0.5)
        rec['scroll_before'] = d.execute_script(
            "var c=document.querySelector('.report-view-container');return c?Math.round(c.scrollTop):null")
        rec['theme_before'] = d.execute_script(
            "return document.documentElement.classList.contains('dark')")
        rec['url_before'] = d.current_url
        # 导出
        z = export_flow(d, os.path.join(ART, 'downloads'))
        rec['zip'] = os.path.basename(z) if z else None
        time.sleep(2.5)
        rec['url_after'] = d.current_url
        rec['collapse_after_export'] = d.execute_script(
            "var ts=Array.from(document.querySelectorAll('[data-slot=\"collapsible-trigger\"]'));"
            "var b=ts.find(function(x){return x.textContent.indexOf('分析结论')>=0;});"
            "var h=b?b.closest('[data-slot=\"collapsible\"]'):null;"
            "var p=h?h.querySelector('[data-slot=\"collapsible-content\"],[data-slot=\"collapsible-panel\"]'):null;"
            "return p?{disp:p.style.display,hidden:p.hasAttribute('hidden'),h:p.offsetHeight}:null")
        rec['scroll_after'] = d.execute_script(
            "var c=document.querySelector('.report-view-container');return c?Math.round(c.scrollTop):null")
        rec['theme_after'] = d.execute_script(
            "return document.documentElement.classList.contains('dark')")
        rec['shot_after'] = sm.shot(d, 'verify2_after_export')
        # 导出 HTML 区块文本
        if z:
            out = os.path.join(ART, 'exported')
            os.makedirs(out, exist_ok=True)
            with zipfile.ZipFile(z) as zf:
                zf.extractall(out)
            fp = os.path.join(out, 'report.html').replace('\\', '/')
            d.get('file:///' + fp); time.sleep(3)
            rec['export_sections'] = d.execute_script(SECTION_JS)
            # 逐区块数值对比：数字集合
            def nums(t):
                return sorted(set(re.findall(r'\d+(?:\.\d+)?', t or '')))
            cmp = {}
            for sid in (rec['page_sections'] or {}):
                p = nums(rec['page_sections'][sid])
                e = nums((rec['export_sections'] or {}).get(sid, ''))
                missing = [x for x in p if x not in e]
                cmp[sid] = {'page_nums': len(p), 'export_nums': len(e), 'missing_in_export': missing[:8]}
            rec['section_number_parity'] = cmp
            rec['shot_export'] = sm.shot(d, 'verify2_exported_overview')
        sm.env_check('verify2_end')
    finally:
        try:
            d.quit()
        except Exception:
            pass
    RESULT['checks']['state2'] = rec
    with open(os.path.join(ART, 'verify2_summary.json'), 'w', encoding='utf-8') as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=2)
    print('VERIFY2_JSON=%s' % os.path.join(ART, 'verify2_summary.json'))


if __name__ == '__main__':
    main()
