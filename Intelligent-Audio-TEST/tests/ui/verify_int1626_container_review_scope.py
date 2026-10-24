# -*- coding: utf-8 -*-
"""INT-1626 验收：挑选合并容器（562）复核计数 / 复核历史抽屉 / AI 复核轮询按源任务（561）归属。

自建测试数据：源任务 561（1 条 test_result 6926 已人工复核）+ 容器 562（引用 6926）。
跑在旁路容器 http://127.0.0.1:15326（交付 commit 83e7abff 构建产物），后端 docker 网关 :15000。
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('BASE', 'http://127.0.0.1:15326')
TASK = int(os.environ.get('TASK', '562'))
SRC = int(os.environ.get('SRC', '561'))
RESULT_ID = int(os.environ.get('RESULT_ID', '6926'))
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


def set_theme(d, mode):
    d.get(BASE + '/')
    d.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0])", mode)


def shot(d, name):
    p = os.path.join(OUT, name + '.png')
    d.save_screenshot(p)
    print('SHOT', p)
    return p


def net(d):
    return d.execute_script('return window.__net || []')


def texts(d):
    return (d.find_element(By.TAG_NAME, 'body').text or '')


def wait_text(d, needle, timeout=90):
    WebDriverWait(d, timeout).until(lambda x: needle in texts(x))


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def main():
    d = driver()
    ev = {'base': BASE, 'task': TASK, 'source': SRC}
    try:
        set_theme(d, 'light')
        d.get('%s/tasks/%d' % (BASE, TASK))
        wait_text(d, '已复核 1 条', 120)
        time.sleep(1.5)
        ev['light_badge'] = True
        ev['light_body_snippet'] = [ln for ln in texts(d).splitlines() if '复核' in ln]
        shot(d, '01_container_badge_light')
        ev['net_after_load'] = net(d)

        # 打开复核历史抽屉
        btn = None
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if '查看复核历史' in (b.text or ''):
                btn = b
                break
        assert btn is not None, '未找到「查看复核历史」按钮'
        js_click(d, btn)
        wait_text(d, '共 1 条', 60)
        time.sleep(1.0)
        drawer = texts(d)
        ev['drawer_light'] = drawer
        ev['drawer_has'] = {
            'total_1': '共 1 条' in drawer,
            'comment': '接线测试_INT1626_人工复核备注' in drawer,
            'transition': ('completed' in drawer and 'failed' in drawer),
            'operator': '操作人' in drawer,
            'case_name': '测试用例_JS062' in drawer,
        }
        shot(d, '02_review_history_drawer_light')
        d.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')  # ESC
        time.sleep(1)

        # 深色
        set_theme(d, 'dark')
        d.get('%s/tasks/%d' % (BASE, TASK))
        wait_text(d, '已复核 1 条', 120)
        time.sleep(1.5)
        ev['dark_html_class'] = d.execute_script("return document.documentElement.className")
        ev['dark_body_bg'] = d.execute_script("return getComputedStyle(document.body).backgroundColor")
        shot(d, '03_container_badge_dark')
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if '查看复核历史' in (b.text or ''):
                js_click(d, b)
                break
        wait_text(d, '共 1 条', 60)
        time.sleep(1.0)
        shot(d, '04_review_history_drawer_dark')
        d.find_element(By.TAG_NAME, 'body').send_keys('\ue00c')
        time.sleep(1)

        # AI 复核上下文：打开 AI 复核弹窗，抓 ai-review-history 请求键
        set_theme(d, 'light')
        d.get('%s/tasks/%d' % (BASE, TASK))
        wait_text(d, '已复核 1 条', 120)
        time.sleep(1.5)
        d.execute_script('window.__net = []')
        ai_btn = None
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if (b.get_attribute('aria-label') or '') == 'AI 复核':
                ai_btn = b
                break
        assert ai_btn is not None, '未找到「AI 复核」按钮'
        js_click(d, ai_btn)
        time.sleep(8)
        ev['net_ai_dialog'] = net(d)
        ev['ai_dialog_text'] = [ln for ln in texts(d).splitlines() if '复核' in ln][:20]
        shot(d, '05_ai_review_context')
    finally:
        with open(os.path.join(OUT, 'evidence_int1626.json'), 'w', encoding='utf-8') as f:
            json.dump(ev, f, ensure_ascii=False, indent=1)
        d.quit()
        print('EVIDENCE', os.path.join(OUT, 'evidence_int1626.json'))


if __name__ == '__main__':
    main()
