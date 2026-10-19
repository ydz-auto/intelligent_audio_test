# -*- coding: utf-8 -*-
"""INT-934 前端UX审计员复验脚本：无效ID错误态 + 有效报告非回归 + 浅/深色截图 + Network。

常驻后端 :5000（AUTH_MODE=off）+ 本 run dev server :<port>。
断言：
1. /report/999999 渲染「报告不存在 / 请提供有效的报告ID」，无「加载失败 / 请重试」
2. /report/67 正常渲染报告详情（未误落「报告不存在」）
3. Network：/reports/999999 → HTTP 400 + envelope {code:404}；/reports/67 → 200
4. Console SEVERE 仅无效ID请求的 400 网络日志
"""
import argparse
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int934_audit')
THEME_KEY = 'iatp:theme:v1:mode'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    drv_path = ''
    if chrome_major and os.path.isdir(cache_root):
        cands = []
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    cands.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
                except ValueError:
                    continue
        same = [exe for ver, exe in cands if ver and ver[0] == chrome_major]
        if same:
            drv_path = max(same)
    service = Service(executable_path=drv_path) if drv_path else Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45)
    return drv


def _goto(drv, base, path, settle=2.0):
    drv.get(base + path)
    WebDriverWait(drv, 25).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(settle)


def _wait_text(drv, text):
    WebDriverWait(drv, 20).until(lambda d: text in (d.page_source or ''))


def _set_theme(drv, mode):
    drv.execute_script('try { localStorage.setItem(%r, %r) } catch (e) {}' % (THEME_KEY, mode))


def _network_entries(drv, needle):
    """从 performance log 双层嵌套解析请求（Selenium 4 + Chrome CDP）。"""
    found = []
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry.get('message', '') or '')
            inner = msg.get('message') or {}
            method = inner.get('method') or ''
            params = inner.get('params') or {}
        except Exception:
            continue
        if method == 'Network.responseReceived':
            resp = params.get('response') or {}
            url = resp.get('url') or ''
            if needle in url:
                found.append({'url': url, 'status': resp.get('status')})
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5360')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)

    drv = _driver()
    results = {}
    try:
        # ===== 1. 无效 ID 错误态 =====
        _goto(drv, base, '/')
        _goto(drv, base, '/report/999999')
        _wait_text(drv, '报告不存在')
        _wait_text(drv, '请提供有效的报告ID')
        results['not_found_rendered'] = True
        page_src = drv.page_source or ''
        results['has_load_failed_text'] = '加载失败' in page_src
        results['has_retry_btn'] = '请重试' in page_src

        # Network：无效 ID 请求
        nf_reqs = _network_entries(drv, '/reports/999999')
        results['nf_req_statuses'] = sorted({r['status'] for r in nf_reqs})
        results['nf_req_count'] = len(nf_reqs)

        # 浅色截图
        _set_theme(drv, 'light')
        drv.refresh()
        _wait_text(drv, '报告不存在')
        time.sleep(1.5)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'report_not_found_light.png'))
        # 深色截图
        _set_theme(drv, 'dark')
        drv.refresh()
        _wait_text(drv, '报告不存在')
        time.sleep(1.5)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'report_not_found_dark.png'))

        # ===== 2. 有效报告非回归（新会话，清主题缓存）=====
        drv.execute_script('localStorage.removeItem(%r)' % THEME_KEY)
        _goto(drv, base, '/report/67', settle=3.0)
        _wait_text(drv, 'Benchmark报告_INT844测试')
        results['valid_report_rendered'] = True
        vs = drv.page_source or ''
        results['valid_reported_not_found_wrongly'] = '报告不存在' in vs
        valid_reqs = _network_entries(drv, '/reports/67')
        results['valid_req_statuses'] = sorted({r['status'] for r in valid_reqs})
        results['valid_req_count'] = len(valid_reqs)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'valid_report_67.png'))

        # ===== 3. Console 摘要 =====
        severe = []
        try:
            for entry in drv.get_log('browser'):
                if entry.get('level') == 'SEVERE':
                    severe.append(entry.get('message', ''))
        except Exception:
            pass
        non_400 = [s for s in severe if '/reports/999999' not in s]
        results['console_severe_count'] = len(severe)
        results['console_severe_non_expected'] = non_400[:5]

        with open(os.path.join(ARTIFACTS, 'result.json'), 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(json.dumps(results, ensure_ascii=False, indent=2))
    finally:
        drv.quit()


if __name__ == '__main__':
    sys.exit(main())
