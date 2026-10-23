# -*- coding: utf-8 -*-
"""INT-1644 取证：算法详情弹窗「评估参数」按主/子维度分组 + 「评估维度关联」层级。

对接本 run dev server（5350，/api 代理 docker 真实栈 15000，库 intelligent_audio_test）。
输出：artifacts/int1644/*.png + dom_int1644.json
"""
import json
import os
import re
import sys
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:5350')
CHROME_BINARY = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, 'artifacts', 'int1644')
os.makedirs(ART, exist_ok=True)

ALGO_NAME = os.environ.get('ALGO_NAME', '小艺语音大模型')

FETCH_PATCH = r"""
window.__fetchLog = [];
const __origFetch = window.fetch;
window.fetch = async function(input, init) {
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const init2 = init || {};
  const method = (init2.method || 'GET').toUpperCase();
  const t0 = Date.now();
  let res;
  try {
    res = await __origFetch.apply(this, arguments);
  } catch (e) {
    window.__fetchLog.push({url: url, method: method, status: -1, error: String(e), ms: Date.now() - t0});
    throw e;
  }
  const entry = {url: url, method: method, status: res.status, ms: Date.now() - t0};
  if (url.indexOf('/api/v1') !== -1) {
    try {
      const text = await res.clone().text();
      entry.bytes = text.length;
      entry.excerpt = text.slice(0, 400);
    } catch (e) {}
  }
  window.__fetchLog.push(entry);
  return res;
};
"""


def make_driver():
    o = Options()
    o.binary_location = CHROME_BINARY
    o.add_argument('--headless=new')
    o.add_argument('--window-size=1600,1500')
    o.add_argument('--disable-gpu')
    o.add_argument('--no-sandbox')
    o.add_argument('--lang=zh-CN')
    o.add_argument('--disable-dev-shm-usage')
    o.set_capability('goog:loggingPrefs', {'browser': 'ALL'})
    import winreg
    major = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'SOFTWARE\Google\Chrome\BLBeacon') as k:
            major = int(winreg.QueryValueEx(k, 'version')[0].split('.')[0])
    except Exception:
        pass
    cache = os.path.join(os.path.expanduser('~'), '.cache', 'selenium', 'chromedriver', 'win64')
    path = ''
    if major and os.path.isdir(cache):
        for ver in os.listdir(cache):
            exe = os.path.join(cache, ver, 'chromedriver.exe')
            if os.path.isfile(exe):
                try:
                    if int(ver.split('.')[0]) == major:
                        path = exe
                except ValueError:
                    pass
    d = webdriver.Chrome(options=o, service=Service(executable_path=path) if path else Service())
    d.set_page_load_timeout(90)
    d.set_script_timeout(60)
    d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {'source': FETCH_PATCH})
    return d


def js_click(drv, el):
    drv.execute_script('arguments[0].scrollIntoView({block:"center"}); arguments[0].click();', el)


def text_of(drv, el):
    return (drv.execute_script('return arguments[0].textContent || "";', el) or '').strip()


def shot(drv, name):
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    print('SHOT', p)
    return p


def wait_css(drv, css, timeout=60):
    WebDriverWait(drv, timeout).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, css)) > 0)
    return drv.find_elements(By.CSS_SELECTOR, css)


def open_detail(drv):
    """算法列表 → 行操作 → 详情。"""
    drv.get(BASE + '/AlgorithmConfig')
    WebDriverWait(drv, 90).until(
        lambda d: len(d.find_elements(By.CSS_SELECTOR, f"[aria-label='算法 {ALGO_NAME} 的操作']")) > 0
    )
    time.sleep(1.5)
    js_click(drv, drv.find_element(By.CSS_SELECTOR, f"[aria-label='算法 {ALGO_NAME} 的操作']"))
    time.sleep(0.8)
    items = [i for i in drv.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if text_of(drv, i) == '详情']
    if not items:
        raise RuntimeError('详情菜单项未出现')
    js_click(drv, items[0])
    WebDriverWait(drv, 60).until(lambda d: len(d.find_elements(By.CSS_SELECTOR, "[role='dialog']")) > 0)
    time.sleep(1.2)


def click_tab(drv, label_prefix):
    tabs = [t for t in drv.find_elements(By.CSS_SELECTOR, "[role='dialog'] [role='tab']")
            if text_of(drv, t).startswith(label_prefix)]
    if not tabs:
        raise RuntimeError('找不到页签 %s' % label_prefix)
    js_click(drv, tabs[0])
    time.sleep(1)
    return tabs[0]


def panel_of(drv, keyword):
    for p in drv.find_elements(By.CSS_SELECTOR, "[role='dialog'] [role='tabpanel']"):
        if keyword in text_of(drv, p):
            return p
    return None


def group_headers(drv):
    out = []
    for row in drv.find_elements(By.CSS_SELECTOR, "[role='dialog'] [role='tabpanel'] tbody tr"):
        btns = row.find_elements(By.CSS_SELECTOR, "button[aria-expanded]")
        if not btns:
            continue
        b = btns[0]
        out.append({
            'text': text_of(drv, b),
            'expanded': b.get_attribute('aria-expanded'),
            'name': text_of(drv, b.find_elements(By.CSS_SELECTOR, 'span')[0]),
            'badges': [text_of(drv, s) for s in b.find_elements(By.CSS_SELECTOR, 'span')],
        })
    return out


def relation_rows(drv):
    rows = []
    # 评估维度关联表在页签之外（dialog 直接子节）
    for table in drv.find_elements(By.CSS_SELECTOR, "[role='dialog'] table"):
        heads = [text_of(drv, th) for th in table.find_elements(By.CSS_SELECTOR, 'thead th')]
        if heads[:3] == ['评估维度', '权重', '默认']:
            for tr in table.find_elements(By.CSS_SELECTOR, 'tbody tr'):
                tds = tr.find_elements(By.CSS_SELECTOR, 'td')
                if tds:
                    rows.append([text_of(drv, td) for td in tds])
            break
    return rows


def network_overlay(drv, name):
    rows = drv.execute_script('return (window.__fetchLog||[]).filter(e => e.url.indexOf("/api/v1/algorithm/definitions") !== -1 || e.url.indexOf("/api/v1/evaluation/dimensions") !== -1);')
    drv.execute_script(
        """
        const rows = arguments[0];
        let box = document.getElementById('__net_overlay');
        if (box) box.remove();
        box = document.createElement('div');
        box.id = '__net_overlay';
        box.style.cssText = 'position:fixed;left:16px;top:16px;z-index:2147483647;max-width:900px;background:#0b1020;color:#e6edf3;font:12px/1.5 Consolas,monospace;padding:12px 14px;border:1px solid #3b82f6;border-radius:8px;box-shadow:0 8px 32px rgba(0,0,0,.6);white-space:pre-wrap;word-break:break-all;';
        const title = document.createElement('div');
        title.textContent = 'Network（window.fetch 打点，本页真实请求）';
        title.style.cssText = 'font-weight:700;color:#93c5fd;margin-bottom:6px;';
        box.appendChild(title);
        rows.forEach(function(r) {
          const d = document.createElement('div');
          d.textContent = r.method + ' ' + r.status + ' ' + r.ms + 'ms  ' + r.bytes + 'B  ' + r.url + '\\n  ' + (r.excerpt || '');
          d.style.cssText = 'margin-bottom:8px;color:' + (r.status === 200 ? '#a7f3d0' : '#fca5a5') + ';';
          box.appendChild(d);
        });
        document.body.appendChild(box);
        """,
        rows,
    )
    time.sleep(0.5)
    path = shot(drv, name)
    drv.execute_script("var b=document.getElementById('__net_overlay'); if(b) b.remove();")
    return rows, path


def set_theme(drv, mode):
    drv.get(BASE + '/AlgorithmConfig')
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)
    drv.refresh()
    WebDriverWait(drv, 60).until(lambda d: d.execute_script('return document.readyState') == 'complete')
    time.sleep(2)


def main():
    d = make_driver()
    result = {}
    try:
        open_detail(d)
        click_tab(d, '评估参数')
        panel = panel_of(d, '来源')
        if panel is None:
            raise RuntimeError('评估参数面板未渲染')
        headers = group_headers(d)
        result['groups'] = headers
        result['group_count'] = len(headers)
        result['row_count'] = len(panel.find_elements(By.CSS_SELECTOR, 'tbody tr')) - len(headers)
        result['group_row_sum'] = sum(
            int(re.search(r'(\d+)\s*条', h['text']).group(1)) for h in headers if re.search(r'(\d+)\s*条', h['text'])
        )
        print('GROUPS', result['group_count'], 'ROWS', result['row_count'], 'SUM', result['group_row_sum'])
        shot(d, '01_light_eval_grouped')

        # Network 证据（含 /algorithm/definitions）
        net_rows, _ = network_overlay(d, '06_network_light')
        result['network'] = [{k: r.get(k) for k in ('method', 'status', 'ms', 'bytes', 'url')} for r in net_rows]

        # 折叠第一组
        first = None
        for row in panel.find_elements(By.CSS_SELECTOR, 'tbody tr'):
            btns = row.find_elements(By.CSS_SELECTOR, 'button[aria-expanded]')
            if btns:
                first = btns[0]
                break
        if first is None:
            raise RuntimeError('无组头按钮')
        before_rows = len(panel.find_elements(By.CSS_SELECTOR, 'tbody tr'))
        before_text = text_of(d, first)
        js_click(d, first)
        time.sleep(0.8)
        after_rows = len(panel.find_elements(By.CSS_SELECTOR, 'tbody tr'))
        result['collapse'] = {'group': before_text, 'rows_before': before_rows, 'rows_after': after_rows}
        print('COLLAPSE', before_text, before_rows, '->', after_rows)
        shot(d, '02_light_eval_collapsed')
        js_click(d, first)
        time.sleep(0.5)
        result['collapse']['rows_restored'] = len(panel.find_elements(By.CSS_SELECTOR, 'tbody tr'))

        # 评估维度关联
        rels = relation_rows(d)
        result['relation_count'] = len(rels)
        result['relations_head'] = rels[:12]
        result['relations_tail'] = rels[-4:]
        # 滚动到关联表
        tbl = None
        for t in d.find_elements(By.CSS_SELECTOR, "[role='dialog'] table"):
            heads = [text_of(d, th) for th in t.find_elements(By.CSS_SELECTOR, 'thead th')]
            if heads[:3] == ['评估维度', '权重', '默认']:
                tbl = t
                break
        if tbl is not None:
            d.execute_script('arguments[0].scrollIntoView({block:"start"});', tbl)
            time.sleep(0.8)
        shot(d, '03_light_dimension_relations')

        # 深色
        set_theme(d, 'dark')
        is_dark = d.execute_script("return document.documentElement.classList.contains('dark')")
        print('DARK', is_dark)
        result['dark'] = is_dark
        open_detail(d)
        click_tab(d, '评估参数')
        shot(d, '04_dark_eval_grouped')
        tbl = None
        for t in d.find_elements(By.CSS_SELECTOR, "[role='dialog'] table"):
            heads = [text_of(d, th) for th in t.find_elements(By.CSS_SELECTOR, 'thead th')]
            if heads[:3] == ['评估维度', '权重', '默认']:
                tbl = t
                break
        if tbl is not None:
            d.execute_script('arguments[0].scrollIntoView({block:"start"});', tbl)
            time.sleep(0.8)
        shot(d, '05_dark_dimension_relations')

        # 编辑模态窗对照（同口径）
        set_theme(d, 'light')
        d.get(BASE + '/AlgorithmConfig')
        WebDriverWait(d, 90).until(
            lambda x: len(x.find_elements(By.CSS_SELECTOR, f"[aria-label='算法 {ALGO_NAME} 的操作']")) > 0
        )
        time.sleep(1.5)
        js_click(d, d.find_element(By.CSS_SELECTOR, f"[aria-label='算法 {ALGO_NAME} 的操作']"))
        time.sleep(0.8)
        edits = [i for i in d.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if text_of(d, i) == '编辑']
        if edits:
            js_click(d, edits[0])
            time.sleep(3)
            # 展开 高级配置 → 评估参数映射
            for label in ('高级配置', '评估参数映射'):
                hits = [b for b in d.find_elements(By.CSS_SELECTOR, "button[aria-expanded='false'], [role='button'][aria-expanded='false']")
                        if label in text_of(d, b)]
                if hits:
                    js_click(d, hits[0])
                    time.sleep(1.2)
                else:
                    print('WARN 未找到折叠项', label)
            edit_headers = []
            for sheet in d.find_elements(By.CSS_SELECTOR, "[role='dialog']"):
                for b in sheet.find_elements(By.CSS_SELECTOR, 'button[aria-expanded]'):
                    t = text_of(d, b)
                    if '条' in t:
                        edit_headers.append(t)
            result['edit_sheet_headers'] = edit_headers[:20]
            print('EDIT HEADERS', len(edit_headers))
            shot(d, '07_edit_sheet_eval_view')
        else:
            result['edit_sheet_headers'] = None
            print('WARN 无编辑菜单项（权限）')

        with open(os.path.join(ART, 'dom_int1644.json'), 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print('DONE')
    finally:
        try:
            logs = d.get_log('browser')
            errs = [l for l in logs if l.get('level') in ('SEVERE',)]
            print('BROWSER_ERRORS', len(errs))
            for e in errs[:5]:
                print('  ', e.get('message', '')[:200])
        except Exception:
            pass
        d.quit()


if __name__ == '__main__':
    main()
