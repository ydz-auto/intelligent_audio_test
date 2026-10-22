# -*- coding: utf-8 -*-
"""INT-1294 probe: 检查真实库栈 tag/category 关联与 categories 列表是否为空。"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5396')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
SUFFIX = int(time.time()) % 100000


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.add_argument('--disable-dev-shm-usage')
    import winreg
    chrome_major = 0
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
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
    return drv


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
    drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
    drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
    WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
    time.sleep(2)
    print('login URL:', drv.current_url)


def api_call(drv, method, path, payload=None):
    body_js = ('JSON.stringify(%s)' % json.dumps(payload)) if payload is not None else 'undefined'
    return drv.execute_script('''
      const token = localStorage.getItem('iatp:auth:token:v1');
      const body = %s;
      return fetch('%s', {
        method: '%s',
        headers: {'Content-Type': 'application/json', 'Authorization': token ? 'Bearer ' + token : ''},
        body: body
      }).then(async r => {
        let d = null;
        try { d = await r.json(); } catch (e) {}
        return {status: r.status, data: d};
      });
    ''' % (body_js, path, method))


def main():
    drv = _driver()
    created = []
    try:
        login(drv)
        # 先看现有 categories
        cats = api_call(drv, 'GET', '/api/v1/tags/categories?page=1&per_page=100')
        print('CATEGORIES LIST:', json.dumps(cats, ensure_ascii=False)[:800])
        # 建分类
        cat_name = f'接线测试_PROBE分类_{SUFFIX}'
        cat = api_call(drv, 'POST', '/api/v1/tags/categories',
                       {'name': cat_name, 'description': 'probe', 'color': '#10b981'})
        print('CREATE CAT:', json.dumps(cat, ensure_ascii=False)[:400])
        cat_id = (cat.get('data') or {}).get('data', {}).get('id')
        print('CAT_ID:', cat_id)
        created.append(('cat', cat_id))
        time.sleep(1)
        # 再查 categories 是否包含新建
        cats2 = api_call(drv, 'GET', '/api/v1/tags/categories?page=1&per_page=100')
        names = [(c.get('id'), c.get('name')) for c in ((cats2.get('data') or {}).get('data') or {}).get('items', [])]
        print('CATEGORIES AFTER CREATE:', names)
        # 建标签带 category_id
        tag_name = f'接线测试_PROBE标签_{SUFFIX}'
        tag_payload = {'name': tag_name, 'description': 'probe', 'color': '#f59e0b'}
        if cat_id:
            tag_payload['category_id'] = cat_id
        tag = api_call(drv, 'POST', '/api/v1/tags', tag_payload)
        print('CREATE TAG:', json.dumps(tag, ensure_ascii=False)[:400])
        tag_id = (tag.get('data') or {}).get('data', {}).get('id')
        created.append(('tag', tag_id))
        time.sleep(1)
        # 查 tags 列表看该 tag 的 category_id
        tags = api_call(drv, 'GET', '/api/v1/tags?page=1&per_page=100')
        items = ((tags.get('data') or {}).get('data') or {}).get('items', [])
        mine = [t for t in items if t.get('name') == tag_name]
        print('MY TAG IN LIST:', json.dumps(mine, ensure_ascii=False)[:400])
        # 查单 tag
        if tag_id:
            one = api_call(drv, 'GET', '/api/v1/tags/%s' % tag_id)
            print('SINGLE TAG:', json.dumps(one, ensure_ascii=False)[:400])
    finally:
        try:
            for kind, id_ in reversed(created):
                if not id_:
                    continue
                if kind == 'cat':
                    r = api_call(drv, 'DELETE', '/api/v1/tags/categories/%s' % id_)
                else:
                    r = api_call(drv, 'DELETE', '/api/v1/tags/%s?cascade=true' % id_)
                print('CLEANUP', kind, id_, json.dumps(r, ensure_ascii=False)[:150])
        except Exception as e:
            print('cleanup err', e)
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
