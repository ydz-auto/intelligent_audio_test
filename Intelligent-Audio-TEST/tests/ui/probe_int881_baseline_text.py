# -*- coding: utf-8 -*-
"""INT-881 wiring/react 基线最终确认——文本版 Network 证据（供验收评论引用）。

独立于 retest_int881_934_935.py 截图证据，把两失败项的请求/响应时序以纯文本输出：
1. INT-934：/report/999999 → GET /reports/999999 的 HTTP 状态 + 响应体（envelope code/message）。
2. INT-935：报告中心二次对比提交 → SSE GET /sse/events 是否先于 POST /reports/secondary-compare；
   提交后 URL 不跳 /report/undefined，进度弹窗终端态文本。
用法：python tests/ui/probe_int881_baseline_text.py --base http://localhost:5307
"""
import argparse
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

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
    prefs = {'browser': 'ALL', 'performance': 'ALL'}
    options.set_capability('goog:loggingPrefs', prefs)
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


def _body(drv):
    return drv.execute_script("return document.body.textContent || ''")


def _wait_body_has(drv, text, timeout=15):
    WebDriverWait(drv, timeout).until(lambda d: text in _body(drv))


def _net_events(drv):
    """CDP performance log → 请求事件（含响应体）。"""
    reqs = []
    try:
        for entry in drv.get_log('performance'):
            try:
                msg = json.loads(entry.get('message', '') or '')
                inner = msg.get('message') or {}
                method = inner.get('method') or ''
                params = inner.get('params') or {}
            except Exception:
                continue
            if method == 'Network.requestWillBeSent':
                r = params.get('request') or {}
                reqs.append({
                    'requestId': params.get('requestId'),
                    'method': r.get('method', 'GET'),
                    'url': r.get('url', ''),
                    'ts': params.get('timestamp', 0),
                    'postData': r.get('postData', '') or '',
                })
            elif method == 'Network.responseReceived':
                rid = params.get('requestId')
                for q in reqs:
                    if q['requestId'] == rid:
                        q['status'] = (params.get('response') or {}).get('status')
            elif method == 'Network.loadingFinished':
                rid = params.get('requestId')
                for q in reqs:
                    if q['requestId'] == rid:
                        q['finished'] = True
    except Exception as e:
        print('performance log read failed:', e)
    return reqs


def _fetch_response_body(drv, request_id):
    """用 CDP 拉取响应体（仅 HTTP/1.1 可用）。"""
    try:
        from selenium.common.exceptions import WebDriverException
    except Exception:
        pass
    try:
        result = drv.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
        return result.get('body', '')
    except Exception as e:
        return '<body fetch failed: %s>' % e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5307')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    out = []

    # ---- INT-934: /report/999999 ----
    drv = _driver()
    try:
        drv.get(base + '/')
        time.sleep(2)
        drv.execute_script('localStorage.removeItem(%r)' % THEME_KEY)
        drv.get(base + '/report/999999')
        time.sleep(8)
        body = _body(drv)
        out.append('INT-934 /report/999999: 报告不存在=%s, 加载失败=%s' %
                   ('报告不存在' in body, '加载失败' in body))
        reqs = _net_events(drv)
        for q in reqs:
            if '/reports/999999' in q['url']:
                bodytxt = _fetch_response_body(drv, q['requestId'])
                out.append('  [NET] %s %s status=%s body=%s' %
                           (q['method'], q['url'], q.get('status'), bodytxt[:220]))
        if not any('/reports/999999' in q['url'] for q in reqs):
            out.append('  [WARN] no /reports/999999 request captured')
    finally:
        drv.quit()

    # ---- INT-935: secondary-compare submit ----
    drv = _driver()
    try:
        drv.get(base + '/')
        time.sleep(2)
        drv.execute_script('localStorage.removeItem(%r)' % THEME_KEY)
        drv.get(base + '/report-center')
        _wait_body_has(drv, '报告中心', 15)
        time.sleep(3)

        checkboxes = drv.find_elements(By.CSS_SELECTOR, 'table tbody tr td:first-child [role="checkbox"]')
        selected = 0
        for cb in checkboxes:
            try:
                drv.execute_script('arguments[0].click();', cb)
                selected += 1
                time.sleep(0.3)
                if selected >= 2:
                    break
            except Exception:
                continue
        out.append('INT-935 selected reports: %d' % selected)
        time.sleep(1.5)

        for label in ('批量对比', '基于已选报告'):
            for b in drv.find_elements(By.TAG_NAME, 'button'):
                try:
                    if label in (b.text or '') and b.is_displayed():
                        drv.execute_script('arguments[0].click();', b)
                        time.sleep(1.2)
                        break
                except Exception:
                    continue

        drv.get_log('performance')
        for b in drv.find_elements(By.TAG_NAME, 'button'):
            try:
                if '生成对比报告' in (b.text or '') and b.is_displayed():
                    drv.execute_script('arguments[0].click();', b)
                    break
            except Exception:
                continue

        terminal = None
        deadline = time.time() + 25
        while time.time() < deadline:
            b = _body(drv)
            if '生成失败' in b:
                terminal = 'failed'
                break
            if '生成完成' in b and '查看报告' in b:
                terminal = 'completed'
                break
            time.sleep(0.8)
        time.sleep(1)
        b = _body(drv)
        url = drv.current_url
        out.append('INT-935 terminal=%s url_has_undefined=%s url=%s' %
                   (terminal, '/report/undefined' in url, url))
        # 失败弹窗错误文案
        if terminal == 'failed':
            idx = b.find('生成失败')
            out.append('  failure-dialog-excerpt: %s' % b[max(0, idx - 60):idx + 140].replace('\n', ' '))

        reqs = _net_events(drv)
        sse = [q for q in reqs if '/sse/events' in q['url'] and q['method'] == 'GET']
        post = [q for q in reqs if '/reports/secondary-compare' in q['url']]
        sse_ts = min((q.get('ts', 0) for q in sse), default=None)
        post_ts = min((q.get('ts', 0) for q in post), default=None)
        out.append('  SSE_GET=%d first_ts=%.3f; POST_secondary_compare=%d first_ts=%s' %
                   (len(sse), sse_ts or 0, len(post), ('%.3f' % post_ts) if post_ts else None))
        out.append('  SSE_opened_before_POST=%s' % (sse_ts is not None and post_ts is not None and sse_ts < post_ts))
        for q in sse[:2]:
            out.append('  [NET] %s %s status=%s' % (q['method'], q['url'][:120], q.get('status')))
        for q in post:
            out.append('  [NET] %s %s status=%s body=%s' %
                       (q['method'], q['url'], q.get('status'), (q.get('postData') or '')[:200]))
    finally:
        drv.quit()

    print('\n'.join(out))


if __name__ == '__main__':
    sys.exit(main())
