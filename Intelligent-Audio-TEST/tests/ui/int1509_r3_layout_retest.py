# -*- coding: utf-8 -*-
"""INT-1509 第三轮复测（测试工程师）：只复测 UX 审计 P2 缺陷 1 与本次修复相关部分。

交付对象：agent/react-b/int-1509-fd4e8c6f73f2 @ cc5288819
（缺陷 1：阶段 1 操作栏被 117 行顶出视口；修复：CherryPickTab 根补 h-full、
CherryPickWizard 步骤区改 flex 纵向容器）

判据（1440x900 / 1600x1000，真实库 117 个可挑选任务）：
- 阶段 1 列表容器 scrollHeight > clientHeight（列表自身滚动），页面文档不整体滚动
- 「下一步：选择结果」rect.bottom <= innerHeight，且「全选当前筛选」同屏可见
- 列表滚到底后顶部标题 / 已选计数仍在视口内，操作栏仍可见
- 本轮修复涉及的容器链对阶段 2 及向导步进无回归：阶段 2 标题、任务集摘要条、
  已选汇总条与「更换任务」回阶段 1 的勾选保留均正常
- Network：阶段 1 只有 pickable-tasks，不请求 candidates

用法：python tests/ui/int1509_r3_layout_retest.py
"""
import json
import os
import time

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('INT1509_BASE', 'http://127.0.0.1:15294')
ART = os.environ.get('INT1509_ART', r'D:\00_user_data\.cache\int1509_r3\shots')
DRIVER = os.environ.get(
    'INT1509_DRIVER',
    r'D:\00_user_data\.cache\selenium\chromedriver\win64\155.0.8059.84\chromedriver.exe',
)

os.makedirs(ART, exist_ok=True)

MEASURE_JS = r"""
const out = {innerHeight: window.innerHeight, innerWidth: window.innerWidth};
const se = document.scrollingElement;
out.docScrollable = se.scrollHeight - se.clientHeight > 4;
out.docScroll = se.scrollHeight - se.clientHeight;
const rows = [...document.querySelectorAll('[data-testid^="pick-task-"]')];
out.rowCount = rows.length;
const byText = (t) => [...document.querySelectorAll('button')].find(b => ((b.textContent||'').trim()) === t);
const nextBtn = [...document.querySelectorAll('button')].find(b => (b.textContent||'').includes('下一步：选择结果'));
const sa = byText('全选当前筛选');
const rect = e => { if (!e) return null; const r = e.getBoundingClientRect();
  return {top: Math.round(r.top), bottom: Math.round(r.bottom),
          visible: r.bottom <= window.innerHeight + 0.5 && r.top >= 0, text: (e.textContent||'').trim()}; };
out.next = rect(nextBtn);
out.selectAll = rect(sa);
if (rows.length) {
  let el = rows[0], list = null;
  while (el) {
    const cs = getComputedStyle(el);
    if (!list && /auto|scroll/.test(cs.overflowY || cs.overflow) && el.scrollHeight > 0) {
      list = {clientHeight: el.clientHeight, scrollHeight: el.scrollHeight,
              scrollable: el.scrollHeight > el.clientHeight + 2, cls: el.className};
    }
    el = el.parentElement;
  }
  out.list = list;
  out.firstRow = rows[0].textContent.slice(0, 60);
}
const h3 = [...document.querySelectorAll('h3')].find(h => (h.textContent||'').includes('阶段 1'));
out.stage1Header = h3 ? Math.round(h3.getBoundingClientRect().top) : null;
// 「已选 N 个任务 / 共 M 个可挑选任务」计数（两段 span 同一父节点）
const cnt = [...document.querySelectorAll('*')].find(e => e.children.length === 0 && /共\s*\d+\s*个可挑选任务/.test(e.textContent||''));
const cntRow = cnt ? cnt.parentElement : null;
out.selectedCount = cntRow ? (cntRow.textContent||'').replace(/\s+/g, ' ').trim() : null;
out.selectedCountTop = cntRow ? Math.round(cntRow.getBoundingClientRect().top) : null;
return out;
"""

SCROLL_LIST_JS = r"""
const rows = [...document.querySelectorAll('[data-testid^="pick-task-"]')];
if (!rows.length) return null;
let el = rows[0], target = null;
while (el) { const cs = getComputedStyle(el);
  if (/auto|scroll/.test(cs.overflowY || cs.overflow) && el.scrollHeight > el.clientHeight + 2) { target = el; break; }
  el = el.parentElement; }
if (target) target.scrollTop = target.scrollHeight;
const nextBtn = [...document.querySelectorAll('button')].find(b => (b.textContent||'').includes('下一步：选择结果'));
const r = nextBtn ? nextBtn.getBoundingClientRect() : null;
const h3 = [...document.querySelectorAll('h3')].find(h => (h.textContent||'').includes('阶段 1'));
const cnt = [...document.querySelectorAll('*')].find(e => e.children.length === 0 && /共\s*\d+\s*个可挑选任务/.test(e.textContent||''));
return {scrollTop: target ? target.scrollTop : null,
        scrollBottom: target ? (target.scrollHeight - target.clientHeight) : null,
        nextBottom: r ? Math.round(r.bottom) : null,
        nextVisible: r ? (r.bottom <= window.innerHeight + 0.5 && r.top >= 0) : null,
        headerTop: h3 ? Math.round(h3.getBoundingClientRect().top) : null,
        countTop: cnt ? Math.round(cnt.getBoundingClientRect().top) : null,
        innerHeight: window.innerHeight};
"""

STAGE2_JS = r"""
const out = {innerHeight: window.innerHeight};
const se = document.scrollingElement;
out.docScrollable = se.scrollHeight - se.clientHeight > 4;
const h3 = [...document.querySelectorAll('h3')].find(h => (h.textContent||'').includes('阶段 2'));
out.headerTop = h3 ? Math.round(h3.getBoundingClientRect().top) : null;
out.headerVisible = h3 ? (h3.getBoundingClientRect().top >= 0 && h3.getBoundingClientRect().top <= window.innerHeight) : null;
const label = [...document.querySelectorAll('*')].find(e => e.children.length === 0 && /已选任务/.test(e.textContent||''));
out.summaryBar = label ? Math.round(label.getBoundingClientRect().top) : null;
const change = [...document.querySelectorAll('button')].find(b => (b.textContent||'').trim().includes('更换任务'));
out.changeBtn = change ? (() => { const r = change.getBoundingClientRect(); return {top: Math.round(r.top), bottom: Math.round(r.bottom), visible: r.bottom <= window.innerHeight + 0.5 && r.top >= 0}; })() : null;
const next2 = [...document.querySelectorAll('button')].find(b => (b.textContent||'').trim().includes('加入挑选'));
out.addBtn = next2 ? (() => { const r = next2.getBoundingClientRect(); return {bottom: Math.round(r.bottom), visible: r.bottom <= window.innerHeight + 0.5 && r.top >= 0}; })() : null;
out.bodyText = (document.body.innerText || '').slice(0, 200);
return out;
"""


def make_driver(width, height):
    opts = webdriver.ChromeOptions()
    opts.add_argument('--headless=new')
    opts.add_argument('--window-size=%d,%d' % (width, height))
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--disable-dev-shm-usage')
    opts.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    d = webdriver.Chrome(service=Service(DRIVER), options=opts)
    d.set_page_load_timeout(120)
    d.set_script_timeout(120)
    return d


def shot(d, name):
    time.sleep(0.6)
    p = os.path.join(ART, name + '.png')
    d.save_screenshot(p)
    return p


def js_click(d, el):
    d.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def network_requests(d):
    urls = []
    for e in d.get_log('performance'):
        try:
            m = json.loads(e['message']).get('message', {})
        except Exception:
            continue
        if m.get('method') == 'Network.requestWillBeSent':
            u = m.get('params', {}).get('request', {}).get('url', '')
            if '/api/' in u:
                urls.append(u)
    return urls


def set_theme(d, mode):
    d.get(BASE + '/')
    d.execute_script("window.localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)
    d.refresh()
    time.sleep(1.5)


def click_text_button(d, text, exact=True):
    for b in d.find_elements(By.TAG_NAME, 'button'):
        try:
            t = (b.text or '').strip()
        except Exception:
            continue
        if (t == text) if exact else (text in t):
            if b.is_displayed():
                js_click(d, b)
                return True
    return False


def open_stage1(d):
    d.get(BASE + '/tasks?tab=cherry-picks')
    WebDriverWait(d, 90).until(
        lambda x: any(b.is_displayed() and '开始挑选' in (b.text or '') for b in x.find_elements(By.TAG_NAME, 'button'))
    )
    click_text_button(d, '开始挑选')
    WebDriverWait(d, 40).until(lambda x: '挑选 · 阶段 1：选择任务' in (x.page_source or ''))
    deadline = time.time() + 180
    while time.time() < deadline:
        st = d.execute_script(MEASURE_JS)
        if st['rowCount'] > 0:
            return st
        if '可挑选任务加载失败' in (d.page_source or ''):
            return st
        time.sleep(2)
    return d.execute_script(MEASURE_JS)


def run_viewport(w, h, theme, tag):
    d = make_driver(w, h)
    res = {'viewport': '%dx%d' % (w, h), 'theme': theme}
    try:
        set_theme(d, theme)
        d.set_window_size(w, h)
        time.sleep(1)
        st = open_stage1(d)
        time.sleep(1.5)
        res['measure'] = d.execute_script(MEASURE_JS)
        urls = network_requests(d)
        res['stage1Requests'] = [u.split('/api/v1/')[-1] for u in urls]
        res['shots'] = [shot(d, 'r3_stage1_%s_%dx%d_top' % (tag, w, h))]

        # 全选当前筛选（同时验证操作栏可点）
        res['selectAllClicked'] = click_text_button(d, '全选当前筛选')
        time.sleep(1.2)
        res['afterSelectAll'] = d.execute_script(MEASURE_JS)
        res['shots'].append(shot(d, 'r3_stage1_%s_%dx%d_selectall' % (tag, w, h)))

        # 列表滚到底：工具栏与操作栏都应仍在视口
        res['afterScroll'] = d.execute_script(SCROLL_LIST_JS)
        time.sleep(0.6)
        res['shots'].append(shot(d, 'r3_stage1_%s_%dx%d_scrolled' % (tag, w, h)))

        # 阶段 2（容器链改动的同栈回归）
        res['nextClicked'] = click_text_button(d, '下一步：选择结果', exact=False)
        if res['nextClicked']:
            try:
                WebDriverWait(d, 60).until(lambda x: '挑选 · 阶段 2：选择结果' in (x.page_source or ''))
            except Exception:
                pass
            time.sleep(2)
            res['stage2'] = d.execute_script(STAGE2_JS)
            res['shots'].append(shot(d, 'r3_stage2_%s_%dx%d' % (tag, w, h)))
            # 回到阶段 1：勾选保留
            if click_text_button(d, '更换任务', exact=False):
                try:
                    WebDriverWait(d, 40).until(lambda x: '挑选 · 阶段 1：选择任务' in (x.page_source or ''))
                except Exception:
                    pass
                time.sleep(1.5)
                res['backToStage1'] = d.execute_script(MEASURE_JS)
                res['shots'].append(shot(d, 'r3_stage1_back_%s_%dx%d' % (tag, w, h)))
    finally:
        try:
            res['consoleSevere'] = [e for e in d.get_log('browser') if e.get('level') == 'SEVERE']
        except Exception:
            res['consoleSevere'] = ['<unavailable>']
        d.quit()
    return res


def main():
    out = {'base': BASE, 'runs': []}
    out['runs'].append(run_viewport(1440, 900, 'light', 'light'))
    out['runs'].append(run_viewport(1600, 1000, 'light', 'light'))
    out['runs'].append(run_viewport(1600, 1000, 'dark', 'dark'))
    for r in out['runs']:
        m = r['measure']
        lst = m.get('list') or {}
        nxt = m.get('next') or {}
        print('==', r['viewport'], r['theme'], 'rows', m['rowCount'],
              '| list', lst.get('clientHeight'), '/', lst.get('scrollHeight'), 'scrollable', lst.get('scrollable'),
              '| next bottom', nxt.get('bottom'), '/', m['innerHeight'], 'visible', nxt.get('visible'),
              '| selectAll', (m.get('selectAll') or {}).get('visible'),
              '| docScrollable', m['docScrollable'],
              '| afterScroll', r.get('afterScroll'),
              '| stage2', r.get('stage2'),
              '| severe', r.get('consoleSevere'))
    p = os.path.join(ART, 'r3_layout_retest.json')
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print('saved', p)


if __name__ == '__main__':
    main()
