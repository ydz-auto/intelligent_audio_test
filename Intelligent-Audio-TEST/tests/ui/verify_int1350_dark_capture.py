# -*- coding: utf-8 -*-
"""INT-1350 二轮返工：深色主题截图取证（编辑抽屉回显输出字段代码 + 评估维度页）。"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5371')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ARTIFACTS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    'tests', 'ui', 'artifacts', 'int1350_dimension_edit_dark')

USERNAME = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'
NAME = '接线测试_INT1350_dark_shot'


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
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45)
    return drv


def _body_text(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _list_items(lst):
    data = lst.get('data') or {}
    if isinstance(data, dict) and 'items' in data:
        return data['items']
    return []


def _unwrap_detail(detail):
    data = detail.get('data') or {}
    if isinstance(data, dict) and data.get('data') is not None and isinstance(data['data'], dict):
        return data['data']
    return data


def _save(drv, name):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    drv.save_screenshot(os.path.join(d, 'screenshot.png'))
    with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
        f.write(drv.page_source)


def _api(drv, method, path, body=None):
    script = '''
      const method = arguments[0], path = arguments[1], body = arguments[2];
      const token = window.localStorage.getItem('iatp:auth:token:v1') || '';
      const xhr = new XMLHttpRequest();
      xhr.open(method, '/api/v1' + path, false);
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.setRequestHeader('Authorization', 'Bearer ' + token);
      xhr.send(body ? JSON.stringify(body) : null);
      let data = null;
      try { data = JSON.parse(xhr.responseText || 'null'); } catch (e) {}
      return { status: xhr.status, data };
    '''
    return drv.execute_script(script, method, path, body)


def main():
    os.makedirs(ARTIFACTS, exist_ok=True)
    drv = _driver()
    dim_id = None
    try:
        drv.get(BASE + '/login')
        time.sleep(1.5)
        drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
        drv.get(BASE + '/login')
        WebDriverWait(drv, 20).until(lambda d: len(d.find_elements(By.ID, 'username')) > 0)
        drv.find_element(By.ID, 'username').send_keys(USERNAME)
        drv.find_element(By.ID, 'password').send_keys(PASSWORD)
        drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
        WebDriverWait(drv, 20).until(lambda d: '/login' not in d.current_url)
        time.sleep(2.0)

        # 清理遗留
        try:
            leftover = _api(drv, 'GET', f'/evaluation/dimensions?search={NAME}&per_page=100')
            for it in _list_items(leftover):
                if it.get('name') == NAME:
                    _api(drv, 'DELETE', f"/evaluation/dimensions/{it['id']}")
                    print('CLEANUP_LEFT_OVER id=', it['id'])
        except Exception as e:
            print('CLEANUP_SKIP', e)

        # 切深色主题：写 iatp:theme:v1:mode + about:blank 打断 bfcache 强刷
        drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', JSON.stringify({'state': {'mode': 'dark'}, 'version': 0}))")
        drv.get('about:blank')
        time.sleep(0.8)

        # 评估维度页（深色）
        drv.get(BASE + '/Evaluation')
        WebDriverWait(drv, 20).until(lambda d: '评估维度' in _body_text(d))
        time.sleep(1.5)
        _save(drv, '01_evaluation_page_dark')

        # 新增维度
        drv.find_element(By.XPATH, "//button[contains(., '新增维度')]").click()
        time.sleep(1.2)
        sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
        sheet.find_element(By.ID, 'dim-name').send_keys(NAME)
        time.sleep(0.3)
        tab = [t for t in sheet.find_elements(By.CSS_SELECTOR, "[role='tab']") if t.text.strip() == 'API配置']
        assert tab, 'API配置 tab 缺失'
        tab[0].click()
        time.sleep(0.8)
        add_btn = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                   if b.text.strip() == '添加字段' and b.is_displayed()]
        add_btn[0].click()
        time.sleep(0.5)
        rows = sheet.find_elements(By.CSS_SELECTOR, "input[aria-label^='输出字段代码 ']")
        rows[1].send_keys('wer')
        time.sleep(0.3)
        save_btn = [b for b in sheet.find_elements(By.TAG_NAME, 'button')
                    if b.text.strip() == '保存' and b.is_displayed()]
        drv.execute_script('arguments[0].click();', save_btn[0])
        WebDriverWait(drv, 20).until(lambda d: '评估维度添加成功' in _body_text(d))
        time.sleep(1.0)

        # 列表搜名称 → 打开编辑抽屉（深色回显取证）
        drv.get(BASE + '/Evaluation')
        time.sleep(1.5)
        search = drv.find_element(By.CSS_SELECTOR, "input[aria-label='搜索评估维度']")
        search.send_keys(NAME)
        WebDriverWait(drv, 15).until(
            lambda d: len(d.find_elements(By.CSS_SELECTOR, f"button[aria-label='编辑维度 {NAME}']")) > 0)
        drv.find_elements(By.CSS_SELECTOR, f"button[aria-label='编辑维度 {NAME}']")[0].click()
        time.sleep(1.5)
        sheet = drv.find_element(By.CSS_SELECTOR, "[data-slot='sheet-content']")
        tab = [t for t in sheet.find_elements(By.CSS_SELECTOR, "[role='tab']") if t.text.strip() == 'API配置']
        tab[0].click()
        time.sleep(1.0)
        codes = [i.get_attribute('value') for i in drv.find_elements(By.CSS_SELECTOR, "input[aria-label^='输出字段代码 ']")]
        in_codes = [i.get_attribute('value') for i in drv.find_elements(By.CSS_SELECTOR, "input[aria-label^='输入参数键名 ']")]
        print('DARK_EDIT_ECHO output=', codes, 'inputs=', in_codes)
        assert codes[0] == 'score' and 'wer' in codes, f'深色编辑回显输出字段异常：{codes}'
        assert in_codes[0] in ('asr_result', 'asr_ref'), f'深色编辑回显输入参数异常：{in_codes}'
        _save(drv, '02_edit_drawer_api_dark')

        # 清理
        lst = _api(drv, 'GET', f'/evaluation/dimensions?search={NAME}&per_page=100')
        for it in _list_items(lst):
            if it.get('name') == NAME:
                dim_id = it['id']
                _api(drv, 'DELETE', f"/evaluation/dimensions/{dim_id}")
                print('CLEANUP_DELETE id=', dim_id)
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
