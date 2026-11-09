# -*- coding: utf-8 -*-
"""INT-2418 验收探针：报告详情「导出 → HTML」= 前端 DOM 快照 zip（不再走后端 /reports/export）。

复用 smoke_frontend_int1854 的驱动/登录/截图/网络日志设施，只跑报告详情链路并额外验证：
  1) 浅色页面导出：zip 内 report.html + css/report.css、区块锚点齐全、用例全量、无操作按钮残留；
  2) 全程无 `POST /reports/export` 请求；
  3) `file://` 离线打开导出 HTML：无任何 http(s) 请求、有截图；
  4) 深色页面导出：产物仍是浅色版，导出后页面主题复原为深色。

跑法：
  python tests/ui/probe_int2418_html_export.py --base http://localhost:15259
  （环境变量 UI_TEST_USERNAME / UI_TEST_PASSWORD 可覆盖登录账号）
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from tests.ui import smoke_frontend_int1854 as sm  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

ART = os.path.join(sm.ART_ROOT, 'int2418')
RESULT = {'kind': 'react', 'art': ART, 'checks': {}, 'notes': []}


def log(msg):
    print('[int2418] %s' % msg, flush=True)


def open_first_report(drv, base):
    """报告中心 → 首个带具体用例的报告详情页。"""
    drv.get(base.rstrip('/') + '/report-center')
    time.sleep(5)
    sm.wait_quiet(drv, 40)
    rows = [r for r in drv.find_elements(By.CSS_SELECTOR, 'tbody tr') if r.is_displayed()]
    if not rows:
        raise AssertionError('报告中心无数据行')
    sm.click_js(drv, rows[0])
    time.sleep(7)
    sm.wait_quiet(drv, 40)
    return drv.current_url


def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', required=True)
    ap.add_argument('--report', type=int, default=None,
                    help='指定报告 id（缺省用报告中心首行）')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ART, exist_ok=True)

    sm.env_check('probe_start')
    smoke = sm.Smoke('react', base)
    # Smoke.__init__ 会把 RESULT['art'] 重置成 ART_ROOT/<kind>；探针产物统一放 int2418/
    sm.RESULT['art'] = ART
    download_dir = os.path.join(ART, 'downloads')
    os.makedirs(download_dir, exist_ok=True)
    driver = sm.make_driver(download_dir)
    RESULT['driver'] = 'chrome-headless'
    try:
        smoke.drv = driver
        login = smoke.login()
        RESULT['checks']['login'] = {'ok': login.get('ok'), 'url': login.get('url_after')}
        assert login.get('ok'), '登录失败: %s' % login

        # ---- 1) 浅色报告详情 + HTML 导出 ----
        if args.report:
            detail_url = '%s/report/%d' % (base, args.report)
            driver.get(detail_url)
            time.sleep(7)
            sm.wait_quiet(driver, 40)
        else:
            detail_url = open_first_report(driver, base)
        RESULT['detail_url'] = detail_url
        RESULT['checks']['detail_text'] = sm.body_text(driver)[:400]
        RESULT['checks']['detail_shot'] = sm.shot(driver, '2418_report_detail_light')
        export_light = smoke.export_html(driver)
        RESULT['checks']['export_light'] = export_light
        log('export_light ok=%s zip=%s cases=%s' % (
            export_light.get('ok'), export_light.get('zip'), export_light.get('exported_case_cards')))

        # ---- 2) 深色页面导出：产物仍浅色，页面主题复原 ----
        driver.get(detail_url)
        time.sleep(2)
        driver.execute_script(
            "localStorage.setItem('iatp:theme:v1:mode','dark'); location.reload();")
        time.sleep(6)
        sm.wait_quiet(driver, 40)
        dark_before = driver.execute_script(
            "return document.documentElement.classList.contains('dark')")
        RESULT['checks']['dark_page_before'] = bool(dark_before)
        RESULT['checks']['dark_shot'] = sm.shot(driver, '2418_report_detail_dark')
        export_dark = smoke.export_html(driver) if dark_before else {'ok': False, 'error': '页面未进入深色'}
        # 导出结束会跳到 file:// 预览页，主题复原与否取导出后、离开页面前的读数
        dark_after = export_dark.get('theme_class_after_export')
        export_dark['theme_restored_dark'] = bool(dark_after)
        # 产物不带深色根类（固定浅色版）
        html_path = os.path.join(ART, 'exported_html', 'report.html')
        if os.path.exists(html_path):
            with open(html_path, 'r', encoding='utf-8') as fh:
                exported_html = fh.read()
            export_dark['exported_html_has_dark_class'] = bool(
                __import__('re').search(r'<html[^>]*class="[^"]*dark', exported_html))
            export_dark['exported_html_size'] = len(exported_html)
        RESULT['checks']['export_dark'] = export_dark
        log('export_dark ok=%s restored=%s' % (export_dark.get('ok'), dark_after))

        # ---- 汇总 ----
        light_ok = bool(export_light.get('ok'))
        dark_ok = bool(export_dark.get('ok')) and export_dark.get('theme_restored_dark') \
            and not export_dark.get('exported_html_has_dark_class')
        RESULT['ok'] = light_ok and dark_ok
        RESULT['console_errors'] = sm.console_errors(driver)
        sm.env_check('probe_end')
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
