# -*- coding: utf-8 -*-
"""INT-492 首页可视稿对齐 浏览器走查（真实 Chrome headless，按 test_ui_09 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273）：
1. Hero 品牌区：badge/标题/亮点句定稿文案 + 四角主节点 + 六枚算法能力 floating 芯片
   （实时语音大模型/语音识别 ASR/语音合成 TTS/翻译/声纹识别·说话人分割/通话与会话场景），
   SVG 连线仅四象限四条（算法芯片不接 SVG 连线）
2. 分区⑤ 接入测试对象（03_首页.md §3.6 / INT-420）：三对象卡（被测设备/被测APP/被测API
   各「怎么接」+入口）+ 接入演示三页签（设备连接/应用装卸/API 连接测试）点击切换 +
   示例值标注「示例数据」+ 复制按钮可用
3. 全站文案：首页无用户可见「控制台」残留；登录后 /dashboard 侧栏「灵犀Agent」、
   首页主按钮「进入工作台」
4. Hero 文案定稿逐条：highlight 卖点句合并、titleLine2 纯色（无渐变）、QUICK_START 四步

失败落 tests/ui/artifacts/int492_home_align/<用例>/（截图+console+source）。
"""
import json
import os
import time

import pytest
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int492_home_align')

# 5273 = 本工作区常驻 dev server；env 可覆写（INT-473 隔离副本为 5274）
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
    global _DRIVER
    _DRIVER = _driver()
    yield _DRIVER
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


def _goto(drv, path):
    drv.get(BASE + path)
    WebDriverWait(drv, 15).until(
        lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(1.2)


def _body_text(drv):
    # 用 textContent 全量读取（AnimateInView 初态 opacity-0 的元素不在 innerText
    # 内但已挂载；可见性另以 scroll-to-visible 断言，见 _ensure_visible）
    return drv.execute_script('return document.body.textContent || ""')


def _ensure_visible(drv, text):
    """滚动到含指定文案的元素处，触发 AnimateInView（opacity-0 → landing-animate-*），
    断言其最终可见（断言可见状态而非仅 DOM 存在——test_ui_05 先例）。"""
    found = drv.execute_script(
        f"""
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let n;
        while (n = walker.nextNode()) {{
          if (n.textContent.includes({text!r})) {{
            let el = n.parentElement;
            el.scrollIntoView({{ block: 'center' }});
            return true;
          }}
        }}
        return false;
        """)
    assert found, f'文案「{text}」未在 DOM 中找到'
    time.sleep(1.0)
    # 断言可见：display 非 none、visibility 非 hidden、opacity 已离开 0
    visible = drv.execute_script(
        f"""
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let n;
        while (n = walker.nextNode()) {{
          if (n.textContent.includes({text!r})) {{
            const el = n.parentElement;
            const cs = getComputedStyle(el);
            const r = el.getBoundingClientRect();
            return !(cs.display === 'none' || cs.visibility === 'hidden'
                     || +cs.opacity === 0 || r.width === 0 || r.height === 0);
          }}
        }}
        return false;
        """)
    assert visible, f'文案「{text}」滚动后仍不可见'


def _login(drv, username='demo_admin'):
    _goto(drv, '/login')
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/login')
    drv.find_element(By.ID, 'username').send_keys(username)
    drv.find_element(By.ID, 'password').send_keys('mock-pass-001')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 15).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.0)


# ── 1. Hero 品牌区：定稿文案 + 四角节点 + 六枚算法芯片 ───────
def test_01_hero_copy_and_orbit(drv):
    _goto(drv, '/')
    txt = _body_text(drv)
    # 定稿文案逐条（负责人 2026-10-16；badge 随 f6207251 INT-492 审计 P3 定稿为「算法可插拔」）
    assert '算法可插拔 · 从 ASR 到实时语音大模型' in txt, f'badge 缺失：{txt[:120]}'
    assert '智能语音测试平台' in txt, '标题第一行缺失'
    assert '让每一次语音交互都可度量' in txt, '标题第二行（slogan）缺失'
    assert '真实设备、真实链路、真实指标，多友商横向对比，看清真实用户体验。' in txt, \
        f'highlight 卖点句未合并：{txt[:200]}'
    # 四角主节点
    for node in ['测试用例', '被测 API', '设备集群', '报告分析']:
        assert node in txt, f'四角节点「{node}」缺失'
    # 六枚算法能力 floating 芯片（INT-421）
    for chip in ['实时语音大模型', '语音识别 ASR', '语音合成 TTS', '翻译',
                 '声纹识别 · 说话人分割', '通话与会话场景']:
        assert chip in txt, f'算法芯片「{chip}」缺失'
    # 可见性：滚动至枢纽图后算法芯片可见
    _ensure_visible(drv, '实时语音大模型')
    # SVG 连线仅四象限四条（算法芯片不接 SVG 连线）；作用域限定枢纽图 SVG（viewBox 500 430）
    orbit_svgs = drv.find_elements(By.CSS_SELECTOR, "svg[viewBox='0 0 500 430']")
    assert orbit_svgs, '枢纽图 SVG 未找到'
    d = orbit_svgs[0].find_element(By.CSS_SELECTOR, 'path').get_attribute('d')
    # 单条 path 内含 4 个 M 起点（四象限 C 曲线子路径）；算法芯片不进 SVG
    m_starts = d.count('M')
    assert m_starts == 4, f'枢纽图连线应为 4 段 C 曲线（4 个 M 起点），实际 {m_starts}'
    # 算法芯片为独立 div（border-dashed），不属于 SVG 连线图元
    chip_divs = drv.find_elements(
        By.CSS_SELECTOR, 'div.border-dashed')
    assert chip_divs, '算法能力 floating 节点（虚线描边 div）未找到'


# ── 2. 分区⑤ 接入测试对象：三对象卡 + 三页签切换 + 示例数据 + 复制 ──
def test_02_section5_test_object_access(drv):
    _goto(drv, '/')
    txt = _body_text(drv)
    assert '03 / 接入测试对象' in txt, f'分区⑤ eyebrow 缺失：{txt[:150]}'
    assert '把被测对象接进平台。' in txt, '分区⑤ heading 缺失'
    # 三对象卡（怎么接 + 入口）
    for obj, action in [('被测设备', '去设备管理'), ('被测 APP', '去装载应用'),
                        ('被测 API', '去配置 API')]:
        assert obj in txt, f'对象卡「{obj}」缺失'
        assert action in txt, f'对象卡「{obj}」入口「{action}」缺失'
    assert '查看接入指引' in txt, '「查看接入指引」链接缺失'
    # 三页签切换（先滚动到分区⑤ 使 AnimateInView 触发）
    _ensure_visible(drv, '03 / 接入测试对象')
    for tab_label in ['设备连接', '应用装卸', 'API 连接测试']:
        tabs = drv.find_elements(By.XPATH, f"//button[contains(., '{tab_label}')]")
        assert tabs, f'页签「{tab_label}」未找到'
        tabs[0].click()
        time.sleep(0.8)
        txt = _body_text(drv)
        if tab_label == '设备连接':
            assert 'adb devices -l' in txt, f'设备连接页签内容缺失：{txt[-400:]}'
            assert 'hdc list targets' in txt, '设备连接页签缺 HDC 命令'
        elif tab_label == '应用装卸':
            assert '安装应用' in txt and '卸载应用' in txt, '应用装卸页签内容缺失'
        else:
            assert '/api/v1/apis/:id/health' in txt, 'API 连接测试页签端点缺失'
            assert 'health_score' in txt and 'response_time' in txt, \
                'API 连接测试响应字段缺失'
        # 示例值一律标注「示例数据」
        assert '示例数据' in txt, f'页签「{tab_label}」示例值未标「示例数据」'
        # 复制按钮在页签内可用（CopyButton 可点击）
        copy_btns = drv.find_elements(By.CSS_SELECTOR, "button[aria-label='复制代码']")
        assert copy_btns, f'页签「{tab_label}」复制按钮缺失'
    # 尾行「常用入口」
    for tail in ['常用入口', '配置播放设备', '配置评估维度', '导入测试音频']:
        assert tail in _body_text(drv), f'尾行「{tail}」缺失'


# ── 3. 全站文案：首页无「控制台」残留 ─────────────────────
def test_03_no_console_residue(drv):
    _goto(drv, '/')
    txt = _body_text(drv)
    assert '控制台' not in txt, '首页存在用户可见「控制台」残留'


# ── 4. 登录后：侧栏「灵犀Agent」+ 首页主按钮「进入工作台」 ───
def test_04_login_sidebar_and_hero_button(drv):
    _login(drv)
    _goto(drv, '/dashboard')
    txt = _body_text(drv)
    assert '灵犀Agent' in txt, f'侧栏未显示「灵犀Agent」：{txt[:200]}'
    assert '工作台' in txt, f'/dashboard 标题未显示「工作台」：{txt[:200]}'
    _goto(drv, '/')
    txt = _body_text(drv)
    assert '进入工作台' in txt, f'已登录首页主按钮未变「进入工作台」：{txt[:200]}'


# ── 5. QUICK_START 四步 ──────────────────────────────────
def test_05_quick_start_four_steps(drv):
    _goto(drv, '/')
    txt = _body_text(drv)
    assert '01 / 开始测试' in txt, 'QUICK_START eyebrow 缺失'
    _ensure_visible(drv, '01 / 开始测试')
    # 四步流程（工作树含并行 INT-486 合并口径：第二步「选择设备/API」同屏同选）
    for step in ['选择用例', '选择设备/API', '执行测试', '查看结果']:
        assert step in _body_text(drv), f'QUICK_START 四步缺「{step}」'
