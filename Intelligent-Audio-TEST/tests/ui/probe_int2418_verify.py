# -*- coding: utf-8 -*-
"""INT-2418 复测探针（测试工程师）：大报告全量用例 / 导出内交互 / 状态复原 / 重复点击。

与实现方 probe_int2418_html_export.py 互补：
  - 大报告（387，576 用例）：导出卡数 == 页面 total、默认 10 条/页、翻页/跳页/搜索/展开可用、
    无操作按钮、区块齐全、导出 HTML 全部图片为内联 data url 且无破图；
  - 导出后页面状态复原（折叠 / 用例筛选词 / 滚动位置 / 主题），连续点击导出只产生一个 zip。
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

ART = os.path.join(sm.ART_ROOT, 'int2418_verify')
RESULT = {'checks': {}, 'notes': []}


def log(msg):
    print('[verify2418] %s' % msg, flush=True)


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


def open_export_dialog_and_click(d, double=False):
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
    if double:
        time.sleep(0.4)
        try:
            mains2 = [b for b in d.find_elements(By.TAG_NAME, 'button')
                      if b.is_displayed() and (b.text or '').strip() == '导出']
            if mains2:
                sm.click_js(d, mains2[-1])
        except Exception:
            pass


def wait_zip(dl_dir, timeout=200):
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


def extract(zip_path, out_dir):
    os.makedirs(os.path.join(out_dir, 'css'), exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        zf.extractall(out_dir)
    return names


def part_large(base, d):
    rec = {}
    d.get(base + '/report/387')
    time.sleep(9)
    sm.wait_quiet(d, 40)
    page_text = sm.body_text(d)
    m = re.search(r'共\s*(\d+)\s*条结果', page_text)
    rec['page_total'] = int(m.group(1)) if m else None
    rec['page_cards_dom'] = d.execute_script(
        "return document.querySelectorAll('[data-export-case]').length")
    rec['page_canvases'] = d.execute_script("return document.querySelectorAll('canvas').length")
    rec['page_sections'] = d.execute_script(
        "return Array.from(document.querySelectorAll('section[id^=\"report-\"]')).map(s=>s.id)")
    rec['page_table_headers'] = d.execute_script(
        "var t=document.querySelector('#report-resource-stats table');"
        "return t?Array.from(t.querySelectorAll('th')).map(e=>e.textContent.trim()):null")
    dl = os.path.join(ART, 'downloads_large')
    os.makedirs(dl, exist_ok=True)
    for f in os.listdir(dl):
        os.remove(os.path.join(dl, f))
    d.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': dl})
    sm.parse_perf(d.get_log('performance'))
    open_export_dialog_and_click(d)
    z = wait_zip(dl, 240)
    rec['zip'] = os.path.basename(z) if z else None
    assert z, '大报告未下载到 zip'
    rec['zip_size'] = os.path.getsize(z)
    apis = sm.parse_perf(d.get_log('performance'))
    rec['export_requests'] = [a.get('url') for a in apis if '/reports/export' in (a.get('url') or '')]
    out = os.path.join(ART, 'exported_large')
    names = extract(z, out)
    rec['zip_entries'] = names
    html = open(os.path.join(out, 'report.html'), encoding='utf-8').read()
    css = open(os.path.join(out, 'css', 'report.css'), encoding='utf-8').read()
    rec['html_size'] = len(html)
    rec['css_size'] = len(css)
    rec['case_cards'] = len(re.findall(r'data-case-index="(\d+)"', html))
    ta = re.search(r'data-export-case-total="(\d+)"', html)
    rec['case_total_attr'] = int(ta.group(1)) if ta else None
    rec['anchors'] = [a for a in ('report-overview', 'report-resource-stats', 'report-conclusion',
                                  'report-case-category', 'report-case-tag', 'report-specific-cases',
                                  'report-documents') if ('id="%s"' % a) in html]
    rec['residual_buttons'] = re.findall(
        r'<button[^>]*>\s*(?:保存|发布|取消发布|导出|删除|彻底删除|下载日志|人工复核)\s*</button>', html)
    rec['has_dialog'] = 'role="dialog"' in html or 'data-slot="dialog-content"' in html
    rec['has_toast'] = 'data-sonner-toast' in html
    rec['canvas_left'] = html.count('<canvas')
    rec['img_tags'] = len(re.findall(r'<img\b', html))
    rec['img_data_urls'] = len(re.findall(r'<img[^>]+src="data:', html))
    rec['external_urls_in_css'] = len(re.findall(r'url\(\s*["\']?(?:https?:)?//', css))
    rec['export_script_inline'] = 'export-case-search' in html and '<script' in html
    # 打开导出 HTML（file://）验证交互
    fpath = os.path.join(out, 'report.html').replace('\\', '/')
    sm.parse_perf(d.get_log('performance'))
    d.get('file:///' + fpath)
    time.sleep(3)
    rec['offline_http'] = [a.get('url') for a in sm.parse_perf(d.get_log('performance'))
                           if (a.get('url') or '').startswith(('http://', 'https://'))]
    rec['offline_images_broken'] = d.execute_script(
        "return Array.from(document.images).filter(function(i){return i.complete && i.naturalWidth===0;}).length")
    rec['offline_images_total'] = d.execute_script("return document.images.length")
    rec['pageinfo'] = d.execute_script(
        "var e=document.getElementById('export-case-pageinfo');return e?e.textContent:null")
    rec['visible_default'] = d.execute_script(
        "return Array.prototype.filter.call(document.querySelectorAll('[data-export-case]'),"
        "function(e){return e.style.display!=='none';}).length")
    # 翻页
    d.execute_script("document.getElementById('export-case-next').click()")
    time.sleep(0.5)
    rec['visible_page2'] = d.execute_script(
        "return Array.prototype.filter.call(document.querySelectorAll('[data-export-case]'),"
        "function(e){return e.style.display!=='none';}).length")
    rec['pageinfo_after_next'] = d.execute_script(
        "return document.getElementById('export-case-pageinfo').textContent")
    rec['first_visible_index_page2'] = d.execute_script(
        "var c=Array.prototype.filter.call(document.querySelectorAll('[data-export-case]'),"
        "function(e){return e.style.display!=='none';});"
        "return c.length?c[0].getAttribute('data-case-index'):null")
    # 跳页
    d.execute_script(
        "document.getElementById('export-case-jump').value='58';"
        "document.getElementById('export-case-jump-btn').click()")
    time.sleep(0.5)
    rec['visible_last_page'] = d.execute_script(
        "return Array.prototype.filter.call(document.querySelectorAll('[data-export-case]'),"
        "function(e){return e.style.display!=='none';}).length")
    rec['pageinfo_last'] = d.execute_script(
        "return document.getElementById('export-case-pageinfo').textContent")
    # 搜索：用第一张卡的用例 ID
    cid = d.execute_script(
        "var c=document.querySelector('[data-export-case]');return c?c.getAttribute('data-export-case-id'):null")
    rec['sample_case_id'] = cid
    d.execute_script(
        "var i=document.getElementById('export-case-search');i.value='%s';"
        "i.dispatchEvent(new Event('input',{bubbles:true}));" % (cid or ''))
    time.sleep(0.5)
    rec['visible_search_hit'] = d.execute_script(
        "return Array.prototype.filter.call(document.querySelectorAll('[data-export-case]'),"
        "function(e){return e.style.display!=='none';}).length")
    d.execute_script(
        "var i=document.getElementById('export-case-search');i.value='zzz_not_exist_zzz';"
        "i.dispatchEvent(new Event('input',{bubbles:true}));")
    time.sleep(0.5)
    rec['visible_search_miss'] = d.execute_script(
        "return Array.prototype.filter.call(document.querySelectorAll('[data-export-case]'),"
        "function(e){return e.style.display!=='none';}).length")
    d.execute_script(
        "var i=document.getElementById('export-case-search');i.value='';"
        "i.dispatchEvent(new Event('input',{bubbles:true}));")
    # 展开用例卡
    rec['case_detail_hidden_before'] = d.execute_script(
        "var c=document.querySelector('[data-export-case]');"
        "var dd=c&&c.querySelector('[data-export-case-detail]');return dd?dd.hasAttribute('hidden'):null")
    d.execute_script(
        "var b=document.querySelector('[data-export-case-toggle]');if(b)b.click();")
    time.sleep(0.5)
    rec['case_detail_hidden_after'] = d.execute_script(
        "var c=document.querySelector('[data-export-case]');"
        "var dd=c&&c.querySelector('[data-export-case-detail]');return dd?dd.hasAttribute('hidden'):null")
    # 分区折叠
    rec['section_collapse_script'] = d.execute_script(
        "var b=document.querySelector('[data-slot=\"collapsible-trigger\"]');"
        "if(!b)return 'no-trigger';"
        "b.click();"
        "var h=b.closest('[data-slot=\"collapsible\"]');"
        "var p=h?h.querySelector('[data-slot=\"collapsible-content\"],[data-slot=\"collapsible-panel\"]'):null;"
        "return p?p.style.display:null;")
    rec['shot'] = sm.shot(d, 'verify_2418_exported_large')
    RESULT['checks']['large'] = rec
    return rec


def part_state(base, d):
    rec = {}
    d.get(base + '/report/426')
    time.sleep(8)
    sm.wait_quiet(d, 40)
    dl = os.path.join(ART, 'downloads_state')
    os.makedirs(dl, exist_ok=True)
    for f in os.listdir(dl):
        os.remove(os.path.join(dl, f))
    d.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': dl})
    # 预设状态：折叠首个分区 + 滚动 + 主题浅色
    rec['collapsed_before'] = d.execute_script(
        "var b=document.querySelector('[data-slot=\"collapsible-trigger\"]');if(!b)return null;"
        "b.click();"
        "var h=b.closest('[data-slot=\"collapsible\"]');"
        "var p=h?h.querySelector('[data-slot=\"collapsible-content\"],[data-slot=\"collapsible-panel\"]'):null;"
        "return p?(p.style.display==='none'||p.hasAttribute('hidden')?'collapsed':'expanded'):null")
    d.execute_script("window.scrollTo(0, 600);")
    time.sleep(1)
    d.execute_script("window.scrollTo(0, 500);")
    time.sleep(0.6)
    rec['scroll_before'] = d.execute_script("return Math.round(window.scrollY)")
    rec['theme_before'] = d.execute_script(
        "return document.documentElement.classList.contains('dark')")
    open_export_dialog_and_click(d, double=True)
    z = wait_zip(dl, 200)
    rec['zip'] = os.path.basename(z) if z else None
    rec['zip_count'] = len([f for f in os.listdir(dl) if f.lower().endswith('.zip')])
    time.sleep(2.5)
    rec['zip_count_after_wait'] = len([f for f in os.listdir(dl) if f.lower().endswith('.zip')])
    rec['collapsed_after'] = d.execute_script(
        "var b=document.querySelector('[data-slot=\"collapsible-trigger\"]');"
        "var h=b?b.closest('[data-slot=\"collapsible\"]'):null;"
        "var p=h?h.querySelector('[data-slot=\"collapsible-content\"],[data-slot=\"collapsible-panel\"]'):null;"
        "return p?(p.style.display==='none'||p.hasAttribute('hidden')?'collapsed':'expanded'):null")
    rec['scroll_after'] = d.execute_script("return Math.round(window.scrollY)")
    rec['theme_after'] = d.execute_script(
        "return document.documentElement.classList.contains('dark')")
    rec['exporting_buttons'] = d.execute_script(
        "return Array.from(document.querySelectorAll('button')).filter(b=>b.disabled).map(b=>b.textContent.trim()).filter(Boolean).slice(0,10)")
    rec['shot'] = sm.shot(d, 'verify_2418_after_export_state')
    RESULT['checks']['state'] = rec
    return rec


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--only', default=None, choices=['large', 'state'])
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ART, exist_ok=True)
    sm.env_check('verify_start')
    smoke = sm.Smoke('react', base)
    sm.RESULT['art'] = ART
    driver = sm.make_driver(ART)
    try:
        smoke.drv = driver
        login(driver, base)
        if args.only in (None, 'large'):
            part_large(base, driver)
            log('large done')
        if args.only in (None, 'state'):
            part_state(base, driver)
            log('state done')
        sm.env_check('verify_end')
    finally:
        try:
            driver.quit()
        except Exception:
            pass
    with open(os.path.join(ART, 'verify_summary.json'), 'w', encoding='utf-8') as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=2)
    print('VERIFY_JSON=%s' % os.path.join(ART, 'verify_summary.json'))


if __name__ == '__main__':
    main()
