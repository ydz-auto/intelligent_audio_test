# -*- coding: utf-8 -*-
"""INT-1076 前端回归日巡：开始测试向导交互流（E2E + API）。

走 TestFlow 向导真实交互：选择算法 → 选择用例 → 选择设备/API → 开始任务 →
观察执行步骤状态 → 任务列表/详情核验。截图到 tests/ui/artifacts/smoke_daily/。
"""
import argparse
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACT_ROOT = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'smoke_daily')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _chrome_major():
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            return int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        return 0


def _resolve_chromedriver():
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium',
                              'chromedriver', 'win64')
    candidates = []
    if os.path.isdir(cache_root):
        for ver in os.listdir(cache_root):
            exe = os.path.join(cache_root, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                candidates.append((tuple(int(x) for x in ver.split('.') if x.isdigit()), exe))
    major = _chrome_major()
    if major:
        same = [exe for ver, exe in candidates if ver and ver[0] == major]
        if same:
            return max(same)
    if candidates:
        return sorted(candidates, reverse=True)[0][1]
    return ''


def shot(driver, name):
    os.makedirs(ARTIFACT_ROOT, exist_ok=True)
    p = os.path.join(ARTIFACT_ROOT, f'{name}.png')
    driver.save_screenshot(p)
    return os.path.relpath(p, PROJECT_ROOT)


def _click_js_fallback(driver, el):
    """原生点击不可交互（重叠/隐藏态）时 JS 直点，Vue 事件委托必达。"""
    try:
        el.click()
    except Exception:
        driver.execute_script('arguments[0].click();', el)
    return el


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--frontend', default='http://127.0.0.1:5400')
    ap.add_argument('--username', default='admin')
    ap.add_argument('--password', default='admin123')
    ap.add_argument('--test-type', default='e2e', choices=['e2e', 'api'])
    args = ap.parse_args()
    base = args.frontend.rstrip('/')
    report = {'test_type': args.test_type, 'steps': {}}

    opts = webdriver.ChromeOptions()
    opts.binary_location = CHROME_BINARY
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1680,1050')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--lang=zh-CN')
    opts.set_capability('goog:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    drv_path = _resolve_chromedriver()
    svc = webdriver.ChromeService(executable_path=drv_path) if drv_path else webdriver.ChromeService()
    driver = webdriver.Chrome(options=opts, service=svc)
    driver.set_page_load_timeout(60)
    wait = WebDriverWait(driver, 30)

    try:
        # ── 登录 ────────────────────────────────────────
        driver.get(f'{base}/#/login')
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.login-card')))
        driver.find_element(By.CSS_SELECTOR, '.login-card form input[type="text"]').send_keys(args.username)
        driver.find_element(By.CSS_SELECTOR, '.login-card form input[type="password"]').send_keys(args.password)
        driver.find_element(By.CSS_SELECTOR, '.login-card form button.login-btn').click()
        wait.until(lambda d: '/login' not in d.current_url.split('#')[-1])
        report['steps']['login'] = True

        route = '/E2ETest' if args.test_type == 'e2e' else '/APITest'
        driver.get(f'{base}/#{route}')
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.test-view-common')))
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.step-panel.active')))
        report['steps']['page_open'] = shot(driver, f'wizard_{args.test_type}_open')

        # ── Step 0: 选择算法 ────────────────────────────
        alg_cards = wait.until(EC.presence_of_all_elements_located(
            (By.CSS_SELECTOR, '.step-panel.active .algorithm-card')))
        if not alg_cards:
            report['steps']['step0'] = {'ok': False, 'err': '无算法卡片'}
            raise RuntimeError('no algorithm card')
        _click_js_fallback(driver, alg_cards[0])
        time.sleep(0.5)
        sel = driver.find_elements(By.CSS_SELECTOR, '.step-panel.active .algorithm-card.selected')
        report['steps']['step0'] = {'ok': bool(sel), 'algo_name': alg_cards[0].text.strip()[:60]}
        shot(driver, f'wizard_{args.test_type}_step0_algorithm_selected')
        driver.find_element(By.CSS_SELECTOR, '.step-panel.active .step-actions .btn-primary').click()

        # ── Step 1: 选择用例 ────────────────────────────
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.test-case-list-container')))
        time.sleep(1.0)
        # 默认标签视图无卡片，先切到分组视图
        group_toggle = driver.find_elements(By.CSS_SELECTOR,
                                            '.view-switcher .btn-toggle')
        for btn in group_toggle:
            if 'group' in (btn.get_attribute('title') or '').lower() \
               or '分组' in (btn.get_attribute('title') or ''):
                btn.click()
                break
        time.sleep(1.2)
        # 分组视图下可能需展开分组
        cards_sel = '.step-panel.active .case-card'
        for _ in range(10):
            case_cards = driver.find_elements(By.CSS_SELECTOR, cards_sel)
            if case_cards:
                break
            # 点击分组头展开
            group_heads = driver.find_elements(
                By.CSS_SELECTOR,
                '.step-panel.active .group-header, .step-panel.active .group-item, '
                '.step-panel.active .group-row, .step-panel.active .group-name')
            if not group_heads:
                time.sleep(0.8)
                continue
            _click_js_fallback(driver, group_heads[0])
            time.sleep(0.8)
        report['steps']['step1'] = {'ok': False, 'err': '无用例卡片', 'visible': len(case_cards)}
        if not case_cards:
            panel_html = driver.find_element(By.CSS_SELECTOR,
                                             '.step-panel.active').get_attribute('innerHTML')
            report['steps']['step1']['panel_snippet'] = panel_html[:800]
            report['steps']['step1']['panel_text'] = driver.find_element(
                By.CSS_SELECTOR, '.step-panel.active').text[:400]
            shot(driver, f'wizard_{args.test_type}_step1_no_cards')
        if case_cards:
            _click_js_fallback(driver, case_cards[0])
            time.sleep(0.5)
            checked = driver.find_elements(By.CSS_SELECTOR,
                                           '.step-panel.active .case-card.card-selected')
            report['steps']['step1'] = {'ok': bool(checked),
                                        'selected_name': case_cards[0].text.strip()[:60],
                                        'visible': len(case_cards)}
            shot(driver, f'wizard_{args.test_type}_step1_cases_selected')
            # 下一步
            next_btn = driver.find_element(By.CSS_SELECTOR,
                                           '.step-panel.active .step-actions .btn-primary')
            next_btn.click()

        # ── Step 2: 选择设备/API ────────────────────────
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.resource-grid-container')))
        time.sleep(1.0)
        res_cards = driver.find_elements(By.CSS_SELECTOR, '.step-panel.active .resource-card')
        online = [c for c in res_cards
                  if c.find_elements(By.CSS_SELECTOR, '.status-online')
                  or 'online' in (c.get_attribute('class') or '')]
        report['steps']['step2'] = {'ok': False, 'err': '无资源卡片',
                                    'total': len(res_cards), 'online': len(online)}
        target = online[0] if online else res_cards[0]
        _click_js_fallback(driver, target)
        time.sleep(0.5)
        selected = driver.find_elements(By.CSS_SELECTOR, '.step-panel.active .resource-card.selected')
        # 离线卡片点击被禁用时，退化为尝试前若干卡片（在线卡不可交互时记录）
        for cand in res_cards[:8]:
            if selected:
                break
            if cand is target:
                continue
            _click_js_fallback(driver, cand)
            time.sleep(0.4)
            selected = driver.find_elements(By.CSS_SELECTOR,
                                            '.step-panel.active .resource-card.selected')
        report['steps']['step2'] = {'ok': bool(selected),
                                    'name': (selected[0].text.strip()[:60] if selected
                                             else target.text.strip()[:60]),
                                    'total': len(res_cards), 'online': len(online)}
        shot(driver, f'wizard_{args.test_type}_step2_resource_selected')
        # 开始任务
        start_btns = driver.find_elements(By.CSS_SELECTOR, '.step-panel.active .step-actions .btn-primary')
        if start_btns:
            start_btns[0].click()
        else:
            report['steps']['step2']['ok'] = False
            report['steps']['step2']['err'] = '未找到开始任务按钮'
            raise RuntimeError('start task button missing')

        # ── Step 3: 执行 ────────────────────────────────
        exec_ok = False
        for _ in range(30):
            els = driver.find_elements(By.CSS_SELECTOR, '.step-panel.active .step-title')
            titles = [e.text for e in els]
            if any('执行' in t for t in titles):
                exec_ok = True
                break
            # 可能出现 toast（如无在线设备报错）
            time.sleep(1)
        report['steps']['step3'] = {'ok': exec_ok}
        shot(driver, f'wizard_{args.test_type}_step3_execution')
        # 收集执行面板文本（状态 / 进度）
        time.sleep(3)
        body = driver.find_element(By.CSS_SELECTOR, '.step-panel.active').text[:800].replace('\n', ' | ')
        report['steps']['step3']['body_preview'] = body
        shot(driver, f'wizard_{args.test_type}_step3_execution_later')

        # ── 任务列表核验 ────────────────────────────────
        driver.get(f'{base}/#/tasks')
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, '.tasks-view')))
        time.sleep(2)
        rows = driver.find_elements(By.CSS_SELECTOR, '.tasks-view .task-item, .tasks-view tbody tr, .tasks-view .task-row')
        report['steps']['task_list'] = {'ok': len(rows) > 0, 'rows': len(rows)}
        shot(driver, f'wizard_{args.test_type}_tasks_list')

    except Exception as exc:
        report['error'] = f'{type(exc).__name__}: {str(exc)[:300]}'
        try:
            shot(driver, f'wizard_{args.test_type}_FAIL')
        except Exception:
            pass
    finally:
        try:
            driver.quit()
        except Exception:
            pass

    print(json.dumps(report, ensure_ascii=False, indent=2))
    out = os.path.join(ARTIFACT_ROOT, f'wizard_{args.test_type}_report.json')
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    print(f'WIZARD_JSON={out}')


if __name__ == '__main__':
    main()
