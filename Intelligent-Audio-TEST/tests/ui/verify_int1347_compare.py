# -*- coding: utf-8 -*-
"""INT-1347 复测项④：报告对比生成（批量勾选 2 报告 → 基于已选报告 → POST /reports/secondary-compare
→ 后端 body 解析修复后生成对比报告 + SSE 事件 → 跳转新报告页）。

环境：
- dev server http://localhost:5321（/api 代理 → docker :15000，主库 intelligent_audio_test）
- AUTH_MODE=off → dev_user('*') 放行
- 页面: /report-center → 批量对比 → 基于已选报告 → 生成对比报告 → 跳转 /report/{newId}

失败落 tests/ui/artifacts/int1347_compare/<步骤>/。
"""
import json
import os
import re
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1347_compare')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
API = 'http://127.0.0.1:15000/api/v1'

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


def _click_text_contains(drv, text, timeout=12):
    els = drv.find_elements(By.XPATH, f"//button[contains(normalize-space(.), '{text}')]")
    if not els:
        els = drv.find_elements(By.XPATH, f"//*[contains(normalize-space(.), '{text}')]")
    if not els:
        raise Exception(f'未找到含「{text}」的可点击元素')
    _js_click(drv, els[0])


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

        _goto(drv, '/report-center', wait_text='报告中心', timeout=30)
        _wait_text(drv, '豆包', timeout=60)
        body = _body_text(drv)
        check('报告中心渲染', '报告中心' in body)

        # 勾选真实数据报告 493（豆包拒识环境理解E2E）与 481（豆包拒识E2E，2026/10/13）
        sel = WebDriverWait(drv, 15).until(
            lambda d: d.find_element(By.XPATH, "//*[@role='checkbox' and contains(@aria-label, '豆包拒识环境理解E2E测试任务')]"))
        sel2 = WebDriverWait(drv, 15).until(
            lambda d: d.find_element(By.XPATH, "//*[@role='checkbox' and contains(@aria-label, '豆包拒识E2E测试任务_2026/10/13')]"))
        _js_click(drv, sel)
        _js_click(drv, sel2)
        time.sleep(1.0)
        body = _body_text(drv)
        check('批量浮条「已选择 2 个报告」', '已选择 2 个报告' in body, body[:120])
        _save_evidence('01_rows_selected', drv, _network_api_calls(drv))
        _click_text_contains(drv, '批量对比')
        _wait_text(drv, '报告对比', timeout=15)
        body = _body_text(drv)
        check('对比弹窗打开', '报告对比' in body)
        _save_evidence('02_compare_dialog', drv, _network_api_calls(drv))
        # 切到「基于已选报告」
        _click_text_contains(drv, '基于已选报告')
        time.sleep(1.0)
        body = _body_text(drv)
        check('基于已选报告 tab 显示选中报告', '已选择 2 个报告' in body, body[body.find('基于已选报告'):body.find('基于已选报告')+150] if '基于已选报告' in body else '')
        _save_evidence('03_report_tab', drv, _network_api_calls(drv))
        # 提交生成
        submit = drv.find_elements(By.XPATH, "//button[contains(normalize-space(.), '生成对比报告')]")
        check('生成对比报告按钮存在', len(submit) > 0)
        if submit:
            _js_click(drv, submit[0])
            # 等进度弹窗/toast
            time.sleep(2.0)
            body = _body_text(drv)
            _save_evidence('04_after_submit', drv, _network_api_calls(drv))
            # 等跳转 /report/{newId}（最多 180s；生成约 50-190s；完成后进度弹窗出「查看报告」需点击跳转）
            new_url = drv.current_url
            new_id = None
            for _ in range(180):
                time.sleep(1)
                new_url = drv.current_url
                m = re.search(r'/report/(\d+)', new_url)
                if m and int(m.group(1)) not in (493, 481):
                    new_id = int(m.group(1))
                    break
                # 进度弹窗完成 → 点「查看报告」触发跳转
                try:
                    btn = drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '查看报告')]")
                    if btn.is_enabled():
                        _js_click(drv, btn)
                        time.sleep(1.0)
                except Exception:
                    pass
                body = _body_text(drv)
                if '报告生成失败' in body or '生成失败' in body:
                    break
            check('POST 后跳转新报告页 /report/{id}', new_id is not None, new_url)
            if new_id:
                # 二次对比报告页：等标题/概览渲染（无任务报告专属「具体用例」区）
                _wait_text(drv, '概览', timeout=40)
                body = _body_text(drv)
                check(f'新对比报告页渲染（/report/{new_id}）', '对比' in body or '概览' in body, body[:150])
                net = _network_api_calls(drv)
                urls = [n.get('url', '') for n in net]
                check('Network 含 POST /reports/secondary-compare', any('secondary-compare' in u for u in urls), str([u for u in urls if 'secondary' in u]))
                _save_evidence('05_new_report_page', drv, net)
                # 记录新报告 id 供清理
                with open(os.path.join(ARTIFACTS, 'new_report_id.txt'), 'w', encoding='utf-8') as f:
                    f.write(str(new_id))

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
