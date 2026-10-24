# -*- coding: utf-8 -*-
"""INT-1626 验收第三轮：容器详情内提交人工复核后，徽章/抽屉按源任务聚合刷新。

初始状态：源任务 561 两条留痕（6926 容器引用 / 6927 未入容器）。
本轮在容器 562 行内再提交一条复核（同一结果 6926）：
- 徽章仍「已复核 1 条」（按结果去重）；
- 抽屉「共 2 条」（同结果多次留痕，历史不覆盖）；
- 请求命中 /tasks/results/561/review-history，不存在 562 的历史查询。
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('BASE', 'http://127.0.0.1:15326')
CONTAINER = int(os.environ.get('TASK', '562'))
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
    ev = {'steps': []}
    try:
        d.get(BASE + '/')
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")
        d.get('%s/tasks/%d' % (BASE, CONTAINER))
        wait_text(d, '已复核 1 条')
        time.sleep(1.5)

        row_review = None
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if (b.get_attribute('aria-label') or '') == '人工复核':
                row_review = b
                break
        assert row_review is not None, '未找到行内「人工复核」按钮'
        js_click(d, row_review)
        time.sleep(1.5)
        dlg = d.find_element(By.CSS_SELECTOR, "[data-slot='manual-review-dialog']")
        ev['steps'].append('dialog_opened')

        # 选执行状态（第一个 combobox）；当前结果已是 failed，改选「执行完成」才允许改判
        combos = dlg.find_elements(By.CSS_SELECTOR, "[role='combobox']")
        assert combos, '弹窗内无状态下拉'
        js_click(d, combos[0])
        time.sleep(0.8)
        opt = None
        for label in ('执行完成', '已完成', '执行失败'):
            for o in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
                if o.is_displayed() and label in (o.text or ''):
                    opt = o
                    break
            if opt is not None:
                break
        if opt is None:
            for o in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
                if o.is_displayed() and o.text.strip():
                    opt = o
                    break
        assert opt is not None, '无可用状态选项'
        ev['steps'].append('status_selected:' + opt.text.strip())
        js_click(d, opt)
        time.sleep(0.6)

        ta = dlg.find_element(By.CSS_SELECTOR, "textarea[data-slot='review-comment']")
        js_click(d, ta)
        ta.send_keys(Keys.CONTROL, 'a')
        ta.send_keys(Keys.DELETE)
        ta.send_keys('接线测试_INT1626_容器页内复核')
        time.sleep(0.5)

        submit = None
        for b in dlg.find_elements(By.TAG_NAME, 'button'):
            if '提交复核' in (b.text or ''):
                submit = b
                break
        assert submit is not None, '未找到提交复核按钮'
        assert submit.is_enabled(), '提交按钮不可用'
        js_click(d, submit)
        time.sleep(3)
        ev['after_submit_text'] = [ln for ln in body(d).splitlines() if '复核' in ln][:12]
        shot(d, '10_after_submit')
        ev['net_submit'] = net(d)

        # 徽章仍 1 条 + 抽屉 2 条
        wait_text(d, '已复核 1 条', 60)
        time.sleep(1)
        ev['badge_after'] = '已复核 1 条' in body(d)
        d.execute_script('window.__net = []')
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if '查看复核历史' in (b.text or ''):
                js_click(d, b)
                break
        wait_text(d, '共 2 条', 60)
        time.sleep(1)
        t = body(d)
        ev['drawer_after'] = {
            'total_2': '共 2 条' in t,
            'has_new_comment': '接线测试_INT1626_容器页内复核' in t,
            'has_old_comment': '接线测试_INT1626_人工复核备注' in t,
            'leaks_other_result': '接线测试_INT1626_未入容器留痕' in t,
        }
        ev['net_drawer_after'] = net(d)
        shot(d, '11_drawer_after_submit')
    finally:
        with open(os.path.join(OUT, 'evidence_int1626_round3.json'), 'w', encoding='utf-8') as f:
            json.dump(ev, f, ensure_ascii=False, indent=1)
        d.quit()
        print('EVIDENCE', os.path.join(OUT, 'evidence_int1626_round3.json'))


if __name__ == '__main__':
    main()
