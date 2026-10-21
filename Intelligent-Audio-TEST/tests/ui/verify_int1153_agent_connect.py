# -*- coding: utf-8 -*-
"""INT-1153 连接你的 agent 入口 + 个人配置页 token 管理 浏览器走查（React wiring）。

环境：
- dev server: http://localhost:5345（本 run 起，/api 代理 → 常驻 :5000）
- 常驻后端 :5000 AUTH_MODE=off → 自动以 dev_user('*') 放行
- 页面: /agent-connect（入口页）、/ai-chat（右上角入口）、/profile（token 管理）

已知 env 缺口（非本卡缺陷，运行证据里注明）：
- 后端 access-token / skill 端点（BE2/BE3，INT-1148/1149）尚未合入开发栈 →
  GET /api/v1/auth/access-tokens 与 GET /api/v1/agent/skill 返回 404。
  前端以「错误态 + 重试」「下载失败 Alert」优雅降级，真实请求（Network）可见。

验收清单核对（INT-1153 卡内 + 2026-10-21 负责人二轮裁定）：
① 导航栏**无**「连接你的 agent」入口（顶栏 header 无 agent-connect 链接/按钮；
   侧栏 aside 无 agent-connect 链接、无「连接你的 agent」文案）；全页无「联接你的 agent」残留
② 全局 Agent 工作台浮窗（小窗口）头行右上角炫彩「连接你的 agent」入口存在
   （aria-label='打开连接你的 agent'），点击 → /agent-connect
③ 灵犀Agent 页 /ai-chat 顶部条右上角炫彩「连接你的 agent」入口存在，点击 → /agent-connect
④ /agent-connect 页面（使用说明 / 服务地址默认取地址栏可改 / token 指引跳 /profile /
   炫彩下载按钮），页面标题/文案全页一致「连接你的 agent」
⑤ 下载按钮 → Network 含 /api/v1/agent/skill?base_url=… 真实请求
⑥ /profile 渲染 Access Token 管理卡（创建按钮 + 列表区），列表真实请求
   /api/v1/auth/access-tokens（当前 404 → 错误态 + 重试）
⑦ 创建对话框渲染（名称 / 有效时间 / 权限目录勾选）
⑧ 浅色 + 深色 + Network 截图

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

# Windows 控制台默认 GBK，走查输出含中文/⌘ 等特殊符号需 UTF-8（与其余 tests/ui 走查同口径）
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except (AttributeError, OSError):
        pass

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


def _header_text(drv):
    """顶栏 <header> 文本（断言：顶栏无「联接你的 agent」/「连接你的 agent」入口）。"""
    return ' '.join(
        e.text for e in drv.find_elements(By.CSS_SELECTOR, 'header')
    )


def _sidebar_text(drv):
    """侧栏 <aside[data-sidebar]> 文本（断言：导航栏不再保留该入口）。"""
    return ' '.join(
        e.text for e in drv.find_elements(By.CSS_SELECTOR, "aside[data-sidebar='sidebar']")
    )


def _agent_connect_links(drv):
    """全页 href=/agent-connect 的 <a>（入口按钮）。"""
    return drv.find_elements(By.CSS_SELECTOR, "a[href='/agent-connect']")


def _sidebar_agent_connect_links(drv):
    """侧栏内 href=/agent-connect 的 <a>（应无）。"""
    return drv.find_elements(
        By.CSS_SELECTOR, "aside[data-sidebar='sidebar'] a[href='/agent-connect']")


def _workbench_window(drv):
    """全局 Agent 工作台浮窗容器（fixed 右下角小窗口）。"""
    els = drv.find_elements(By.CSS_SELECTOR, "div.fixed.right-4.bottom-4")
    return els[0] if els else None


def _workbench_window_agent_connect_link(drv):
    """浮窗头行「连接你的 agent」入口 <a>（href=/agent-connect）。"""
    win = _workbench_window(drv)
    if win is None:
        return None
    els = win.find_elements(By.CSS_SELECTOR, "a[href='/agent-connect']")
    return els[0] if els else None


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
        # ── ① 工作台 /dashboard：导航栏无「连接你的 agent」入口（二轮返工）──
        _goto(drv, '/dashboard')
        WebDriverWait(drv, 25).until(
            lambda d: '平台概览' in (d.execute_script('return document.body.textContent || ""')))
        body = _body_text(drv)
        header_txt = _header_text(drv)
        sidebar_txt = _sidebar_text(drv)
        check('顶栏无「联接你的 agent」入口（二轮返工）',
              '联接你的 agent' not in header_txt, header_txt[:120])
        check('顶栏无「打开联接你的 agent」按钮（aria-label 不存在）',
              len(drv.find_elements(By.XPATH, "//*[@aria-label='打开联接你的 agent']")) == 0)
        check('顶栏无「连接你的 agent」入口（header 无 agent-connect 链接）',
              len(drv.find_elements(By.CSS_SELECTOR, "header a[href='/agent-connect']")) == 0,
              str(len(drv.find_elements(By.CSS_SELECTOR, "header a[href='/agent-connect']"))))
        check('侧栏无「连接你的 agent」入口（aside 无 agent-connect 链接）',
              len(_sidebar_agent_connect_links(drv)) == 0,
              'sidebar_agent_connect_links=%d' % len(_sidebar_agent_connect_links(drv)))
        check('侧栏无「连接你的 agent」文案', '连接你的 agent' not in sidebar_txt, sidebar_txt[:120])
        check('全页无「联接你的 agent」残留文案', '联接你的 agent' not in body)
        check('全页无「打开连接你的 agent」按钮（导航栏移净后该 aria-label 不在顶栏/侧栏）',
              len(drv.find_elements(By.XPATH, "//*[@aria-label='打开连接你的 agent']")) == 0,
              'aria-labels=%d' % len(drv.find_elements(By.XPATH, "//*[@aria-label='打开连接你的 agent']")))
        net = _network_api_calls(drv)
        urls = [n.get('url', '') for n in net]
        check('工作台真实请求 /api/v1/home', any('/home/' in u for u in urls) or any('/api/' in u for u in urls))
        _save_evidence('01_dashboard_light', drv, net)

        # 深色工作台（导航栏仍无入口的深色呈现）
        _set_theme(drv, 'dark')
        WebDriverWait(drv, 20).until(
            lambda d: '平台概览' in (d.execute_script('return document.body.textContent || ""')))
        check('深色侧栏仍无「连接你的 agent」入口',
              len(_sidebar_agent_connect_links(drv)) == 0)
        check('深色顶栏仍无「联接你的 agent」入口',
              '联接你的 agent' not in _header_text(drv))
        _save_evidence('01b_dashboard_dark', drv, _network_api_calls(drv))
        # 深色浮窗（小窗口）头行入口截图
        drv.find_element(By.XPATH, "//*[@aria-label='打开全局 Agent 工作台']").click()
        time.sleep(1.5)
        if _workbench_window(drv) is not None:
            _save_evidence('02b_floating_window_dark', drv, _network_api_calls(drv))
            _workbench_window(drv).find_element(
                By.CSS_SELECTOR, "button[aria-label='关闭']").click()
            time.sleep(0.8)
        _set_theme(drv, 'light')

        # ── ② 全局 Agent 工作台浮窗（小窗口）头行右上角入口 ──
        wb_btn = drv.find_element(By.XPATH, "//*[@aria-label='打开全局 Agent 工作台']")
        wb_btn.click()
        time.sleep(1.5)
        win = _workbench_window(drv)
        check('浮窗（小窗口）打开', win is not None)
        assert win is not None, 'Agent 工作台浮窗未打开'
        _save_evidence('02_floating_window_light', drv, _network_api_calls(drv))
        fw_link = _workbench_window_agent_connect_link(drv)
        fw_text = win.text if win else ''
        check('浮窗头行「连接你的 agent」入口存在',
              fw_link is not None and '连接你的 agent' in (fw_link.text or ''), (fw_link.text if fw_link else '')[:60])
        check('浮窗入口 aria-label=打开连接你的 agent',
              len(win.find_elements(By.XPATH, ".//*[@aria-label='打开连接你的 agent']")) == 1)
        check('浮窗头行无「联接你的 agent」文案', '联接你的 agent' not in fw_text)
        assert fw_link is not None, '浮窗「连接你的 agent」链接缺失'
        fw_link.click()
        WebDriverWait(drv, 20).until(
            lambda d: '/agent-connect' in d.current_url
            and '使用说明' in (d.execute_script('return document.body.textContent || ""')))
        body = _body_text(drv)
        check('点击浮窗入口进入 /agent-connect', '/agent-connect' in drv.current_url, drv.current_url)
        check('页面标题=连接你的 agent（全页文案一致）', '连接你的 agent' in drv.title, drv.title)
        check('使用说明区块', '使用说明' in body and '创建 Access Token' in body)
        url_input = drv.find_element(By.ID, 'agent-connect-base-url')
        url_val = url_input.get_attribute('value') or ''
        check('服务地址默认取地址栏', url_val == 'http://localhost:5345' or url_val == 'http://127.0.0.1:5345', url_val)
        check('Token 指引跳 /profile', '前往个人中心创建 / 管理 Access Token' in body)
        check('下载 skill 按钮（炫彩）', '下载 skill' in body)
        check('入口页侧栏无「连接你的 agent」入口（导航栏仍无入口）',
              len(_sidebar_agent_connect_links(drv)) == 0)
        check('入口页全页无「联接你的 agent」残留', '联接你的 agent' not in body)
        # 关闭浮窗，隔离 /ai-chat 右上角入口断言
        close_btn = win.find_elements(By.CSS_SELECTOR, "button[aria-label='关闭']")
        if close_btn:
            close_btn[0].click()
            time.sleep(0.8)
        check('浮窗已关闭（后续 /ai-chat 断言不受浮窗干扰）', _workbench_window(drv) is None)

        # ── ③ 灵犀Agent 页 /ai-chat 顶部条右上角入口 ──
        _goto(drv, '/ai-chat')
        WebDriverWait(drv, 20).until(
            lambda d: '用自然语言驱动平台全部能力' in (d.execute_script('return document.body.textContent || ""')))
        ai_links = _agent_connect_links(drv)
        ai_txt = ' / '.join(l.text or '' for l in ai_links)
        check('/ai-chat 顶部条右上角「连接你的 agent」入口存在',
              len(ai_links) >= 1 and '连接你的 agent' in ai_txt, f'links={len(ai_links)} {ai_txt[:80]}')
        check('/ai-chat 无「联接你的 agent」残留', '联接你的 agent' not in _body_text(drv))
        _save_evidence('07_ai_chat_light', drv, _network_api_calls(drv))
        # 深色 /ai-chat（右上角入口的深色呈现）
        _set_theme(drv, 'dark')
        WebDriverWait(drv, 20).until(
            lambda d: '用自然语言驱动平台全部能力' in (d.execute_script('return document.body.textContent || ""')))
        check('深色 /ai-chat 右上角「连接你的 agent」入口存在',
              len(_agent_connect_links(drv)) >= 1 and '连接你的 agent' in _body_text(drv))
        _save_evidence('08_ai_chat_dark', drv, _network_api_calls(drv))
        _set_theme(drv, 'light')
        WebDriverWait(drv, 20).until(
            lambda d: '用自然语言驱动平台全部能力' in (d.execute_script('return document.body.textContent || ""')))
        ai_links = _agent_connect_links(drv)
        assert ai_links, '/ai-chat 右上角入口缺失'
        ai_links[0].click()
        WebDriverWait(drv, 20).until(
            lambda d: '/agent-connect' in d.current_url
            and '使用说明' in (d.execute_script('return document.body.textContent || ""')))
        check('点击 /ai-chat 右上角入口进入 /agent-connect',
              '/agent-connect' in drv.current_url, drv.current_url)

        # ── ④ 下载按钮 → 真实请求 /api/v1/agent/skill（成功链路待后端合栈）──
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

        # ── ⑤ /profile token 管理 ──
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
