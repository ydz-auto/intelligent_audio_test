# -*- coding: utf-8 -*-
"""INT-1325 P2 定向证据：捕获删除默认 RMS-SPL 时前端发出的 set-default(null) 与 DELETE 请求。
验证 handleConfirmDeleteDigital 修复路径（70709ca6）：删除默认映射前先清 API 默认指针再删。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1325_retest')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
UNIQ = '接线测试_INT1325_验B'
BASE = 'http://localhost:5325'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
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


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 25).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _login(drv):
    _goto(drv, '/login')
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/login')
    drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
    time.sleep(2.0)


def _fetch_json(drv, url):
    return drv.execute_script(
        'return (async () => {'
        '  const t = (() => { try { return localStorage.getItem("iatp:auth:token:v1") } catch(e){ return "" } })();'
        '  const r = await fetch(arguments[0], {headers: {"Authorization": "Bearer " + t}});'
        '  const text = await r.text();'
        '  return JSON.stringify({status: r.status, body: text});'
        '})()', url)


def _save(name, drv):
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv.save_screenshot(os.path.join(ARTIFACTS, name + '.png'))


def main():
    drv = _driver()
    results = []
    try:
        drv.set_page_load_timeout(60)
        _login(drv)
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "light")')
        _goto(drv, '/SPLMapping')
        time.sleep(2)

        # 切数字域
        drv.find_element(By.XPATH, "//*[@role='tab'][contains(., 'API/Realtime RMS-SPL')]").click()
        time.sleep(1.5)

        # 新建 RMS-SPL 映射
        drv.find_element(By.XPATH, "//button[contains(., '添加 RMS-SPL 映射')]").click()
        WebDriverWait(drv, 10).until(
            lambda d: d.find_elements(By.XPATH, "//*[contains(@role,'dialog')]"))
        time.sleep(1.0)
        n = drv.find_element(By.XPATH, "//input[@aria-label='映射名称']")
        n.clear()
        n.send_keys(UNIQ + '_RMS')
        drv.execute_script(
            "var t = document.querySelector('button[aria-label=\"关联被测 API\"]'); if(t) t.click();")
        time.sleep(1.0)
        opts = drv.find_elements(By.XPATH, "//*[@role='option']")
        if opts:
            opts[0].click()
        else:
            drv.execute_script(
                "var opts = Array.from(document.querySelectorAll('[role=option]'));"
                "if(opts.length) opts[0].click();")
        time.sleep(0.6)
        drv.find_element(By.XPATH, "//button[contains(., '保存')]").click()
        time.sleep(3.0)

        # 找新行 id / api
        j = json.loads(_fetch_json(drv, BASE + '/api/v1/digital-spl?page=1&per_page=100'))
        b = json.loads(j.get('body') or '{}')
        items = b.get('data', {}).get('items', b.get('items', [])) if isinstance(b, dict) else []
        dm = None
        for it in items:
            if it.get('name') == UNIQ + '_RMS':
                dm = it
                break
        if not dm:
            results.append(('create', 'FAILED - record not found'))
            print(json.dumps(results, ensure_ascii=False))
            return
        digital_id = dm['id']
        api_id = dm['api_id']
        results.append(('created', {'id': digital_id, 'api_id': api_id}))

        # 设默认
        btn = drv.find_element(By.XPATH, "//button[@aria-label='映射 %s 的操作']" % (UNIQ + '_RMS'))
        drv.execute_script('arguments[0].click()', btn)
        WebDriverWait(drv, 5).until(
            lambda d: d.find_elements(By.XPATH, "//*[@role='menuitem']"))
        for it in drv.find_elements(By.XPATH, "//*[@role='menuitem']"):
            if '设默认' in it.text:
                drv.execute_script('arguments[0].click()', it)
                break
        time.sleep(2.5)
        j2 = json.loads(_fetch_json(drv, BASE + '/api/v1/apis?page=1&per_page=100'))
        b2 = json.loads(j2.get('body') or '{}')
        items2 = b2.get('data', {}).get('items', b2.get('items', [])) if isinstance(b2, dict) else []
        ptr_before = None
        for it in items2:
            if it.get('id') == api_id:
                ptr_before = it.get('rms_spl_mapping_id')
        results.append(('ptr_before_delete', ptr_before))

        # 挂 fetch 钩子捕获 DELETE + set-default
        drv.execute_script('window.__mut = []')
        drv.execute_script(
            'const orig = window.fetch;'
            'window.fetch = function(url, opts){'
            '  try { if (opts && opts.method && (opts.method === "DELETE" || String(opts.method) === "POST")) {'
            '    const u = String(url);'
            '    if (u.includes("/digital-spl") || u.includes("/apis")) {'
            '      window.__mut.push({method: opts.method, url: u, body: opts.body || ""});'
            '    }'
            '  } } catch(e){}'
            '  return orig.apply(this, arguments);'
            '};')

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
        _save('08_p2_delete_confirm', drv)
        for it in drv.find_elements(By.XPATH, "//button"):
            if it.text.strip() == '删除':
                drv.execute_script('arguments[0].click()', it)
                break
        time.sleep(3.0)

        captured = drv.execute_script('return window.__mut')
        results.append(('captured_mutations', captured))

        # 删除后核对
        j3 = json.loads(_fetch_json(drv, BASE + '/api/v1/apis?page=1&per_page=100'))
        b3 = json.loads(j3.get('body') or '{}')
        items3 = b3.get('data', {}).get('items', b3.get('items', [])) if isinstance(b3, dict) else []
        ptr_after = None
        for it in items3:
            if it.get('id') == api_id:
                ptr_after = it.get('rms_spl_mapping_id')
        results.append(('ptr_after_delete', ptr_after))
        chk = _fetch_json(drv, BASE + '/api/v1/digital-spl/%d' % digital_id)
        results.append(('get_digital_after_delete', json.loads(chk).get('status')))

        # 深色
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "dark")')
        _goto(drv, '/SPLMapping')
        time.sleep(2)
        _save('09_spl_page_dark_after_p2', drv)

        print('==== INT-1325 P2 DIRECTED CAPTURE ====')
        for k, v in results:
            print('%s: %s' % (k, json.dumps(v, ensure_ascii=False) if not isinstance(v, str) else v))
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
