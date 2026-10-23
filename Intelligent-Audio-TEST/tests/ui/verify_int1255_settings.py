# -*- coding: utf-8 -*-
"""INT-1255 CRUD走查·React·报告与系统 — 系统设置六域渲染核验。

环境：
- dev server http://localhost:5311（/api 代理 → docker :15000，主库 intelligent_audio_test）
- AUTH_MODE=off → dev_user('*') 放行
- 页面: /system-settings/<site|auth|appearance|security|operations>/<section>

验收：六域侧栏 + 各域默认分区渲染 + 对应真实接口请求。
"""
import json
import os
import sys
import time
import urllib.request

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5311')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1255_settings')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
API = 'http://127.0.0.1:15000/api/v1'

os.makedirs(ARTIFACTS, exist_ok=True)

DOMAINS = [
    ('site', '站点设置', '站点信息', ['/home/site']),
    ('iam', '用户与权限', '用户管理', ['/auth/users', '/auth/roles']),
    ('auth', '认证设置', '认证方式', ['/auth/mode', '/auth/oauth/providers']),
    ('appearance', '外观与主题', '外观预设', ['/option/']),
    ('security', '安全设置', '访问控制', ['/auth/roles', '/auth/users']),
    ('operations', '运维设置', '日志运维', ['/logs', '/logs/refresh']),
]


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
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
    drv.set_page_load_timeout(60)
    return drv


def _goto(drv, path, wait_text=None, timeout=30):
    drv.get(BASE + path)
    WebDriverWait(drv, timeout).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)
    if wait_text:
        WebDriverWait(drv, timeout).until(
            lambda d: wait_text in (d.execute_script('return document.body.textContent || ""')))


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _save_evidence(name, drv, net=None):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'network.json'), 'w', encoding='utf-8') as f:
            json.dump(net or [], f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _network_api_calls(drv):
    out = []
    try:
        for entry in drv.get_log('performance'):
            msg = json.loads(entry['message'])
            inner = msg.get('message', {})
            if inner.get('method') == 'Network.requestWillBeSent':
                p = inner.get('params', {})
                url = p.get('request', {}).get('url', '')
                if '/api/' in url:
                    req = p.get('request', {})
                    out.append({'url': url, 'method': req.get('method'),
                                'postData': req.get('postData')})
    except Exception as e:
        out.append({'error': str(e)})
    return out


def _wait_text(drv, text, timeout=30):
    WebDriverWait(drv, timeout).until(
        lambda d: text in (d.execute_script('return document.body.textContent || ""')))


def run():
    drv = _driver()
    failures = []
    results = []

    def check(name, cond, detail=''):
        tag = 'PASS' if cond else 'FAIL'
        results.append((tag, name, detail))
        print(f'[{tag}] {name}' + (f' — {detail}' if detail else ''))
        if not cond:
            failures.append(name)

    try:
        health = None
        for _ in range(3):
            try:
                with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=20) as r:
                    health = json.loads(r.read().decode('utf-8'))
                break
            except Exception as e:
                health = {'error': str(e)}
                time.sleep(2)
        check('防串库① docker :15000 database=intelligent_audio_test', health.get('database') == 'intelligent_audio_test', str(health))

        _goto(drv, '/dashboard', wait_text='工作台', timeout=30)
        drv.execute_script('try { window.localStorage.clear() } catch(e) {}')

        # 侧栏六域可见
        _goto(drv, '/system-settings/site/info', wait_text='站点信息', timeout=30)
        body = _body_text(drv)
        check('侧栏六域标题齐', all(d[1] in body for d in DOMAINS), str([d[1] for d in DOMAINS if d[1] not in body]))

        for dom_id, dom_title, section_title, api_frags in DOMAINS:
            path = f'/system-settings/{dom_id}'
            try:
                drv.get(BASE + path)
                WebDriverWait(drv, 25).until(
                    lambda d: d.execute_script('return document.readyState') == 'complete')
                time.sleep(2.0)
                body = _body_text(drv)
                net = _network_api_calls(drv)
                urls = [n.get('url', '') for n in net]
                check(f'域 {dom_id} 标题渲染「{dom_title}」', dom_title in body)
                matched = [a for a in api_frags if any(a in u for u in urls)]
                check(f'域 {dom_id} 真实接口请求 {api_frags}', len(matched) > 0 or dom_id == 'operations' and matched, str([u for u in urls if 'api' in u][:2]))
                _save_evidence(f'domain_{dom_id}', drv, net)
            except Exception as e:
                check(f'域 {dom_id} 加载', False, str(e))

        # 防串库②
        for _ in range(3):
            try:
                with urllib.request.urlopen('http://127.0.0.1:15000/health', timeout=20) as r:
                    health2 = json.loads(r.read().decode('utf-8'))
                break
            except Exception as e:
                health2 = {'error': str(e)}
                time.sleep(2)
        check('防串库② docker :15000 database=intelligent_audio_test', health2.get('database') == 'intelligent_audio_test', str(health2))

    except Exception:
        _save_evidence('FAILURE_dump', drv, _network_api_calls(drv))
        import traceback
        traceback.print_exc()
        failures.append('脚本异常')
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    with open(os.path.join(ARTIFACTS, 'results.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(f'{tag}\t{name}\t{detail}' for tag, name, detail in results))
        f.write('\n')
        f.write('FAILURES: ' + json.dumps(failures, ensure_ascii=False) + '\n')

    print('=' * 60)
    print(f'PASS {sum(1 for t, _, _ in results if t == "PASS")} / {len(results)}')
    if failures:
        print(f'FAILED ({len(failures)}): {failures}')
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(run())
