# -*- coding: utf-8 -*-
"""INT-596 报告域全量走查补齐 浏览器验收（真实 Chrome headless，按 test_ui_18/test_ui_25 先例）。

针对 frontend-react/ mock 稿（无后端依赖，直接驱动 dev server，默认 5273，可用 REACT_DEV_BASE 覆盖）：
覆盖 INT-596 交付清单的浏览器可见项：
1. 报告中心排序维度补「状态/算法」（§2 REPORT_SORT_OPTIONS）
2. 报告中心高级搜索折叠区补「时间范围」（任务类型×设备类型×创建者×时间范围四条件）
3. 报告中心表格空态补「生成报告」CTA
4. 展示页 /reports 排序维度同 §2 + 算法卡片网格（选择算法/全部算法）
5. 报告查看 /report/1201 报告头：← 返回 / 复制报告ID与名称 / 打印 / 任务名进任务详情
6. 底部操作条：保存 / 取消发布（published 报告）
7. 设备与API统计：API 状态文案「活跃」
8. 对比表格：导出按钮 + 表体可展开（首页/末页 mock 行数 <10 不触发，代码核查）
9. 按用例分组对比「选择用例标签（可多选）」/ 按用例标签对比「选择用例分组（可多选）」
10. 具体用例卡片七块（评分指标/多轮对话结果/执行结果/用例参数/评估结果/设备·API执行结果）+ 资源状态徽标
11. 具体用例长错误文本折叠（>50 字 → 展开/收起）
12. Benchmark 排行（/report/1185）参考线「最佳」标注
13. 二次对比（/report/1188）趋势折线「对比趋势」
14. 统计分析页 趋势分析 子页签 + 趋势折线「执行用例数时间趋势」
15. 全走查无 console SEVERE

失败落 tests/ui/artifacts/int596_reports/<用例>/（截图+console+source）。
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
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int596_reports')

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


# ---------------------------------------------------------------------------
# 用例
# ---------------------------------------------------------------------------

def test_report_center_sort_has_status_and_algorithm(drv):
    """报告中心排序维度补「状态/算法」（§2：创建时间/名称/状态/算法/通过率/用例数）。"""
    _clear_global_algorithm(drv)
    _goto(drv, '/report-center')
    _wait_text(drv, '报告中心')
    drv.find_element(By.XPATH, "//button[starts-with(normalize-space(.), '创建时间')]").click()
    time.sleep(0.5)
    text = _body_text(drv)
    for label in ('创建时间', '报告名称', '状态', '算法', '通过率', '用例数'):
        assert label in text, f'排序下拉缺「{label}」'
    # 选中「状态」→ URL 态 sortBy=status 生效
    drv.find_element(By.XPATH, "//*[@role='menuitem' and contains(., '状态')]").click()
    _wait_text(drv, '状态', timeout=8)
    assert 'sortBy=status' in drv.current_url, f'排序未写回 URL：{drv.current_url}'


def test_report_center_advanced_search_has_time_range(drv):
    """高级搜索折叠区补「时间范围」（任务类型×设备类型×创建者×时间范围四条件，§2 :117）。"""
    _clear_global_algorithm(drv)
    _goto(drv, '/report-center')
    _wait_text(drv, '报告中心')
    drv.find_element(By.XPATH, "//button[contains(., '高级搜索')]").click()
    time.sleep(0.5)
    text = _body_text(drv)
    for label in ('任务类型', '设备类型', '创建者', '时间范围'):
        assert label in text, f'高级搜索折叠区缺「{label}」'
    drv.find_element(By.XPATH, "//button[@id='adv-time-range']")


def test_report_center_table_empty_state_cta(drv):
    """表格空态补「生成报告」CTA（§2：未找到匹配报告 + 生成报告按钮）。"""
    _clear_global_algorithm(drv)
    _goto(drv, '/report-center')
    _wait_text(drv, '报告中心')
    search = drv.find_element(By.XPATH, "//input[@placeholder='搜索报告名称、任务或算法...']")
    drv.execute_script("arguments[0].scrollIntoView({block:'center'})", search)
    time.sleep(0.3)
    search.click()
    search.send_keys('zzzz-绝无此报告-xyz')
    _wait_text(drv, '清除全部筛选')
    text = _body_text(drv)
    assert '生成报告' in text, '表格空态缺「生成报告」CTA'


def test_showcase_sort_options_and_algorithm_grid(drv):
    """展示页：排序维度含状态/算法 + 算法卡片网格（选择算法/全部算法）。"""
    _clear_global_algorithm(drv)
    _goto(drv, '/reports')
    _wait_text(drv, '浏览测试报告')
    text = _body_text(drv)
    assert '选择算法' in text
    assert '全部算法' in text
    drv.find_element(By.XPATH, "//button[starts-with(normalize-space(.), '创建时间')]").click()
    time.sleep(0.5)
    body = _body_text(drv)
    assert '状态' in body and '算法' in body, '展示页排序下拉缺「状态/算法」'
    # 关闭菜单（Esc）避免遮挡后续
    drv.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
    time.sleep(0.3)


def test_report_header_toolbar(drv):
    """报告查看报告头：← 返回 / 复制报告ID与名称 / 打印 / 任务名点击进任务详情。"""
    _goto(drv, '/report/1201')
    _wait_text(drv, '旗舰音箱全量回归 · 第 3 轮报告')
    drv.find_element(By.XPATH, "//button[contains(., '返回')]")
    drv.find_element(By.XPATH, "//button[@aria-label='复制报告ID与名称']")
    drv.find_element(By.XPATH, "//button[contains(., '打印')]")
    task_link = drv.find_element(By.XPATH, "//a[contains(., '智能音箱旗舰机型全量回归 · 第 3 轮')]")
    assert '/tasks/' in task_link.get_attribute('href'), '任务名未链接到任务详情'


def test_report_bottom_action_bar(drv):
    """底部操作条补 保存 / 取消发布（保存仅编辑态出现，进入编辑后断言；published → 取消发布）。"""
    _goto(drv, '/report/1201')
    _wait_text(drv, '旗舰音箱全量回归 · 第 3 轮报告')
    # 进入编辑态 → 保存 按钮出现（§3.1 保存 report:update）
    drv.find_element(By.XPATH, "//button[contains(., '编辑')]").click()
    _wait_text(drv, '保存')
    text = _body_text(drv)
    assert '保存' in text, '底部操作条缺「保存」（编辑态）'
    assert '取消发布' in text, '底部操作条缺「取消发布」（published 报告）'


def test_report_resource_stats_api_active(drv):
    """设备与API统计：API 状态文案「活跃」（原误显「在线」，INT-596 修正）。"""
    _goto(drv, '/report/1201')
    _wait_text(drv, '设备与API统计')
    _wait_text(drv, '活跃')
    text = _body_text(drv)
    assert 'asr-streaming-v3' in text, '设备与API统计缺 API 资源行'
    assert '在线' in text, '设备在线状态文案缺失'


def test_report_comparison_table_export(drv):
    """对比表格：导出按钮 + 表体展开可见行（首页/末页 mock 行数 <10 不触发分页）。"""
    _goto(drv, '/report/1201')
    _wait_text(drv, '对比表格')
    section = drv.find_element(By.XPATH, "//section[@id='report-comparison-tables']")
    exports = section.find_elements(By.XPATH, ".//button[contains(., '导出')]")
    assert exports, '对比表格缺「导出」按钮'
    # 展开默认折叠的表体（default_collapsed: true）
    title_btn = section.find_element(By.XPATH, ".//button[contains(., '设备/API信息对比')]")
    drv.execute_script("arguments[0].scrollIntoView({block:'center'})", title_btn)
    time.sleep(0.3)
    before = drv.execute_script(
        "return document.querySelectorAll('#report-comparison-tables tbody tr').length")
    title_btn.click()
    time.sleep(0.6)
    after = drv.execute_script(
        "return document.querySelectorAll('#report-comparison-tables tbody tr').length")
    assert after > before, f'对比表格展开后无行增加（before={before}, after={after}）'
    # 首页/末页：仅 pages>1 渲染（mock 表 5 行 < pageSize 10 → 不出现；代码核查 comparison-table.tsx:201/211）
    assert '第 1 页，共 1 页' not in _body_text(drv), 'mock 表未超 10 行不应出现分页条（预期不渲染）'


def test_case_category_tag_comparison_multi_select(drv):
    """按用例分组对比「用例标签多选」/ 按用例标签对比「用例分组多选」（§3.3.5/§3.3.6）。"""
    _goto(drv, '/report/1201')
    _wait_text(drv, '按用例分组对比')
    _wait_text(drv, '选择用例标签（可多选）')
    _wait_text(drv, '按用例标签对比')
    _wait_text(drv, '选择用例分组（可多选）')


def test_specific_case_cards_seven_blocks(drv):
    """具体用例卡片七块：评分指标/多轮对话结果/执行结果/用例参数/设备·API执行结果/音频区（评估结果块代码级核查——mock 用例无 dimension 归属字段不渲染）。"""
    _goto(drv, '/report/1201')
    _wait_text(drv, '具体用例对比')
    # 多轮对话用例（voice_llm 三轮）：七块中多轮/参数/音频齐备
    _wait_text(drv, '多轮对话-闲聊上下文（voice_llm）', timeout=20)
    drv.execute_script(
        "const row=[...document.querySelectorAll('div.rounded-xl.border')]"
        ".find(d=>d.textContent.includes('多轮对话-闲聊上下文（voice_llm）'));"
        "if(row){const bs=row.querySelectorAll('button');bs[bs.length-1].click()}")
    _wait_text(drv, '评分指标', timeout=15)
    text = _body_text(drv)
    for label in ('评分指标', '多轮对话结果', '执行结果', '用例参数', '设备/API 执行结果', '结果音频'):
        assert label in text, f'具体用例卡片缺块「{label}」'


def test_specific_case_long_error_fold(drv):
    """具体用例长错误文本折叠：>50 字 metricError 展开/收起（§3.5.1）。"""
    _goto(drv, '/report/1201')
    _wait_text(drv, '具体用例对比')
    _wait_text(drv, '近场唤醒-桌面 0.5 米', timeout=20)
    drv.execute_script(
        "const row=[...document.querySelectorAll('div.rounded-xl.border')]"
        ".find(d=>d.textContent.includes('近场唤醒-桌面 0.5 米'));"
        "if(row){const bs=row.querySelectorAll('button');bs[bs.length-1].click()}")
    _wait_text(drv, '建议复核超长指令', timeout=15)
    # 长错误折叠按钮（限定在含长文本的容器内找「展开」）
    fold = drv.find_element(
        By.XPATH, "//div[contains(., '建议复核超长指令')]//button[contains(., '展开')]")
    fold.click()
    time.sleep(0.4)
    _wait_text(drv, '收起')
    drv.find_element(
        By.XPATH, "//div[contains(., '建议复核超长指令')]//button[contains(., '收起')]").click()
    time.sleep(0.4)
    assert '展开' in _body_text(drv), '折叠收回后应回到「展开」态'


def test_normal_distribution_chart_renders(drv):
    """矩阵显示类型切换：正态分布图（§3 分组/标签/分类对比 + 正态分布统计图）。"""
    _goto(drv, '/report/1201')
    _wait_text(drv, '正态分布图')
    btn = drv.find_element(By.XPATH, "//button[contains(., '正态分布图')]")
    drv.execute_script("arguments[0].scrollIntoView({block:'center'})", btn)
    time.sleep(0.4)
    btn.click()
    time.sleep(1.2)
    canvases = drv.execute_script("return document.querySelectorAll('canvas').length")
    assert canvases >= 1, f'正态分布图未渲染 canvas（count={canvases}）'


def test_benchmark_best_markline_label(drv):
    """Benchmark 排行参考线标注「最佳」（§3.8 中位数/最佳 双 markLine）。"""
    _goto(drv, '/report/1185')
    _wait_text(drv, 'Benchmark 排行')
    _wait_text(drv, '最佳', timeout=20)
    text = _body_text(drv)
    assert '中位数' in text, 'Benchmark 缺「中位数」参考线标注'
    assert '实测轨' in text, 'Benchmark 缺版本标注'


def test_secondary_comparison_trend_line(drv):
    """二次对比趋势折线「对比趋势」（§3.4 INT-360 §4.8 保留）。"""
    _goto(drv, '/report/1188')
    _wait_text(drv, '二次对比')
    _wait_text(drv, '对比趋势')


def test_statistics_trend_line(drv):
    """统计分析页 趋势分析 子页签 + 趋势折线（§2.2 趋势分析）。"""
    _goto(drv, '/report-statistics')
    _wait_text(drv, '报告统计分析')
    drv.find_element(By.XPATH, "//button[contains(., '趋势分析')]").click()
    time.sleep(0.5)
    text = _body_text(drv)
    for label in ('时间趋势', '维度趋势', '趋势图表', '预测分析'):
        assert label in text, f'趋势分析子页签缺「{label}」'
    assert '执行用例数时间趋势' in text, '趋势折线标题缺失'


def test_no_console_severe(drv):
    """全走查无 console SEVERE（无 console.error）。"""
    global _CONSOLE_SEVERE
    _drain_console(drv)
    severe = [m for m in _CONSOLE_SEVERE if 'favicon' not in m.lower()]
    assert not severe, f'存在 console SEVERE：\n' + '\n'.join(severe[:10])
