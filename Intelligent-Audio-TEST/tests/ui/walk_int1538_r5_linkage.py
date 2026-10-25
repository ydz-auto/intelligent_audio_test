# -*- coding: utf-8 -*-
"""INT-1538 返工 P1-3：批量提交后列表计数 / 页签 / 分组计数同步刷新。

路径：自建源组 3 条用例 → 组头「批量修改 → 调整分组」移到自建目标组 → 同页不刷新读计数。
取证：提交前/后同页截图（浅/深）、分组卡计数、列表 footer 计数、视图页签状态、POST /testcases/batch 请求响应。
自建数据带 接线测试_ 前缀，脚本末尾清理（软删行由收尾 SQL 清）。
"""
import json
import os
import re
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1538_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

TAG = time.strftime('%m%d%H%M%S')
SRC = '接线测试_INT1538_R5链表源组_' + TAG
DST = '接线测试_INT1538_R5链表目标组_' + TAG
CASE_PREFIX = '接线测试_INT1538_R5链表用例_' + TAG
OUT = {'tag': TAG, 'src_group': SRC, 'dst_group': DST, 'sections': {}}

CARD_JS = """
const out = [];
for (const el of document.querySelectorAll('div')) {
  const cls = (el.className || '').toString();
  if (cls.includes('cursor-pointer') && cls.includes('justify-between')) {
    const t = (el.innerText || '').trim();
    if (t) out.push(t.slice(0, 120));
  }
}
return out;
"""


def sec(name):
    def deco(fn):
        t0 = time.time()
        try:
            fn()
            OUT['sections'][name] = {'ok': True, 'dur': round(time.time() - t0, 1)}
        except Exception:
            OUT['sections'][name] = {'ok': False, 'err': traceback.format_exc()[-900:],
                                     'dur': round(time.time() - t0, 1)}
        return fn
    return deco


def vis(el):
    try:
        return el.is_displayed()
    except Exception:
        return False


def retry(fn, timeout=25, interval=0.5):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        try:
            r = fn()
            if r is not None:
                return r
        except Exception as e:
            last = e
        time.sleep(interval)
    if last:
        raise last
    return None


def api_groups():
    st, payload, raw = L.api_json(d, '/groups?page=1&per_page=200')
    items = (((payload or {}).get('data') or {}).get('items') or [])
    return {x.get('name'): x.get('test_case_count', x.get('testCaseCount')) for x in items}


def api_cases_total():
    st, payload, raw = L.api_json(d, '/testcases?page=1&per_page=1')
    return ((payload or {}).get('data') or {}).get('total')


def card_counts():
    """分组卡：名称 → 条数（从卡片文本 '「组名」\\nN 条' 解析）。"""
    out = {}
    for t in (d.execute_script(CARD_JS) or []):
        lines = [x for x in t.split('\n') if x.strip()]
        if not lines:
            continue
        m = re.search(r'(\d+)\s*条', t)
        out[lines[0].strip()] = int(m.group(1)) if m else None
    return out


def ui_state():
    """同页 UI 计数：分组卡（名称 + 条数）、列表 footer、视图页签。"""
    tabs = []
    for x in d.find_elements(By.CSS_SELECTOR, "[role='tab']"):
        if vis(x):
            t = (x.text or '').strip()
            if t in ('按分组', '按标签') and t not in tabs:
                tabs.append(t)
    active = [x.text.strip() for x in d.find_elements(By.CSS_SELECTOR, "[role='tab']")
              if vis(x) and (x.get_attribute('data-state') == 'active' or x.get_attribute('aria-selected') == 'true')]
    body = L.body_text(d)
    return {'cards': card_counts(), 'tabs': tabs, 'active_tabs': active,
            'footer': re.findall(r'已显示[^\n]*', body),
            'group_tail': re.findall(r'已加载全部\s*\d+\s*个分组', body)}


def load_all_groups():
    for _ in range(12):
        more = next((b for b in d.find_elements(By.TAG_NAME, 'button')
                     if vis(b) and '加载更多' in (b.text or '')), None)
        if not more:
            break
        L.js_click(d, more)
        time.sleep(2.5)


d = L.driver()
try:
    L.login(d)

    def mk_group(name, desc):
        st, payload, raw = L.api_json(d, '/groups', 'POST',
                                      {'name': name, 'description': desc, 'algorithm_type': ''})
        return st, str(((payload or {}).get('data') or {}).get('id') or ''), raw[:200]

    st, SRC_ID, raw = mk_group(SRC, 'INT-1538 P1-3 源组')
    OUT['src_create'] = {'status': st, 'id': SRC_ID}
    st, DST_ID, raw = mk_group(DST, 'INT-1538 P1-3 目标组')
    OUT['dst_create'] = {'status': st, 'id': DST_ID, 'body': raw}

    case_ids = []
    for i in (1, 2, 3):
        st, payload, raw = L.api_json(d, '/testcases', 'POST',
                                      {'name': '%s_%d' % (CASE_PREFIX, i),
                                       'description': 'INT-1538 P1-3 联动计数夹具',
                                       'group_id': SRC_ID})
        cid = str(((payload or {}).get('data') or {}).get('id') or '')
        case_ids.append(cid)
        OUT['case_%d' % i] = {'status': st, 'id': cid}
    OUT['case_ids'] = case_ids

    @sec('linkage')
    def _():
        d.get(L.BASE + '/testcases')
        time.sleep(5)
        # 现页分组卡按条数降序分页，自建组在末页 → 先全部加载出来，同页才能前后对比
        load_all_groups()
        time.sleep(2)

        OUT['api_before'] = api_groups()
        OUT['api_cases_total_before'] = api_cases_total()
        OUT['ui_before'] = ui_state()
        L.shot(d, 'l01_before_batch_light')

        # 组内用例懒加载：不展开时 caseIds 为空（批量会提交 ids:[] 空转），先展开再全选
        def _hdr():
            for el in d.find_elements(By.CSS_SELECTOR, 'div.cursor-pointer'):
                cls = (el.get_attribute('class') or '')
                if 'justify-between' in cls and (el.text or '').strip().startswith(SRC):
                    return el
            return None

        hdr = retry(_hdr, 25)
        d.execute_script('arguments[0].scrollIntoView({block:"center"});', hdr)
        time.sleep(0.8)
        L.js_click(d, hdr)
        time.sleep(4)
        # 全选分组
        chk = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, '[aria-label]')
                                  if (x.get_attribute('aria-label') or '') == '全选分组 ' + SRC), None), 20)
        L.js_click(d, chk)
        time.sleep(2)
        OUT['selected_count_text'] = re.findall(r'已选\s*\d+\s*[条个]', L.body_text(d))[:3]

        # 组头「批量修改」→ 调整分组（aria-label = 组名 + 批量修改）
        def _trig():
            for b in d.find_elements(By.CSS_SELECTOR, 'button'):
                if vis(b) and (b.get_attribute('aria-label') or '') == SRC + ' 批量修改':
                    return b
            return None

        trig = retry(_trig, 25)
        d.execute_script('arguments[0].scrollIntoView({block:"center"});', trig)
        time.sleep(0.8)
        L.clear_fetch_log(d)
        L.js_click(d, trig)
        time.sleep(1.2)
        item = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='menuitem'], button")
                                   if vis(x) and (x.text or '').strip() == '调整分组'), None), 15)
        L.js_click(d, item)
        time.sleep(1.5)
        dlg = retry(lambda: next((x for x in L.dialogs(d) if '批量调整分组' in (x.text or '')), None), 15)
        OUT['dialog_text'] = (dlg.text or '')[:300]
        L.shot(d, 'l02_adjust_group_dialog_light')
        L.apply_theme(d, 'dark')
        time.sleep(1)
        L.shot(d, 'l03_adjust_group_dialog_dark')
        L.apply_theme(d, 'light')
        time.sleep(0.5)
        # 目标分组 Select
        sel = retry(lambda: next((x for x in dlg.find_elements(By.CSS_SELECTOR, "[role='combobox'], button")
                                  if vis(x) and ('请选择分组' in (x.text or '') or '分组' in (x.text or ''))), None), 15)
        L.js_click(d, sel)
        time.sleep(1.2)
        opt = retry(lambda: next((x for x in d.find_elements(By.CSS_SELECTOR, "[role='option'], button, div")
                                  if vis(x) and (x.text or '').strip() == DST), None), 15)
        L.js_click(d, opt)
        time.sleep(1)
        L.shot(d, 'l04_target_selected_light')
        ok = retry(lambda: next((x for x in dlg.find_elements(By.TAG_NAME, 'button')
                                 if vis(x) and (x.text or '').strip() == '确定'), None), 15)
        L.js_click(d, ok)
        time.sleep(4)
        OUT['toasts'] = L.wait_toast(d, 15)
        OUT['batch_fetch'] = [(e.get('method'), e.get('url', '')[:70], e.get('status'), (e.get('reqBody') or '')[:200])
                              for e in L.fetch_log(d) if 'batch' in (e.get('url') or '')]

        # 同页不刷新读计数（组卡集合因计数变化重排，补加载一次再看）
        time.sleep(2)
        load_all_groups()
        OUT['api_after'] = api_groups()
        OUT['api_cases_total_after'] = api_cases_total()
        OUT['ui_after'] = ui_state()
        L.shot(d, 'l05_after_batch_light')
        L.apply_theme(d, 'dark')
        time.sleep(1)
        L.shot(d, 'l06_after_batch_dark')
        L.apply_theme(d, 'light')

    # 清理：软删 3 条夹具用例 + 两个自建组（库内软删行由收尾 SQL 清）
    OUT['cleanup'] = []
    for cid in case_ids:
        if cid:
            st, _p, raw = L.api_json(d, '/testcases/' + cid, 'DELETE')
            OUT['cleanup'].append({'case': cid, 'status': st})
    for gid in (SRC_ID, DST_ID):
        if gid:
            st, _p, raw = L.api_json(d, '/groups/' + gid, 'DELETE')
            OUT['cleanup'].append({'group': gid, 'status': st})
finally:
    L.save_evidence('round5_linkage', OUT)
    print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
    try:
        d.quit()
    except Exception:
        pass
