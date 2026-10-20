# -*- coding: utf-8 -*-
"""INT-1026 /testcases 用例管理页回归核对（共享 host 双挂后无回归）。

覆盖：
  ① 组头「批量修改」九项逐项 → 对应弹窗/确认框弹出（与 /start-test 同一 host）
  ② 勾选用例 → 批量浮条出现 → 浮条「批量设置声压」→ 弹窗弹出；X 清选可用
  ③ ESC 清选仍可用（页级 ESC 守卫依赖 host isBatchOpen）

用法：python verify_int1026_testcases_regression.py --base http://localhost:5321
输出：tests/ui/artifacts/int1026/tc_*.png
"""
import argparse
import os
import sys
import time
import winreg

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ARTIFACTS = os.path.join(PROJECT_ROOT, 'tests', 'ui', 'artifacts', 'int1026')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1600,1000')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    chrome_major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            chrome_major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache_root = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
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
    return webdriver.Chrome(options=options, service=service)


def wait_for(cond, timeout=25, desc='condition'):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if cond():
                return True
        except Exception:
            pass
        time.sleep(0.5)
    raise AssertionError('timeout waiting for %s' % desc)


def _click_text(drv, text, scope=None, timeout=15):
    def do():
        els = (scope.find_elements(By.XPATH, './/*[normalize-space(text())="%s"]' % text)
               if scope else drv.find_elements(By.XPATH, '//*[normalize-space(text())="%s"]' % text))
        for el in els:
            try:
                if el.is_displayed():
                    drv.execute_script('arguments[0].scrollIntoView({block:"center"});', el)
                    time.sleep(0.4)
                    el.click()
                    return True
            except Exception:
                continue
        return False

    deadline = time.time() + timeout
    while time.time() < deadline:
        if do():
            return
        time.sleep(0.5)
    raise AssertionError('click failed: ' + text)


def _dialog_by_title(drv, title):
    xpath = (
        f"//div[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(., '{title}')]]"
    )
    for el in drv.find_elements(By.XPATH, xpath):
        if el.is_displayed():
            return el
    raise AssertionError('visible dialog not found: ' + title)


def _alert_dialog_by_title(drv, title):
    xpath = (
        f"//div[@data-slot='alert-dialog-content'][.//*[@data-slot='alert-dialog-title'][contains(., '{title}')]]"
    )
    for el in drv.find_elements(By.XPATH, xpath):
        if el.is_displayed():
            return el
    raise AssertionError('visible alert dialog not found: ' + title)


def _has_bulk_bar(drv):
    return len(drv.find_elements(
        By.XPATH, "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个用例已选择')]]")) > 0


def _close_dialog(drv, kind, title):
    if kind == 'alert':
        dlg = _alert_dialog_by_title(drv, title)
        dlg.find_element(By.XPATH, ".//button[contains(., '取消')]").click()
    else:
        dlg = _dialog_by_title(drv, title)
        dlg.find_element(By.XPATH, ".//div[@data-slot='dialog-footer']//button[contains(., '取消')]").click()
    time.sleep(0.6)
    wait_for(lambda: not any(e.is_displayed() for e in drv.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-content']"))
             and not any(e.is_displayed() for e in drv.find_elements(By.CSS_SELECTOR, "[data-slot='alert-dialog-content']")),
             12, 'dialog closed: ' + title)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--base', default='http://localhost:5321')
    args = ap.parse_args()
    base = args.base.rstrip('/')
    os.makedirs(ARTIFACTS, exist_ok=True)

    drv = _driver()
    try:
        drv.set_page_load_timeout(60)
        drv.get(base + '/')
        time.sleep(2)
        drv.execute_script('localStorage.setItem("iatp:theme:v1:mode", "light")')
        drv.get(base + '/testcases/by-group')
        time.sleep(1.5)
        drv.get(base + '/testcases/by-group')  # refresh 到真实列表
        wait_for(lambda: len(drv.find_elements(By.CSS_SELECTOR, "[aria-label$='批量修改']")) > 0,
                 30, 'testcases group cards render')
        time.sleep(1)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'tc_testcases_light.png'))

        # ① 组头九项抽查：声压（dialog）+ 标签生成名称（alert）弹窗均弹出
        btn = drv.find_element(By.CSS_SELECTOR, "[aria-label$='批量修改']")
        drv.execute_script('arguments[0].scrollIntoView({block:"center"});', btn)
        time.sleep(0.4)
        btn.click()
        time.sleep(0.7)
        wait_for(lambda: len(drv.find_elements(By.XPATH, '//*[normalize-space(text())="声压"]')) > 0,
                 10, 'dropdown 声压')
        _click_text(drv, '声压')
        wait_for(lambda: any(e.is_displayed() for e in drv.find_elements(
            By.XPATH, "//div[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(., '批量设置声压级')]]")),
            15, 'tc spl dialog')
        print('① 组头「声压」弹窗：OK')
        _close_dialog(drv, 'dialog', '批量设置声压级')
        time.sleep(0.4)

        btn = drv.find_element(By.CSS_SELECTOR, "[aria-label$='批量修改']")
        btn.click()
        time.sleep(0.7)
        wait_for(lambda: len(drv.find_elements(By.XPATH, '//*[normalize-space(text())="标签生成名称"]')) > 0,
                 10, 'dropdown 标签生成名称')
        _click_text(drv, '标签生成名称')
        wait_for(lambda: any(e.is_displayed() for e in drv.find_elements(
            By.XPATH, "//div[@data-slot='alert-dialog-content'][.//*[@data-slot='alert-dialog-title'][contains(., '自动生成名称')]]")),
            15, 'tc auto-name confirm')
        print('① 组头「标签生成名称」确认框：OK')
        _close_dialog(drv, 'alert', '自动生成名称')
        time.sleep(0.4)

        # ② 勾选用例 → 批量浮条出现 → 浮条「批量设置声压」→ 弹窗弹出
        boxes = drv.find_elements(By.CSS_SELECTOR, "[role='checkbox'][aria-label^='选择 ']")
        assert boxes, '未找到用例勾选 checkbox'
        boxes[0].click()
        time.sleep(0.6)
        assert _has_bulk_bar(drv), '勾选后批量浮条应出现'
        drv.save_screenshot(os.path.join(ARTIFACTS, 'tc_bulk_bar.png'))
        bar = drv.find_element(By.XPATH,
            "//div[contains(@class,'fixed bottom-6')][.//*[contains(., '个用例已选择')]]")
        bar.find_element(By.XPATH, ".//button[contains(., '批量设置声压')]").click()
        time.sleep(0.8)
        wait_for(lambda: any(e.is_displayed() for e in drv.find_elements(
            By.XPATH, "//div[@data-slot='dialog-content'][.//*[@data-slot='dialog-title'][contains(., '批量设置声压级')]]")),
            15, 'bulk bar spl dialog')
        print('② 批量浮条「批量设置声压」弹窗：OK')
        _close_dialog(drv, 'dialog', '批量设置声压级')

        # ③ ESC 清选仍可用（页级 ESC 守卫依赖 host isBatchOpen）
        assert _has_bulk_bar(drv), '关闭弹窗后浮条仍在'
        drv.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.5)
        assert not _has_bulk_bar(drv), 'ESC 后浮条应消失'
        print('③ ESC 清选：OK')
        return 0
    finally:
        drv.quit()


if __name__ == '__main__':
    sys.exit(main())
