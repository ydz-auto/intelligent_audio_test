# -*- coding: utf-8 -*-
"""INT-1777 复测 P2-1（验收器独立复核）：取消 / 关闭后重开不残留上次输入。

覆盖：
  G1 新增态：名称 / 描述 / 最大并发 / 设备类型（Realtime WS）/ 请求模板页签 → 取消 → 重开全复位
  G2 X（关闭按钮）关闭 → 重开复位
  G3 Esc 关闭 → 重开复位
  G4 编辑态：改名 / 描述 / 最大并发 → 取消 → 重开回填已保存值 → 重开直接保存，
     请求体不得含被取消的输入，库内值不变（自建 API，验后删除）
  G5 深色编辑态同场景
  G6 取消 / 重开期间无写请求
  G7 回归探测：弹窗开着时列表后台刷新不得清掉用户正在输入的值（本次修复新增的 form.reset 副作用）

前端：本 run 旁路容器 15277（交付 dist + 15173 同款 nginx）；后端 docker 15000。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402

L.BASE = 'http://127.0.0.1:15277'
L.API = 'http://127.0.0.1:15000'
ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1777_p21r')
os.makedirs(ART, exist_ok=True)

RUN_TAG = time.strftime('%m%d%H%M')
NAME = '接线测试_INT1777_P21R_' + RUN_TAG
NAME_CANCEL = '不该保存的名字_' + RUN_TAG
DESC_SAVED = '原始描述_P21R'
DESC_CANCEL = '不该保存的描述'
MAX_SAVED = '3'

RESULTS = []
SHOTS = []


def check(tag, ok, detail=''):
    RESULTS.append({'item': tag, 'pass': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + tag + (' | ' + str(detail)[:400] if detail else ''), flush=True)
    return ok


def shot(drv, name):
    p = os.path.join(ART, name + '.png')
    drv.save_screenshot(p)
    SHOTS.append(p)
    return p


# ---------------- 元素助手 ----------------

def dlg(drv):
    for _ in range(6):
        try:
            ds = [e for e in drv.find_elements(By.CSS_SELECTOR, "[role='dialog']") if e.is_displayed()]
            return ds[-1] if ds else None
        except Exception:
            time.sleep(0.4)
    return None


def dtext(drv):
    d = dlg(drv)
    return (d.text or '') if d else ''


def by_id(drv, ident):
    return dlg(drv).find_element(By.ID, ident)


def val(drv, ident):
    return drv.find_element(By.ID, ident).get_attribute('value')


def fill(el, text):
    el.click()
    el.send_keys(Keys.CONTROL, 'a')
    el.send_keys(Keys.BACKSPACE)
    if text:
        el.send_keys(text)
    time.sleep(0.3)


def combos(drv):
    return dlg(drv).find_elements(By.CSS_SELECTOR, "[role='combobox']")


def combo_text(drv, idx):
    return (combos(drv)[idx].text or '').strip()


def pick(drv, idx, option_text):
    L.js_click(drv, combos(drv)[idx])
    time.sleep(0.8)
    opts = [o for o in drv.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
    target = None
    for o in opts:
        if (o.text or '').strip() == option_text:
            target = o
            break
    if target is None:
        for o in opts:
            if option_text in (o.text or ''):
                target = o
                break
    if target is None:
        raise RuntimeError('option %r not in %r' % (option_text, [o.text for o in opts]))
    L.js_click(drv, target)
    time.sleep(0.7)


def tab_click(drv, label):
    for t in dlg(drv).find_elements(By.CSS_SELECTOR, "[role='tab']"):
        if (t.text or '').strip() == label:
            L.js_click(drv, t)
            time.sleep(0.6)
            return
    raise RuntimeError('tab not found: %s' % label)


def tab_selected(drv):
    out = []
    for t in dlg(drv).find_elements(By.CSS_SELECTOR, "[role='tab']"):
        if t.get_attribute('aria-selected') == 'true':
            out.append((t.text or '').strip())
    return out


def btn(drv, text):
    for b in dlg(drv).find_elements(By.TAG_NAME, 'button'):
        if (b.text or '').strip() == text:
            return b
    return None


def click_cancel(drv):
    b = btn(drv, '取消')
    if b is None:
        raise RuntimeError('取消 not found')
    L.js_click(drv, b)
    time.sleep(1.3)


def _dialog_open_js(drv):
    """用 JS 判可见弹窗，避开关闭动画期间的 stale element。
    基础页签未挂载时 #api-name 不在 DOM（切到请求模板等页签），用页签字面量兜底。"""
    return bool(drv.execute_script("""
        const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
        const dlgs = Array.from(document.querySelectorAll("[role='dialog']")).filter(vis);
        return dlgs.some(d => (d.innerText || '').includes('请求模板') || !!d.querySelector('#api-name'));
    """))


def dialog_closed(drv, timeout=15):
    for _ in range(int(timeout / 0.5)):
        try:
            if not _dialog_open_js(drv):
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def click_close_x(drv):
    d = dlg(drv)
    closers = d.find_elements(By.CSS_SELECTOR, "[data-slot='dialog-close']")
    if not closers:
        closers = [b for b in d.find_elements(By.TAG_NAME, 'button')
                   if (b.get_attribute('aria-label') or '') in ('Close', '关闭')]
    if not closers:
        raise RuntimeError('X close button not found')
    L.js_click(drv, closers[0])
    time.sleep(1.3)


def press_esc(drv):
    body = drv.find_element(By.TAG_NAME, 'body')
    body.send_keys(Keys.ESCAPE)
    time.sleep(1.3)


def open_new(drv):
    add = [b for b in drv.find_elements(By.TAG_NAME, 'button')
           if b.is_displayed() and (b.text or '').strip() == '新增 API']
    if not add:
        raise RuntimeError('新增 API button not found')
    L.js_click(drv, add[0])
    time.sleep(2.0)
    for _ in range(24):
        d = dlg(drv)
        if d and '新增 API' in (d.text or ''):
            return
        time.sleep(0.5)
    raise RuntimeError('new api dialog not open')


def find_card(drv, name):
    for _ in range(10):
        try:
            cards = [c for c in drv.find_elements(By.CSS_SELECTOR, 'div')
                     if name in (c.text or '') and len(c.text or '') < 800 and c.is_displayed()]
            if cards:
                cards.sort(key=lambda c: len(c.text or ''))
                return cards[0]
        except Exception:
            pass
        time.sleep(0.7)
    return None


def open_edit(drv, name):
    card = find_card(drv, name)
    if card is None:
        raise RuntimeError('card not found: %s' % name)
    drv.execute_script("arguments[0].scrollIntoView({block:'center'});", card)
    time.sleep(0.5)
    more = None
    node = card
    for _ in range(5):
        ms = node.find_elements(By.CSS_SELECTOR, "[aria-label='更多操作']")
        if ms:
            more = ms[-1]
            break
        node = node.find_element(By.XPATH, '..')
    if more is None:
        raise RuntimeError('更多操作 not found')
    L.js_click(drv, more)
    time.sleep(0.9)
    target = None
    for i in drv.find_elements(By.CSS_SELECTOR, "[role='menuitem']"):
        if i.is_displayed() and (i.text or '').strip() == '编辑':
            target = i
            break
    if target is None:
        raise RuntimeError('编辑 menu item not found')
    L.js_click(drv, target)
    time.sleep(2.0)
    for _ in range(24):
        d = dlg(drv)
        if d and '编辑 API' in (d.text or ''):
            return
        time.sleep(0.5)
    raise RuntimeError('edit dialog not open')


def api_list(drv):
    st, payload, raw = L.api_json(drv, '/apis?page=1&page_size=200')
    if st != 200:
        raise RuntimeError('GET /apis failed %s %s' % (st, raw[:200]))
    data = (payload or {}).get('data') or payload or {}
    return data.get('items') or []


def find_api_id(drv, name):
    for it in api_list(drv):
        if (it.get('name') or '') == name:
            return it.get('id')
    return None


def get_api(drv, api_id):
    st, payload, raw = L.api_json(drv, '/apis/%s' % api_id)
    if st != 200:
        raise RuntimeError('GET /apis/%s failed %s' % (api_id, st))
    return (payload or {}).get('data') or payload


def writes(drv, since=0):
    out = []
    for e in L.fetch_log(drv)[since:]:
        u = e.get('url') or ''
        if e.get('method') in ('POST', 'PUT', 'PATCH', 'DELETE') and '/apis' in u and '/health' not in u:
            out.append({'method': e.get('method'), 'url': u, 'status': e.get('status'),
                        'reqBody': e.get('reqBody')})
    return out


def set_theme(drv, mode):
    drv.execute_script("localStorage.setItem('iatp:theme:v1:mode', arguments[0]);", mode)


def goto_resources(drv):
    drv.get(L.BASE + '/start-test')
    time.sleep(5)
    steps = [b for b in drv.find_elements(By.TAG_NAME, 'button')
             if b.is_displayed() and '选择设备' in (b.text or '')]
    if steps:
        L.js_click(drv, steps[0])
        time.sleep(3.5)


def main():
    d = L.driver()
    created_id = None
    try:
        print('LOGIN ->', L.login(d), flush=True)
        d.execute_script(
            "localStorage.setItem('iatp:algorithm:v1', JSON.stringify({state:{algorithmId:'voice_llm'},version:0}));")
        set_theme(d, 'light')
        goto_resources(d)

        # 清理本脚本历史残留（只删本前缀）
        for it in api_list(d):
            if (it.get('name') or '').startswith('接线测试_INT1777_P21R_'):
                L.api_json(d, '/apis/%s' % it.get('id'), 'DELETE')
                print('cleaned stale', it.get('name'), flush=True)

        # ===== 先建一个自建 API 供编辑态用（UI 新建） =====
        open_new(d)
        fill(by_id(d, 'api-name'), NAME)
        fill(by_id(d, 'api-desc'), DESC_SAVED)
        fill(by_id(d, 'max-process'), MAX_SAVED)
        check('自建夹具 API 填名称回显', val(d, 'api-name') == NAME, val(d, 'api-name'))
        L.clear_fetch_log(d)
        L.js_click(d, btn(d, '保存'))
        closed = dialog_closed(d, 25)
        check('自建夹具 API 新建保存后弹窗关闭', closed)
        time.sleep(1.5)
        created_id = find_api_id(d, NAME)
        check('自建夹具 API 出现在列表 / GET 可查', created_id is not None, 'id=%r' % created_id)
        if created_id is None:
            raise RuntimeError('fixture api not created, abort')

        mk = None
        for e in L.fetch_log(d):
            if e.get('method') == 'POST' and '/apis' in (e.get('url') or '') and '/health' not in (e.get('url') or ''):
                mk = e
        if mk and mk.get('reqBody'):
            body = json.loads(mk['reqBody'])
            check('自建夹具 API 创建请求体名正确', body.get('name') == NAME, body.get('name'))

        # ===== G1 新增态取消 → 重开全复位 =====
        L.clear_fetch_log(d)
        w0 = len(L.fetch_log(d))
        open_new(d)
        fill(by_id(d, 'api-name'), NAME_CANCEL)
        fill(by_id(d, 'api-desc'), DESC_CANCEL)
        fill(by_id(d, 'max-process'), '42')
        pick(d, 1, 'Realtime WS')
        dev_before = combo_text(d, 1)
        tab_click(d, '请求模板')
        tmpl_ws = 'WS 请求头' in dtext(d)
        shot(d, 'g1_01_new_before_cancel_light')
        check('G1 取消前设备类型已选 Realtime WS', 'Realtime WS' in dev_before, dev_before)
        check('G1 取消前请求模板显示 WS 组', tmpl_ws)
        click_cancel(d)
        check('G1 新增态取消后弹窗关闭', dialog_closed(d))

        open_new(d)
        v_name, v_desc, v_max = val(d, 'api-name'), val(d, 'api-desc'), val(d, 'max-process')
        v_dev = combo_text(d, 1)
        check('G1 重开名称复位为空', v_name == '', repr(v_name))
        check('G1 重开描述复位为空', v_desc == '', repr(v_desc))
        check('G1 重开最大并发复位 5', v_max == '5', repr(v_max))
        check('G1 重开设备类型回「自动」', '自动' in v_dev, repr(v_dev))
        check('G1 重开页签回「基础」', tab_selected(d) == ['基础'], tab_selected(d))
        tab_click(d, '请求模板')
        check('G1 重开请求模板回 HTTP 组（无 WS 请求头）', 'WS 请求头' not in dtext(d),
              [x for x in ('请求头', 'WS 请求头', '请求体模板（body_template）') if x in dtext(d)])
        check('G1 重开请求模板可见 HTTP 组字段', '请求体模板（body_template）' in dtext(d))
        shot(d, 'g1_02_reopen_new_light')
        click_cancel(d)

        # ===== G2 X 关闭 → 重开复位 =====
        open_new(d)
        fill(by_id(d, 'api-name'), 'X关闭残留名')
        click_close_x(d)
        check('G2 X 关闭后弹窗消失', dialog_closed(d))
        open_new(d)
        check('G2 X 关闭后重开名称复位', val(d, 'api-name') == '', repr(val(d, 'api-name')))
        shot(d, 'g2_reopen_after_xclose_light')
        click_cancel(d)

        # ===== G3 Esc 关闭 → 重开复位 =====
        open_new(d)
        fill(by_id(d, 'api-name'), 'Esc关闭残留名')
        press_esc(d)
        check('G3 Esc 关闭后弹窗消失', dialog_closed(d))
        open_new(d)
        check('G3 Esc 关闭后重开名称复位', val(d, 'api-name') == '', repr(val(d, 'api-name')))
        click_cancel(d)

        # ===== G6（前半）取消 / 重开期间无写请求 =====
        w_cancel = writes(d, w0)
        check('G6 取消 / X / Esc 往返期间无写请求', len(w_cancel) == 0,
              json.dumps(w_cancel, ensure_ascii=False)[:300])

        # ===== G4 编辑态取消 → 重开回填 → 直接保存不写被取消的输入 =====
        open_edit(d, NAME)
        e_name, e_desc, e_max = val(d, 'api-name'), val(d, 'api-desc'), val(d, 'max-process')
        check('G4 编辑态打开回填名称', e_name == NAME, repr(e_name))
        check('G4 编辑态打开回填描述', e_desc == DESC_SAVED, repr(e_desc))
        check('G4 编辑态打开回填最大并发', e_max == MAX_SAVED, repr(e_max))
        fill(by_id(d, 'api-name'), '不该保存的名字_EDIT')
        fill(by_id(d, 'api-desc'), DESC_CANCEL)
        fill(by_id(d, 'max-process'), '77')
        pick(d, 1, 'Realtime WS')
        click_cancel(d)
        check('G4 编辑态取消后弹窗关闭', dialog_closed(d))

        open_edit(d, NAME)
        r_name, r_desc, r_max = val(d, 'api-name'), val(d, 'api-desc'), val(d, 'max-process')
        r_dev = combo_text(d, 1)
        check('G4 重开名称回到已保存值', r_name == NAME, repr(r_name))
        check('G4 重开描述回到已保存值', r_desc == DESC_SAVED, repr(r_desc))
        check('G4 重开最大并发回到已保存值', r_max == MAX_SAVED, repr(r_max))
        # 保存时 auto 按端点派生落成 http_api，重开应显示已保存的 HTTP API（而不是被取消的 Realtime WS）
        check('G4 重开设备类型回到已保存值（HTTP API，非被取消的 Realtime WS）',
              ('HTTP API' in r_dev) and ('Realtime WS' not in r_dev), repr(r_dev))
        shot(d, 'g4_01_reopen_edit_light')

        L.clear_fetch_log(d)
        save_btn = btn(d, '保存')
        L.js_click(d, save_btn)
        saved_closed = dialog_closed(d, 25)
        time.sleep(1.5)
        puts = [e for e in writes(d) if e['method'] == 'PUT']
        check('G4 重开直接保存发出 PUT 且弹窗关闭', saved_closed and len(puts) >= 1,
              'closed=%r puts=%d' % (saved_closed, len(puts)))
        body = json.loads(puts[-1]['reqBody']) if puts and puts[-1].get('reqBody') else {}
        check('G4 保存请求体名称 = 已保存值（无被取消的输入）', body.get('name') == NAME, repr(body.get('name')))
        check('G4 保存请求体描述 = 已保存值', body.get('description') == DESC_SAVED, repr(body.get('description')))
        check('G4 保存请求体最大并发 = 已保存值', body.get('default_max_process') == int(MAX_SAVED),
              repr(body.get('default_max_process')))
        check('G4 保存请求体不含被取消的设备类型 websocket_api',
              body.get('device_type') != 'websocket_api', repr(body.get('device_type')))
        check('G4 保存请求体无被取消的字面残留',
              '不该保存的名字_EDIT' not in json.dumps(body, ensure_ascii=False)
              and DESC_CANCEL not in json.dumps(body, ensure_ascii=False),
              json.dumps(body, ensure_ascii=False)[:300])
        got = get_api(d, created_id)
        check('G4 库内名称未被污染', got.get('name') == NAME, repr(got.get('name')))
        check('G4 库内描述未被污染', got.get('description') == DESC_SAVED, repr(got.get('description')))

        # ===== G6（后半）编辑态取消 / 重开期间也无写请求 =====
        # 注：G4 那次 PUT 是有意的保存，单独核对条数
        all_w = writes(d)
        check('G6 编辑态往返期间仅 1 条写请求（即 G4 有意的保存）',
              len([e for e in all_w if e['method'] == 'PUT']) == 1,
              json.dumps([(e['method'], e['url']) for e in all_w], ensure_ascii=False)[:300])

        # ===== G7 回归探测：弹窗开着时后台刷新不得清掉正在输入的值 =====
        open_edit(d, NAME)
        fill(by_id(d, 'api-name'), '正在输入的名字')
        L.clear_fetch_log(d)
        d.execute_script("""
            try { Object.defineProperty(document,'visibilityState',{configurable:true,get:()=>'visible'}); } catch(e) {}
            window.dispatchEvent(new Event('focus'));
            document.dispatchEvent(new Event('visibilitychange'));
        """)
        time.sleep(4)
        refetches = [e for e in L.fetch_log(d) if e.get('method') == 'GET' and '/apis' in (e.get('url') or '')]
        g7_name = val(d, 'api-name')
        check('G7 等待 + 焦点事件后正在编辑的名称仍在（未被 form.reset 清掉）',
              g7_name == '正在输入的名字',
              'value=%r refetch=%d' % (g7_name, len(refetches)))
        shot(d, 'g7_refetch_keeps_input_light')
        click_cancel(d)

        # ===== G5 深色编辑态同场景 =====
        set_theme(d, 'dark')
        goto_resources(d)
        open_edit(d, NAME)
        fill(by_id(d, 'api-name'), '深色不该保存的名字')
        click_cancel(d)
        open_edit(d, NAME)
        dark_name = val(d, 'api-name')
        check('G5 深色编辑态重开名称回到已保存值', dark_name == NAME, repr(dark_name))
        shot(d, 'g5_01_reopen_edit_dark')
        click_cancel(d)
        set_theme(d, 'light')

    finally:
        # 数据卫生：删除自建夹具
        try:
            if created_id is not None:
                st, _, raw = L.api_json(d, '/apis/%s' % created_id, 'DELETE')
                print('cleanup DELETE', created_id, st, flush=True)
            for it in api_list(d):
                if (it.get('name') or '').startswith('接线测试_INT1777_P21R_'):
                    L.api_json(d, '/apis/%s' % it.get('id'), 'DELETE')
                    print('cleanup sweep', it.get('name'), flush=True)
        except Exception as e:
            print('cleanup error', e, flush=True)
        d.quit()

    failed = [r for r in RESULTS if not r['pass']]
    print('SUMMARY: %d/%d PASS' % (len(RESULTS) - len(failed), len(RESULTS)), flush=True)
    for r in failed:
        print('FAILED:', r['item'], r['detail'], flush=True)
    print('SHOTS:', json.dumps(SHOTS, ensure_ascii=False), flush=True)
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
