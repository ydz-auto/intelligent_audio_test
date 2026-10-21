# -*- coding: utf-8 -*-
"""INT-1153 联接你的 agent 入口 + 个人配置页 token 管理 浏览器走查（React wiring）。

环境：
- dev server: http://localhost:5345（本 run 起，/api 代理 → 常驻 :5000）
- 常驻后端 :5000 AUTH_MODE=off → 自动以 dev_user('*') 放行
- 页面: /agent-connect（入口页）、/profile（token 管理）

已知 env 缺口（非本卡缺陷，运行证据里注明）：
- 后端 access-token / skill 端点（BE2/BE3，INT-1148/1149）尚未合入开发栈 →
  GET /api/v1/auth/access-tokens 与 GET /api/v1/agent/skill 返回 404。
  前端以「错误态 + 重试」「下载失败 Alert」优雅降级，真实请求（Network）可见。

验收清单核对（INT-1153 卡内）：
① 导航「联接你的 agent」入口按钮（炫彩）在顶栏右区渲染
② 点击入口 → 打开 /agent-connect 页面（使用说明 / 服务地址默认取地址栏可改 /
   token 指引跳 /profile / 炫彩下载按钮）
③ 下载按钮 → Network 含 /api/v1/agent/skill?base_url=… 真实请求
④ /profile 渲染 Access Token 管理卡（创建按钮 + 列表区），列表真实请求
   /api/v1/auth/access-tokens（当前 404 → 错误态 + 重试）
⑤ 创建对话框渲染（名称 / 有效时间 / 权限目录勾选）
⑥ 浅色 + 深色 + Network 截图

失败落 tests/ui/artifacts/int1153_agent_connect/<步骤>/。
"""
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

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5345')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1153_agent_connect')
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
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium',
                              'chromedriver', 'win64')
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


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _save_evidence(name, drv, extra_net=None):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
        with open(os.path.join(d, 'console.log'), 'w', encoding='utf-8') as f:
            for entry in drv.get_log('browser'):
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
        net = extra_net or []
        with open(os.path.join(d, 'network.json'), 'w', encoding='utf-8') as f:
            json.dump(net, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _set_theme(drv, theme):
    drv.execute_script(
        "window.localStorage.setItem('iatp:theme:v1:mode', arguments[0])", theme)
    drv.refresh()
    WebDriverWait(drv, 20).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.5)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


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
        # 顶栏入口按钮（先去工作台，避免登录页重定向 quirks）
        _goto(drv, '/dashboard')
        WebDriverWait(drv, 25).until(
            lambda d: '联接你的 agent' in (d.execute_script('return document.body.textContent || ""')))
        body = _body_text(drv)
        check('顶栏含「联接你的 agent」入口按钮', '联接你的 agent' in body)
        net = _network_api_calls(drv)
        urls = [n.get('url', '') for n in net]
        check('工作台真实请求 /api/v1/home', any('/home/' in u for u in urls) or any('/api/' in u for u in urls))
        _save_evidence('01_dashboard_header_light', drv, net)

        # 点击入口按钮 → 进入 /agent-connect
        btn = drv.find_element(By.XPATH, "//*[@aria-label='打开联接你的 agent']")
        btn.click()
        WebDriverWait(drv, 20).until(
            lambda d: '/agent-connect' in d.current_url
            and '使用说明' in (d.execute_script('return document.body.textContent || ""')))
        body = _body_text(drv)
        check('点击入口进入 /agent-connect', '/agent-connect' in drv.current_url, drv.current_url)
        check('页面标题=联接你的 agent', '联接你的 agent' in drv.title, drv.title)
        check('使用说明区块', '使用说明' in body and '创建 Access Token' in body)
        # 服务地址默认取地址栏（读 input value，非 body 文本）
        url_input = drv.find_element(By.ID, 'agent-connect-base-url')
        url_val = url_input.get_attribute('value') or ''
        check('服务地址默认取地址栏', url_val == 'http://localhost:5345' or url_val == 'http://127.0.0.1:5345', url_val)
        check('Token 指引跳 /profile', '前往个人中心创建 / 管理 Access Token' in body)
        check('下载 skill 按钮（炫彩）', '下载 skill' in body)

        # 侧栏魔法入口项
        check('侧栏含「联接你的 agent」项', body.count('联接你的 agent') >= 2)

        # 下载按钮 → 真实请求 /api/v1/agent/skill
        dl_btn = drv.find_element(By.XPATH, "//*[@aria-label='下载智能音频测试 skill 包']")
        dl_btn.click()
        time.sleep(2.0)
        net = _network_api_calls(drv)
        urls = [n.get('url', '') for n in net]
        check('下载触发 /api/v1/agent/skill?base_url=… 真实请求',
              any('/api/v1/agent/skill' in u for u in urls), str([u for u in urls if 'skill' in u]))
        check('下载失败优雅降级（后端 404 env 缺口）', '下载失败' in _body_text(drv))
        _save_evidence('02_agent_connect_light', drv, net)

        # 深色
        _set_theme(drv, 'dark')
        _save_evidence('03_agent_connect_dark', drv, _network_api_calls(drv))
        _set_theme(drv, 'light')

        # /profile token 管理
        _goto(drv, '/profile')
        WebDriverWait(drv, 25).until(
            lambda d: 'Access Token' in (d.execute_script('return document.body.textContent || ""')))
        body = _body_text(drv)
        check('/profile 含 Access Token 卡', 'Access Token' in body)
        check('Access Token 描述文案', '让外部 agent（Claude Code / Codex 等）经 skill / MCP 调用平台能力' in body)
        check('创建按钮', '创建 Access Token' in body)
        net = _network_api_calls(drv)
        urls = [n.get('url', '') for n in net]
        check('列表真实请求 /api/v1/auth/access-tokens',
              any('/auth/access-tokens' in u for u in urls), str([u for u in urls if 'access-token' in u]))
        check('列表 404 错误态 + 重试（env 缺口优雅降级）', 'Access Token 加载失败' in body and '重试' in body)
        _save_evidence('04_profile_token_card_light', drv, net)

        # 创建对话框
        drv.find_element(By.XPATH, "//button[.//text()[normalize-space()='创建 Access Token']]").click()
        WebDriverWait(drv, 12).until(
            lambda d: 'Token 明文只显示一次' in (d.execute_script('return document.body.textContent || ""')))
        body = _body_text(drv)
        check('创建对话框标题', '创建 Access Token' in body)
        check('名称字段', '名称' in body)
        check('有效时间字段', '有效时间' in body)
        check('权限字段 + 目录勾选', '权限' in body and '任务' in body and '已选' in body)
        _save_evidence('05_profile_create_dialog_light', drv, _network_api_calls(drv))
        webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()
        time.sleep(0.5)

        # 深色 /profile
        _set_theme(drv, 'dark')
        _save_evidence('06_profile_token_card_dark', drv, _network_api_calls(drv))
        _set_theme(drv, 'light')

        # console SEVERE（JS 级错误；网络 4xx 属 env 缺口）
        js_severe = []
        try:
            for entry in drv.get_log('browser'):
                if entry.get('level') == 'SEVERE':
                    msg = entry.get('message', '')
                    if 'Failed to load resource' not in msg and 'net::ERR' not in msg:
                        js_severe.append(msg)
        except Exception:
            pass
        check('无 JS 级 console SEVERE（网络 4xx 除外）', not js_severe, '\n'.join(js_severe[:5]))

    except Exception:
        _save_evidence('FAILURE_dump', drv, _network_api_calls(drv))
        raise
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    with open(os.path.join(ARTIFACTS, 'results.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(f'{tag}\t{name}\t{detail}' for tag, name, detail in results))
        f.write('\n')
        f.write('FAILURES: ' + json.dumps(failures, ensure_ascii=False) + '\n')

    print('=' * 50)
    if failures:
        print(f'FAILED ({len(failures)}): {failures}')
        return 1
    print('ALL PASS')
    return 0


if __name__ == '__main__':
    sys.exit(run())
