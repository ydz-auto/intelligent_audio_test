# -*- coding: utf-8 -*-
"""INT-1506 批量设置评估维度·轮次实测（真实库栈 5700 / dev 5321）。

选中两个 2 轮用例 → 批量设置评估维度 → 逐轮设置/指定轮次只出「第 1 轮」「第 2 轮」，
不再出现写死的第 3/4 轮；附浅/深色截图。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5321')
CHROME = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
ART = 'tests/ui/artifacts/int1506'
os.makedirs(ART, exist_ok=True)


def main():
    o = Options()
    o.binary_location = CHROME
    for a in ('--headless=new', '--window-size=1680,1200', '--disable-gpu', '--no-sandbox', '--lang=zh-CN'):
        o.add_argument(a)
    d = webdriver.Chrome(options=o, service=Service())
    d.set_script_timeout(120)
    ok = False
    try:
        d.get(BASE + '/login')
        WebDriverWait(d, 25).until(EC.presence_of_element_located((By.ID, 'username')))
        d.find_element(By.ID, 'username').send_keys('接线测试_admin')
        d.find_element(By.ID, 'password').send_keys('JieXianTest@2026')
        d.find_element(By.XPATH, "//button[contains(., '登') and contains(., '录')]").click()
        WebDriverWait(d, 60).until(lambda x: '/login' not in x.current_url)
        time.sleep(2)
        d.execute_script(
            "localStorage.setItem('iatp:algorithm:v1', JSON.stringify({state:{algorithmId:'voice_llm'},version:0}));"
        )
        for theme in ('light', 'dark'):
            d.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", theme)
            d.get(BASE + '/testcases/by-group')
            box = WebDriverWait(d, 60).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[aria-label='搜索用例']"))
            )
            box.send_keys('测试用例_HJ05')
            # 等用例卡出现
            WebDriverWait(d, 120).until(
                lambda x: x.execute_script(
                    "return document.querySelectorAll(\"button[aria-label='编辑用例']\").length > 0"
                )
            )
            time.sleep(1)
            headers = d.find_elements(
                By.XPATH, "//div[contains(@class,'cursor-pointer') and .//span[contains(., '条')]]"
            )
            for h in headers:
                try:
                    d.execute_script('arguments[0].scrollIntoView({block:"center"});', h)
                    h.click()
                    time.sleep(0.2)
                except Exception:
                    pass
            time.sleep(1)
            n = d.execute_script(
                """
                const cbs = Array.from(document.querySelectorAll("[aria-label^='选择 ']")).slice(0, 2);
                cbs.forEach(cb => { cb.scrollIntoView({block:'center'}); cb.click(); });
                return cbs.map(c => c.getAttribute('aria-label'));
                """
            )
            print(theme, 'selected', json.dumps(n, ensure_ascii=False)[:200])
            time.sleep(0.8)
            btn = WebDriverWait(d, 20).until(
                EC.element_to_be_clickable((By.XPATH, "//button[normalize-space(.)='批量设置评估维度']"))
            )
            btn.click()
            time.sleep(1.2)
            d.find_element(By.XPATH, "//label[contains(normalize-space(.), '逐轮设置')]").click()
            time.sleep(0.8)
            tabs = d.execute_script(
                """
                const bar = document.querySelector("[data-testid='batch-dim-round-cloud']");
                const scope = bar ? bar.parentElement.previousElementSibling : null;
                const root = document.querySelector("[role='dialog']");
                const btns = Array.from(root.querySelectorAll('button'))
                  .map(b => (b.textContent || '').trim())
                  .filter(t => /^第\\s*\\d+\\s*轮$/.test(t));
                return [...new Set(btns)];
                """
            )
            print(theme, '逐轮 tabs', tabs)
            d.save_screenshot(os.path.join(ART, f'batch_dimensions_rounds_{theme}.png'))
            # 指定轮次
            d.find_element(By.XPATH, "//label[contains(normalize-space(.), '指定轮次')]").click()
            time.sleep(0.8)
            specific = d.execute_script(
                """
                const root = document.querySelector("[role='dialog']");
                return [...new Set(Array.from(root.querySelectorAll('label'))
                  .map(l => (l.textContent || '').trim())
                  .filter(t => /^第\\d+轮$/.test(t)))];
                """
            )
            print(theme, '指定轮次', specific)
            expected_tabs = ['第 1 轮', '第 2 轮']
            expected_specific = ['第1轮', '第2轮']
            if theme == 'light':
                ok = tabs == expected_tabs and specific == expected_specific
            d.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
            time.sleep(0.6)
        print('批量轮次判定:', 'PASS' if ok else 'FAIL')
    finally:
        d.quit()


if __name__ == '__main__':
    main()
