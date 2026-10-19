# -*- coding: utf-8 -*-
"""INT-886 个人中心页 真实数据浏览器走查（React wiring，测试工程师验收）。

环境：
- dev server: http://localhost:5313（本 run 起，/api 代理 → 常驻 :5000）
- 常驻后端 :5000 AUTH_MODE=off → hydrateSession 以 dev_user('*') 放行
- 页面: /profile

已知 env 缺口（非本卡缺陷，运行证据里注明）：
- /auth/oauth/bindings 在 off 栈 401（oauth_bp 内部自验用户态，dev_user id=0 判未登录），
  client 全局 401→sessionExpired 会把整个页面弹回 /login —— 本脚本用 CDP fetch 覆写
  bindings 返回空列表，隔离该 env 缺口，验证其余真实数据渲染。
- /auth/oauth/providers 常驻栈 500（网关 gRPC relay 缺口），前端 rows=[] 优雅降级空态。

验收清单核对（INT-886 卡内）：
① 个人资料真实数据渲染 —— /auth/me 真实返回渲染（dev_user / user_id=0 /
   permissions=['*'] → 1 项权限 + 通配文案）；收藏计数走 GET /favorites
② 显示名编辑 —— 个人中心页按设计（13_个人中心.md §3.4）只读（后端无自助改资料
   端点）；页面无「编辑/修改」入口；显示名编辑在 IAM 用户页（INT-698 范围，已由
   test_ui_31_int698_display_name.py 实测）—— 本卡核对该只读口径
③ 浅色 + 深色 + Network 截图

失败落 tests/ui/artifacts/int886_profile/<步骤>/（截图 + page_source + console + network）。
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

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5313')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int886_profile')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

os.makedirs(ARTIFACTS, exist_ok=True)

# 覆写 bindings 响应：隔离 off 栈 /auth/oauth/bindings 401 的 env 缺口
FAKE_BINDINGS = r"""
const origFetch = window.fetch;
window.fetch = async (url, init) => {
  if (typeof url === 'string' && url.includes('/auth/oauth/bindings')) {
    return new Response(JSON.stringify({bindings: []}), {status: 200, headers: {'Content-Type':'application/json'}});
  }
  return origFetch(url, init);
};
"""


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
                if '/api/v1/' in url:
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
        # bindings 覆写（隔离 off 栈 env 缺口）
        drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FAKE_BINDINGS})

        _goto(drv, '/profile')
        WebDriverWait(drv, 25).until(
            lambda d: 'dev_user' in (d.execute_script('return document.body.textContent || ""'))
            and '个人信息' in (d.execute_script('return document.body.textContent || ""')))

        body = _body_text(drv)
        check('URL 停在 /profile（未弹回登录）', '/profile' in drv.current_url, drv.current_url)
        check('页面标题=个人中心', '个人中心' in drv.title, drv.title)
        check('身份卡真实用户名 @dev_user（/auth/me）', '@dev_user' in body)
        check('用户 ID 徽章=0（/auth/me user_id=0）', '用户 ID 0' in body)
        check('个人信息卡渲染', '账号基础信息与权限概览' in body)
        check('权限徽章=1 项权限（permissions=[*]）', '1 项权限' in body)
        check('只读说明文案', '当前页面为只读展示。如需修改用户名、邮箱或重置密码，请联系平台管理员。' in body)
        check('我的收藏格（GET /favorites 真实计数 0）', '我的收藏' in body)
        check('账号安全卡', '账号安全' in body and '第三方账号绑定' in body)
        check('快捷入口卡', '快捷入口' in body and '工作台' in body)
        # 绑定区 env 缺口 → 优雅空态
        check('绑定区空态（providers 500 env 缺口优雅降级）', '当前没有可绑定的第三方登录方式' in body)

        # 权限 Popover
        drv.find_element(By.XPATH, "//button[@aria-label='查看权限清单']").click()
        WebDriverWait(drv, 8).until(
            lambda d: '超级管理员持有全部权限（通配 *）' in d.execute_script(
                'return document.body.textContent || ""'))
        check('权限 Popover 通配文案', '超级管理员持有全部权限（通配 *）' in _body_text(drv))
        webdriver.ActionChains(drv).send_keys(Keys.ESCAPE).perform()
        time.sleep(0.4)

        # 只读：无「编辑/修改」入口
        edits = [e.text for e in drv.find_elements(By.TAG_NAME, 'button')
                 if e.text and ('编辑' in e.text or '修改' in e.text)]
        check('页面无「编辑/修改」入口（设计只读）', not edits, str(edits))

        net = _network_api_calls(drv)
        urls = [n.get('url', '') for n in net]
        check('Network 含 /auth/me', any('/auth/me' in u for u in urls))
        check('Network 含 /favorites', any('/favorites' in u for u in urls))
        check('Network 含 /auth/oauth/providers（绑定区真实请求）',
              any('/auth/oauth/providers' in u for u in urls))
        check('Network 含 /home/site（壳站点配置）', any('/home/site' in u for u in urls))
        _save_evidence('01_profile_light', drv, net)

        _set_theme(drv, 'dark')
        _save_evidence('02_profile_dark', drv, _network_api_calls(drv))
        _set_theme(drv, 'light')
        _save_evidence('01b_profile_light_after', drv, _network_api_calls(drv))

        # console SEVERE 检查（network 4xx/5xx 的 SEVERE 属 env 缺口，单独列；JS 错误才算）
        js_severe = []
        try:
            for entry in drv.get_log('browser'):
                if entry.get('level') == 'SEVERE':
                    msg = entry.get('message', '')
                    if 'Failed to load resource' not in msg and 'net::ERR' not in msg:
                        js_severe.append(msg)
        except Exception:
            pass
        check('无 JS 级 console SEVERE（网络 4xx/5xx 除外）', not js_severe, '\n'.join(js_severe[:5]))

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
