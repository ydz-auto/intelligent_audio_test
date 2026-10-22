# -*- coding: utf-8 -*-
"""INT-1325 真实库栈复验（连真实库栈 5700，经 dev server 5320 代理）。

两项缺陷复验：
- 问题 1：设备 SPL 新建提交 digital_gain 后 GET /spl/{id} 回读与提交一致（不再是 None）。
  （INT-1337 后端 create 分支已落 digital_gain；本脚本以浏览器新建实测回读。）
- 问题 2：删除默认 RMS-SPL 映射后 GET /apis 该 API 不再残留 rms_spl_mapping_id 悬挂指针。
  （前端 handleConfirmDeleteDigital 删除前先清默认指针；70709ca6。）

证据：浅/深色截图 + Network 请求/响应 + 页面渲染核对。
用法：python verify_int1325_spl_digital_gain.py --base http://localhost:5320
"""
import argparse
import base64
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1325_spl')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
UNIQ = '接线测试_INT1325_A1'


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
    time.sleep(1.5)


def _fetch_json(drv, url):
    """页内 fetch 带 token 取真实接口 JSON（跳开 UI 往返，直接读读侧）。"""
    return drv.execute_script(
        'return (async () => {'
        '  const t = (() => { try { return localStorage.getItem("iatp:auth:token:v1") } catch(e){ return "" } })();'
        '  const r = await fetch(arguments[0], {headers: {"Authorization": "Bearer " + t}});'
        '  const text = await r.text();'
        '  return JSON.stringify({status: r.status, body: text});'
        '})()', url)


def _perf_requests(drv):
    """从 performance log 提取 HTTP 请求（双层嵌套解析）。"""
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
                    'requestId': params.get('requestId'),
                    'postData': req.get('postData') or '',
                    'status': None,
                })
            elif method == 'Network.responseReceived':
                rid = params.get('requestId')
                for r in reqs:
                    if r['requestId'] == rid:
                        r['status'] = (params.get('response') or {}).get('status')
        except Exception:
            continue
    return reqs


def _save_evidence(name, drv, base):
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv.save_screenshot(os.path.join(ARTIFACTS, name + '.png'))


def _drain_perf():
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5320')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)

    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        _login(drv, base)
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "light")')
        _goto(drv, base, '/SPLMapping')
        time.sleep(2)
        _save_evidence('01_spl_page_light', drv, base)

        results = []

        # ───────── 问题 1：设备 SPL 新建 digital_gain 回读一致 ─────────
        drv.execute_script('window.__postBodies = []')
        drv.execute_script(
            'const orig = window.fetch;'
            'window.fetch = function(url, opts){'
            '  try { if (opts && opts.method === "POST" && String(url).includes("/spl")) {'
            '    window.__postBodies.push({url: String(url), body: opts.body || ""});'
            '  } } catch(e){}'
            '  return orig.apply(this, arguments);'
            '};')
        # 添加增益映射
        drv.find_element(By.XPATH, "//button[contains(., '添加增益映射')]").click()
        WebDriverWait(drv, 10).until(
            lambda d: d.find_elements(By.XPATH, "//*[contains(@role,'dialog')]"))
        time.sleep(1.0)
        # 填名称
        name_input = drv.find_element(By.XPATH, "//input[@aria-label='映射名称']")
        name_input.clear()
        name_input.send_keys(UNIQ + '_设备SPL')
        # 关联播放设备 select（base-ui JS click → 选第一项）
        drv.execute_script(
            "var t = document.querySelector('button[aria-label=\"关联播放设备\"]'); if(t) t.click();")
        time.sleep(1.0)
        opts = drv.find_elements(By.XPATH, "//*[@role='option']")
        if opts:
            opts[0].click()
        else:
            # 后备：直接取 select 内第一项
            drv.execute_script(
                "var opts = Array.from(document.querySelectorAll('[role=option]'));"
                "if(opts.length) opts[0].click();")
        time.sleep(0.6)
        # 数字增益 = 2
        dg = drv.find_element(By.XPATH, "//input[@aria-label='数字增益']")
        dg.clear()
        dg.send_keys('2')
        time.sleep(0.5)
        _save_evidence('02_device_create_filled_dg2', drv, base)
        # 保存
        drv.find_element(By.XPATH, "//button[contains(., '保存')]").click()
        time.sleep(3.0)
        post_bodies = drv.execute_script('return window.__postBodies')
        create_req = [p for p in post_bodies if '/api/v1/spl' in p.get('url', '') and p.get('url', '').count('/spl') == 1 and 'by-api' not in p['url']]
        create_body = None
        if post_bodies:
            for p in post_bodies:
                if '/api/v1/spl' in p['url'] and '/by-api' not in p['url']:
                    create_body = p
                    break
        results.append(('P1 create request captured', bool(create_body)))

        # 从列表找新行 id：读 /spl 列表
        time.sleep(2)
        list_json = _fetch_json(drv, base + '/api/v1/spl?page=1&per_page=100')
        list_data = json.loads(list_json)
        created = None
        if list_data.get('status') == 200:
            body = json.loads(list_data.get('body') or '{}')
            items = body.get('data', {}).get('items', body.get('items', [])) if isinstance(body, dict) else []
            for it in items:
                if it.get('name') == UNIQ + '_设备SPL':
                    created = it
                    break
        results.append(('P1 record found in /spl list', created is not None))
        if created:
            detail_json = _fetch_json(drv, base + '/api/v1/spl/%d' % created['id'])
            detail = json.loads(detail_json)
            detail_dg = None
            if detail.get('status') == 200:
                b = json.loads(detail.get('body') or '{}')
                d = b.get('data', b)
                detail_dg = d.get('digital_gain')
            results.append(('P1 GET /spl/%d digital_gain' % created['id'], detail_dg))
            results.append(('P1 GET /spl/%d name' % created['id'], created['name']))
            created_id = created['id']
        else:
            created_id = None

        # 记录 POST body 内容
        if create_body:
            results.append(('P1 POST body', create_body.get('body', '')[:400]))

        # 删除新建的设备 SPL（数据卫生）
        if created_id:
            try:
                r = drv.execute_script(
                    'return (async () => {'
                    '  const t = (() => { try { return localStorage.getItem("iatp:auth:token:v1") } catch(e){ return "" } })();'
                    '  const r = await fetch("/api/v1/spl/%d", {method: "DELETE", headers: {"Authorization": "Bearer " + t}});'
                    '  return r.status;'
                    '})()' % created_id)
                results.append(('P1 cleanup DELETE /spl/%d status' % created_id, r))
            except Exception as e:
                results.append(('P1 cleanup DELETE error', str(e)))

        # ───────── 问题 2：删除默认 RMS-SPL 映射后 /apis 不残留指针 ─────────
        # 切数字域页签
        drv.find_element(By.XPATH, "//*[@role='tab'][contains(., 'API/Realtime RMS-SPL')]").click()
        time.sleep(1.5)
        # 添加 RMS-SPL 映射
        drv.find_element(By.XPATH, "//button[contains(., '添加 RMS-SPL 映射')]").click()
        WebDriverWait(drv, 10).until(
            lambda d: d.find_elements(By.XPATH, "//*[contains(@role,'dialog')]"))
        time.sleep(1.0)
        name2 = drv.find_element(By.XPATH, "//input[@aria-label='映射名称']")
        name2.clear()
        name2.send_keys(UNIQ + '_RMS')
        # 选第一个 API
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
        _save_evidence('03_digital_create_filled', drv, base)
        drv.find_element(By.XPATH, "//button[contains(., '保存')]").click()
        time.sleep(3.0)

        # 读 /digital-spl 找新行 id
        ds_json = _fetch_json(drv, base + '/api/v1/digital-spl?page=1&per_page=100')
        ds = json.loads(ds_json)
        digital_id = None
        api_id = None
        if ds.get('status') == 200:
            b = json.loads(ds.get('body') or '{}')
            items = b.get('data', {}).get('items', b.get('items', [])) if isinstance(b, dict) else []
            for it in items:
                if it.get('name') == UNIQ + '_RMS':
                    digital_id = it.get('id')
                    api_id = it.get('api_id')
                    break
        results.append(('P2 digital mapping created id/api', (digital_id, api_id)))

        # 行菜单：设默认
        if digital_id:
            try:
                btn = drv.find_element(
                    By.XPATH, "//button[@aria-label='映射 %s 的操作']" % (UNIQ + '_RMS'))
                drv.execute_script('arguments[0].click()', btn)
                WebDriverWait(drv, 5).until(
                    lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
                for it in drv.find_elements(By.XPATH, "//*[@role='menuitem']"):
                    if '设默认' in it.text:
                        drv.execute_script('arguments[0].click()', it)
                        break
                time.sleep(2.0)
                # 核对 /apis 该 API 默认指针命中新映射
                apis_json = _fetch_json(drv, base + '/api/v1/apis?page=1&per_page=100')
                apis = json.loads(apis_json)
                default_ptr = None
                if apis.get('status') == 200:
                    b = json.loads(apis.get('body') or '{}')
                    items = b.get('data', {}).get('items', b.get('items', [])) if isinstance(b, dict) else []
                    for it in items:
                        if it.get('id') == api_id:
                            default_ptr = it.get('rms_spl_mapping_id')
                            break
                results.append(('P2 set-default ptr on API', default_ptr))
                _save_evidence('04_digital_set_default', drv, base)

                # 行菜单：删除（触发 handleConfirmDeleteDigital 清默认指针）
                btn2 = drv.find_element(
                    By.XPATH, "//button[@aria-label='映射 %s 的操作']" % (UNIQ + '_RMS'))
                drv.execute_script('arguments[0].click()', btn2)
                WebDriverWait(drv, 5).until(
                    lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
                for it in drv.find_elements(By.XPATH, "//*[@role='menuitem']"):
                    if '删除' in it.text:
                        drv.execute_script('arguments[0].click()', it)
                        break
                # 确认弹窗
                WebDriverWait(drv, 10).until(
                    lambda d: d.find_elements(By.XPATH, "//*[contains(@role,'dialog')]"))
                time.sleep(1.2)
                _save_evidence('05_digital_delete_confirm', drv, base)
                for it in drv.find_elements(By.XPATH, "//button"):
                    if it.text.strip() == '删除':
                        drv.execute_script('arguments[0].click()', it)
                        break
                time.sleep(3.0)

                # 核对 /apis 该 API 默认指针已清空（无悬挂指针）
                apis_json2 = _fetch_json(drv, base + '/api/v1/apis?page=1&per_page=100')
                apis2 = json.loads(apis_json2)
                ptr_after = None
                if apis2.get('status') == 200:
                    b = json.loads(apis2.get('body') or '{}')
                    items = b.get('data', {}).get('items', b.get('items', [])) if isinstance(b, dict) else []
                    for it in items:
                        if it.get('id') == api_id:
                            ptr_after = it.get('rms_spl_mapping_id')
                            break
                results.append(('P2 after delete ptr on API (期望 null)', ptr_after))
                _save_evidence('06_digital_deleted', drv, base)

                # 确认 /digital-spl/{id} 已 404（软删）
                chk = _fetch_json(drv, base + '/api/v1/digital-spl/%d' % digital_id)
                results.append(('P2 GET /digital-spl/%d after delete' % digital_id, chk[:200]))
            except Exception as e:
                results.append(('P2 flow error', str(e)))

        # ───────── 深色截图 ─────────
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "dark")')
        _goto(drv, base, '/SPLMapping')
        time.sleep(2)
        _save_evidence('07_spl_page_dark', drv, base)

        # ───────── Network 证据（performance log 摘要） ─────────
        perf = _perf_requests(drv)
        net_lines = []
        for r in perf:
            if any(k in r['url'] for k in ('/spl', '/digital-spl', '/apis')):
                net_lines.append('%s %s status=%s' % (r['method'], r['url'], r['status']))
        results.append(('Network spl/digital/apis requests', net_lines[:30]))

        # ───────── 输出结论 ─────────
        print('==== INT-1325 REAL-STACK VERIFY RESULT ====')
        for k, v in results:
            print('%s: %s' % (k, v))
        print('artifacts: %s' % ARTIFACTS)

        # 浏览器 console SEVERE
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
