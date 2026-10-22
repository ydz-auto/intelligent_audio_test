# -*- coding: utf-8 -*-
"""INT-1279 P2 复测：报告具体用例入口 dimension_ids 异步源竞态。

复现审计打回路径：/report/480（源任务 419），CDP 预注入延迟源任务详情
`/tasks/419`（10s，不延迟 case-results/reviews）→ 用例卡先渲染 → 立即点「快速复核」
→ 修复后发起前 await 源任务详情解析 → POST /tasks/results/ai-review 请求体带
dimension_ids → 响应 200（不再静默缺省 400 code 203）。

断言三件事：
1. 点击发生在源任务详情解析完成前（竞态真实命中）；
2. ai-review 请求体含 dimension_ids 与 result_ids；
3. ai-review 响应 200。
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
    os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1279_p2_race')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'

# CDP 预注入：每次新文档都执行——延迟源任务详情 /tasks/419（排除 case-results /cases/ 与 /reviews/），
# 同时打点 ai-review 调用（body/status/response）。
PATCH = r'''
window.__taskDetailResolved = false;
window.__taskDetailStartedAt = 0;
window.__taskDetailResolvedAt = 0;
window.__clickTs = 0;
window.__aiReviewCalls = [];
const __origFetch = window.fetch;
window.fetch = function(...args) {
  const url = typeof args[0] === 'string' ? args[0] : (args[0] && args[0].url) || '';
  const init = args[1] || {};
  const method = init.method || 'GET';
  let body = init.body || '';
  if (typeof body !== 'string') { try { body = JSON.stringify(body); } catch(e) {} }
  // 仅延迟源任务详情（task detail），不延迟 case-results / reviews / ai-review
  if (/\/tasks\/419$|\/tasks\/419[/?]/.test(url) && !/\/cases\//.test(url) && !/\/reviews\//.test(url) && url.indexOf('/tasks/results/') === -1) {
    window.__taskDetailStartedAt = Date.now();
    return new Promise((resolve, reject) => {
      setTimeout(() => {
        __origFetch.apply(this, args).then((r) => {
          window.__taskDetailResolved = true;
          window.__taskDetailResolvedAt = Date.now();
          resolve(r);
        }, reject);
      }, 18000);
    });
  }
  return __origFetch.apply(this, args).then((resp) => {
    if (url.indexOf('/tasks/results/ai-review') !== -1 || url.indexOf('ai-review') !== -1) {
      const cloned = resp.clone();
      cloned.text().then((t) => {
        window.__aiReviewCalls.push({ url: url, method: method, body: body, status: resp.status, response: t.slice(0, 600), ts: Date.now() });
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
    drv.set_page_load_timeout(60)
    # CDP 预注入：跨整页导航存活
    try:
        drv.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': PATCH})
        print('CDP pre-inject OK')
    except Exception as e:
        print('CDP pre-inject FAILED:', e)
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
        # patch 是否存活（新文档应重挂）
        alive = drv.execute_script('return typeof window.__origFetch !== "undefined"')
        print('patch alive on dashboard:', alive)
        drv.get(BASE + '/report/480')
        # 等「快速复核」按钮进 DOM（报告数据快于源任务详情；不滚动、尽早点击）
        WebDriverWait(drv, 90).until(
            lambda d: d.find_elements(By.XPATH, "//button[contains(., '快速复核')]"))
        time.sleep(0.5)
        btns = drv.find_elements(By.XPATH, "//button[contains(., '快速复核')]")
        print('quick review buttons:', len(btns))
        drv.execute_script('window.__clickTs = Date.now();')
        if not btns:
            raise SystemExit('NO quick review button')
        # 立即 JS 点击第一个（不等滚动）
        drv.execute_script("arguments[0].click()", btns[0])
        # 弹窗（发起前 await 源任务详情解析，10s 延迟 + case-results 网关慢，给足 90s）
        WebDriverWait(drv, 90).until(
            lambda d: d.find_elements(By.CSS_SELECTOR, "[data-slot='quick-ai-review-dialog']"))
        time.sleep(1)
        launch = drv.find_elements(By.XPATH, "//button[contains(., '发起快速复核')]")
        if not launch:
            raise SystemExit('NO launch button')
        os.makedirs(ARTIFACTS, exist_ok=True)
        drv.save_screenshot(os.path.join(ARTIFACTS, 'dialog_light.png'))
        launch[0].click()
        time.sleep(8)
        d = os.path.join(ARTIFACTS)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'calls.json'), 'w', encoding='utf-8') as f:
            json.dump(drv.execute_script('return window.__aiReviewCalls || []'), f, ensure_ascii=False, indent=1)
        timing = drv.execute_script(
            'return { started: window.__taskDetailStartedAt, resolved: window.__taskDetailResolvedAt, '
            'click: window.__clickTs, resolvedFlag: window.__taskDetailResolved }')
        print('TIMING:', json.dumps(timing))
        calls = drv.execute_script('return window.__aiReviewCalls || []')
        print('=== ai-review calls ===')
        for c in calls:
            print(json.dumps(c, ensure_ascii=False)[:400])
        race_hit = bool(timing['click'] and timing['resolved'] and timing['click'] < timing['resolved'])
        print('RACE_HIT (click before task detail resolved):', race_hit)
        # 取 POST 调用（GET 是 ai-reviews 列表轮询，body 空）
        posts = [c for c in calls if (c.get('method') or '').upper() == 'POST']
        if posts:
            p = posts[0]
            body = p.get('body') or ''
            ok = p.get('status') == 200
            has_dims = 'dimension_ids' in body and 'result_ids' in body
            print('POST_BODY:', body[:300])
            print('POST_STATUS:', p.get('status'))
            print('STATUS_OK:', ok, 'HAS_DIMS:', has_dims)
            if ok and has_dims and race_hit:
                print('PASS_P2_RACE')
            else:
                print('FAIL_P2_RACE (need ok + has_dims + race_hit)')
        else:
            print('NO_POST_CALL')
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == '__main__':
    main()
