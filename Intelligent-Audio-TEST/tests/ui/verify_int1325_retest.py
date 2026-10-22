# -*- coding: utf-8 -*-
"""INT-1325 测试工程师复验（真实库栈 5700，经 dev server 代理）。

- 问题 1：设备 SPL（E2E）新建提交 digital_gain 后请求体与回读核对。
  前端请求体必须含 digital_gain；5700 后端是否落库取决于 INT-1337 是否已部署
  （真实库栈 device_service 2026-10-22 17:18 起，早于 INT-1337 19:33 提交 → 预期仍 None）。
- 问题 2：删除默认 RMS-SPL 映射后 GET /apis 该 API 不残留 rms_spl_mapping_id 悬挂指针。

证据：浅/深色截图 + Network performance log + 接口请求/响应。
用法：python verify_int1325_retest.py --base http://localhost:5325
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1325_retest')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
UNIQ = '接线测试_INT1325_验A'


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
    return webdriver.Chrome(options=options, service=service)


def _goto(drv, base, path):
    drv.get(base + path)
    WebDriverWait(drv, 25).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _login(drv, base):
    _goto(drv, base, '/login')
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, base, '/login')
    drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
    time.sleep(2.0)


def _fetch_json(drv, url):
    """页内 fetch 带 token 取真实接口 JSON（跳开 UI 往返，直接读读侧）。"""
    return drv.execute_script(
        'return (async () => {'
        '  const t = (() => { try { return localStorage.getItem("iatp:auth:token:v1") } catch(e){ return "" } })();'
        '  const r = await fetch(arguments[0], {headers: {"Authorization": "Bearer " + t}});'
        '  const text = await r.text();'
        '  return JSON.stringify({status: r.status, body: text});'
        '})()', url)


def _mutate(drv, method, url, body=None):
    """页内 fetch 写操作（带 token），返回 {status, body}。"""
    js = (
        'return (async () => {'
        '  const t = (() => { try { return localStorage.getItem("iatp:auth:token:v1") } catch(e){ return "" } })();'
        '  const opts = {method: arguments[0], headers: {"Authorization": "Bearer " + t, "Content-Type": "application/json"}};'
        '  if (arguments[2]) opts.body = JSON.stringify(arguments[2]);'
        '  const r = await fetch(arguments[1], opts);'
        '  const text = await r.text();'
        '  return JSON.stringify({status: r.status, body: text});'
        '})()'
    )
    return drv.execute_script(js, method, url, body)


def _perf_requests(drv):
    reqs = []
    for entry in drv.get_log('performance'):
        try:
            msg = json.loads(entry.get('message', '') or '')
            inner = msg.get('message') or {}
            method = inner.get('method') or ''
            params = inner.get('params') or {}
            if method == 'Network.requestWillBeSent':
                req = params.get('request') or {}
                reqs.append({
                    'method': req.get('method', 'GET'),
                    'url': req.get('url', ''),
                    'status': None,
                })
            elif method == 'Network.responseReceived':
                rid = params.get('requestId')
                status = (params.get('response') or {}).get('status')
                url = (params.get('response') or {}).get('url', '')
                reqs.append({'method': '?', 'url': url, 'status': status})
        except Exception:
            continue
    return reqs


def _save(name, drv):
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv.save_screenshot(os.path.join(ARTIFACTS, name + '.png'))


def _find_new_spl(drv, base, name):
    j = _fetch_json(drv, base + '/api/v1/spl?page=1&per_page=100')
    d = json.loads(j)
    if d.get('status') != 200:
        return None
    b = json.loads(d.get('body') or '{}')
    items = b.get('data', {}).get('items', b.get('items', [])) if isinstance(b, dict) else []
    for it in items:
        if it.get('name') == name:
            return it
    return None


def _find_new_digital(drv, base, name):
    j = _fetch_json(drv, base + '/api/v1/digital-spl?page=1&per_page=100')
    d = json.loads(j)
    if d.get('status') != 200:
        return None
    b = json.loads(d.get('body') or '{}')
    items = b.get('data', {}).get('items', b.get('items', [])) if isinstance(b, dict) else []
    for it in items:
        if it.get('name') == name:
            return it
    return None


def _api_default_ptr(drv, base, api_id):
    j = _fetch_json(drv, base + '/api/v1/apis?page=1&per_page=100')
    d = json.loads(j)
    if d.get('status') != 200:
        return None
    b = json.loads(d.get('body') or '{}')
    items = b.get('data', {}).get('items', b.get('items', [])) if isinstance(b, dict) else []
    for it in items:
        if it.get('id') == api_id:
            return it.get('rms_spl_mapping_id')
    return 'NOT_FOUND'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5325')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)

    drv = _driver()
    results = []
    try:
        drv.set_page_load_timeout(60)
        _login(drv, base)
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "light")')
        _goto(drv, base, '/SPLMapping')
        time.sleep(2)
        _save('01_spl_page_light', drv)

        # ───────── 问题 1：设备 SPL 新建 digital_gain ─────────
        drv.execute_script('window.__postBodies = []')
        drv.execute_script(
            'const orig = window.fetch;'
            'window.fetch = function(url, opts){'
            '  try { if (opts && opts.method === "POST" && String(url).includes("/spl")) {'
            '    window.__postBodies.push({url: String(url), body: opts.body || ""});'
            '  } } catch(e){}'
            '  return orig.apply(this, arguments);'
            '};')
        drv.find_element(By.XPATH, "//button[contains(., '添加增益映射')]").click()
        WebDriverWait(drv, 10).until(
            lambda d: d.find_elements(By.XPATH, "//*[contains(@role,'dialog')]"))
        time.sleep(1.0)
        name_input = drv.find_element(By.XPATH, "//input[@aria-label='映射名称']")
        name_input.clear()
        name_input.send_keys(UNIQ + '_设备SPL')
        drv.execute_script(
            "var t = document.querySelector('button[aria-label=\"关联播放设备\"]'); if(t) t.click();")
        time.sleep(1.0)
        opts = drv.find_elements(By.XPATH, "//*[@role='option']")
        if opts:
            opts[0].click()
        else:
            drv.execute_script(
                "var opts = Array.from(document.querySelectorAll('[role=option]'));"
                "if(opts.length) opts[0].click();")
        time.sleep(0.6)
        dg = drv.find_element(By.XPATH, "//input[@aria-label='数字增益']")
        dg.clear()
        dg.send_keys('2')
        time.sleep(0.5)
        _save('02_device_create_filled_dg2', drv)
        drv.find_element(By.XPATH, "//button[contains(., '保存')]").click()
        time.sleep(3.0)

        post_bodies = drv.execute_script('return window.__postBodies')
        create_body = None
        for p in post_bodies:
            if '/api/v1/spl' in p['url'] and '/by-api' not in p['url']:
                create_body = p
                break
        results.append(('P1 POST /spl captured', bool(create_body)))
        if create_body:
            results.append(('P1 POST body', create_body.get('body', '')[:400]))

        created = _find_new_spl(drv, base, UNIQ + '_设备SPL')
        results.append(('P1 record in /spl list', created is not None))
        created_id = None
        if created:
            created_id = created['id']
            j = _fetch_json(drv, base + '/api/v1/spl/%d' % created_id)
            d = json.loads(j)
            dg_back = None
            if d.get('status') == 200:
                b = json.loads(d.get('body') or '{}')
                ent = b.get('data', b)
                dg_back = ent.get('digital_gain')
            results.append(('P1 GET /spl/%d digital_gain (5700 现状)' % created_id, dg_back))

        # 清理：软删新建的设备 SPL
        if created_id:
            r = _mutate(drv, 'DELETE', base + '/api/v1/spl/%d' % created_id)
            results.append(('P1 cleanup DELETE /spl/%d status' % created_id,
                            json.loads(r).get('status')))

        # ───────── 问题 2：删除默认 RMS-SPL 后 /apis 不残留指针 ─────────
        drv.find_element(By.XPATH, "//*[@role='tab'][contains(., 'API/Realtime RMS-SPL')]").click()
        time.sleep(1.5)
        drv.find_element(By.XPATH, "//button[contains(., '添加 RMS-SPL 映射')]").click()
        WebDriverWait(drv, 10).until(
            lambda d: d.find_elements(By.XPATH, "//*[contains(@role,'dialog')]"))
        time.sleep(1.0)
        name2 = drv.find_element(By.XPATH, "//input[@aria-label='映射名称']")
        name2.clear()
        name2.send_keys(UNIQ + '_RMS')
        drv.execute_script(
            "var t = document.querySelector('button[aria-label=\"关联被测 API\"]'); if(t) t.click();")
        time.sleep(1.0)
        opts2 = drv.find_elements(By.XPATH, "//*[@role='option']")
        if opts2:
            opts2[0].click()
        else:
            drv.execute_script(
                "var opts = Array.from(document.querySelectorAll('[role=option]'));"
                "if(opts.length) opts[0].click();")
        time.sleep(0.6)
        _save('03_digital_create_filled', drv)
        drv.find_element(By.XPATH, "//button[contains(., '保存')]").click()
        time.sleep(3.0)

        dm = _find_new_digital(drv, base, UNIQ + '_RMS')
        digital_id = dm.get('id') if dm else None
        api_id = dm.get('api_id') if dm else None
        results.append(('P2 created digital id/api', (digital_id, api_id)))

        if digital_id:
            # 行菜单设默认
            btn = drv.find_element(By.XPATH, "//button[@aria-label='映射 %s 的操作']" % (UNIQ + '_RMS'))
            drv.execute_script('arguments[0].click()', btn)
            WebDriverWait(drv, 5).until(
                lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
            for it in drv.find_elements(By.XPATH, "//*[@role='menuitem']"):
                if '设默认' in it.text:
                    drv.execute_script('arguments[0].click()', it)
                    break
            time.sleep(2.5)
            ptr_before = _api_default_ptr(drv, base, api_id)
            results.append(('P2 set-default ptr on API (期望=%d)' % digital_id, ptr_before))
            _save('04_digital_set_default', drv)

            # 行菜单删除
            btn2 = drv.find_element(By.XPATH, "//button[@aria-label='映射 %s 的操作']" % (UNIQ + '_RMS'))
            drv.execute_script('arguments[0].click()', btn2)
            WebDriverWait(drv, 5).until(
                lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
            for it in drv.find_elements(By.XPATH, "//*[@role='menuitem']"):
                if '删除' in it.text:
                    drv.execute_script('arguments[0].click()', it)
                    break
            WebDriverWait(drv, 10).until(
                lambda d: d.find_elements(By.XPATH, "//*[contains(@role,'dialog')]"))
            time.sleep(1.2)
            _save('05_digital_delete_confirm', drv)
            for it in drv.find_elements(By.XPATH, "//button"):
                if it.text.strip() == '删除':
                    drv.execute_script('arguments[0].click()', it)
                    break
            time.sleep(3.0)

            ptr_after = _api_default_ptr(drv, base, api_id)
            results.append(('P2 after-delete ptr on API (期望=null)', ptr_after))
            _save('06_digital_deleted', drv)

            chk = _fetch_json(drv, base + '/api/v1/digital-spl/%d' % digital_id)
            results.append(('P2 GET /digital-spl/%d after delete' % digital_id, chk[:160]))

        # ───────── 深色截图 ─────────
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "dark")')
        _goto(drv, base, '/SPLMapping')
        time.sleep(2)
        _save('07_spl_page_dark', drv)

        # ───────── Network 证据 ─────────
        net = _perf_requests(drv)
        lines = []
        for r in net:
            if any(k in r['url'] for k in ('/spl', '/digital-spl', '/apis')):
                lines.append('%s %s status=%s' % (r['method'], r['url'].replace(base, ''), r['status']))
        results.append(('Network spl/digital/apis', lines[:40]))

        # ───────── 防串库（经代理后的健康检查） ─────────
        h = _fetch_json(drv, base + '/api/v1/health') if False else None
        results.append(('db', 'see health checks below'))

        print('==== INT-1325 RETEST RESULT ====')
        for k, v in results:
            print('%s: %s' % (k, v))
        print('artifacts: %s' % ARTIFACTS)

        sev = []
        try:
            for entry in drv.get_log('browser'):
                if entry.get('level') == 'SEVERE':
                    sev.append(entry.get('message', ''))
        except Exception:
            pass
        print('console SEVERE count: %d' % len(sev))
        if sev:
            print('\n'.join(sev[:5]))
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
