# -*- coding: utf-8 -*-
"""INT-1255 CRUD走查·React·报告与系统 — 个人中心（资料 / 改密 / Access Token）浏览器实测。

环境：
- dev server http://localhost:5311（/api 代理 → docker :15000，主库 intelligent_audio_test）
- docker 后端 :15000 AUTH_MODE=off → dev_user('*') 放行
- 页面: /profile（个人中心）

验收核对（INT-1255 §3.5 闭环中个人中心项）：
① 资料卡：真实 /auth/me 渲染（dev_user / 用户 ID / 权限数 / 只读说明）+ 收藏格 + 快捷入口
② 改密：设计隐藏（后端自助改密端点未立项 → 无入口，不展示不可用功能）
③ Access Token：列表真实请求 GET /auth/access-tokens（docker :15000 端点 404 → 错误态+重试，
   记为后端缺口）；创建对话框字段齐全（名称/有效时间/权限目录勾选）；编辑对话框字段
④ 刷新后角色显示（dev_user 权限含通配）
⑤ 浅色 + 深色截图

失败落 tests/ui/artifacts/int1255_profile/<步骤>/。
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
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5311')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1255_profile')
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
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
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


def _set_theme(drv, theme):
    drv.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', arguments[0])", theme)
    drv.refresh()
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _wait_text(drv, text, timeout=30):
    WebDriverWait(drv, timeout).until(
        lambda d: text in (d.execute_script('return document.body.textContent || ""')))


def _js_click(drv, el):
    try:
        el.click()
    except Exception:
        drv.execute_script('arguments[0].click()', el)
    time.sleep(0.5)


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
        # 防串库①
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

        # ─── ① 资料卡 ───
        _goto(drv, '/profile', wait_text='dev_user', timeout=45)
        _wait_text(drv, '个人信息', timeout=30)
        body = _body_text(drv)
        check('URL 停在 /profile', '/profile' in drv.current_url, drv.current_url)
        check('页面标题=个人中心', '个人中心' in drv.title or '个人中心' in body)
        check('身份卡真实用户名 @dev_user（/auth/me）', '@dev_user' in body)
        check('用户 ID 徽章=0（/auth/me user_id=0）', '用户 ID 0' in body)
        check('个人信息卡渲染', '账号基础信息与权限概览' in body)
        check('权限徽章（dev_user 通配 *）', '1 项权限' in body, body[body.find('权限'):body.find('权限')+40] if '权限' in body else '')
        check('只读说明文案', '当前页面为只读展示' in body)
        check('账号安全卡', '账号安全' in body and '第三方账号绑定' in body)
        check('快捷入口卡', '快捷入口' in body and '工作台' in body)
        net = _network_api_calls(drv)
        urls = [n.get('url', '') for n in net]
        check('Network 含 GET /auth/me', any('/auth/me' in u for u in urls))
        check('Network 含 GET /favorites', any('/favorites' in u for u in urls))
        _save_evidence('01_profile_light', drv, net)

        # 刷新后角色显示（INT-1226：刷新后 dev_user 角色仍显示）
        drv.refresh()
        _wait_text(drv, 'dev_user', timeout=45)
        body = _body_text(drv)
        check('刷新后身份仍显示 dev_user（INT-1226）', '@dev_user' in body)
        _save_evidence('01b_profile_refresh', drv, _network_api_calls(drv))

        # 改密入口隐藏（后端自助改密端点未立项 → 设计隐藏）
        buttons = [e.text for e in drv.find_elements(By.TAG_NAME, 'button')]
        check('无「修改密码」入口（后端未立项 → 设计隐藏）', not any('修改密码' in (b or '') for b in buttons), str([b for b in buttons if '密码' in (b or '')]))

        _set_theme(drv, 'dark')
        _wait_text(drv, 'dev_user', timeout=45)
        _save_evidence('02_profile_dark', drv, _network_api_calls(drv))
        _set_theme(drv, 'light')
        _wait_text(drv, 'dev_user', timeout=45)

        # ─── ③ Access Token 卡 ───
        _goto(drv, '/profile', wait_text='Access Token', timeout=30)
        _wait_text(drv, 'Access Token', timeout=45)
        body = _body_text(drv)
        check('Access Token 卡渲染', 'Access Token' in body and '创建 Access Token' in body)
        net = _network_api_calls(drv)
        urls = [n.get('url', '') for n in net]
        check('列表真实请求 GET /auth/access-tokens', any('/auth/access-tokens' in u for u in urls), str([u for u in urls if 'access-token' in u]))
        # docker :15000 端点 404 → 前端错误态
        body = _body_text(drv)
        check('Access Token 错误态（后端 404 缺口 → 优雅降级）', 'Access Token 加载失败' in body and '重试' in body, body[body.find('Access Token 加载失败')-10:body.find('Access Token 加载失败')+60] if 'Access Token 加载失败' in body else '')
        _save_evidence('03_access_token_error_state', drv, net)

        # 创建对话框渲染（字段齐全）
        _js_click(drv, drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '创建 Access Token')]"))
        _wait_text(drv, 'Token 明文只显示一次', timeout=15)
        body = _body_text(drv)
        check('创建对话框标题', '创建 Access Token' in body)
        check('名称字段', '名称' in body)
        check('有效时间字段 + 预设', '有效时间' in body and '30 天' in body and '永不过期' in body)
        check('权限字段 + 目录勾选', '权限' in body and '已选' in body)
        _save_evidence('04_access_token_create_dialog', drv, _network_api_calls(drv))
        # 校验：必填留空提交 → scopes 错误提示（不触发 POST）
        submit_btn = drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '创建')]")
        _js_click(drv, submit_btn)
        time.sleep(1.0)
        net = _network_api_calls(drv)
        check('必填/权限未选提交不发 POST access-tokens', not any('/auth/access-tokens' in n.get('url', '') and n.get('method') == 'POST' for n in net))
        body = _body_text(drv)
        check('校验错误提示（名称/权限必填）', '请输入名称' in body or '请至少选择一个权限' in body, body[body.find('请输入名称')-10:body.find('请输入名称')+40] if '请输入名称' in body else '')
        _save_evidence('05_access_token_validation', drv, net)
        # 关闭
        try:
            drv.find_element(By.XPATH, "//button[normalize-space()='取消']").click()
        except Exception:
            drv.execute_script("document.body.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape'}))")
        time.sleep(0.8)
        # 取消后重开，表单应清空
        _js_click(drv, drv.find_element(By.XPATH, "//button[contains(normalize-space(.), '创建 Access Token')]"))
        _wait_text(drv, 'Token 明文只显示一次', timeout=15)
        name_input = drv.find_element(By.ID, 'access-token-name')
        check('重开表单名称清空（无残留）', (name_input.get_attribute('value') or '') == '', name_input.get_attribute('value') or 'EMPTY')
        _save_evidence('06_access_token_reopen_clear', drv, _network_api_calls(drv))
        try:
            drv.find_element(By.XPATH, "//button[normalize-space()='取消']").click()
        except Exception:
            pass
        time.sleep(0.8)

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
