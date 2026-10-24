# -*- coding: utf-8 -*-
"""INT-1509 返工复核：阶段 1 任务列表内部滚动、底部操作栏常驻（UX 审计缺陷 1）。

判据（1440x900 / 1600x1000 两个视口，117 个可挑选任务）：
- 底部「下一步：选择结果」按钮 rect.bottom <= innerHeight（不滚页面即可见）
- 任务列表容器 scrollHeight > clientHeight（列表自身滚动）
- 列表滚到底后操作栏仍在视口内、顶部工具栏仍可见（页签容器不整体滚动）

用法：python tests/ui/int1509_layout_verify.py
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('INT1509_BASE', 'http://127.0.0.1:15291')
ART = os.path.join('tests', 'ui', 'artifacts', 'int1509_r2')
DRIVER = os.environ.get(
    'INT1509_DRIVER',
    r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe',
)

os.makedirs(ART, exist_ok=True)

MEASURE_JS = r"""
const out = {innerHeight: window.innerHeight, docScroll: document.scrollingElement.scrollHeight - window.innerHeight};
const rows = [...document.querySelectorAll('[data-testid^="pick-task-"]')];
out.rowCount = rows.length;
const nextBtn = [...document.querySelectorAll('button')].find(b => (b.textContent||'').includes('下一步：选择结果'));
if (nextBtn) {
  const r = nextBtn.getBoundingClientRect();
  out.next = {top: Math.round(r.top), bottom: Math.round(r.bottom),
              visible: r.bottom <= window.innerHeight + 0.5 && r.top >= 0,
              text: (nextBtn.textContent||'').trim()};
}
const selectAll = [...document.querySelectorAll('button')].find(b => (b.textContent||'').trim() === '全选当前筛选');
if (selectAll) { const r = selectAll.getBoundingClientRect(); out.selectAll = {top: Math.round(r.top), bottom: Math.round(r.bottom)}; }
if (rows.length) {
  let el = rows[0], list = null, outer = null;
  while (el) {
    const cs = getComputedStyle(el);
    if (!list && /auto|scroll/.test(cs.overflowY || cs.overflow) && el.scrollHeight > 0) {
      list = {cls: el.className, clientHeight: el.clientHeight, scrollHeight: el.scrollHeight,
              scrollTop: el.scrollTop, scrollable: el.scrollHeight > el.clientHeight + 2};
    } else if (list && !outer && /auto|scroll/.test(cs.overflowY || cs.overflow)) {
      outer = {cls: el.className, clientHeight: el.clientHeight, scrollHeight: el.scrollHeight,
               scrollable: el.scrollHeight > el.clientHeight + 2};
    }
    el = el.parentElement;
  }
  out.list = list;
  out.outer = outer;
  out.firstRow = rows[0].textContent.slice(0, 40);
}
return out;
"""

SCROLL_LIST_JS = r"""
const rows = [...document.querySelectorAll('[data-testid^="pick-task-"]')];
if (!rows.length) return null;
let el = rows[0];
while (el) { const cs = getComputedStyle(el);
  if (/auto|scroll/.test(cs.overflowY || cs.overflow) && el.scrollHeight > el.clientHeight + 2) { el.scrollTop = el.scrollHeight; break; }
  el = el.parentElement; }
const nextBtn = [...document.querySelectorAll('button')].find(b => (b.textContent||'').includes('下一步：选择结果'));
const r = nextBtn ? nextBtn.getBoundingClientRect() : null;
const h3 = [...document.querySelectorAll('h3')].find(h => (h.textContent||'').includes('阶段 1'));
const hr = h3 ? h3.getBoundingClientRect() : null;
return {scrollTop: el ? el.scrollTop : null,
        nextBottom: r ? Math.round(r.bottom) : null,
        nextVisible: r ? (r.bottom <= window.innerHeight + 0.5 && r.top >= 0) : null,
        headerTop: hr ? Math.round(hr.top) : null,
        innerHeight: window.innerHeight};
"""


def driver(width, height):
    os.environ.setdefault('SE_OFFLINE', 'true')
    opts = webdriver.ChromeOptions()
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=%d,%d' % (width, height))
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
        if m.get('method') == 'Network.requestWillBeSent':
            u = m.get('params', {}).get('request', {}).get('url', '')
            if '/api/' in u:
                out.append(u.split('/api/v1/')[-1])
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
    WebDriverWait(d, 30).until(lambda x: '挑选 · 阶段 1：选择任务' in (x.page_source or ''))
    deadline = time.time() + 180
    while time.time() < deadline:
        st = d.execute_script(MEASURE_JS)
        if st['rowCount'] > 0 or '可挑选任务加载失败' in (d.page_source or ''):
            return st
        time.sleep(2)
    return d.execute_script(MEASURE_JS)


def run_viewport(w, h, theme='light', tag='light'):
    d = driver(w, h)
    res = {'viewport': '%dx%d' % (w, h), 'theme': theme}
    try:
        d.get(BASE + '/')
        set_theme(d, theme)
        d.set_window_size(w, h)
        st = open_stage1(d)
        time.sleep(1.5)
        res['measure'] = d.execute_script(MEASURE_JS)
        res['requests'] = drain(d)
        res['shots'] = [shot(d, 'stage1_%s_%dx%d_top' % (tag, w, h))]
        res['afterScroll'] = d.execute_script(SCROLL_LIST_JS)
        time.sleep(0.6)
        res['shots'].append(shot(d, 'stage1_%s_%dx%d_scrolled' % (tag, w, h)))
        # 阶段 2：操作栏形态不受影响
        nextBtn = None
        for b in d.find_elements(By.TAG_NAME, 'button'):
            if b.is_displayed() and '下一步：选择结果' in (b.text or ''):
                nextBtn = b
                break
        res['nextClickable'] = nextBtn is not None
    finally:
        d.quit()
    return res


def main():
    out = {'base': BASE, 'runs': []}
    out['runs'].append(run_viewport(1440, 900, 'light', 'light'))
    out['runs'].append(run_viewport(1600, 1000, 'light', 'light'))
    out['runs'].append(run_viewport(1600, 1000, 'dark', 'dark'))
    for r in out['runs']:
        m = r['measure']
        print('==', r['viewport'], r['theme'], 'rows', m['rowCount'],
              'list', (m.get('list') or {}).get('clientHeight'), '/', (m.get('list') or {}).get('scrollHeight'),
              'next', (m.get('next') or {}).get('bottom'), '/', m['innerHeight'],
              'visible', (m.get('next') or {}).get('visible'),
              'outerScrollable', (m.get('outer') or {}).get('scrollable'),
              'afterScroll', r['afterScroll'])
    p = os.path.join(ART, 'layout_verify.json')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print('saved', p)


if __name__ == '__main__':
    main()
