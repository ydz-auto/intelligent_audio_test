# -*- coding: utf-8 -*-
"""INT-379 React 登录页+首页门户+错误页三件 可视稿浏览器走查（真实 Chrome headless）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，5273 端口）：
1. /login：auth-layout 品牌角标 + 480 卡 + auth-shell 光斑底；登录/注册双页拆分
   （RHF+zod 校验 mock：空表单内联错误 / 密码显隐）；RSA 加密桩链路（提交走
   fetchEncryptionKey → encryptPassword）；错误码 105 卡内 Alert、106 sonner toast；
   OAuth 提供方区 mock 2 按钮 + 分隔线；登录成功 → /dashboard
2. /register：四字段中文校验（邮箱格式 / 密码 6 位 / 两次一致）；closed 用户名
   403 引导态；注册成功 → 回 /login 预填用户名
3. / 首页门户九分区（未登录降级文案）：品牌 hero + 规模条降级行 + 快速开始 +
   为什么选择 + 八入口卡降级空态 + 架构演示终端 + 数据可靠性 + 部署与边界 +
   FAQ + CTA + 页脚；登录后八入口卡 8 卡全显 + 规模条 mock 数字
4. /403 /404 /500 错误页三件同构版式；未匹配路径落根路由 404 兜底
5. 全程 console.error / pageerror / unhandledrejection 零采集

失败落 tests/ui/artifacts/int379_react_login_home/<用例>/（截图+console+source）。
"""
import json
import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

# 栈门禁豁免：本文件走查 frontend-react/ mock 稿（无后端依赖），
# tests/ui/conftest.py 经 STACK_GATE_EXEMPT_MODULES 对本模块放行。

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int379_react_login_home')

# 3000 被 newAPI 参照实例常驻占用；React dev server 钉死 5273（rsbuild.config.ts，strictPort）。
BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5273')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    # Chrome 主版本 → 缓存同主版本 chromedriver（tests/ui/conftest 先例）
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


_DRIVER = None


def _save_evidence(name, drv):
    d = os.path.join(ARTIFACTS, name)
    os.makedirs(d, exist_ok=True)
    try:
        drv.save_screenshot(os.path.join(d, 'screenshot.png'))
        with open(os.path.join(d, 'page_source.html'), 'w', encoding='utf-8') as f:
            f.write(drv.page_source)
        with open(os.path.join(d, 'console.log'), 'w', encoding='utf-8') as f:
            for entry in drv.get_log('browser'):
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass


@pytest.fixture(scope='session')
def drv():
    """会话级 Chrome：单测隔离运行也能自足（各用例自清会话）。"""
    global _DRIVER
    _DRIVER = _driver()
    try:
        yield _DRIVER
    finally:
        try:
            _DRIVER.quit()
        except Exception:
            pass


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if rep.when == 'call' and rep.failed and _DRIVER is not None:
        _save_evidence(item.name, _DRIVER)


# ── 工具 ─────────────────────────────────────────────────────

def _install_error_collector(drv):
    """全量 load 后装 JS 级错误采集（SPA 客户端导航不重装，跨用例累积）。"""
    drv.execute_script(
        "window.__iatpTestErrors = window.__iatpTestErrors || [];"
        "window.addEventListener('error', (e) => window.__iatpTestErrors"
        ".push('pageerror: ' + e.message));"
        "window.addEventListener('unhandledrejection', (e) => window.__iatpTestErrors"
        ".push('rejection: ' + String(e.reason && e.reason.message || e.reason)));"
        "const _ce = window.console.error;"
        "window.console.error = (...a) => { window.__iatpTestErrors"
        ".push('console: ' + a.map(x => (x && x.message) || String(x)).join(' '));"
        "_ce(...a); };"
    )


def _goto(drv, path, marker=None):
    """全量加载 path；marker 为 body 文本必现标记（AnimateInView 入场不阻塞 DOM）。"""
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    if marker:
        WebDriverWait(drv, 15).until(
            lambda d: marker in d.find_element(By.TAG_NAME, 'body').text)
    time.sleep(1.0)


def _goto_anon(drv, path, marker=None):
    """清会话后全量加载（匿名态）。"""
    drv.get(BASE + '/login')
    time.sleep(1.0)
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, path, marker)


def _scroll_through(drv):
    """逐段滚到底触发 AnimateInView 入场（once=true，滚过后 opacity-0 移除），
    再等数字滚动（RollingNumber 1.2s ease-out）落终值。"""
    drv.execute_script('window.scrollTo(0, 0)')
    height = drv.execute_script('return document.body.scrollHeight')
    viewport = drv.execute_script('return window.innerHeight')
    y = 0
    while y < height:
        y = min(y + viewport, height)
        drv.execute_script(f'window.scrollTo(0, {y})')
        time.sleep(0.3)
    drv.execute_script('window.scrollTo(0, document.body.scrollHeight)')
    time.sleep(1.5)
    drv.execute_script('window.scrollTo(0, 0)')
    time.sleep(0.5)


def _body_text(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _errors(drv):
    return drv.execute_script('return window.__iatpTestErrors || []')


def _toasts(drv):
    return drv.execute_script(
        "return Array.from(document.querySelectorAll('[data-sonner-toast]'))"
        ".map(e => e.textContent.trim())")


def _login(drv, username='demo_admin'):
    """清会话 → 表单登录（mock 任意账号可进）。"""
    _goto_anon(drv, '/login', marker='登录')
    drv.find_element(By.ID, 'username').send_keys(username)
    drv.find_element(By.ID, 'password').send_keys('mock-pass-001')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 15).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.0)


# ── 1. /login：auth-layout 版式 + 双页拆分 + OAuth 提供方区 ──
def test_01_login_layout_and_oauth_zone(drv):
    _goto_anon(drv, '/login', marker='登录')
    txt = _body_text(drv)
    # auth-layout：品牌角标 + 480 卡 + auth-shell 光斑背景类
    assert '智能语音测试平台' in txt, '品牌角标缺失'
    assert drv.find_element(By.CSS_SELECTOR, 'div.auth-shell'), 'auth-shell 光斑背景缺失'
    assert drv.execute_script(
        "return !!document.querySelector('[data-slot=card][class*=max-w-]')"), \
        '480 登录卡缺失'
    # 登录页头部 + 副行（双页拆分）
    assert '登录' in txt, '标题「登录」缺失'
    link_href = drv.find_element(By.XPATH, "//a[contains(., '注册')]").get_attribute('href')
    assert link_href.endswith('/register'), f'「注册」链接未指向 /register：{link_href}'
    # 表单字段
    for label in ['用户名或电子邮件', '密码', '登 录']:
        assert label in txt, f'登录表单缺「{label}」'
    assert drv.find_element(By.ID, 'username').is_displayed()
    assert drv.find_element(By.ID, 'password').is_displayed()
    # OAuth 提供方区：分隔线 + mock 2 个按钮
    assert '或使用账号登录' in txt, 'OAuth 分隔线缺失'
    for provider in ['使用 GitHub 登录', '使用 企业统一认证 登录']:
        assert provider in txt, f'OAuth 按钮缺「{provider}」'
    # 密码显隐眼睛钮：点击后 input type=password → text（可见性切换生效）
    pwd_input = drv.find_element(By.ID, 'password')
    assert pwd_input.get_attribute('type') == 'password', '密码框初始非 password'
    eye_btn = pwd_input.find_element(By.XPATH, '..').find_element(
        By.CSS_SELECTOR, 'button')
    eye_btn.click()
    time.sleep(0.5)
    assert drv.find_element(By.ID, 'password').get_attribute('type') == 'text', \
        '眼睛钮未切换密码可见性'
    # 注记（低severity 观察项）：password-input.tsx 眼睛钮 aria-label 为英文
    # 「Toggle password visibility」（基座 INT-377 文件），规范 §8 期望
    # 「切换密码可见性」（红线④ 站内无英文文案）——随基座卡或后续卡勘误。
    # 演示触发词提示（105/106 文案映射可视化）
    assert 'error_105' in txt and 'error_106' in txt, '演示触发词提示缺失'


# ── 2. 登录空表单 → RHF+zod 内联校验 ──────────────────────────
def test_02_login_empty_submit_inline_errors(drv):
    _goto_anon(drv, '/login', marker='登录')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    time.sleep(0.8)
    txt = _body_text(drv)
    assert '请输入用户名或邮箱' in txt, '空用户名校验文案缺失'
    assert '请输入密码' in txt, '空密码校验文案缺失'
    # 校验错误走 FormMessage 内联，不弹 toast（三层分离）
    assert _toasts(drv) == [], f'字段校验错误不应走 toast：{_toasts(drv)}'


# ── 3. 错误码 105 → 卡内 Alert（加密校验失败）─────────────────
def test_03_login_error_105_card_alert(drv):
    _goto_anon(drv, '/login', marker='登录')
    drv.find_element(By.ID, 'username').send_keys('error_105')
    drv.find_element(By.ID, 'password').send_keys('whatever')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    time.sleep(1.2)
    txt = _body_text(drv)
    assert '登录加密校验失败，请刷新页面重试' in txt, f'105 未落卡内 Alert：{txt[:300]}'
    assert '/login' in drv.current_url, '105 不应跳离登录页'
    # Alert 是卡内 destructive 态件（role=alert）
    alert_texts = drv.execute_script(
        "return Array.from(document.querySelectorAll('[data-slot=alert]'))"
        ".map(e => e.textContent.trim())")
    assert any('加密校验失败' in t for t in alert_texts), f'Alert 件缺失：{alert_texts}'


# ── 4. 错误码 106 → sonner toast（用户名或密码错误）────────────
def test_04_login_error_106_toast(drv):
    _goto_anon(drv, '/login', marker='登录')
    drv.find_element(By.ID, 'username').send_keys('error_106')
    drv.find_element(By.ID, 'password').send_keys('whatever')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 10).until(lambda d: _toasts(d))
    time.sleep(0.8)
    toasts = _toasts(drv)
    assert any('登录失败：用户名或密码错误' in t for t in toasts), f'106 未弹 toast：{toasts}'
    assert '/login' in drv.current_url, '106 不应跳离登录页'
    # 106 走 toast，不走卡内 Alert
    assert not drv.execute_script(
        "return Array.from(document.querySelectorAll('[data-slot=alert]'))"
        ".some(e => e.textContent.includes('加密'))"), '106 误落卡内 Alert'


# ── 5. 登录成功 → toast「欢迎回来！」+ /dashboard ──────────────
def test_05_login_success_lands_dashboard(drv):
    _goto_anon(drv, '/login', marker='登录')
    drv.find_element(By.ID, 'username').send_keys('qa_user_01')
    drv.find_element(By.ID, 'password').send_keys('whatever')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 15).until(lambda d: '/dashboard' in d.current_url)
    toasts = _toasts(drv)
    assert any('欢迎回来！' in t for t in toasts), f'成功 toast 缺失：{toasts}'
    # 会话落 store（iatp:auth:v1）
    assert drv.execute_script(
        "return !!window.localStorage.getItem('iatp:auth:v1')"), '会话未写 localStorage'


# ── 6. OAuth 按钮点击 → 演示未接线 toast ──────────────────────
def test_06_oauth_button_demo_toast(drv):
    _goto_anon(drv, '/login', marker='登录')
    drv.find_element(By.XPATH, "//button[contains(., '使用 GitHub 登录')]").click()
    WebDriverWait(drv, 10).until(lambda d: _toasts(d))
    time.sleep(0.8)
    toasts = _toasts(drv)
    assert any('跳转未接线' in t and 'GitHub' in t for t in toasts), \
        f'OAuth 演示 toast 缺失：{toasts}'
    assert '/login' in drv.current_url, 'OAuth 点击不应跳离登录页'


# ── 7. /register：四字段校验（邮箱/密码 6 位/两次一致）──────────
def test_07_register_validation(drv):
    _goto_anon(drv, '/register', marker='创建账号')
    txt = _body_text(drv)
    # 双页拆分：注册页标题 + 副行回登录
    assert '创建账号' in txt, '注册页标题缺失'
    login_href = drv.find_element(By.XPATH, "//a[contains(., '登录')]").get_attribute('href')
    assert login_href.endswith('/login'), f'「登录」链接未指向 /login：{login_href}'
    # 空表单提交 → 四字段内联校验
    drv.find_element(By.XPATH, "//button[contains(., '注 册')]").click()
    time.sleep(0.8)
    txt = _body_text(drv)
    for msg in ['请输入用户名', '请输入邮箱', '请输入密码（至少 6 位）', '请再次输入密码']:
        assert msg in txt, f'注册校验缺「{msg}」：{txt[:300]}'
    # 邮箱格式非法
    drv.find_element(By.ID, 'register-email').send_keys('not-an-email')
    drv.find_element(By.XPATH, "//button[contains(., '注 册')]").click()
    time.sleep(0.8)
    assert '请输入有效的邮箱地址' in _body_text(drv), '邮箱格式校验文案缺失'
    # 两次密码不一致
    drv.find_element(By.ID, 'register-email').clear()
    drv.find_element(By.ID, 'register-email').send_keys('ok@example.com')
    drv.find_element(By.ID, 'register-password').send_keys('abcdef')
    drv.find_element(By.ID, 'register-confirm').send_keys('abcdeg')
    drv.find_element(By.XPATH, "//button[contains(., '注 册')]").click()
    time.sleep(0.8)
    assert '两次输入的密码不一致' in _body_text(drv), '确认密码不一致校验缺失'


# ── 8. 注册成功 → 回 /login 预填用户名 ────────────────────────
def test_08_register_success_prefills_login(drv):
    _goto_anon(drv, '/register', marker='创建账号')
    drv.find_element(By.ID, 'register-username').send_keys('new_qa_user')
    drv.find_element(By.ID, 'register-email').send_keys('new@example.com')
    drv.find_element(By.ID, 'register-password').send_keys('abcdef')
    drv.find_element(By.ID, 'register-confirm').send_keys('abcdef')
    drv.find_element(By.XPATH, "//button[contains(., '注 册')]").click()
    WebDriverWait(drv, 15).until(lambda d: '/login' in d.current_url)
    toasts = _toasts(drv)
    assert any('注册成功，请登录' in t for t in toasts), f'注册成功 toast 缺失：{toasts}'
    time.sleep(0.8)
    val = drv.find_element(By.ID, 'username').get_attribute('value')
    assert val == 'new_qa_user', f'登录页未预填注册用户名：{val!r}'


# ── 9. 注册开关关闭（closed）→ 403 引导态 ─────────────────────
def test_09_register_closed_guide_state(drv):
    _goto_anon(drv, '/register', marker='创建账号')
    drv.find_element(By.ID, 'register-username').send_keys('closed')
    drv.find_element(By.ID, 'register-email').send_keys('closed@example.com')
    drv.find_element(By.ID, 'register-password').send_keys('abcdef')
    drv.find_element(By.ID, 'register-confirm').send_keys('abcdef')
    drv.find_element(By.XPATH, "//button[contains(., '注 册')]").click()
    time.sleep(1.2)
    txt = _body_text(drv)
    for item in ['当前站点未开放注册', '请联系管理员开通账号后使用密码登录。', '返回登录']:
        assert item in txt, f'403 引导态缺「{item}」：{txt[:300]}'
    toasts = _toasts(drv)
    assert any('当前站点未开放注册' in t for t in toasts), f'关闭注册 toast 缺失：{toasts}'


# ── 10. / 首页门户九分区（匿名降级态）──────────────────────────
def test_10_home_nine_sections_anonymous(drv):
    _goto_anon(drv, '/', marker='智能语音测试平台')
    _scroll_through(drv)
    txt = _body_text(drv)
    # ① 品牌区 hero
    for item in ['智能语音测试平台', '让每一次语音交互都可度量',
                 '真实设备、真实链路、真实指标——一句话看到全部。',
                 '立即开始测试', '查看文档', '一个平台，覆盖语音测试全流程']:
        assert item in txt, f'品牌区缺「{item}」：{txt[:400]}'
    # 卖点四卡
    for item in ['多设备并行', '任务稳定调度', '多维自动评估', '报告开箱即用']:
        assert item in txt, f'卖点卡缺「{item}」'
    # 枢纽图 aria（role=img + 平台总览）
    assert drv.execute_script(
        "return !!document.querySelector('[role=img][aria-label=\"平台总览\"]')"), \
        '枢纽图 aria-label 缺失'
    # 平台规模条匿名降级文案（RBAC 未登录降级）
    assert '登录后可查看平台实时规模' in txt, '规模条未登录降级文案缺失'
    assert drv.execute_script(
        "return Array.from(document.querySelectorAll('a')).some("
        "a => a.textContent.trim() === '登录' && a.getAttribute('href')?.endsWith('/login'))"), \
        '规模条「登录」链接缺失'
    # ② 快速开始
    for item in ['01 / 开始测试', '五步跑通一次语音测试。',
                 '选择算法', '选择用例', '选择设备', '执行测试', '查看结果',
                 '端到端测试', 'API 测试']:
        assert item in txt, f'快速开始缺「{item}」'
    # ③ 为什么选择本平台
    for item in ['更快的执行，更全的评估，更可信的报告。',
                 '真实设备测试', '多 API 接入', '自动化评估引擎', '高效任务调度',
                 '细粒度权限体系', '数据全量自有']:
        assert item in txt, f'为什么选择缺「{item}」'
    # ④ 功能入口：八卡降级空态（未登录无权限 → 登录后可查看全部功能入口）
    assert '02 / 功能入口' in txt and '八个模块，覆盖测试全生命周期。' in txt, '入口区标题缺失'
    assert '登录后可查看全部功能入口' in txt, '入口区未登录降级文案缺失'
    assert '任务管理' not in txt, '匿名态不应渲染八卡'
    # ⑤ 架构演示终端块
    for item in ['03 / 开发者友好', '工具照常用，平台接进来。',
                 '进度轮询', '实时事件', '常用入口']:
        assert item in txt, f'终端演示缺「{item}」'
    # ⑥ 数据与可靠性
    for item in ['任务交给平台，结果实时可查。', '异步执行', '失败重试', '实时推送',
                 '全流程可追溯', '任务提交', '报告生成']:
        assert item in txt, f'数据可靠性缺「{item}」'
    # ⑦ 部署与数据边界
    for item in ['数据留在本地，权限各归其位。', '本地化部署', '账号与角色隔离', '操作留痕',
                 '系统信息', '后端框架', '接口版本', '本地存储', '账号隔离', '审计日志']:
        assert item in txt, f'部署与数据边界缺「{item}」'
    # ⑧ FAQ（首项默认展开）
    for item in ['开始之前，你可能想问。', '需要写代码才能用吗？',
                 '首次使用先准备什么？', '端到端测试和 API 测试怎么选？',
                 '测试失败了怎么排查？', '报告能导出吗？']:
        assert item in txt, f'FAQ 缺「{item}」'
    # ⑨ 尾部 CTA（匿名主钮「立即体验」→ /login；Button render=Link 落 <a>）
    assert '准备好开始下一次测试了吗？' in txt, 'CTA 标题缺失'
    assert '立即体验' in txt, 'CTA 匿名主钮文案缺失'
    cta_btn = drv.find_element(By.XPATH, "//a[contains(., '立即体验')]")
    assert cta_btn.get_attribute('href') and cta_btn.get_attribute('href').endswith('/login'), \
        f'CTA 匿名主钮未指向 /login：{cta_btn.get_attribute("href")}'
    # 页脚
    assert '© 2026 智能语音测试平台. 保留所有权利。' in txt, '页脚版权行缺失'


# ── 11. 登录后 / 首页：八入口卡全显 + 规模条 mock 数字 ─────────
def test_11_home_logged_in_entries_and_stats(drv):
    _login(drv)
    _goto(drv, '/', marker='智能语音测试平台')
    _scroll_through(drv)
    txt = _body_text(drv)
    # 八入口卡全显（mock 管理员 '*'）
    for card in ['任务管理', '端到端测试', 'API 测试', '用例管理',
                 '音频管理', '设备管理', '报告中心', '评估维度']:
        assert card in txt, f'八入口卡缺「{card}」'
    assert '登录后可查看全部功能入口' not in txt, '登录态不应显示入口空态'
    # 规模条 mock 数字（MOCK_HOME_STATS）
    for item in ['测试用例', '128', '测试任务', '342', '评估维度',
                 '音频文件', '1560', '在线设备', 'API 服务']:
        assert item in txt, f'规模条缺「{item}」：{txt[:500]}'
    # 未登录降级行消失
    assert '登录后可查看平台实时规模' not in txt, '登录态仍显示规模条降级行'
    # Hero 主钮与 CTA 主钮切登录态
    assert '进入控制台' in txt, '登录态 Hero/CTA 主钮文案缺失'


# ── 12. 错误页三件：/403 /404 /500 同构版式 ───────────────────
def test_12_error_pages_403_404_500(drv):
    # /403：数字 + 主文 + 两行说明 + 三钮
    _goto_anon(drv, '/403?from=/tasks', marker='403')
    txt = _body_text(drv)
    for item in ['403', '禁止访问', '您没有必要的权限，', '无法查看此资源。',
                 '返回', '返回主页', '切换账号', '来源页面：/tasks']:
        assert item in txt, f'/403 缺「{item}」：{txt[:300]}'
    # /404：数字 + 主文 + 双钮
    _goto_anon(drv, '/404', marker='404')
    txt = _body_text(drv)
    for item in ['404', '糟糕！页面未找到！', '您要查找的页面似乎',
                 '不存在或可能已被移除。', '返回', '返回主页']:
        assert item in txt, f'/404 缺「{item}」：{txt[:300]}'
    # /500：数字 + 主文 + 三钮（刷新页面在列）
    _goto_anon(drv, '/500', marker='500')
    txt = _body_text(drv)
    for item in ['500', '糟糕！出错了', '对于由此造成的不便，我们深表歉意。',
                 '请稍后再试。', '返回', '刷新页面', '返回主页']:
        assert item in txt, f'/500 缺「{item}」：{txt[:300]}'


# ── 13. 根路由兜底：未匹配路径落 404 版式 ─────────────────────
def test_13_unknown_path_falls_to_404(drv):
    _goto_anon(drv, '/no-such-page-379', marker='404')
    txt = _body_text(drv)
    assert '糟糕！页面未找到！' in txt, '未匹配路径未落 404 兜底'
    assert '返回主页' in txt, '404 兜底缺返回主页按钮'


# ── 14. 403「切换账号」→ 清会话回登录页 ───────────────────────
def test_14_switch_account_logs_out(drv):
    _login(drv)
    assert drv.execute_script(
        "return !!window.localStorage.getItem('iatp:auth:v1')"), '前置登录态缺失'
    _goto(drv, '/403', marker='403')
    drv.find_element(By.XPATH, "//button[contains(., '切换账号')]").click()
    WebDriverWait(drv, 15).until(lambda d: '/login' in d.current_url)
    time.sleep(0.8)
    # 会话清空：persist 写入 {state:{user:null}}——断言 store.user 为 null（URL 落登录页）
    store = drv.execute_script(
        "const s = JSON.parse(window.localStorage.getItem('iatp:auth:v1') || '{}');"
        "return (s.state && s.state.user) || null")
    assert store is None, f'切换账号未清会话：{store}'
    assert drv.find_element(By.ID, 'username').is_displayed(), '切换账号未落登录表单'


# ── 15. 全程 console.error / pageerror / unhandledrejection 零采集 ──
def test_15_no_console_or_page_errors(drv):
    _goto_anon(drv, '/', marker='智能语音测试平台')
    _install_error_collector(drv)
    # 走查登录 → 错误页 → 注册（SPA 内错误零采集）
    _login(drv)
    _goto(drv, '/403', marker='403')
    _goto(drv, '/404', marker='404')
    _goto_anon(drv, '/register', marker='创建账号')
    time.sleep(2.0)
    errs = _errors(drv)
    assert errs == [], f'浏览器 JS 错误非零：{errs}'
    severe = [e for e in drv.get_log('browser') if e.get('level') == 'SEVERE']
    assert severe == [], f'浏览器 SEVERE 日志非零：{severe}'


# ── 16.【缺陷复验】⑦ 部署卡主钮/小字文案与跳转（打回项修复确认）──
def test_16_deploy_card_anon_button_label_href_mismatch(drv):
    """INT-379 打回项复验（commit 660cfd2d）：部署与数据边界右卡主按钮
    文案与跳转一致——匿名态「立即体验」→ /login、登录态「进入控制台」→
    /dashboard，小字「阅读使用手册」仅登录态 → /user-guide。
    """
    def _card_links():
        # 仅取 ⑦ 部署与数据边界 section 内 anchors（避开 ③ 为什么选择尾部同文案 link）
        return drv.execute_script(
            "const h2s = Array.from(document.querySelectorAll('h2'));"
            "const s = h2s.find(x => x.textContent.includes('数据留在本地'));"
            "const sec = s ? s.closest('section') : null;"
            "if (!sec) return [];"
            "return Array.from(sec.querySelectorAll('a')).map(a => ({"
            "text: a.textContent.trim(), href: a.getAttribute('href')}))")
    # 匿名态：主钮「立即体验」→ /login；「阅读使用手册」小字不渲染
    _goto_anon(drv, '/', marker='智能语音测试平台')
    _scroll_through(drv)
    btns = _card_links()
    assert btns, '⑦ 部署卡 section 未找到或无可点击锚点'
    anon_main = [b for b in btns if b['text'].startswith('立即体验')]
    assert anon_main, f'匿名态主钮「立即体验」缺失：{btns}'
    assert (anon_main[0]['href'] or '').endswith('/login'), \
        f'匿名态主钮未指向 /login：{anon_main[0]}'
    assert not any(b['text'].startswith('阅读使用手册') for b in btns), \
        f'匿名态不应渲染「阅读使用手册」小字：{btns}'
    # 登录态：主钮「进入控制台」→ /dashboard；小字「阅读使用手册」→ /user-guide
    _login(drv)
    _goto(drv, '/', marker='智能语音测试平台')
    _scroll_through(drv)
    btns = _card_links()
    assert btns, '登录态 ⑦ 部署卡 section 未找到'
    auth_main = [b for b in btns if b['text'].startswith('进入控制台')]
    assert auth_main, f'登录态主钮「进入控制台」缺失：{btns}'
    assert (auth_main[0]['href'] or '').endswith('/dashboard'), \
        f'登录态主钮未指向 /dashboard：{auth_main[0]}'
    manual = [b for b in btns if b['text'].startswith('阅读使用手册')]
    assert manual, f'登录态小字「阅读使用手册」缺失：{btns}'
    assert (manual[0]['href'] or '').endswith('/user-guide'), \
        f'小字未指向 /user-guide：{manual[0]}'
