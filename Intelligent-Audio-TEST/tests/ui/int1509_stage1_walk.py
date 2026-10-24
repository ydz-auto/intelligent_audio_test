# -*- coding: utf-8 -*-
"""INT-1509 阶段 1 数据源走查：pickable-tasks 接线实测（真实库栈 15000，dev server 5309）。

取证：
- 打开挑选向导进入阶段 1，抓 Network：阶段 1 只应有 `pickable-tasks`（不再有 candidates 聚合）
- 阶段 1 清单条数 / total / 大任务 419、418
- 排序切换（任务名/状态/时间 × 升降序）重新请求并带 sort_by/sort_order
- 浅色 + 深色截图

用法：python tests/ui/int1509_stage1_walk.py [success|error]
"""
import json
import os
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('INT1509_BASE', 'http://localhost:5309')
API = 'http://localhost:15000/api/v1'
ART = os.path.join('tests', 'ui', 'artifacts', 'int1509')
DRIVER = os.environ.get(
    'INT1509_DRIVER',
    r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe',
)
MODE = sys.argv[1] if len(sys.argv) > 1 else 'success'

os.makedirs(ART, exist_ok=True)


def driver():
    os.environ.setdefault('SE_OFFLINE', 'true')
    opts = webdriver.ChromeOptions()
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=1680,1050')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    d = webdriver.Chrome(service=Service(DRIVER), options=opts)
    d.set_page_load_timeout(120)
    return d


def shot(d, name):
    time.sleep(0.6)
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    return p


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def drain(d):
    out = []
    for e in d.get_log('performance'):
        try:
            m = json.loads(e['message']).get('message', {})
        except Exception:
            continue
        meth = m.get('method')
        pr = m.get('params', {})
        if meth == 'Network.requestWillBeSent':
            u = pr.get('request', {}).get('url', '')
            if '/api/' in u:
                out.append({'kind': 'req', 'url': u, 'post': pr.get('request', {}).get('postData')})
        elif meth == 'Network.responseReceived':
            r = pr.get('response', {})
            u = r.get('url', '')
            if '/api/' in u:
                out.append({'kind': 'resp', 'url': u, 'status': r.get('status')})
    return out


def set_theme(d, mode):
    d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)
    d.refresh()
    time.sleep(2)


def open_stage1(d):
    d.get(BASE + '/tasks?tab=cherry-picks')
    WebDriverWait(d, 90).until(
        lambda x: any(
            b.is_displayed() and '开始挑选' in (b.text or '')
            for b in x.find_elements(By.TAG_NAME, 'button')
        )
    )
    for b in d.find_elements(By.TAG_NAME, 'button'):
        if b.is_displayed() and (b.text or '').strip() == '开始挑选':
            js_click(d, b)
            break
    WebDriverWait(d, 30).until(
        lambda x: '挑选 · 阶段 1：选择任务' in (x.page_source or '')
    )


def stage_state(d):
    rows = [r for r in d.find_elements(By.CSS_SELECTOR, "[data-testid^='pick-task-']")]
    texts = [(r.text or '').replace('\n', ' ') for r in rows]
    body = d.page_source or ''
    err = '可挑选任务加载失败' in body
    empty = '暂无可挑选的终态任务' in body
    total_txt = ''
    for s in d.find_elements(By.XPATH, "//span[contains(normalize-space(.),'共 ') and contains(normalize-space(.),'个可挑选任务')]"):
        if s.is_displayed():
            total_txt = (s.text or '').strip()
            break
    return {'rows': len(rows), 'row_texts': texts[:6], 'error': err, 'empty': empty,
            'total_text': total_txt}


def switch_sort(d, key_label):
    trig = None
    for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label='排序方式']"):
        if b.is_displayed():
            trig = b
            break
    if trig is None:
        return False
    js_click(d, trig)
    time.sleep(0.8)
    for m in d.find_elements(By.CSS_SELECTOR, "[role='option'], [role='menuitem'], [data-slot='select-item']"):
        if m.is_displayed() and (m.text or '').strip() == key_label:
            js_click(d, m)
            time.sleep(2.5)
            return True
    return False


def main():
    d = driver()
    result = {'base': BASE, 'mode': MODE, 'stage1': {}, 'network': {}, 'shots': []}
    try:
        d.get(BASE + '/')
        set_theme(d, 'light')
        open_stage1(d)
        deadline = time.time() + 120
        st = stage_state(d)
        while time.time() < deadline and not (st['rows'] > 0 or st['error'] or st['empty']):
            time.sleep(2)
            st = stage_state(d)
        time.sleep(1.5)
        result['stage1']['light'] = st
        result['network']['light'] = drain(d)
        result['shots'].append(shot(d, 'p1_stage1_light'))

        # 排序切换（仅成功态有意义；失败态只记录下拉可点击）
        sorts = []
        for label in ('任务名', '创建时间', '状态'):
            ok = switch_sort(d, label)
            sorts.append({'label': label, 'clicked': ok, 'state': stage_state(d)})
            result['network'].setdefault('sort', []).append(drain(d))
        result['sorts'] = sorts
        result['shots'].append(shot(d, 'p2_stage1_sorted'))

        # 升降序切换
        dir_btn = None
        for b in d.find_elements(By.CSS_SELECTOR, "button[aria-label*='升序'], button[aria-label*='降序']"):
            if b.is_displayed():
                dir_btn = b
                break
        if dir_btn is not None:
            label = dir_btn.get_attribute('aria-label')
            js_click(d, dir_btn)
            time.sleep(2.5)
            result['direction_toggle'] = {'from': label, 'state': stage_state(d)}
            result['network'].setdefault('direction', []).append(drain(d))
            result['shots'].append(shot(d, 'p3_stage1_desc'))

        # 深色
        set_theme(d, 'dark')
        open_stage1(d)
        deadline = time.time() + 120
        st = stage_state(d)
        while time.time() < deadline and not (st['rows'] > 0 or st['error'] or st['empty']):
            time.sleep(2)
            st = stage_state(d)
        time.sleep(1.5)
        result['stage1']['dark'] = st
        result['network']['dark'] = drain(d)
        result['shots'].append(shot(d, 'p4_stage1_dark'))
    finally:
        d.quit()
    out = os.path.join(ART, 'stage1_%s.json' % MODE)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2)[:6000])
    print('saved', out)


if __name__ == '__main__':
    main()
