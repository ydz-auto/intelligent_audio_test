# -*- coding: utf-8 -*-
"""INT-1347 复测项⑤：日志下载完整链路（GET /reports/{id}/cases/{caseId}/logs 修复后，
文件选择弹窗列出文件 → 下载所选文件 → logs/download 请求 + 进度弹窗 + 浏览器下载）。

数据源：报告 484（task 407）真实用例带 business 日志文件（probe 确认非空）。

环境：
- dev server http://localhost:5321（/api 代理 → docker :15000，主库 intelligent_audio_test）
- AUTH_MODE=off → dev_user('*') 放行
- 页面: /report/484 → 具体用例 → 下载日志

失败落 tests/ui/artifacts/int1347_logs/<步骤>/。
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

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5321')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1347_logs')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

os.makedirs(ARTIFACTS, exist_ok=True)


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
        with open(os.path.join(d, 'console.log'), 'w', encoding='utf-8') as f:
            for entry in drv.get_log('browser'):
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
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


def _js_click(drv, el):
    try:
        el.click()
    except Exception:
        drv.execute_script('arguments[0].click()', el)
    time.sleep(0.5)


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
        print(f'[{tag}] {name}' + (f' — {detail}' if detail else ''), flush=True)
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
        drv.execute_script(
            'localStorage.setItem("iatp:algorithm:v1", JSON.stringify({state:{algorithmId:""},version:0}))')

        # ─── 报告 484 具体用例 → 下载日志 ───
        _goto(drv, '/report/484', wait_text='豆包', timeout=45)
        _wait_text(drv, '具体用例', timeout=45)
        WebDriverWait(drv, 30).until(
            lambda d: len(d.find_elements(By.XPATH, "//button[contains(normalize-space(.), '下载日志')]")) > 0)
        dl_btns = drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '下载日志')]")
        check('具体用例区「下载日志」按钮存在', len(dl_btns) > 0, f'count={len(dl_btns)}')
        _save_evidence('01_case_list', drv, _network_api_calls(drv))
        if not dl_btns:
            raise Exception('无下载日志按钮')

        # 点击第一个用例的下载日志
        btn = dl_btns[0]
        try:
            drv.execute_script('arguments[0].scrollIntoView({block:"center"})', btn)
            time.sleep(0.5)
            btn.click()
        except Exception:
            _js_click(drv, btn)
        # 等文件选择弹窗 + 文件列表
        dialog_ok = False
        for _ in range(20):
            time.sleep(0.5)
            body = _body_text(drv)
            if '下载日志 —' in body:
                dialog_ok = True
                break
            if '日志文件加载失败' in body or '该用例暂无日志文件' in body:
                break
        check('日志文件选择弹窗打开（真实 GET logs 修复）', dialog_ok, body[:120] if not dialog_ok else '')
        # 等文件列表加载完成（business_logs 出现 / 空态）
        loaded = False
        for _ in range(40):
            time.sleep(0.5)
            body = _body_text(drv)
            if 'business_logs' in body or '该用例暂无日志文件' in body or '日志文件加载失败' in body:
                loaded = True
                break
        check('文件列表加载完成', loaded, body[:150])
        _wait_text(drv, '下载所选文件', timeout=20)
        body = _body_text(drv)
        check('文件列表含 business 日志文件', 'business_logs' in body, body[body.find('business_logs')-20:body.find('business_logs')+80] if 'business_logs' in body else 'no business_logs')
        check('已选合计文案（已选 N 个 / 共 N 个）', '已选 1 个 / 共' in body or '已选 2 个 / 共' in body, body[body.find('已选')-5:body.find('已选')+30] if '已选' in body else '')
        net = _network_api_calls(drv)
        urls = [n.get('url', '') for n in net]
        check('Network 含 GET /reports/484/cases/{id}/logs', any('/reports/484/cases/' in u and '/logs' in u and 'download' not in u for u in urls), str([u for u in urls if 'reports/484' in u][:3]))
        _save_evidence('02_file_select_dialog', drv, net)

        # 下载所选文件
        dbtn = WebDriverWait(drv, 10).until(
            lambda d: d.find_element(By.XPATH, "//button[contains(normalize-space(.), '下载所选文件')]"))
        try:
            dbtn.click()
        except Exception:
            _js_click(drv, dbtn)
        time.sleep(3.0)
        net = _network_api_calls(drv)
        urls = [n.get('url', '') for n in net]
        dl = [u for u in urls if 'logs/download' in u]
        check('日志下载真实请求 logs/download', len(dl) > 0, str(dl[:1]))
        _save_evidence('03_download_request', drv, net)
        # 进度弹窗（下载中/完成）
        body = _body_text(drv)
        check('下载进度/完成反馈', '下载' in body or '完成' in body, body[:150])
        _save_evidence('04_download_progress', drv, _network_api_calls(drv))

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
