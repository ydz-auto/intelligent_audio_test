# -*- coding: utf-8 -*-
"""INT-2350 接线·React 报告中心搜索一致性 浏览器实测（真实库栈 docker 15000 + 本卡构建 15251）。

核对：
1. 关键字输入后 页头「共 N」/ Hero 汇总 / 徽章行 / 类型 chips / 工具栏 同口径收缩，清除后恢复；
2. 无命中空态「未找到匹配报告 / 试试其他关键字」+ 清除筛选；收藏视图空结果不误报「暂无报告」；
3. placeholder 与 H1 为名称/描述口径；
4. Network：tab-counts 请求带 keyword/favorite/deleted 且响应含 types/favorite；
5. 浅色 + 深色截图。

用法：REACT_BASE=http://localhost:15251 python int2350_ui_verify.py
结果 JSON：tests/ui/artifacts/int2350/evidence.json；截图同目录。
"""
import json
import os
import re
import sys
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L  # noqa: E402

BASE = os.environ.get('REACT_BASE', 'http://localhost:15251')
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int2350')
os.makedirs(ART, exist_ok=True)

SNAPSHOT_JS = r"""
const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
const out = {};
out.body = norm(document.body.innerText);
const input = document.querySelector("input[aria-label^='搜索报告']");
out.search = input ? { placeholder: input.getAttribute('placeholder'), aria: input.getAttribute('aria-label'), value: input.value } : null;
out.h1 = [...document.querySelectorAll('h1')].map((e) => norm(e.textContent)).join(' | ');
const typeNav = document.querySelector("nav[aria-label='报告类型筛选']");
out.typeChips = typeNav ? [...typeNav.querySelectorAll('button')].map((b) => norm(b.textContent)) : [];
out.statBadges = [...document.querySelectorAll('button')]
  .filter((b) => !b.closest("nav[aria-label='报告类型筛选']"))
  .map((b) => norm(b.textContent))
  .filter((t) => /^(全部报告|已发布|草稿|对比报告)\d+$/.test(t));
const toolbar = [...document.querySelectorAll('div.bg-card')]
  .find((e) => /个报告/.test(e.textContent || ''));
out.toolbar = toolbar ? norm(toolbar.firstElementChild ? toolbar.firstElementChild.textContent : toolbar.textContent) : null;
out.emptyTitle = (document.querySelector("[data-slot='empty-title']") || {}).textContent || '';
out.emptyDesc = (document.querySelector("[data-slot='empty-description']") || {}).textContent || '';
out.rows = document.querySelectorAll('table tbody tr').length;
out.empty = !!document.querySelector("[data-slot='empty']");
const header = out.body.match(/共\s*(\d+)\s*个报告/);
out.headerCount = header ? Number(header[1]) : null;
const hero = out.body.match(/共\s*(\d+)\s*个报告，其中草稿\s*(\d+)\s*个、已发布\s*(\d+)\s*个/);
out.hero = hero ? { all: Number(hero[1]), draft: Number(hero[2]), published: Number(hero[3]) } : null;
return JSON.stringify(out);
"""


def norm_ws(s):
    return re.sub(r'\s+', ' ', s or '').strip()


def login(drv):
    drv.get(BASE + '/login')
    WebDriverWait(drv, 30).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2)
    if '/login' not in drv.current_url:
        return drv.current_url
    u = WebDriverWait(drv, 25).until(lambda d: d.find_element(By.ID, 'username'))
    u.clear()
    u.send_keys('dev_user')
    p = drv.find_element(By.ID, 'password')
    p.clear()
    p.send_keys('dev_password')
    L.js_click(drv, drv.find_element(By.CSS_SELECTOR, "button[type='submit']"))
    WebDriverWait(drv, 45).until(lambda d: '/login' not in d.current_url)
    time.sleep(2)
    return drv.current_url


def set_search(drv, value):
    el = WebDriverWait(drv, 20).until(
        lambda d: d.find_element(By.CSS_SELECTOR, "input[aria-label^='搜索报告']"))
    drv.execute_script(
        """
        const el = arguments[0], v = arguments[1];
        const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
        setter.call(el, v);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        """, el, value)
    # 防抖 300ms + 两次请求（列表 + 计数）
    time.sleep(4.5)


def snapshot(drv):
    return json.loads(drv.execute_script(SNAPSHOT_JS))


def set_theme(drv, mode):
    """主题 key iatp:theme:v1:mode 必须写纯字符串（JSON 带引号会静默回退浅色）。"""
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)
    drv.get('about:blank')
    drv.get(BASE + '/report-center?pageSize=20')
    time.sleep(3)


def scroll_to(drv, where):
    drv.execute_script("""
      const els = [...document.querySelectorAll('*')].filter((e) => {
        const st = getComputedStyle(e);
        return (st.overflowY === 'auto' || st.overflowY === 'scroll') && e.scrollHeight > e.clientHeight + 20;
      });
      els.forEach((e) => { e.scrollTop = arguments[0] === 'bottom' ? e.scrollHeight : 0; });
      window.scrollTo(0, arguments[0] === 'bottom' ? document.body.scrollHeight : 0);
      """, where)
    time.sleep(1)


def shot(drv, name):
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('SHOT', p)
    return p


def tab_counts_log(drv):
    entries = drv.execute_script(
        "return JSON.stringify((window.__fetchLog || []).filter(e => e.url.indexOf('/tab-counts') !== -1));")
    out = []
    for e in json.loads(entries or '[]'):
        body = e.get('resBody') or ''
        try:
            data = json.loads(body).get('data', {})
        except Exception:
            data = None
        out.append({'url': e.get('url'), 'status': e.get('status'), 'data': data})
    return out


def newest_tab_counts(drv, needle):
    for e in reversed(tab_counts_log(drv)):
        if needle in (e.get('url') or ''):
            return e
    return None


def wait_for(drv, predicate, timeout=60, label=''):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        last = snapshot(drv)
        if predicate(last):
            return last
        time.sleep(1.5)
    raise RuntimeError('wait_for timeout %s: %s' % (label, json.dumps(last, ensure_ascii=False)[:800]))


def toggles(drv):
    # base-ui Switch.Root 在 label 内渲染为 <span role="switch">（非 button）
    return {norm_ws(e.get_attribute('aria-label')): e
            for e in drv.find_elements(By.CSS_SELECTOR, "[role='switch']")}


def click_switch(drv, el):
    drv.execute_script(
        """
        const el = arguments[0];
        for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
          const Ctor = type.startsWith('pointer') ? PointerEvent : MouseEvent;
          el.dispatchEvent(new Ctor(type, { bubbles: true, cancelable: true, button: 0 }));
        }
        """, el)
    time.sleep(0.5)
    return el.get_attribute('aria-checked')


def main():
    drv = L.driver()
    evidence = {'base': BASE, 'steps': []}
    try:
        print('LOGIN ->', login(drv))
        set_theme(drv, 'light')

        drv.get(BASE + '/report-center?pageSize=20')
        first = wait_for(drv, lambda s: s['headerCount'] is not None and not s['empty'] and s['rows'] > 0,
                         timeout=90, label='default list')
        first['shot'] = shot(drv, 'light_01_default')
        evidence['steps'].append({'step': 'default', **first})

        # --- 关键字收缩 ---
        set_search(drv, 'E2E')
        filtered = wait_for(drv, lambda s: s['headerCount'] is not None and s['headerCount'] < 60
                            and s['hero'] and s['hero']['all'] == s['headerCount'],
                            label='keyword shrink')
        filtered['shot'] = shot(drv, 'light_02_filtered_E2E')
        filtered['network'] = newest_tab_counts(drv, 'keyword=E2E')
        evidence['steps'].append({'step': 'keyword=E2E', **filtered})

        # --- 无命中空态 ---
        set_search(drv, 'zzz-no-hit-2350')
        nohit = wait_for(drv, lambda s: s['empty'] and '未找到' in (s['emptyTitle'] or ''),
                         label='no hit empty')
        scroll_to(drv, 'bottom')
        nohit['shot'] = shot(drv, 'light_03_nohit')
        nohit['network'] = newest_tab_counts(drv, 'keyword=zzz-no-hit-2350')
        evidence['steps'].append({'step': 'no-hit', **nohit})

        # --- 清除筛选恢复 ---
        clear = [b for b in drv.find_elements(By.TAG_NAME, 'button')
                 if norm_ws(b.text) == '清除全部筛选' and b.is_displayed()]
        L.js_click(drv, clear[0])
        time.sleep(3)
        restored = wait_for(drv, lambda s: s['headerCount'] == 60 and s['rows'] > 0
                            and (s['search'] or {}).get('value') == '',
                            label='restore')
        scroll_to(drv, 'top')
        restored['shot'] = shot(drv, 'light_04_restored')
        evidence['steps'].append({'step': 'restored', **restored})

        # --- 回收站视图（计数同口径，空态优先「回收站是空的」）---
        t = toggles(drv)
        if '回收站模式' in t:
            print('TRASH ON ->', click_switch(drv, t['回收站模式']))
            time.sleep(3)
            trash = wait_for(drv, lambda s: s['toolbar'] and '已筛选' in s['toolbar'],
                             label='trash mode')
            scroll_to(drv, 'top')
            trash['shot'] = shot(drv, 'light_05_trash')
            trash['network'] = newest_tab_counts(drv, 'deleted=true')
            evidence['steps'].append({'step': 'trash', **trash})
            print('TRASH OFF ->', click_switch(drv, toggles(drv)['回收站模式']))
            time.sleep(2.5)

        # --- 仅看收藏（dev_user 无收藏：计数 0，空态应为「未找到匹配报告」而非「暂无报告」）---
        t = toggles(drv)
        if '仅看收藏' in t:
            print('FAV ON ->', click_switch(drv, t['仅看收藏']))
            time.sleep(3)
            fav = wait_for(drv, lambda s: s['search'] is not None and
                           (s['headerCount'] == 0 or s['rows'] > 0),
                           label='favorite mode')
            scroll_to(drv, 'bottom')
            fav['shot'] = shot(drv, 'light_06_favorite')
            fav['network'] = newest_tab_counts(drv, 'favorite=true')
            evidence['steps'].append({'step': 'favorite', **fav})
            print('FAV OFF ->', click_switch(drv, toggles(drv)['仅看收藏']))
            time.sleep(2.5)

        # --- 深色 ---
        set_theme(drv, 'dark')
        dark_default = wait_for(drv, lambda s: s['headerCount'] == 60 and s['rows'] > 0,
                                label='dark default')
        dark_default['shot'] = shot(drv, 'dark_01_default')
        evidence['steps'].append({'step': 'dark default', **dark_default})

        set_search(drv, 'E2E')
        dark_filtered = wait_for(drv, lambda s: s['headerCount'] is not None and s['headerCount'] < 60,
                                 label='dark filtered')
        dark_filtered['shot'] = shot(drv, 'dark_02_filtered_E2E')
        evidence['steps'].append({'step': 'dark filtered', **dark_filtered})

        set_search(drv, 'zzz-no-hit-2350')
        dark_empty = wait_for(drv, lambda s: s['empty'] and '未找到' in (s['emptyTitle'] or ''),
                              label='dark no-hit')
        scroll_to(drv, 'bottom')
        dark_empty['shot'] = shot(drv, 'dark_03_nohit')
        evidence['steps'].append({'step': 'dark no-hit', **dark_empty})

        evidence['tab_counts_requests'] = tab_counts_log(drv)
        path = os.path.join(ART, 'evidence.json')
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(evidence, f, ensure_ascii=False, indent=1)
        print('EVIDENCE', path)

        # 控制台摘要
        for step in evidence['steps']:
            print('\n==', step['step'], '| header', step.get('headerCount'),
                  '| hero', step.get('hero'))
            print('   toolbar:', step.get('toolbar'))
            print('   chips:', step.get('typeChips'))
            print('   badges:', step.get('statBadges'))
            print('   empty:', (step.get('emptyTitle') or '') + ' / ' + (step.get('emptyDesc') or ''),
                  '| rows', step.get('rows'))
            if step.get('network'):
                print('   net:', (step['network'].get('url') or '')[:120],
                      '| data.keys', sorted((step['network'].get('data') or {}).keys()))
    finally:
        drv.quit()


if __name__ == '__main__':
    main()
