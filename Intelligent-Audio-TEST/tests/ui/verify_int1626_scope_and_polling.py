# -*- coding: utf-8 -*-
"""INT-1626 验收第二轮：范围裁剪 / 普通任务回归 / 快速复核轮询键。

- 源任务 561 现有 2 条留痕：6926（容器 562 引用，备注「人工复核备注」）、
  6927（未入容器，备注「未入容器留痕」）。
- 预期：容器 562 徽章/抽屉只含 6926（1 条）；普通任务 561 徽章 2 条、抽屉 2 条。
- 容器行「快速复核」发起后，轮询 /tasks/results/{task_id}/ai-review-history 的 task_id 必须是 561。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('BASE', 'http://127.0.0.1:15326')
CONTAINER = int(os.environ.get('TASK', '562'))
SRC = int(os.environ.get('SRC', '561'))
OUT = os.environ.get('OUT', 'tests/ui/artifacts/int1626')
DRIVER = r'D:/00_user_data/.cache/selenium/chromedriver/win64/155.0.8059.84/chromedriver.exe'
os.makedirs(OUT, exist_ok=True)

RECORDER = """
window.__net = [];
try {
  const _f = window.fetch;
  window.fetch = function() {
    try {
      const a = arguments[0];
      const u = (typeof a === 'string') ? a : (a && a.url);
      const m = (arguments[1] && arguments[1].method) || 'GET';
      window.__net.push({url: String(u), method: m, t: Date.now()});
    } catch (e) {}
    return _f.apply(this, arguments);
  };
} catch (e) {}
"""


def driver():
    opts = webdriver.ChromeOptions()
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1600,1000')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--lang=zh-CN')
    d = webdriver.Chrome(service=Service(DRIVER), options=opts)
    d.set_script_timeout(60)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': RECORDER})
    return d


def body(d):
    return d.find_element(By.TAG_NAME, 'body').text or ''


def wait_text(d, needle, timeout=120):
    WebDriverWait(d, timeout).until(lambda x: needle in body(x))


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def shot(d, name):
    p = os.path.join(OUT, name + '.png')
    d.save_screenshot(p)
    print('SHOT', p)


def net(d):
    return [n for n in (d.execute_script('return window.__net || []')) if '/api/v1/' in n['url']]


def main():
    d = driver()
    ev = {}
    try:
        d.get(BASE + '/')
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")

        # 1) 容器 562：只含容器引用的结果留痕
        d.get('%s/tasks/%d' % (BASE, CONTAINER))
        wait_text(d, '已复核 1 条')
        time.sleep(1.5)
        ev['container_badge_only_one'] = '已复核 1 条' in body(d)
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if '查看复核历史' in (b.text or ''):
                js_click(d, b)
                break
        wait_text(d, '共 1 条', 60)
        time.sleep(1)
        t = body(d)
        ev['container_drawer'] = {
            'total_1': '共 1 条' in t,
            'has_container_comment': '接线测试_INT1626_人工复核备注' in t,
            'leaks_other_result': '接线测试_INT1626_未入容器留痕' in t,
        }
        shot(d, '06_container_drawer_trimmed')
        d.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
        time.sleep(1)

        # 2) 普通任务 561 回归：徽章/抽屉按后端 review_count
        d.execute_script('window.__net = []')
        d.get('%s/tasks/%d' % (BASE, SRC))
        wait_text(d, '已复核 2 条')
        time.sleep(1.5)
        ev['src_badge_two'] = '已复核 2 条' in body(d)
        ev['src_net'] = net(d)
        shot(d, '07_normal_task_badge')
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if '查看复核历史' in (b.text or ''):
                js_click(d, b)
                break
        wait_text(d, '共 2 条', 60)
        time.sleep(1)
        t = body(d)
        ev['src_drawer'] = {
            'total_2': '共 2 条' in t,
            'has_both': ('接线测试_INT1626_人工复核备注' in t and '接线测试_INT1626_未入容器留痕' in t),
        }
        shot(d, '08_normal_task_drawer')
        d.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
        time.sleep(1)

        # 3) 容器行「快速复核」→ 发起 → 轮询键
        d.get('%s/tasks/%d' % (BASE, CONTAINER))
        wait_text(d, '已复核 1 条')
        time.sleep(1.5)
        j = d.execute_script('window.__net = []')
        quick = None
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if (b.get_attribute('aria-label') or '') == '快速复核':
                quick = b
                break
        assert quick is not None, '未找到「快速复核」按钮'
        js_click(d, quick)
        time.sleep(2)
        launch = None
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if '发起快速复核' in (b.text or ''):
                launch = b
                break
        assert launch is not None, '未找到「发起快速复核」按钮'
        js_click(d, launch)
        time.sleep(16)  # 轮询间隔 3s，观察多轮
        ev['quick_net'] = net(d)
        ev['quick_dialog_text'] = body(d)
        shot(d, '09_quick_ai_review_polling')
    finally:
        with open(os.path.join(OUT, 'evidence_int1626_round2.json'), 'w', encoding='utf-8') as f:
            json.dump(ev, f, ensure_ascii=False, indent=1)
        d.quit()
        print('EVIDENCE', os.path.join(OUT, 'evidence_int1626_round2.json'))


if __name__ == '__main__':
    main()
