# -*- coding: utf-8 -*-
"""INT-1279 验收：fetch 打点捕获 ai-review 响应状态（Chrome 155 fetch patch）。"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_DEV_BASE', 'http://127.0.0.1:5399')
ARTIFACTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1279_fetch_patch')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

PATCH = r'''
window.__aiReviewCalls = [];
const __origFetch = window.fetch;
window.fetch = function(...args) {
  const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
  const init = args[1] || {};
  const method = init.method || 'GET';
  let body = init.body || '';
  if (typeof body !== 'string') { try { body = JSON.stringify(body); } catch(e) {} }
  return __origFetch.apply(this, args).then((resp) => {
    if (url.indexOf('/tasks/results/ai-review') !== -1 || url.indexOf('ai-review') !== -1) {
      const cloned = resp.clone();
      cloned.text().then((t) => {
        window.__aiReviewCalls.push({
          url: url, method: method, body: body, status: resp.status,
          response: t.slice(0, 800), ts: Date.now(),
        });
      }).catch(() => {});
    }
    return resp;
  }).catch((err) => {
    if (url.indexOf('ai-review') !== -1) {
      window.__aiReviewCalls.push({ url: url, method: method, body: body, status: 'ERR', response: String(err) });
    }
    throw err;
  });
};
'''


def _driver():
    options = Options()
    options.binary_location = CHROME_BINARY
    options.add_argument('--headless=new')
    options.add_argument('--window-size=1680,1050')
    options.add_argument('--disable-gpu')
    options.add_argument('--no-sandbox')
    options.add_argument('--lang=zh-CN')
    options.set_capability('goog:loggingPrefs', {'browser': 'ALL', 'performance': 'ALL'})
    service = Service()
    drv = webdriver.Chrome(options=options, service=service)
    drv.set_page_load_timeout(45)
    return drv


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
        WebDriverWait(drv, 30).until(lambda d: len(d.find_elements(By.XPATH, "//button[contains(., '快速复核')]")) > 0)
        time.sleep(1)
        # inject fetch patch
        drv.execute_script(PATCH)
        btns = drv.find_elements(By.XPATH, "//button[contains(., '快速复核')]")
        btns[0].click()
        WebDriverWait(drv, 15).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "[data-slot='quick-ai-review-dialog']"))
        time.sleep(1)
        launch = drv.find_elements(By.XPATH, "//button[contains(., '发起快速复核')]")
        launch[0].click()
        time.sleep(6)
        calls = drv.execute_script('return window.__aiReviewCalls || []')
        d = os.path.join(ARTIFACTS)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'calls.json'), 'w', encoding='utf-8') as f:
            json.dump(calls, f, ensure_ascii=False, indent=1)
        print('=== ai-review calls (fetch hook) ===')
        for c in calls:
            print(json.dumps(c, ensure_ascii=False)[:400])
        if not calls:
            print('NO CALLS CAPTURED')
        else:
            ok = calls[0].get('status') == 200
            has_dims = 'dimension_ids' in (calls[0].get('body') or '')
            print('STATUS_OK:', ok, 'HAS_DIMS:', has_dims)
            if ok and has_dims:
                print('PASS')
            else:
                print('FAIL')
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
