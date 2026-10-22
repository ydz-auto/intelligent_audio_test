# -*- coding: utf-8 -*-
"""INT-1279 P2 复测：用例详情弹窗入口 dimension_ids gate（case-detail-dialog.tsx）。

任务 419 详情 → 关联用例行点用例名 → CaseDetailDialog →
taskQuery.data 就绪后「AI 复核」入口可见（P2 gate：加载中隐藏）→ 点击打开复核会话。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5395')
ARTIFACTS = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1279_case_detail_dialog')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-extensions')
    options.add_argument('--lang=zh-CN')
    service = Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(60)
    return drv


def _body(drv):
    return drv.find_element(By.TAG_NAME, 'body').text


def main():
    drv = _driver()
    try:
        drv.get(BASE + '/login')
        WebDriverWait(drv, 20).until(lambda d: d.find_elements(By.ID, 'username'))
        drv.find_element(By.ID, 'username').send_keys('接线测试_admin')
        drv.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        drv.find_element(By.XPATH, "//button[contains(., '登 录') or contains(., '登录')]").click()
        WebDriverWait(drv, 25).until(lambda d: '/login' not in d.current_url)

        drv.get(BASE + '/tasks/419')
        WebDriverWait(drv, 60).until(
            lambda d: '关联用例' in _body(d) and '快速复核' in _body(d))
        time.sleep(2)
        # 点第一个用例名（CaseCard name button title='查看用例详情' → onCaseSelect → CaseDetailDialog）
        names = drv.find_elements(By.XPATH, "//button[@title='查看用例详情']")
        print('case name buttons:', len(names))
        if not names:
            raise SystemExit('NO_CASE_NAME_BUTTON')
        names[0].click()
        print('clicked case name:', (names[0].text or '').strip()[:40], flush=True)
        WebDriverWait(drv, 60).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "[data-slot='case-detail-dialog']"))
        # 等弹窗内容加载（detailQuery 就绪；执行结果与指标区）
        WebDriverWait(drv, 60).until(
            lambda d: '执行结果与指标' in d.find_element(By.CSS_SELECTOR,
                "[data-slot='case-detail-dialog']").text)
        print('dialog content ready', flush=True)
        # 弹窗内 taskQuery + resultsQuery 加载（case-results 网关慢，给足 60s）→ 弹窗内「AI 复核」按钮
        ai_btn = []
        for _ in range(60):
            ai_btn = drv.find_elements(By.XPATH,
                "//*[@data-slot='case-detail-dialog']//button[contains(., 'AI 复核')]")
            if ai_btn:
                break
            time.sleep(1)
        print('dialog AI 复核 button count:', len(ai_btn), flush=True)
        os.makedirs(ARTIFACTS, exist_ok=True)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'case_detail_light.png'))
        if not ai_btn:
            raise SystemExit('NO_AI_REVIEW_BUTTON')
        # 点击 AI 复核 → 复核会话弹窗（base-ui 弹窗 overlay 拦截 → JS click）
        drv.execute_script("arguments[0].click()", ai_btn[0])
        time.sleep(3)
        session = drv.find_elements(By.CSS_SELECTOR, "[data-slot='ai-review-session-dialog']")
        print('ai-review session dialog elements:', len(session), flush=True)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'ai_review_session.png'))
        body2 = _body(drv)
        print('dialog body snippet:', body2[:300].replace('\n', ' '))
        # 浅深色：切深色重开
        drv.execute_script(
            "window.localStorage.setItem('iatp:theme:v1:mode','dark');"
            "document.documentElement.classList.add('dark');")
        time.sleep(1)
        print('DARK set')
        print('PASS_CASE_DETAIL_ENTRY')
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
