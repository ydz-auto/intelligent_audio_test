# -*- coding: utf-8 -*-
"""INT-1538 返工 P1-2：分组「改名 → 删除（确认框）→ 软删核对 → 同名再建状态码原文」。

UI 侧：编辑分组弹窗改名 + 保存；删除分组确认框 + 确认。
API 侧：核对 /groups 列表、同名 POST 的状态码原文（软删后同名复用口径）。
浅/深截图 + fetch 请求响应取证。自建组带 接线测试_ 前缀，脚本末尾清理（库内软删行由收尾 SQL 清）。
"""
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1538_lib as L
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait

TAG = time.strftime('%m%d%H%M%S')
NAME = '接线测试_INT1538_R5组_' + TAG
NAME2 = NAME + '_改'
OUT = {'tag': TAG, 'group_name': NAME, 'renamed': NAME2, 'sections': {}}


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


def fill(el, value):
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.DELETE)
    el.send_keys(value)


def group_dialog(name_hint='分组'):
    ds = [x for x in L.dialogs(d) if name_hint in (x.text or '') and '用例' not in (x.text or '')[:4]]
    return ds[-1] if ds else None


def pick_group_filter(name):
    """分组全部 facet → 选中自建组（圈定组卡，组头才有编辑/删除）。"""
    rst = next((b for b in d.find_elements(By.TAG_NAME, 'button') if vis(b) and (b.text or '').strip() == '重置'), None)
    if rst:
        L.js_click(d, rst)
        time.sleep(3)
    trig = retry(lambda: next((b for b in d.find_elements(By.TAG_NAME, 'button')
                               if vis(b) and (b.text or '').replace('\n', '') == '分组全部'), None), 25)
    L.js_click(d, trig)
    time.sleep(1.2)
    def _opt():
        cands = [b for b in d.find_elements(By.CSS_SELECTOR, "button, [role='option']") if vis(b)]
        for b in cands:
            if name in (b.text or ''):
                return b
        # 选项文本可能被截断：退回片段匹配
        for b in cands:
            t = (b.text or '').strip()
            if 'INT1538_R5组' in t and t.endswith(('…', '...')):
                return b
        return None

    opt = retry(_opt, 20)
    if opt is None:
        raise RuntimeError('facet option not found: ' + name)
    L.js_click(d, opt)
    time.sleep(4)
    for _ in range(6):
        if name in L.body_text(d):
            break
        more = next((b for b in d.find_elements(By.TAG_NAME, 'button')
                     if vis(b) and '加载更多' in (b.text or '')), None)
        if not more:
            break
        L.js_click(d, more)
        time.sleep(4)


def group_card_buttons(label):
    return [b for b in d.find_elements(By.TAG_NAME, 'button')
            if vis(b) and (b.text or '').strip() == label]


def all_groups():
    st, payload, raw = L.api_json(d, '/groups?page=1&per_page=200')
    items = (((payload or {}).get('data') or {}).get('items') or [])
    return st, items


def group_exists(name):
    """分组 keyword 参数不过滤（实测），改用全量列表按名判定存在性。"""
    _st, items = all_groups()
    return any((x.get('name') or '') == name for x in items)


d = L.driver()
try:
    L.login(d)
    d.get(L.BASE + '/testcases')
    time.sleep(5)

    # 建组（UI 无「新建分组」入口，已在第二轮裁定 P3；此处用真实接口建自建组）
    st, payload, raw = L.api_json(d, '/groups', 'POST',
                                  {'name': NAME, 'description': 'INT-1538 返工 P1-2 自建组', 'algorithm_type': ''})
    OUT['create_group'] = {'status': st, 'body': raw[:300]}
    GID = str(((payload or {}).get('data') or {}).get('id') or '')
    OUT['group_id'] = GID
    if not GID:
        raise RuntimeError('create group failed: ' + raw[:300])

    # 空组不渲染组卡（INT-595 空态优先），先补 1 条用例让组头出现
    st, payload, raw = L.api_json(d, '/testcases', 'POST',
                                  {'name': '接线测试_INT1538_R5组内用例_' + TAG,
                                   'description': 'INT-1538 返工 P1-2 组卡渲染用',
                                   'group_id': GID})
    OUT['create_case'] = {'status': st, 'body': raw[:300]}
    OUT['case_id'] = str(((payload or {}).get('data') or {}).get('id') or '')

    OUT['exists_after_create'] = group_exists(NAME)

    @sec('rename')
    def _():
        d.get(L.BASE + '/testcases')
        time.sleep(5)
        pick_group_filter(NAME)
        L.clear_fetch_log(d)
        L.shot(d, 'g01_group_card_light')
        edit_btns = retry(lambda: group_card_buttons('编辑') or None, 20)
        L.js_click(d, edit_btns[0])
        time.sleep(1.5)
        top = retry(lambda: group_dialog(), 15)
        OUT['edit_dialog_text'] = (top.text or '')[:300]
        L.shot(d, 'g02_group_edit_dialog_light')
        inp = [i for i in top.find_elements(By.TAG_NAME, 'input') if vis(i)]
        OUT['name_before'] = inp[0].get_attribute('value') if inp else None
        fill(inp[0], NAME2)
        L.shot(d, 'g03_group_renamed_input_light')
        for c in top.find_elements(By.TAG_NAME, 'button'):
            if (c.text or '').strip() in ('保存', '确定', '确认') and vis(c):
                L.js_click(d, c)
                break
        time.sleep(3)
        OUT['rename_toasts'] = L.wait_toast(d, 12)
        OUT['rename_fetch'] = [(e.get('method'), e.get('url', '')[:80], e.get('status'), e.get('reqBody'))
                               for e in L.fetch_log(d) if '/groups' in (e.get('url') or '')]
        OUT['exists_after_rename'] = group_exists(NAME2)
        OUT['old_name_still_exists'] = group_exists(NAME)
        L.shot(d, 'g04_after_rename_light')

    @sec('delete')
    def _():
        # 重新圈定（改名后 facet 选项已变）
        d.get(L.BASE + '/testcases')
        time.sleep(5)
        pick_group_filter(NAME2)
        L.clear_fetch_log(d)
        del_btns = retry(lambda: group_card_buttons('删除') or None, 20)
        OUT['delete_btn_count'] = len(del_btns)
        L.js_click(d, del_btns[0])
        time.sleep(2.5)

        def _confirm():
            # ConfirmDialog 用 AlertDialog（role=alertdialog），不是 role=dialog
            for x in d.find_elements(By.CSS_SELECTOR, "[role='alertdialog'], [role='dialog']"):
                if vis(x) and '删除' in (x.text or ''):
                    return x
            return None

        w = retry(_confirm, 20)
        OUT['delete_dialog_text'] = (w.text or '')[:400]
        L.shot(d, 'g05_group_delete_confirm_light')
        L.apply_theme(d, 'dark')
        time.sleep(1)
        L.shot(d, 'g06_group_delete_confirm_dark')
        L.apply_theme(d, 'light')
        time.sleep(0.5)
        # 确认删除按钮（弹窗内，非「取消」）
        btn = None
        for c in w.find_elements(By.TAG_NAME, 'button'):
            t = (c.text or '').strip()
            if vis(c) and t in ('删除', '确定', '确认', '删除分组'):
                btn = c
                break
        OUT['delete_confirm_button'] = (btn.text or '').strip() if btn else None
        if btn is not None:
            L.js_click(d, btn)
        time.sleep(3)
        OUT['delete_toasts'] = L.wait_toast(d, 12)
        OUT['delete_fetch'] = [(e.get('method'), e.get('url', '')[:80], e.get('status'))
                               for e in L.fetch_log(d) if '/groups' in (e.get('url') or '')]
        time.sleep(1)
        L.shot(d, 'g07_after_delete_light')
        OUT['exists_after_delete'] = group_exists(NAME2)
        st3, items3 = all_groups()
        OUT['groups_total_after_delete'] = len(items3)

    @sec('recreate_same_name')
    def _():
        # 软删后同名再建，抓状态码原文
        L.clear_fetch_log(d)
        st, payload, raw = L.api_json(d, '/groups', 'POST',
                                      {'name': NAME2, 'description': '同名复用探针', 'algorithm_type': ''})
        OUT['recreate'] = {'status': st, 'body': raw[:400]}
        gid2 = str(((payload or {}).get('data') or {}).get('id') or '')
        OUT['recreate_id'] = gid2
        OUT['exists_after_recreate'] = group_exists(NAME2)
        # 清理再建出来的组
        if gid2:
            st5, _p, r5 = L.api_json(d, '/groups/' + gid2, 'DELETE')
            OUT['cleanup_delete2'] = {'status': st5, 'body': r5[:200]}
finally:
    L.save_evidence('round5_group', OUT)
    print(json.dumps(OUT, ensure_ascii=False, indent=1, default=str))
    try:
        d.quit()
    except Exception:
        pass
