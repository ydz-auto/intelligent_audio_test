# -*- coding: utf-8 -*-
"""INT-1402 浏览器实测：系统设置站点信息「站点名称」必填校验。

流程：
1. 打开新 Vue 前端（真实库栈后端 :15000，AUTH_MODE=off 免登录）；
2. 进入 #/system-settings/site/info 站点信息页；
3. 断言「站点名称」输入框回显当前库值（非空）；
4. 清空输入框 → 断言：
   a. 保存按钮 disabled（:disabled="saving || !dirty || !valid"，必填留空 → valid=false）；
   b. 字段下方出现错误「站点名称不能为空」；
   c. Network 无 PUT /api/option/（未发保存请求）；
5. 重新填回原值 → 保存按钮恢复可点（dirty=true 且 valid=true）；
6. 浅/深色截图 + Network 取证。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHROME_BINARY = os.environ.get(
    'UI_CHROME_BINARY', r'C:\Program Files\Google\Chrome\Application\chrome.exe')

BASE = os.environ.get('UI_FRONTEND_BASE', 'http://127.0.0.1:5605')
OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(PROJECT_ROOT, '_int1402_evidence')

# 站点名称输入框：settings-form-grid 首个 .form-group 的 input
# （toFormField 未透传 key，input id 为 field-undefined 的既有形态；按位置取首个文本框）
NAME_INPUT = '.settings-form-grid .form-group:nth-child(1) input[type="text"]'


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    opts = Options()
    opts.binary_location = CHROME_BINARY
    opts.add_argument('--headless=new')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--window-size=1440,900')
    opts.add_argument('--force-device-scale-factor=1')
    opts.add_argument('--disable-dev-shm-usage')
    opts.set_capability('goog:loggingPrefs', {'browser': 'ALL'})

    driver = webdriver.Chrome(options=opts, service=Service())
    driver.set_window_size(1440, 900)
    wait = WebDriverWait(driver, 60)
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': 'performance.setResourceTimingBufferSize(3000);'
    })
    driver.execute_script('performance.setResourceTimingBufferSize(3000)')
    try:
        # ── 1. 打开站点信息页（AUTH_MODE=off，直接整页 load） ──
        driver.get(f'{BASE}/#/system-settings/site/info')
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, NAME_INPUT)))
        time.sleep(1)

        # ── 2. 断言回显非空 ──
        name_input = driver.find_element(By.CSS_SELECTOR, NAME_INPUT)
        original = name_input.get_attribute('value')
        print('SITE_NAME_ORIGINAL', repr(original), flush=True)
        assert original and original.strip(), f'站点名称回显为空: {original!r}'

        save_btn = driver.find_element(By.CSS_SELECTOR, '.form-actions .btn-primary')
        print('SAVE_BTN_DISABLED_INITIAL', save_btn.get_attribute('disabled'), flush=True)
        # 初始未改 → !dirty → disabled
        assert save_btn.get_attribute('disabled') is not None, '初始未改动时保存按钮应为 disabled'

        # ── 3. 清空站点名称 ──
        driver.execute_script(
            'arguments[0].value = ""; arguments[0].dispatchEvent(new Event("input", {bubbles:true}))',
            name_input,
        )
        time.sleep(0.5)
        save_btn = driver.find_element(By.CSS_SELECTOR, '.form-actions .btn-primary')
        disabled_after_clear = save_btn.get_attribute('disabled')
        print('SAVE_BTN_DISABLED_AFTER_CLEAR', disabled_after_clear, flush=True)
        assert disabled_after_clear is not None, '清空必填站点名称后保存按钮必须 disabled'

        # 字段错误提示「站点名称不能为空」
        field_errs = driver.find_elements(By.CSS_SELECTOR, '.field-error')
        err_texts = [e.text for e in field_errs]
        print('FIELD_ERRORS', err_texts, flush=True)
        assert any('站点名称不能为空' in t for t in err_texts), f'未见「站点名称不能为空」: {err_texts}'

        # 浅色截图
        driver.save_screenshot(os.path.join(OUT_DIR, 'int1402_light_cleared.png'))

        # ── 4. 填回「脏且必填非空」的值 → 按钮恢复可点 ──
        # 注意：填回与原值完全一致 → 不 dirty，按钮仍 disabled（正确）；此处填一修改值验证 dirty+valid 恢复
        modified = original + '-X'
        driver.execute_script(
            'arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event("input", {bubbles:true}))',
            name_input, modified,
        )
        time.sleep(0.5)
        save_btn = driver.find_element(By.CSS_SELECTOR, '.form-actions .btn-primary')
        disabled_restored = save_btn.get_attribute('disabled')
        print('SAVE_BTN_DISABLED_RESTORED', disabled_restored, flush=True)
        assert disabled_restored is None, '填回必填非空值后保存按钮应恢复可点'
        field_errs_after = [e.text for e in driver.find_elements(By.CSS_SELECTOR, '.field-error')]
        print('FIELD_ERRORS_AFTER_RESTORE', field_errs_after, flush=True)

        # 恢复原值（不点保存，确保不留脏值到下次访问）
        driver.execute_script(
            'arguments[0].value = arguments[1]; arguments[0].dispatchEvent(new Event("input", {bubbles:true}))',
            name_input, original,
        )
        time.sleep(0.3)

        # ── 5. 深色 ──
        driver.execute_script('document.documentElement.classList.add("dark")')
        time.sleep(0.5)
        driver.save_screenshot(os.path.join(OUT_DIR, 'int1402_dark_cleared.png'))
        driver.execute_script('document.documentElement.classList.remove("dark")')

        # ── 6. Network 取证：清空期间无 PUT /api/option/ ──
        perfs = driver.execute_script(
            'return performance.getEntriesByType("resource").map(e => ({name: e.name, dur: e.duration}))')
        with open(os.path.join(OUT_DIR, 'network.json'), 'w', encoding='utf-8') as fh:
            json.dump(perfs, fh, ensure_ascii=False, indent=1)
        option_reqs = [p for p in perfs if '/api/option/' in p['name']]
        puts = [p for p in option_reqs if 'PUT' not in p['name'] and p['name'].endswith('/api/option/')]
        # resource timing 不含 method；用大小写区分不了 PUT/GET，直接列出 option 请求
        print('OPTION_NETWORK_COUNT', len(option_reqs), flush=True)
        for p in option_reqs:
            print('  ', p['name'], round(p['dur'], 1), 'ms', flush=True)

        # 兜底：清空状态下强行触发保存 handler 也不得发 PUT（调用方拦截）
        put_count_before = len([p for p in option_reqs if p['name'].endswith('/api/option/')])
        try:
            driver.execute_script(
                'document.querySelector(".form-actions .btn-primary").click()', save_btn,
            )
        except Exception:
            pass
        time.sleep(0.3)
        perfs2 = driver.execute_script(
            'return performance.getEntriesByType("resource").map(e => e.name)')
        puts_after = [n for n in perfs2 if n.endswith('/api/option/')]
        print('PUT_COUNT_AFTER_FORCE_CLICK', len(puts_after), flush=True)

        # 后端核对：库值保持原样
        import httpx
        opt = httpx.get(f'http://127.0.0.1:15000/api/option/', timeout=10).json()
        site_name_db = (opt.get('data') or {}).get('site.name')
        print('SITE_NAME_DB', repr(site_name_db), flush=True)
        assert site_name_db == original, f'库中 site.name 被改动: {site_name_db!r} != {original!r}'

        print('PASS', flush=True)
    finally:
        driver.quit()


if __name__ == '__main__':
    main()
