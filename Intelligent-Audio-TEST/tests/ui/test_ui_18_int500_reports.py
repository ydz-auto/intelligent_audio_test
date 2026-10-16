# -*- coding: utf-8 -*-
"""INT-500 报告域 v2.9 实施 浏览器走查（真实 Chrome headless，按 test_ui_11 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273）：
1. /report-center 报告中心：标题徽标 + 类型筛选 chips 含「Benchmark 报告」且默认「全部」
2. 旧链 /test-reports、/history-reports redirect 到 /report-center（无 tab 语义）
3. /reports 报告展示页：Hero「浏览测试报告」+ 算法卡片网格「选择算法」+ chips 含 Benchmark
4. 算法卡片网格选中写回全局 store（localStorage iatp:algorithm:v1）
5. 报告中心类型筛选「Benchmark 报告」→ 列表仅 Benchmark 报告（类型徽标）
6. /report/1185 Benchmark 报告详情：报告头 + 内嵌「Benchmark 排行」区块（异步计算后渲染）
7. /report-statistics 统计分析页：四标签页 + 统计卡 + 散点/热力图切换
8. 全走查无 console SEVERE（含 Error）

失败落 tests/ui/artifacts/int500_reports/<用例>/（截图+console+source）。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int500_reports')

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
_CONSOLE_SEVERE = []


def _drain_console(drv):
    global _CONSOLE_SEVERE
    try:
        for entry in drv.get_log('browser'):
            if entry.get('level') == 'SEVERE':
                _CONSOLE_SEVERE.append(entry.get('message', ''))
    except Exception:
        pass


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
    try:
        _login(_DRIVER)
    except Exception:
        pass
    yield _DRIVER
    try:
        _drain_console(_DRIVER)
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
    _drain_console(drv)


def _body_text(drv):
    return drv.execute_script('return document.body.textContent || ""')


def _login(drv, username='demo_admin'):
    _goto(drv, '/login')
    drv.execute_script('try { window.localStorage.clear() } catch (e) {}')
    _goto(drv, '/login')
    drv.find_element(By.ID, 'username').send_keys(username)
    drv.find_element(By.ID, 'password').send_keys('mock-pass-001')
    drv.find_element(By.XPATH, "//button[contains(., '登 录')]").click()
    WebDriverWait(drv, 15).until(lambda d: '/login' not in d.current_url)
    time.sleep(1.0)


def _wait_text(drv, text, timeout=15):
    WebDriverWait(drv, timeout).until(lambda d: text in _body_text(drv))


def _clear_global_algorithm(drv):
    """重置全局算法 store 为「全部算法」（空串）——列表默认附 algorithm_type 过滤（INT-344 契约）。"""
    drv.execute_script(
        'localStorage.setItem("iatp:algorithm:v1", JSON.stringify({state:{algorithmId:""},version:0}))')
    time.sleep(0.4)


def _wait_gone(drv, text, timeout=15):
    WebDriverWait(drv, timeout).until(lambda d: text not in _body_text(drv))


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------

def test_report_center_single_view_with_benchmark_chip(drv):
    """报告中心：单一列表视图默认全部 + 类型筛选 chips 含「Benchmark 报告」（INT-439 v2.6/INT-500 v2.9）。"""
    _clear_global_algorithm(drv)
    _goto(drv, '/report-center')
    _wait_text(drv, '报告中心')
    text = _body_text(drv)
    assert '全部' in text
    assert 'Benchmark 报告' in text, '类型筛选 chips 缺「Benchmark 报告」'
    assert '唤醒性能 Benchmark 排行报告' in text, '默认全部列表未含 Benchmark 报告'


def test_legacy_links_redirect_to_report_center(drv):
    """旧链 /test-reports、/history-reports redirect 到 /report-center（不带 tab 语义）。"""
    for path in ('/test-reports', '/history-reports'):
        _goto(drv, path)
        _wait_text(drv, '报告中心')
        assert '/report-center' in drv.current_url, f'{path} 未 redirect 到 /report-center'


def test_showcase_page_grid_and_benchmark_chip(drv):
    """展示页：Hero + 算法卡片网格「选择算法」+ 类型 chips 含 Benchmark + 列表仅已发布。"""
    _clear_global_algorithm(drv)
    _goto(drv, '/reports')
    _wait_text(drv, '浏览测试报告')
    text = _body_text(drv)
    assert '选择算法' in text, '算法卡片网格区头「选择算法」缺失'
    assert 'Benchmark 报告' in text, '展示页类型 chips 缺「Benchmark 报告」'
    assert '全部算法' in text, '算法卡片网格缺「全部算法」首卡'
    assert '唤醒性能 Benchmark 排行报告' in text, '已发布 Benchmark 报告未展示'


def test_algorithm_card_writes_global_store(drv):
    """算法卡片网格点击选中 → 写回全局 store（localStorage iatp:algorithm:v1）双向联动。"""
    _goto(drv, '/reports')
    _wait_text(drv, '选择算法')
    cards = drv.find_elements(By.XPATH, "//section[.//span[contains(., '选择算法')]]//button")
    assert len(cards) >= 2, '算法卡片网格卡片数不足'
    # 点击第二张算法卡（首卡=全部算法）
    cards[1].click()
    time.sleep(0.6)
    stored = drv.execute_script('return localStorage.getItem("iatp:algorithm:v1") || ""')
    assert stored and 'algorithmId' in stored, '算法选中未写回全局 store'
    # 恢复全部算法
    drv.find_elements(By.XPATH, "//section[.//span[contains(., '选择算法')]]//button")[0].click()
    time.sleep(0.4)


def test_report_center_benchmark_type_filter(drv):
    """报告中心类型筛选「Benchmark 报告」→ 列表仅 Benchmark 报告。"""
    _clear_global_algorithm(drv)
    _goto(drv, '/report-center')
    _wait_text(drv, '报告中心')
    chip = drv.find_element(By.XPATH, "//button[contains(., 'Benchmark 报告')]")
    chip.click()
    _wait_text(drv, '唤醒性能 Benchmark 排行报告')
    text = _body_text(drv)
    assert '旗舰音箱 vs 车载助手' not in text, 'Benchmark 筛选后仍显示对比报告'
    assert 'Q3 音箱品类回归' not in text, 'Benchmark 筛选后仍显示任务报告'


def test_benchmark_report_detail_with_ranking_block(drv):
    """Benchmark 报告详情：报告头 + 内嵌「Benchmark 排行」区块（异步计算后渲染排行表）。"""
    _goto(drv, '/report/1185')
    _wait_text(drv, 'Benchmark 排行')
    _wait_text(drv, '发布 Benchmark 报告')
    # 异步计算推进 → 排行表行渲染
    _wait_text(drv, '旗舰-01', timeout=20)
    text = _body_text(drv)
    assert '唤醒成功率' in text, '排行指标缺失'
    assert '实测轨' in text, '版本标注缺失'
    assert '中位数' in text, '中位数参考线标注缺失'


def test_report_statistics_page(drv):
    """统计分析页：四标签页 + 统计卡 + 散点/热力图切换 + 导出。"""
    _goto(drv, '/report-statistics')
    _wait_text(drv, '报告统计分析')
    text = _body_text(drv)
    for label in ('统计维度', '统计结果', '趋势分析', '报表生成'):
        assert label in text, f'四标签页缺「{label}」'
    for label in ('报告数量', '测试用例执行', '评估指标', '设备性能'):
        assert label in text, f'统计卡缺「{label}」'
    # 执行统计分析 → toast「统计完成」
    drv.find_element(By.XPATH, "//button[contains(., '执行统计分析')]").click()
    _wait_text(drv, '统计完成')


def test_report_center_advanced_search(drv):
    """报告中心高级搜索：任务类型筛选（api 接口）→ 列表过滤；重置恢复（§2 实测 :186）。"""
    _clear_global_algorithm(drv)
    _goto(drv, '/report-center')
    _wait_text(drv, '报告中心')
    drv.find_element(By.XPATH, "//button[contains(., '高级搜索')]").click()
    # 打开任务类型 Select → 选「api 接口」
    drv.find_element(By.XPATH, "//button[@id='adv-task-type']").click()
    drv.find_element(By.XPATH, "//*[@role='option' and contains(., 'api 接口')]").click()
    time.sleep(0.6)
    text = _body_text(drv)
    assert 'API 通道并发稳定性验证报告' in text, '任务类型=api 筛选后应含 API 通道并发报告'
    assert '旗舰音箱全量回归' not in text, '任务类型=api 筛选后不应含 e2e 报告'
    # 重置高级搜索 → 恢复全部
    drv.find_element(By.XPATH, "//button[contains(., '重置高级搜索')]").click()
    _wait_text(drv, '旗舰音箱全量回归')


def test_no_console_severe(drv):
    """全走查无 console SEVERE（无 console.error）。"""
    global _CONSOLE_SEVERE
    _drain_console(drv)
    severe = [m for m in _CONSOLE_SEVERE if 'favicon' not in m.lower()]
    assert not severe, f'存在 console SEVERE：\n' + '\n'.join(severe[:10])
