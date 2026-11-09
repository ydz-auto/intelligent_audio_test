# -*- coding: utf-8 -*-
"""INT-2418 返工复测探针：对比表格列头（P2-1）/ 图表静态化（P3-2）/ 筛选卡残留（P3-3）。

跑法：
  python tests/ui/probe_int2418_export_rework.py --base http://localhost:15258
  （--report 默认 395 对比报告；UI_TEST_USERNAME / UI_TEST_PASSWORD 可覆盖登录账号）
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

ART = os.path.join(sm.ART_ROOT, 'int2418_rework')
RESULT = {'checks': {}}

SECTION_JS = (
    "var s=document.getElementById('report-case-category');return !!s;"
)
PAGE_TH_JS = (
    "return Array.from(document.querySelectorAll('#report-case-category th, #report-case-tag th'))"
    ".map(function(e){return (e.innerText||e.textContent||'').trim();});"
)


def log(msg):
    print('[rework2418] %s' % msg, flush=True)


def login_harness(smoke):
    """用 smoke 驱动的登录（校验 /auth/login 200 + token 落库 + 刷新后会话保持）。"""
    rec = smoke.login()
    assert rec.get('ok'), '登录失败: %s' % rec
    log('login ok url=%s' % rec.get('url_after'))


def switch_display(d, label):
    """点分组/标签对比卡里的显示类型切换按钮（表格 / 柱状图 ...）。"""
    btns = [b for b in d.find_elements(By.TAG_NAME, 'button')
            if b.is_displayed() and (b.text or '').strip() == label]
    if not btns:
        return False
    sm.click_js(d, btns[0])
    time.sleep(2.5)
    return True


def export_zip(d, tag):
    """走报告详情导出弹窗，返回 (zip_path, 下载目录)。"""
    dl = os.path.join(ART, 'downloads_%s' % tag)
    os.makedirs(dl, exist_ok=True)
    for f in os.listdir(dl):
        os.remove(os.path.join(dl, f))
    d.execute_cdp_cmd('Page.setDownloadBehavior', {'behavior': 'allow', 'downloadPath': dl})
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
    deadline = time.time() + 240
    last = -1
    while time.time() < deadline:
        files = [f for f in os.listdir(dl) if f.lower().endswith('.zip')]
        if files:
            p = os.path.join(dl, files[0])
            try:
                size = os.path.getsize(p)
            except OSError:
                size = -1
            if size > 0 and size == last:
                return p, dl
            last = size
        time.sleep(1)
    return None, dl


def extract(zip_path, out_dir):
    os.makedirs(os.path.join(out_dir, 'css'), exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        zf.extractall(out_dir)
    return names


def analyze_html(html_path, rec):
    html = open(html_path, encoding='utf-8').read()
    rec['html_size'] = len(html)
    # P2-1：th 文本（去标签后非空）
    ths = re.findall(r'<th\b[^>]*>(.*?)</th>', html, re.S)
    texts = [re.sub(r'<[^>]+>', '', t).strip() for t in ths]
    rec['th_total'] = len(texts)
    rec['th_empty'] = len([t for t in texts if not t])
    rec['th_sample'] = [t for t in texts if t][:12]
    # P3-2：图表静态化
    rec['canvas_left'] = html.count('<canvas')
    rec['img_total'] = len(re.findall(r'<img\b', html))
    rec['chart_img'] = len(re.findall(r'<img[^>]+src="data:image/png', html))
    # P3-3：筛选卡骨架残留
    rec['filter_label_case_name'] = html.count('>用例名称<')
    rec['filter_label_metric'] = html.count('>评估维度<')
    rec['role_checkbox'] = html.count('role="checkbox"')
    rec['input_left'] = len(re.findall(r'<input\b', html))
    # 操作按钮残留
    rec['residual_action_buttons'] = re.findall(
        r'<button[^>]*>\s*(?:保存|发布|取消发布|导出|删除|彻底删除|下载日志|人工复核)\s*</button>', html)
    return html


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--report', type=int, default=395)
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ART, exist_ok=True)

    sm.env_check('rework_start')
    smoke = sm.Smoke('react', base)
    sm.RESULT['art'] = ART
    d = sm.make_driver(os.path.join(ART, 'downloads_driver'))
    try:
        smoke.drv = d
        login_harness(smoke)
        detail_url = '%s/report/%d' % (base, args.report)
        d.get(detail_url)
        time.sleep(9)
        sm.wait_quiet(d, 40)
        rec = {}
        rec['has_case_category'] = bool(d.execute_script(SECTION_JS))
        rec['page_th'] = d.execute_script(PAGE_TH_JS)
        rec['page_canvases_table_view'] = d.execute_script(
            "return Array.from(document.querySelectorAll('#report-case-category canvas')).length")
        rec['page_shot_light'] = sm.shot(d, 'rework_page_light_table')

        # ---- 1) 表格视图导出（P2-1 列头 / P3-3 筛选卡）----
        z1, _ = export_zip(d, 'table')
        assert z1, '表格视图导出未下载到 zip'
        rec['zip_table'] = os.path.basename(z1)
        rec['zip_table_size'] = os.path.getsize(z1)
        out1 = os.path.join(ART, 'export_table')
        rec['entries_table'] = extract(z1, out1)
        rec['table'] = {}
        html_table = analyze_html(os.path.join(out1, 'report.html'), rec['table'])
        rec['table']['ok_p2_1'] = rec['table']['th_empty'] == 0 and rec['table']['th_total'] > 0
        rec['table']['ok_p3_3'] = (rec['table']['filter_label_case_name'] == 0
                                   and rec['table']['filter_label_metric'] == 0
                                   and rec['table']['role_checkbox'] == 0)
        time.sleep(1)
        rec['table']['shot_export'] = sm.shot(d, 'rework_export_table')

        # ---- 2) 切柱状图后导出（P3-2 静态图）----
        d.get(detail_url)
        time.sleep(7)
        sm.wait_quiet(d, 40)
        rec['switch_bar'] = switch_display(d, '柱状图')
        rec['page_canvases_bar_view'] = d.execute_script(
            "return Array.from(document.querySelectorAll('#report-case-category canvas')).length")
        rec['page_shot_bar'] = sm.shot(d, 'rework_page_light_bar')
        z2, _ = export_zip(d, 'bar')
        assert z2, '柱状图视图导出未下载到 zip'
        rec['zip_bar'] = os.path.basename(z2)
        rec['zip_bar_size'] = os.path.getsize(z2)
        out2 = os.path.join(ART, 'export_bar')
        extract(z2, out2)
        rec['bar'] = {}
        analyze_html(os.path.join(out2, 'report.html'), rec['bar'])
        rec['bar']['ok_p3_2'] = (rec['bar']['canvas_left'] == 0
                                 and rec['bar']['chart_img'] >= max(1, rec['page_canvases_bar_view']))
        # 导出 HTML file:// 打开：图表区域截图
        fpath = os.path.join(out2, 'report.html').replace('\\', '/')
        sm.parse_perf(d.get_log('performance'))
        d.get('file:///' + fpath)
        time.sleep(3)
        rec['offline_http'] = [a.get('url') for a in sm.parse_perf(d.get_log('performance'))
                               if (a.get('url') or '').startswith(('http://', 'https://'))]
        rec['offline_images_total'] = d.execute_script("return document.images.length")
        rec['offline_images_broken'] = d.execute_script(
            "return Array.from(document.images).filter(function(i){return i.complete && i.naturalWidth===0;}).length")
        rec['offline_canvas'] = d.execute_script("return document.querySelectorAll('canvas').length")
        sec = d.find_element(By.ID, 'report-case-category')
        d.execute_script("arguments[0].scrollIntoView({block:'start'});", sec)
        time.sleep(1)
        rec['offline_shot_bar'] = sm.shot(d, 'rework_export_bar_chart')

        # ---- 3) 深色页面截图（导出口径不变，仍是浅色产物）----
        d.get(detail_url)
        time.sleep(2)
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark'); location.reload();")
        time.sleep(7)
        sm.wait_quiet(d, 40)
        rec['dark_page'] = bool(d.execute_script(
            "return document.documentElement.classList.contains('dark')"))
        rec['page_shot_dark'] = sm.shot(d, 'rework_page_dark')

        RESULT['checks']['report'] = rec
        RESULT['ok'] = bool(
            rec['has_case_category']
            and rec['table']['ok_p2_1']
            and rec['table']['ok_p3_3']
            and rec['switch_bar']
            and rec['bar']['ok_p3_2']
            and not rec['offline_http']
            and rec['offline_images_broken'] == 0
        )
        RESULT['console_errors'] = sm.console_errors(d)
        sm.env_check('rework_end')
    finally:
        try:
            d.quit()
        except Exception:
            pass

    out_path = os.path.join(ART, 'summary.json')
    with open(out_path, 'w', encoding='utf-8') as fh:
        json.dump(RESULT, fh, ensure_ascii=False, indent=2)
    print('SUMMARY_JSON=%s' % out_path)
    print('OK=%s' % RESULT.get('ok'))


if __name__ == '__main__':
    main()
