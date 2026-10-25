# -*- coding: utf-8 -*-
"""获取 token 存盘（跨脚本复用）+ 创建 接线测试 在线设备/API 探针。"""
import json, os, time
import urllib.request
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

BASE = 'http://localhost:15173'
API = 'http://127.0.0.1:15000'
TOKEN_FILE = 'tests/ui/artifacts/int1486/token.txt'
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    o = Options(); o.binary_location = CHROME_BINARY
    for a in ['--headless=new', '--window-size=1600,1000', '--disable-gpu', '--no-sandbox', '--lang=zh-CN',
              '--disable-dev-shm-usage', '--no-first-run', '--no-default-browser-check']:
        o.add_argument(a)
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        for v in os.listdir(cache):
            exe = os.path.join(cache, v, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int([x for x in v.split('.') if x.isdigit()][0]) == major:
                        path = exe
                except (ValueError, IndexError):
                    continue
    return webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())


def req(method, path, token, body=None):
    data = json.dumps(body).encode('utf-8') if body is not None else None
    r = urllib.request.Request(API + path, data=data, method=method,
                               headers={'Authorization': 'Bearer ' + token,
                                        'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            return resp.status, json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode('utf-8', 'replace')[:400]


def main():
    drv = _driver()
    try:
        drv.get(BASE + '/login')
        WebDriverWait(drv, 25).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(1.5)
        try:
            u = WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, 'username')))
            u.send_keys('接线测试_admin')
            drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
            drv.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
            WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)
        except Exception:
            pass
        time.sleep(2)
        token = drv.execute_script("return localStorage.getItem('iatp:auth:token:v1')")
        print('token?', bool(token))
        if token:
            with open(TOKEN_FILE, 'w') as f:
                f.write(token)
    finally:
        drv.quit()

    token = open(TOKEN_FILE).read().strip()
    suffix = str(int(time.time()))[-6:]
    # 在线测试设备
    body = {'name': f'接线测试_INT1486_设备_{suffix}', 'model': 'probe', 'type': 'physical',
            'system': 'Android', 'system_version': '14', 'status': 'online',
            'supported_algorithms': ['voice_llm']}
    print('CREATE device:', req('POST', '/api/v1/test-devices', token, body))
    st, d = req('GET', '/api/v1/test-devices?per_page=1000', token)
    items = d.get('data', d).get('items', []) if isinstance(d, dict) else []
    dev = [x for x in items if x['name'] == body['name']]
    print('READBACK device:', json.dumps(dev, ensure_ascii=False)[:500])
    # 在线 API
    ab = {'name': f'接线测试_INT1486_APIX_{suffix}', 'algorithm_type': '小艺语音大模型',
          'default_max_process': 5, 'description': 'probe',
          'endpoints': [{'endpoint': 'https://example.test/probe', 'name': 'probe', 'priority': 1,
                         'max_process': 1, 'max_timeout': 30, 'max_audio_duration': 60, 'status': 'online'}]}
    print('CREATE api:', req('POST', '/api/v1/apis', token, ab))
    st, d = req('GET', '/api/v1/apis?per_page=1000', token)
    items = d.get('data', d).get('items', []) if isinstance(d, dict) else []
    print('READBACK apis:', json.dumps([{'id': x['id'], 'name': x['name'], 'status': x.get('status')} for x in items], ensure_ascii=False))
    print('SUFFIX', suffix)


if __name__ == '__main__':
    main()
