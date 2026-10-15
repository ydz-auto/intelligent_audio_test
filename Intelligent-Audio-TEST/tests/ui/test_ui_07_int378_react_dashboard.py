# -*- coding: utf-8 -*-
"""INT-378 React /dashboard 工作台可视稿浏览器走查（真实 Chrome headless，按 test_ui_06 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server）：
1. mock 登录 → /dashboard 落地，四分区 + 页头面包屑/Actions 齐全
2. 设置引导卡：mock 数据四步探针全完成 → 默认折叠横条（已完成 4/4 + 前 4 快捷操作），
   展开双栏大卡（API 预览卡 + 复制 curl → toast 已复制 + 推荐操作 8 项快捷操作），
   刷新页面记住展开/折叠（localStorage iatp:dashboard:v1:setup-guide）
3. 平台概览：三 StatCard（任务总数 342 / 通过率 86.8% / 平均得分 87.5）+ 设备状态
   （8 台在线 · 2 台离线）· 音频文件 1560/干音 980 · API 服务 5/在线 4
4. 最近任务：mock 8 行覆盖状态徽章五色 + 算法 outline 徽章 + 用例完成度；
   头部「状态演示」数据/加载中 Skeleton/空态三段切换
5. 任务统计图表区：#task-charts 两图真实渲染（VChart canvas）、粒度 日/周/月/年 与
   形态 柱状图/面积图 切换不崩；切深色模式图表整图重建不崩（ThemeManager key 机制）
6. 全程 console.error / pageerror / unhandledrejection 零采集（JS 级监听器）

注记：饼图图例/趋势 tooltip 为 VChart canvas 内渲染（非 DOM 文本），机器断言到
canvas 存在 + 卡片标题 + 交互切换不崩，图例文案与 tooltip 汇总行以交付截图佐证。
失败落 tests/ui/artifacts/int378_react_dashboard/<用例>/（截图+console+source）。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int378_react_dashboard')

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
    """会话级 Chrome：创建后先登录一次（各用例自足，单测隔离运行也能跑）。"""
    global _DRIVER
    _DRIVER = _driver()
    try:
        _login(_DRIVER)
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


def _goto_dashboard(drv, marker='平台概览'):
    """全量加载 /dashboard，等 readyState + 内容标记后装错误采集（时间窗内稳定）。"""
    drv.get(BASE + '/dashboard')
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    _install_error_collector(drv)
    WebDriverWait(drv, 15).until(
        lambda d: marker in d.find_element(By.TAG_NAME, 'body').text)
    time.sleep(1.0)


def _body_text(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def _errors(drv):
    return drv.execute_script('return window.__iatpTestErrors || []')


def _chart_canvases(drv):
    """#task-charts 的兄弟图表卡内 VChart canvas 数（图卡与锚点 div 同属一个 section）。"""
    return drv.execute_script(
        "return document.querySelectorAll('#task-charts ~ div canvas').length")


def _login(drv, username='demo_admin'):
    # 先清会话：已登录时 /login 的 beforeLoad 会 redirect 到 /dashboard（用例间状态泄漏防护）。
    drv.get(BASE + '/login')
    time.sleep(1.2)
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    drv.get(BASE + '/login')
    time.sleep(1.2)
    drv.find_element(By.ID, 'username').send_keys(username)
    drv.find_element(By.ID, 'password').send_keys('mock-pass-001')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 15).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.0)


# ── 1. mock 登录 → /dashboard 四分区 + 页头 ──────────────────
def test_01_login_and_four_sections(drv):
    assert '/dashboard' in drv.current_url, f'登录后未落地 /dashboard：{drv.current_url}'
    _goto_dashboard(drv)
    txt = _body_text(drv)
    # 页头面包屑 控制台 / 工作台 + Actions 三件（§3.3/交付清单 2）
    for item in ['控制台', '工作台', '刷新统计', '查看任务']:
        assert item in txt, f'页头缺「{item}」'
    # 四分区标题
    for item in ['开始使用', '平台概览', '最近任务', '任务统计']:
        assert item in txt, f'工作台缺分区「{item}」：{txt[:300]}'
    assert drv.execute_script("return !!document.getElementById('task-charts')"), \
        '#task-charts 锚点缺失'


# ── 2. 引导卡折叠态默认（mock 四步全完成 → 折叠横条）──────────
def test_02_setup_guide_collapsed_default(drv):
    _goto_dashboard(drv)
    drv.execute_script("window.localStorage.removeItem('iatp:dashboard:v1:setup-guide')")
    _goto_dashboard(drv)
    txt = _body_text(drv)
    # 折叠横条：开始使用 + 已完成 4/4 徽章 + 前 4 快捷操作 + 显示引导
    assert '已完成 4/4' in txt, f'折叠态缺完成度徽章：{txt[:200]}'
    assert '显示引导' in txt, '折叠态缺「显示引导」'
    for action in ['端到端测试', 'API 测试', '任务管理', '用例管理']:
        assert action in txt, f'折叠态前 4 快捷操作缺「{action}」'
    # 折叠态不应渲染展开态内容
    assert '通过 API 驱动测试' not in txt, '折叠态误渲染展开态内容'
    assert '隐藏引导' not in txt, '折叠态不应有「隐藏引导」'


# ── 3. 引导卡展开/折叠双态 + localStorage 持久化 ─────────────
def test_03_setup_guide_expand_collapse_persist(drv):
    _goto_dashboard(drv)
    drv.execute_script("window.localStorage.removeItem('iatp:dashboard:v1:setup-guide')")
    _goto_dashboard(drv)
    # 展开
    drv.find_element(By.XPATH, "//button[contains(., '显示引导')]").click()
    WebDriverWait(drv, 10).until(
        lambda d: '通过 API 驱动测试' in d.find_element(By.TAG_NAME, 'body').text)
    time.sleep(1.0)
    txt = _body_text(drv)
    # 「复制 curl」按钮在「开发者 API 示例」折叠区内，折叠态不可见——展开态断言不含它
    for item in ['通过 API 驱动测试', '开发者 API 示例',
                 '推荐操作', '让平台保持就绪', '隐藏引导',
                 '音频管理', '设备管理', '报告中心', '评估维度']:
        assert item in txt, f'展开态缺「{item}」：{txt[:300]}'
    assert drv.execute_script(
        "return window.localStorage.getItem('iatp:dashboard:v1:setup-guide')"
    ) == 'expanded', '展开态未写 localStorage=expanded'
    # 复制 curl（在「开发者 API 示例」折叠区内，先展开该区）→ toast「已复制」
    drv.find_element(By.XPATH, "//button[contains(., '开发者 API 示例')]").click()
    time.sleep(1.0)
    assert '复制 curl' in _body_text(drv), '展开「开发者 API 示例」后缺「复制 curl」按钮'
    try:
        drv.execute_cdp_cmd('Browser.grantPermissions', {
            'permissions': ['clipboardReadWrite', 'clipboardSanitizedWrite'],
            'origin': BASE,
        })
    except Exception:
        pass
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='复制 curl 示例']").click()
    time.sleep(1.0)
    toasts = drv.execute_script(
        "return Array.from(document.querySelectorAll('[data-sonner-toast]'))"
        ".map(e => e.textContent.trim())")
    assert any('已复制' in t for t in toasts), f'复制 curl 未弹「已复制」toast：{toasts}'
    # 收起 → localStorage=collapsed
    drv.find_element(By.XPATH, "//button[contains(., '隐藏引导')]").click()
    time.sleep(0.8)
    assert '通过 API 驱动测试' not in _body_text(drv), '收起后展开态内容仍在'
    assert drv.execute_script(
        "return window.localStorage.getItem('iatp:dashboard:v1:setup-guide')"
    ) == 'collapsed', '收起态未写 localStorage=collapsed'
    # 刷新后仍折叠（持久化闭环）
    _goto_dashboard(drv)
    txt = _body_text(drv)
    assert '显示引导' in txt and '通过 API 驱动测试' not in txt, '刷新后折叠态丢失'


# ── 4. 平台概览：三 StatCard + 设备/资产面板 ─────────────────
def test_04_platform_summary_values(drv):
    _goto_dashboard(drv)
    txt = _body_text(drv)
    # 三 StatCard（任务总数/通过率/平均得分，与基座 MOCK_HOME_STATS 对齐）
    for item in ['任务总数', '342', '297 个已完成',
                 '通过率', '86.8%', '297/342 执行完成',
                 '平均得分', '87.5', '142 份报告参与评分']:
        assert item in txt, f'StatCard 缺「{item}」：{txt[:400]}'
    # 设备状态 + 资产面板（「8 台在线」为数字 span + 下标 span 视觉间距，DOM 文本无空格）
    for item in ['设备状态', '8台在线', '2 台离线',
                 '音频文件', '1560', '干音 980 个',
                 'API 服务', '5', '在线 4 个']:
        assert item in txt, f'设备/资产面板缺「{item}」：{txt[:400]}'
    # sparkline（StatCard line sparkline 的 viewBox=160 36 SVG）——可视化非仅文本
    sparklines = drv.execute_script(
        "return Array.from(document.querySelectorAll('svg')).filter("
        "s => s.getAttribute('viewBox') && /160 36/.test(s.getAttribute('viewBox')))")
    assert len(sparklines) >= 1, 'StatCard sparkline SVG 未渲染'


# ── 5. 最近任务：mock 8 行 + 状态徽章五色 + 算法徽章 ──────────
def test_05_recent_tasks_rows_and_badges(drv):
    _goto_dashboard(drv)
    txt = _body_text(drv)
    for name in ['智能音箱旗舰机型全量回归 · 第 3 轮',
                 '车载语音助手唤醒词响应测试',
                 'API 通道并发稳定性验证（压测时段）',
                 '耳机产品线夜间批量回归',
                 '新风控语音播报音质评估',
                 '多方言识别准确性抽样测试',
                 'TTS 自然度主观评估（第 2 期）',
                 'Q3 音箱品类回归汇总（合并自 4 个任务）']:
        assert name in txt, f'最近任务缺行「{name}」'
    # 状态徽章八态中文（五色覆盖：success/info/danger/warning/neutral + purple）
    for label in ['执行中', '已完成', '执行失败', '排队中', '已暂停',
                  '待执行', '已停止', '已合并']:
        assert label in txt, f'状态徽章缺「{label}」'
    # 算法类型 outline 徽章
    for algo in ['流式语音识别', '唤醒词检测', '语音合成评估']:
        assert algo in txt, f'算法徽章缺「{algo}」'
    # 用例完成度（执行中任务 31/48）
    assert '用例 31/48' in txt, '用例完成度「31/48」缺失'
    # 徽章配色类挂到 DOM（data-slot=status-badge 的 textColorMap 类）
    badge_classes = drv.execute_script(
        "return Array.from(document.querySelectorAll('[data-slot=status-badge]'))"
        ".map(e => e.className).join(' ')")
    for cls in ['text-info', 'text-success', 'text-destructive', 'text-warning',
                'text-muted-foreground', 'text-chart-4']:
        assert cls in badge_classes, f'状态徽章缺配色类「{cls}」：{badge_classes[:300]}'


# ── 6. 最近任务：状态演示 数据/加载中/空态（各态自数据默认可达）────────
def test_06_recent_tasks_demo_states(drv):
    """PanelWrapper 三态逐态自默认数据态验证。注记：状态演示开关挂在
    PanelWrapper headerActions，仅数据态渲染——切到加载/空态后开关随之隐藏
    （演示件特性，接线时移除）；故各态之间以重新加载回到数据默认再切。
    """
    # 数据态（默认）：8 行在
    _goto_dashboard(drv, marker='最近任务')
    assert '智能音箱旗舰机型全量回归 · 第 3 轮' in _body_text(drv), '数据态缺任务行'
    # 加载中 → Skeleton，任务行消失
    drv.find_element(By.XPATH, "//button[contains(., '加载中')]").click()
    WebDriverWait(drv, 10).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "[data-slot='skeleton']"))
    time.sleep(0.6)
    assert '智能音箱旗舰机型全量回归 · 第 3 轮' not in _body_text(drv), '加载中仍渲染任务行'
    # 回数据态（重载）→ 空态文案 + 任务行消失
    _goto_dashboard(drv, marker='最近任务')
    drv.find_element(By.XPATH, "//button[contains(., '空态')]").click()
    time.sleep(0.8)
    txt = _body_text(drv)
    assert '发起第一次测试后，最近任务会显示在这里' in txt, '空态文案缺失'
    assert '智能音箱旗舰机型全量回归 · 第 3 轮' not in txt, '空态仍渲染任务行'
    # 回数据态（重载）→ 8 行还原
    _goto_dashboard(drv, marker='最近任务')
    assert '智能音箱旗舰机型全量回归 · 第 3 轮' in _body_text(drv), '数据态未还原任务行'


# ── 7. 任务统计图表：#task-charts 两图 + 粒度/形态切换 ────────
def test_07_task_charts_render_and_controls(drv):
    _goto_dashboard(drv, marker='任务统计')
    txt = _body_text(drv)
    for item in ['任务完成趋势', '任务类型分布']:
        assert item in txt, f'图表卡缺标题「{item}」'
    # VChart canvas 渲染（非仅 DOM 文本）
    WebDriverWait(drv, 20).until(lambda d: _chart_canvases(drv) >= 2)
    time.sleep(1.5)
    assert _chart_canvases(drv) >= 2, '图表区 VChart canvas 不足 2 张'
    # 形态切换 柱状图 → 面积图（不崩、画布仍在）
    drv.find_element(By.XPATH, "//button[contains(., '面积图')]").click()
    time.sleep(1.2)
    assert _chart_canvases(drv) >= 2, '切面积图后画布消失'
    # 粒度切换 日 → 周 → 月 → 年（不崩、画布仍在）
    for gran in ['周', '月', '年']:
        drv.find_element(By.XPATH, f"//button[contains(., '{gran}')]").click()
        time.sleep(1.0)
        assert _chart_canvases(drv) >= 2, f'切粒度「{gran}」后画布消失'


# ── 8. 切深色模式：图表整图重建不崩、画布仍在 ────────────────
def test_08_dark_mode_charts_rerender(drv):
    _goto_dashboard(drv, marker='任务统计')
    assert _chart_canvases(drv) >= 2, '初始图表画布缺失'
    drv.find_element(By.CSS_SELECTOR, "button[aria-label='打开主题设置']").click()
    time.sleep(1.0)
    drv.find_element(By.XPATH, "//span[@role='radio'][@aria-label='选择深色']").click()
    time.sleep(1.5)
    assert drv.execute_script(
        "return document.documentElement.classList.contains('dark')"), '切深色后 html.dark 未生效'
    # ThemeManager 门控重建：两图画布仍在且无 JS 错误
    assert _chart_canvases(drv) >= 2, '深色模式下图表画布消失'
    assert _errors(drv) == [], f'深色切换触发 JS 错误：{_errors(drv)}'
    # 还原：切回跟随系统
    drv.find_element(By.XPATH, "//span[@role='radio'][@aria-label='选择跟随系统']").click()
    time.sleep(0.8)
    drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
    time.sleep(0.6)
    assert not drv.execute_script(
        "return document.documentElement.classList.contains('dark')"), '还原后 html.dark 仍在'


# ── 9. 全程 console.error / pageerror / unhandledrejection 零采集 ──
def test_09_no_console_or_page_errors(drv):
    _goto_dashboard(drv)
    time.sleep(2.0)
    errs = _errors(drv)
    assert errs == [], f'浏览器 JS 错误非零：{errs}'
    # 浏览器日志层 SEVERE 兜底（含 JS 监听未覆盖的网络/资源错误）
    severe = [e for e in drv.get_log('browser') if e.get('level') == 'SEVERE']
    assert severe == [], f'浏览器 SEVERE 日志非零：{severe}'
