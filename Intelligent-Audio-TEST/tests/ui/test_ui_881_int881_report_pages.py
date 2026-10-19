# -*- coding: utf-8 -*-
"""INT-881 报告列表/详情/对比 接线真实数据走查（真实 Chrome headless + 常驻后端 :5000）。

范围：/report-center 列表真实数据渲染 + 筛选；/report/{id} 详情用例卡 + 人工复核入口；
报告对比 Dialog 提交流程；空态/错误态；浅色+深色+Network 截图（artifacts/int881_report/）。

后端依赖：常驻 5000（AUTH_MODE=off dev_user 全放行），dev server :5305 代理 /api。
"""
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int881_report')
os.makedirs(ARTIFACTS, exist_ok=True)

BASE = os.environ.get('REACT_DEV_BASE', 'http://localhost:5305')
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
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
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


def _screenshot(drv, name):
    path = os.path.join(ARTIFACTS, name)
    drv.save_screenshot(path)
    return path


def _drain_severe(drv):
    sev = [e for e in drv.get_log('browser') if e.get('level') == 'SEVERE']
    return sev


def wait_text(drv, text, timeout=12):
    return WebDriverWait(drv, timeout).until(
        lambda d: text in d.find_element(By.TAG_NAME, 'body').text
    )


def _body_text(drv):
    """Return body textContent via JS (Selenium .text can be empty for truncate cells)."""
    return drv.execute_script("return document.body.textContent || ''")


def test_report_list_light():
    """报告中心列表真实数据渲染 + 类型 chips + 状态 tab（浅色）。"""
    drv = _driver()
    try:
        drv.get(BASE + '/report-center')
        wait_text(drv, '报告中心')
        time.sleep(2)
        body = _body_text(drv)
        assert 'INT321_API报告' in body, '缺少真实任务报告名 INT321_API报告'
        assert 'Benchmark报告' in body, '缺少真实 Benchmark 报告名'
        assert 'prb338' in body, '缺少真实 e2e 报告名 prb338'
        rows = drv.find_elements(By.CSS_SELECTOR, 'table tbody tr')
        assert len(rows) == 4, '列表应有 4 个报告，实际 %d' % len(rows)
        assert '任务报告' in body and 'Benchmark 报告' in body and '对比报告' in body
        assert '草稿' in body and '已发布' in body
        _screenshot(drv, '01_report_center_light.png')
        sev = _drain_severe(drv)
        real = [e for e in sev if 'algorithm/options' not in e.get('message', '')]
        assert not real, '报告中心存在 console SEVERE: %s' % [e.get('message')[:200] for e in real]
    finally:
        drv.quit()


def test_report_list_status_filter():
    """状态筛选：草稿 → 仅 prb338。"""
    drv = _driver()
    try:
        drv.get(BASE + '/report-center')
        wait_text(drv, '报告中心')
        time.sleep(2)
        draft_btns = drv.find_elements(By.XPATH, "//*[contains(text(),'草稿')]")
        clicked = False
        for b in draft_btns:
            try:
                if b.is_displayed() and b.tag_name in ('button', 'div', 'span', 'a'):
                    b.click()
                    clicked = True
                    break
            except Exception:
                continue
        time.sleep(2.5)
        body = _body_text(drv)
        rows = drv.find_elements(By.CSS_SELECTOR, 'table tbody tr')
        print('DRAFT rows:', len(rows), 'has prb:', 'prb338' in body, 'has INT321:', 'INT321' in body)
        assert len(rows) == 1 and 'prb338' in body, '草稿筛选应只剩 prb338'
    finally:
        drv.quit()


def test_report_detail_case_card():
    """报告详情：真实用例卡 + 人工复核/AI 复核入口（浅色）。"""
    drv = _driver()
    try:
        drv.get(BASE + '/report/2')
        wait_text(drv, 'INT321_API报告')
        time.sleep(3)
        body = _body_text(drv)
        assert '测试用例_2026144019.wav_153241' in body, '缺少真实用例卡名称'
        assert '63cf495d' in body, '缺少真实用例 ID'
        assert '人工复核' in body, '缺少人工复核入口'
        assert 'AI 复核' in body, '缺少 AI 复核入口'
        assert '下载日志' in body, '缺少下载日志按钮'
        expand_btns = drv.find_elements(
            By.CSS_SELECTOR, "button[aria-label='展开详情'], button[aria-expanded='false']")
        for b in expand_btns:
            try:
                if b.is_displayed():
                    b.click()
                    break
            except Exception:
                continue
        time.sleep(2)
        body2 = _body_text(drv)
        print('EXPANDED has 评分:', '评分指标' in body2 or '评估结果' in body2)
        _screenshot(drv, '02_report_detail_light.png')
        sev = _drain_severe(drv)
        real = [e for e in sev
                if 'algorithm/options' not in e.get('message', '')
                and '/tasks/' not in e.get('message', '')]
        assert not real, '报告详情存在 console SEVERE: %s' % [e.get('message')[:200] for e in real]
    finally:
        drv.quit()


def test_report_compare_dialog():
    """报告中心对比 Dialog：勾选 2 报告 → 批量对比 → Dialog 提交（观察生成流程）。"""
    drv = _driver()
    try:
        drv.get(BASE + '/report-center')
        wait_text(drv, '报告中心')
        time.sleep(2.5)
        # 勾选前两行报告（列表勾选 ≥2 → 二次对比数据源）
        checkboxes = drv.find_elements(
            By.CSS_SELECTOR, 'table tbody tr td:first-child [role="checkbox"]')
        print('row checkbox count:', len(checkboxes))
        selected = 0
        for cb in checkboxes[:3]:
            try:
                drv.execute_script('arguments[0].click();', cb)
                selected += 1
                time.sleep(0.3)
                if selected >= 2:
                    break
            except Exception:
                continue
        time.sleep(1)
        body = _body_text(drv)
        print('after select, 已选择:', '已选择 2' in body or '已选择' in body)
        # 点击批量对比按钮
        compare_btns = [e for e in drv.find_elements(By.TAG_NAME, 'button')
                        if '批量对比' in (e.text or '')]
        print('批量对比 buttons:', len(compare_btns))
        clicked = False
        for b in compare_btns:
            try:
                if b.is_displayed():
                    drv.execute_script('arguments[0].click();', b)
                    clicked = True
                    break
            except Exception:
                continue
        time.sleep(2)
        body = _body_text(drv)
        print('DIALOG has 报告对比:', '报告对比' in body,
              '| has 二次对比:', '二次对比' in body)
        _screenshot(drv, '03_compare_dialog_light.png')
        # 切换到「基于已选报告」tab 并提交
        report_tabs = [e for e in drv.find_elements(By.TAG_NAME, 'button')
                       if '基于已选报告' in (e.text or '')]
        for t in report_tabs:
            try:
                if t.is_displayed():
                    drv.execute_script('arguments[0].click();', t)
                    break
            except Exception:
                continue
        time.sleep(1)
        body = _body_text(drv)
        print('AFTER REPORT TAB has 已选择 2 个报告:', '已选择 2 个报告' in body or '已选择 2' in body)
        submit_btns = [e for e in drv.find_elements(By.TAG_NAME, 'button')
                       if '生成对比报告' in (e.text or '')]
        print('submit btns:', len(submit_btns))
        clicked = False
        for b in submit_btns:
            try:
                if b.is_displayed():
                    print('submit enabled:', b.is_enabled())
                    drv.execute_script('arguments[0].click();', b)
                    clicked = True
                    break
            except Exception:
                continue
        time.sleep(4)
        body2 = _body_text(drv)
        print('AFTER SUBMIT has 正在生成:', '正在生成' in body2,
              '| 生成完成:', '生成完成' in body2,
              '| 加载失败:', '加载失败' in body2,
              '| 二次对比报告已生成:', '二次对比报告已生成' in body2)
        _screenshot(drv, '04_compare_progress_light.png')
    finally:
        drv.quit()


def test_report_error_state():
    """错误态：无效报告 ID 呈现错误态（记录实际文案）；空态：搜索无结果。"""
    drv = _driver()
    try:
        drv.get(BASE + '/report/999999')
        time.sleep(4)
        body = _body_text(drv)
        print('ERROR STATE body has 加载失败:', '加载失败' in body,
              '| 报告不存在:', '报告不存在' in body)
        _screenshot(drv, '05_report_not_found_light.png')
        drv.get(BASE + '/report-center?search=zzz_not_exist')
        time.sleep(3)
        body = _body_text(drv)
        print('EMPTY state:', '共 0 个' in body or '暂无数据' in body or '无' in body)
        _screenshot(drv, '06_report_list_empty_light.png')
    finally:
        drv.quit()


def test_report_detail_dark():
    """深色模式截图：报告列表 + 报告详情（localStorage 预设 dark）。"""
    drv = _driver()
    try:
        drv.get(BASE + '/report-center')
        wait_text(drv, '报告中心')
        time.sleep(1)
        # 预设 dark 主题（iatp:theme:v1:mode），刷新后生效
        drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', 'dark');")
        drv.refresh()
        time.sleep(3)
        _screenshot(drv, '07_report_center_dark.png')
        drv.get(BASE + '/report/2')
        time.sleep(3)
        _screenshot(drv, '08_report_detail_dark.png')
    finally:
        drv.quit()


def test_report_detail_review_entry():
    """人工复核入口：点击后弹出复核 Dialog（真实数据）。"""
    drv = _driver()
    try:
        drv.get(BASE + '/report/2')
        wait_text(drv, 'INT321_API报告')
        time.sleep(3)
        review_btns = [e for e in drv.find_elements(By.TAG_NAME, 'button')
                       if '人工复核' in (e.text or '')]
        print('人工复核 buttons:', len(review_btns))
        for b in review_btns:
            try:
                if b.is_displayed():
                    b.click()
                    break
            except Exception:
                continue
        time.sleep(2)
        body = _body_text(drv)
        print('REVIEW DIALOG has 人工复核:', '人工复核' in body,
              '| 执行状态:', '执行状态' in body or 'execution_status' in body)
        _screenshot(drv, '09_manual_review_dialog_light.png')
    finally:
        drv.quit()
