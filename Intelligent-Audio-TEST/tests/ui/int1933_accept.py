# -*- coding: utf-8 -*-
"""INT-1933 验收：React api-edit 五页签窗复走（INT-1777/1778 已合入）+ 加载/错误态重放。

环境：docker 真实栈，后端 api_gateway :15000（库 intelligent_audio_test），前端 :15173。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402

import int1643_lib as L  # noqa: E402

L.BASE = 'http://127.0.0.1:15173'
L.ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1933')
os.makedirs(L.ART, exist_ok=True)

RUN_TAG = time.strftime('%m%d%H%M%S')
NAME = '接线测试_INT1933_' + RUN_TAG
NAME2 = NAME + '_改'
DESC = 'INT-1933 基础页签验收'

RESULTS = []
SHOTS = []
READBACK = []  # {tab, field, submitted, readback, match}
NET = []       # 各页签保存的写请求（含请求/响应体），用于 Network 证据图


def check(tag, ok, detail=''):
    RESULTS.append({'item': tag, 'pass': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + tag + (' | ' + str(detail)[:400] if detail else ''))
    return ok


def record(tab, field, submitted, readback):
    match = submitted == readback
    READBACK.append({'tab': tab, 'field': field, 'submitted': submitted,
                     'readback': readback, 'match': match})
    return match


def shot(drv, name):
    p = L.shot(drv, name)
    SHOTS.append(p)
    return p


# ---------------- 页面元素助手 ----------------

def visible_dialogs(drv):
    return [e for e in drv.find_elements(By.CSS_SELECTOR, "[role='dialog']") if e.is_displayed()]


def dlg(drv):
    for _ in range(6):
        try:
            ds = visible_dialogs(drv)
            return ds[-1] if ds else None
        except Exception:
            time.sleep(0.4)
    return None


def _api_dialog_open(drv):
    for _ in range(4):
        try:
            return bool(drv.execute_script("""
                const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
                    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
                return Array.from(document.querySelectorAll("[role='dialog']")).filter(vis)
                    .some(d => (d.innerText || '').includes('请求模板') || !!d.querySelector('#api-name'));
            """))
        except Exception:
            time.sleep(0.3)
    return False


def dialog_text(drv):
    for _ in range(6):
        try:
            d = dlg(drv)
            return (d.text or '') if d else ''
        except Exception:
            time.sleep(0.3)
    return ''


def btn(drv, text, scope=None, exact=True):
    root = scope or dlg(drv)
    for b in root.find_elements(By.TAG_NAME, 'button'):
        t = (b.text or '').strip()
        if (t == text) if exact else (text in t):
            return b
    return None


def click_btn(drv, text, scope=None, exact=True):
    b = btn(drv, text, scope, exact)
    if b is None:
        raise RuntimeError('button not found: %s' % text)
    L.js_click(drv, b)
    return b


def tab_click(drv, label):
    for t in dlg(drv).find_elements(By.CSS_SELECTOR, "[role='tab']"):
        if (t.text or '').strip() == label:
            L.js_click(drv, t)
            time.sleep(0.6)
            return t
    raise RuntimeError('tab not found: %s' % label)


def tabs_info(drv):
    return [{'label': (t.text or '').strip(), 'selected': t.get_attribute('aria-selected')}
            for t in dlg(drv).find_elements(By.CSS_SELECTOR, "[role='tab']")]


def combos(drv):
    return dlg(drv).find_elements(By.CSS_SELECTOR, "[role='combobox']")


def combo_text(drv, idx):
    return (combos(drv)[idx].text or '').strip()


def pick(drv, idx, option_text):
    el = combos(drv)[idx]
    drv.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    L.js_click(drv, el)
    time.sleep(0.7)
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
    time.sleep(0.6)


def fill(el, text):
    el.click()
    el.send_keys(Keys.CONTROL, 'a')
    if text == '':
        el.send_keys(Keys.BACKSPACE)
    else:
        el.send_keys(text)
    time.sleep(0.25)


def by_id(drv, ident):
    return dlg(drv).find_element(By.ID, ident)


def by_aria(drv, aria):
    return dlg(drv).find_element(By.CSS_SELECTOR, "[aria-label='%s']" % aria)


def tabpanel_info(drv, label):
    """当前选中页签的可见控件盘点（只读页签应 inputs/textarea/combobox 全 0）。"""
    return drv.execute_script("""
        const tabs = Array.from(document.querySelectorAll("[role='tab']"));
        const t = tabs.find(x => (x.innerText||'').trim() === arguments[0]);
        if (!t) return null;
        const panels = Array.from(document.querySelectorAll("[role='tabpanel']"))
            .filter(p => { const r=p.getBoundingClientRect(); return r.width>0 && r.height>0; });
        const p = panels[panels.length-1];
        if (!p) return {panel:false};
        const q = s => Array.from(p.querySelectorAll(s)).filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0;});
        return {
          panel: true,
          inputs: q('input').length,
          textareas: q('textarea').length,
          comboboxes: q("[role='combobox']").length,
          buttons: q('button').map(b=>(b.innerText||b.getAttribute('aria-label')||'').trim()),
          rows: q('table tbody tr').length,
          text: (p.innerText||'').slice(0, 700)
        };
    """, label)


# ---------------- 业务步骤 ----------------

def goto_step2(drv):
    drv.get(L.BASE + '/start-test')
    time.sleep(5)
    steps = [b for b in drv.find_elements(By.TAG_NAME, 'button')
             if b.is_displayed() and '选择设备' in (b.text or '')]
    if not steps:
        raise RuntimeError('step2 button not found')
    L.js_click(drv, steps[0])
    time.sleep(3.5)


def open_edit(drv, api_name):
    """按卡内 checkbox 的 aria-label 精确定位 API 卡，再点行菜单「编辑」。"""
    anchor = None
    for _ in range(10):
        for e in drv.find_elements(By.CSS_SELECTOR, "[aria-label='选择 API %s']" % api_name):
            if e.is_displayed():
                anchor = e
                break
        if anchor:
            break
        time.sleep(0.6)
    if anchor is None:
        # 兜底：按卡片内文本定位最小可见容器（INT-1777 同款）
        for _ in range(8):
            cards = [c for c in drv.find_elements(By.CSS_SELECTOR, 'div')
                     if c.is_displayed() and api_name in (c.text or '')
                     and len(c.text or '') < 800]
            if cards:
                cards.sort(key=lambda c: len(c.text or ''))
                anchor = cards[0]
                break
            time.sleep(0.5)
    if anchor is None:
        raise RuntimeError('api card not found: %s' % api_name)
    drv.execute_script("arguments[0].scrollIntoView({block:'center'});", anchor)
    time.sleep(0.4)
    more = None
    node = anchor
    for _ in range(8):
        node = node.find_element(By.XPATH, '..')
        ms = node.find_elements(By.CSS_SELECTOR, "[aria-label='更多操作']")
        if ms:
            more = ms[0]
            break
    if more is None:
        raise RuntimeError('更多操作 not found for card %s' % api_name)
    L.js_click(drv, more)
    time.sleep(0.9)
    items = [e for e in drv.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if e.is_displayed()]
    target = None
    for i in items:
        if (i.text or '').strip() == '编辑':
            target = i
            break
    if target is None:
        raise RuntimeError('编辑 menu item not found: %r' % [i.text for i in items])
    L.js_click(drv, target)
    time.sleep(2.4)
    for _ in range(20):
        if _api_dialog_open(drv) and '编辑 API' in dialog_text(drv):
            time.sleep(0.6)
            return dlg(drv)
        time.sleep(0.5)
    raise RuntimeError('edit dialog not open')


def cancel(drv):
    click_btn(drv, '取消')
    for _ in range(12):
        time.sleep(0.4)
        if not _api_dialog_open(drv):
            return True
    return False


def save(drv, expect_close=True):
    L.clear_fetch_log(drv)
    click_btn(drv, '保存')
    if expect_close:
        for _ in range(24):
            time.sleep(0.5)
            if not _api_dialog_open(drv):
                return True
        return False
    time.sleep(1.5)
    return False


def api_writes(drv):
    out = []
    for e in L.fetch_log(drv):
        m = e.get('method')
        u = e.get('url') or ''
        if m in ('POST', 'PUT') and '/apis' in u and '/health' not in u and '/stop-test' not in u:
            out.append(e)
    return out


def api_list(drv):
    st, payload, raw = L.api_json(drv, '/apis?page=1&page_size=200')
    if st != 200:
        raise RuntimeError('GET /apis failed %s %s' % (st, raw[:200]))
    data = (payload or {}).get('data') or payload or {}
    return data.get('items') or []


def find_api(drv, name):
    for it in api_list(drv):
        if it.get('name') == name:
            return it
    return None


def get_api(drv, api_id):
    st, payload, raw = L.api_json(drv, '/apis/%d' % api_id)
    if st != 200:
        raise RuntimeError('GET /apis/%s failed %s %s' % (api_id, st, raw[:200]))
    return (payload or {}).get('data') or payload


# ---------------- 注入（加载 / 错误态） ----------------

def inject_fetch(drv, mode):
    drv.execute_script("""
      if (!window.__i1933_prevFetch) window.__i1933_prevFetch = window.fetch;
      const mode = arguments[0];
      window.fetch = async function(input, init) {
        const url = typeof input === 'string' ? input : (input && input.url) || '';
        const method = ((init && init.method) || 'GET').toUpperCase();
        const path = url.split('?')[0];
        if (mode === 'delay-params' && url.indexOf('/algorithm/params') !== -1) {
          await new Promise(r => setTimeout(r, 4000));
        }
        if (mode === 'fail-params' && url.indexOf('/algorithm/params') !== -1) {
          return new Response(JSON.stringify({detail: 'INT-1933 注入 500（params）'}),
            {status: 500, headers: {'content-type': 'application/json'}});
        }
        if (mode === 'fail-mappings' && url.indexOf('/algorithm/mappings') !== -1) {
          return new Response(JSON.stringify({detail: 'INT-1933 注入 500（mappings）'}),
            {status: 500, headers: {'content-type': 'application/json'}});
        }
        if (mode === 'fail-put-api' && method === 'PUT' && /\\/apis\\/\\d+$/.test(path)) {
          return new Response(JSON.stringify({detail: 'INT-1933 注入保存失败', code: 203}),
            {status: 500, headers: {'content-type': 'application/json'}});
        }
        return window.__i1933_prevFetch.apply(this, arguments);
      };
    """, mode)


def restore_fetch(drv):
    drv.execute_script(
        "if (window.__i1933_prevFetch) { window.fetch = window.__i1933_prevFetch; "
        "window.__i1933_prevFetch = null; }")


# ---------------- Network 证据 ----------------

def network_overlay(drv, entries):
    rows = []
    for e in entries:
        req = e.get('reqBody') or ''
        res = e.get('resBody') or ''
        try:
            req = json.dumps(json.loads(req), ensure_ascii=False, indent=1)
        except Exception:
            pass
        try:
            res = json.dumps(json.loads(res), ensure_ascii=False, indent=1)[:2200]
        except Exception:
            res = res[:1200]
        rows.append(
            "<div style='margin-bottom:10px'><div style='color:#0a7;font-weight:700'>%s %s → %s</div>"
            "<div style='font-size:11px;color:#555'>REQUEST</div>"
            "<pre style='margin:2px 0 6px;padding:8px;background:#0f1720;color:#d6e2ea;font-size:11px;"
            "white-space:pre-wrap;border-radius:6px'>%s</pre>"
            "<div style='font-size:11px;color:#555'>RESPONSE</div>"
            "<pre style='margin:2px 0;padding:8px;background:#10251a;color:#cfe9d6;font-size:11px;"
            "white-space:pre-wrap;border-radius:6px'>%s</pre></div>"
            % (e.get('method'), e.get('url'), e.get('status'),
               req.replace('<', '&lt;'), res.replace('<', '&lt;')))
    html = ("<div id='net-evidence' style='position:fixed;inset:16px;z-index:99999;background:#fff;"
            "border:2px solid #333;border-radius:10px;padding:14px;overflow:auto;font-family:monospace;"
            "box-shadow:0 10px 40px rgba(0,0,0,.4)'><h2 style='margin:0 0 10px;font-size:15px'>"
            "INT-1933 Network 证据（页内 fetch 抓包，请求体 + 响应体）</h2>%s</div>"
            % ''.join(rows))
    drv.execute_script(
        "var old=document.getElementById('net-evidence'); if(old) old.remove();"
        "document.body.insertAdjacentHTML('beforeend', arguments[0]);", html)
    time.sleep(0.6)


def remove_overlay(drv):
    drv.execute_script("var e=document.getElementById('net-evidence'); if(e) e.remove();")


def read_toasts(drv):
    return [e.text for e in drv.find_elements(By.CSS_SELECTOR, '[data-sonner-toast]')]


# ================= main =================

def main():
    d = L.driver()
    created_ids = []
    real_before = None
    try:
        print('LOGIN ->', L.login(d))
        goto_step2(d)

        # 真实库现状（防串库 + 真值备份）
        real_before = get_api(d, 1)
        print('REAL_BEFORE', json.dumps(real_before, ensure_ascii=False)[:600])
        L.save_evidence('real_before', real_before)

        # 清理本前缀历史残留
        for it in api_list(d):
            nm = it.get('name') or ''
            if nm.startswith('接线测试_INT1933_'):
                L.api_json(d, '/apis/%s' % it.get('id'), 'DELETE')
                print('cleaned stale', nm, it.get('id'))

        # 建本 run 自建记录（非空 meta + audio_config，模拟既有配置）
        seed = {
            'name': NAME,
            'algorithm_type': 'voice_llm',
            'default_max_process': 5,
            'description': 'INT-1933 验收自建 API',
            'device_type': 'http_api',
            'endpoints': [{
                'endpoint': 'https://api.example.com/v1/asr',
                'name': 'int1933-ep',
                'max_process': 2, 'max_timeout': 30, 'max_audio_duration': 60,
                'status': 'online', 'priority': 1, 'description': None,
            }],
            'meta': {
                'apiKey': 'real-shaped-keep', 'version': 'v1', 'protocol': 'http',
                'environment': 'development', 'appendix_unknown': {'keep': True},
            },
            'audio_config': {'sample_rate': 24000, 'bit_depth': 's16',
                             'channels': 1, 'container': 'pcm'},
        }
        st, payload, raw = L.api_json(d, '/apis', 'POST', seed)
        api_id = ((payload or {}).get('data') or {}).get('id')
        check('S1 自建测试记录（含非空 meta/audio_config）', st in (200, 201) and api_id is not None,
              {'st': st, 'id': api_id, 'raw': raw[:200]})
        if api_id:
            created_ids.append(api_id)
        seeded = get_api(d, api_id)
        L.save_evidence('seeded', seeded)
        # 列表是在建记录之前载入的，重新进步骤二让新卡出现
        goto_step2(d)

        # ============ A. 真实记录只读回显（不保存） ============
        open_edit(d, '1')
        ti = tabs_info(d)
        check('A1 五页签齐全且顺序正确',
              [t['label'] for t in ti] == ['基础', '请求模板', '响应解析', '输出字段', '映射'], ti)
        check('A2 默认落基础页签', ti[0]['selected'] == 'true', ti[0])
        check('A3 真实记录名称回显', by_id(d, 'api-name').get_attribute('value') == '1',
              by_id(d, 'api-name').get_attribute('value'))
        check('A4 关联算法回显算法名（非类型码）', combo_text(d, 0) == '小艺语音大模型', combo_text(d, 0))
        check('A5 最大并发回显', by_id(d, 'max-process').get_attribute('value') == '5',
              by_id(d, 'max-process').get_attribute('value'))
        check('A6 设备类型回显', combo_text(d, 1) == 'HTTP API', combo_text(d, 1))
        audio_pre = [combo_text(d, i) for i in (2, 3, 4, 5)]
        check('A7 真实记录 audio_config 未配置回显未设置', audio_pre == ['未设置'] * 4, audio_pre)
        shot(d, 'A01_real_basic_light')
        L.apply_theme(d, 'dark')
        time.sleep(0.5)
        shot(d, 'A02_real_basic_dark')
        L.apply_theme(d, 'light')
        time.sleep(0.4)

        tab_click(d, '请求模板')
        check('A8 请求模板回显 method 未设置', combo_text(d, 0) == '未设置', combo_text(d, 0))
        shot(d, 'A03_real_request_light')
        L.apply_theme(d, 'dark'); time.sleep(0.5); shot(d, 'A04_real_request_dark')
        L.apply_theme(d, 'light'); time.sleep(0.4)

        tab_click(d, '响应解析')
        time.sleep(1.6)
        rt = dialog_text(d)
        check('A9 响应解析 C0 判定显示已声明输出字段', '已声明 9 个输出字段' in rt,
              [l for l in rt.split('\n') if '输出字段' in l][:2])
        shot(d, 'A05_real_response_light')
        L.apply_theme(d, 'dark'); time.sleep(0.5); shot(d, 'A06_real_response_dark')
        L.apply_theme(d, 'light'); time.sleep(0.4)

        tab_click(d, '输出字段')
        time.sleep(1.8)
        oi = tabpanel_info(d, '输出字段')
        check('A10 输出字段有真实声明行（9 行）', oi and oi['rows'] == 9, oi)
        check('A11 输出字段只读（无 input/textarea/combobox）',
              oi and oi['inputs'] == 0 and oi['textareas'] == 0 and oi['comboboxes'] == 0,
              {k: oi[k] for k in ('inputs', 'textareas', 'comboboxes')} if oi else oi)
        shot(d, 'A07_real_output_light')
        L.apply_theme(d, 'dark'); time.sleep(0.5); shot(d, 'A08_real_output_dark')
        L.apply_theme(d, 'light'); time.sleep(0.4)

        tab_click(d, '映射')
        time.sleep(1.8)
        mi = tabpanel_info(d, '映射')
        check('A12 映射空态文案', mi and '该算法类型未配置来源为 API 输出的映射' in (mi['text'] or ''), mi['text'][:120] if mi else mi)
        check('A13 映射只读（无 input/textarea/combobox）',
              mi and mi['inputs'] == 0 and mi['textareas'] == 0 and mi['comboboxes'] == 0,
              {k: mi[k] for k in ('inputs', 'textareas', 'comboboxes')} if mi else mi)
        shot(d, 'A09_real_mapping_light')
        L.apply_theme(d, 'dark'); time.sleep(0.5); shot(d, 'A10_real_mapping_dark')
        L.apply_theme(d, 'light'); time.sleep(0.4)
        cancel(d)

        # ============ B. 基础页签写 ============
        open_edit(d, NAME)
        fill(by_id(d, 'api-name'), NAME2)
        fill(by_id(d, 'max-process'), '7')
        fill(by_id(d, 'api-desc'), DESC)
        pick(d, 2, '16000 Hz')
        check('B1 基础页签改动前置成功', combo_text(d, 2) == '16000 Hz', combo_text(d, 2))
        ok = save(d)
        writes = api_writes(d)
        NET.extend(writes[-1:])
        check('B2 基础页签保存关闭弹窗', ok, ok)
        reqB = json.loads(writes[0]['reqBody']) if writes and writes[0].get('reqBody') else {}
        L.save_evidence('write_basic', {'request': reqB, 'entry': writes[0] if writes else None})
        detB = get_api(d, api_id)
        record('基础', 'name', NAME2, detB.get('name'))
        record('基础', 'default_max_process', 7, detB.get('default_max_process'))
        record('基础', 'description', DESC, detB.get('description'))
        record('基础', 'audio_config.sample_rate', 16000,
               (detB.get('audio_config') or {}).get('sample_rate'))
        record('基础', 'audio_config.bit_depth', 's16', (detB.get('audio_config') or {}).get('bit_depth'))
        record('基础', 'audio_config.channels', 1, (detB.get('audio_config') or {}).get('channels'))
        record('基础', 'audio_config.container', 'pcm', (detB.get('audio_config') or {}).get('container'))
        check('B3 基础页签 GET 回读一致', all(r['match'] for r in READBACK if r['tab'] == '基础'),
              [r for r in READBACK if r['tab'] == '基础' and not r['match']])
        # 重开回显
        time.sleep(1.2)
        open_edit(d, NAME2)
        check('B4 重开回显名称/最大并发', by_id(d, 'api-name').get_attribute('value') == NAME2
              and by_id(d, 'max-process').get_attribute('value') == '7',
              {'name': by_id(d, 'api-name').get_attribute('value'),
               'max': by_id(d, 'max-process').get_attribute('value')})
        check('B5 重开回显 audio_config 四项',
              [combo_text(d, i) for i in (2, 3, 4, 5)] == ['16000 Hz', 's16', '1（单声道）', 'pcm'],
              [combo_text(d, i) for i in (2, 3, 4, 5)])
        shot(d, 'B01_basic_prefill_light')
        L.apply_theme(d, 'dark'); time.sleep(0.5); shot(d, 'B02_basic_prefill_dark')
        L.apply_theme(d, 'light'); time.sleep(0.4)
        cancel(d)

        # ============ C. 请求模板页签写 ============
        open_edit(d, NAME2)
        tab_click(d, '请求模板')
        pick(d, 0, 'PUT')
        click_btn(d, '添加请求头')
        time.sleep(0.5)
        fill(by_aria(d, '请求头名称'), 'X-Int1933')
        fill(by_aria(d, '请求头值'), 'yes')
        fill(by_id(d, 'meta-body-template'), '{"text":"{{text}}","temperature":0.3}')
        fill(by_id(d, 'meta-vendor-adapter'), 'HttpApiAdapter')
        save(d)
        writes = api_writes(d)
        NET.extend(writes[-1:])
        reqC = json.loads(writes[0]['reqBody']) if writes and writes[0].get('reqBody') else {}
        L.save_evidence('write_request', {'request': reqC, 'entry': writes[0] if writes else None})
        detC = get_api(d, api_id)
        metaC = detC.get('meta') or {}
        record('请求模板', 'meta.method', 'PUT', metaC.get('method'))
        record('请求模板', 'meta.headers', {'X-Int1933': 'yes'}, metaC.get('headers'))
        record('请求模板', 'meta.body_template',
               {'text': '{{text}}', 'temperature': 0.3}, metaC.get('body_template'))
        record('请求模板', 'meta.vendor_adapter', 'HttpApiAdapter', metaC.get('vendor_adapter'))
        check('C1 请求模板 GET 回读一致',
              all(r['match'] for r in READBACK if r['tab'] == '请求模板'),
              [r for r in READBACK if r['tab'] == '请求模板' and not r['match']])
        check('C2 未知 meta 键保留（apiKey / appendix_unknown）',
              metaC.get('apiKey') == 'real-shaped-keep'
              and metaC.get('appendix_unknown') == {'keep': True},
              {k: metaC.get(k) for k in ('apiKey', 'appendix_unknown')})
        check('C3 基础页签字段未被请求模板保存清空',
              (detC.get('audio_config') or {}).get('sample_rate') == 16000
              and detC.get('default_max_process') == 7,
              {'audio': detC.get('audio_config'), 'max': detC.get('default_max_process')})
        time.sleep(1.2)
        open_edit(d, NAME2)
        tab_click(d, '请求模板')
        check('C4 重开回显 method/header/body',
              combo_text(d, 0) == 'PUT'
              and by_aria(d, '请求头名称').get_attribute('value') == 'X-Int1933'
              and '{{text}}' in (by_id(d, 'meta-body-template').get_attribute('value') or ''),
              {'method': combo_text(d, 0),
               'header': by_aria(d, '请求头名称').get_attribute('value'),
               'body': (by_id(d, 'meta-body-template').get_attribute('value') or '')[:60]})
        shot(d, 'C01_request_prefill_light')
        L.apply_theme(d, 'dark'); time.sleep(0.5); shot(d, 'C02_request_prefill_dark')
        L.apply_theme(d, 'light'); time.sleep(0.4)
        cancel(d)

        # ============ D. 响应解析页签写 ============
        open_edit(d, NAME2)
        tab_click(d, '响应解析')
        time.sleep(1.2)
        fill(by_id(d, 'meta-result-parser'),
             '{"asr_text_path":"data.text","session_id_path":"data.session_id"}')
        fill(by_id(d, 'meta-asr-mapping'), '$.data.text')
        pick(d, 0, '否（保留最后一条分片）')
        save(d)
        writes = api_writes(d)
        NET.extend(writes[-1:])
        reqD = json.loads(writes[0]['reqBody']) if writes and writes[0].get('reqBody') else {}
        L.save_evidence('write_response', {'request': reqD, 'entry': writes[0] if writes else None})
        detD = get_api(d, api_id)
        metaD = detD.get('meta') or {}
        record('响应解析', 'meta.result_parser',
               {'asr_text_path': 'data.text', 'session_id_path': 'data.session_id'},
               metaD.get('result_parser'))
        record('响应解析', 'meta.asr_mapping', '$.data.text', metaD.get('asr_mapping'))
        record('响应解析', 'meta.append_mode', False, metaD.get('append_mode'))
        check('D1 响应解析 GET 回读一致',
              all(r['match'] for r in READBACK if r['tab'] == '响应解析'),
              [r for r in READBACK if r['tab'] == '响应解析' and not r['match']])
        check('D2 请求模板 meta 跨页签保存后仍在（不再被静默清空）',
              metaD.get('method') == 'PUT'
              and metaD.get('headers') == {'X-Int1933': 'yes'}
              and '{{text}}' in json.dumps(metaD.get('body_template') or {}, ensure_ascii=False),
              {k: metaD.get(k) for k in ('method', 'headers', 'body_template')})
        check('D3 audio_config 跨页签保存后仍在',
              (detD.get('audio_config') or {}).get('sample_rate') == 16000,
              detD.get('audio_config'))
        check('D4 未知 meta 键仍保留', metaD.get('apiKey') == 'real-shaped-keep'
              and metaD.get('appendix_unknown') == {'keep': True},
              {k: metaD.get(k) for k in ('apiKey', 'appendix_unknown')})
        time.sleep(1.2)
        open_edit(d, NAME2)
        tab_click(d, '响应解析')
        time.sleep(1.2)
        check('D5 重开回显 result_parser/asr_mapping/append_mode',
              'asr_text_path' in (by_id(d, 'meta-result-parser').get_attribute('value') or '')
              and by_id(d, 'meta-asr-mapping').get_attribute('value') == '$.data.text'
              and combo_text(d, 0) == '否（保留最后一条分片）',
              {'parser': (by_id(d, 'meta-result-parser').get_attribute('value') or '')[:60],
               'asr': by_id(d, 'meta-asr-mapping').get_attribute('value'),
               'append': combo_text(d, 0)})
        shot(d, 'D01_response_prefill_light')
        L.apply_theme(d, 'dark'); time.sleep(0.5); shot(d, 'D02_response_prefill_dark')
        L.apply_theme(d, 'light'); time.sleep(0.4)

        # ============ E. 只读页签（自建记录，数据态截图） ============
        tab_click(d, '输出字段')
        time.sleep(1.6)
        oi2 = tabpanel_info(d, '输出字段')
        check('E1 自建记录输出字段只读且有数据',
              oi2 and oi2['rows'] == 9 and oi2['inputs'] == 0 and oi2['textareas'] == 0
              and oi2['comboboxes'] == 0,
              {k: oi2[k] for k in ('rows', 'inputs', 'textareas', 'comboboxes')} if oi2 else oi2)
        check('E2 输出字段提供「去算法配置」入口', oi2 and '去算法配置' in (oi2['buttons'] or []),
              oi2['buttons'] if oi2 else oi2)
        shot(d, 'E01_output_light')
        L.apply_theme(d, 'dark'); time.sleep(0.5); shot(d, 'E02_output_dark')
        L.apply_theme(d, 'light'); time.sleep(0.4)
        tab_click(d, '映射')
        time.sleep(1.6)
        mi2 = tabpanel_info(d, '映射')
        check('E3 自建记录映射只读空态',
              mi2 and mi2['inputs'] == 0 and mi2['rows'] == 0
              and '未配置来源为 API 输出的映射' in (mi2['text'] or ''),
              {k: mi2[k] for k in ('rows', 'inputs')} if mi2 else mi2)
        shot(d, 'E03_mapping_light')
        L.apply_theme(d, 'dark'); time.sleep(0.5); shot(d, 'E04_mapping_dark')
        L.apply_theme(d, 'light'); time.sleep(0.4)

        # ============ F. 交互边界：页签切换草稿保留 ============
        tab_click(d, '请求模板')
        pick(d, 0, 'POST')
        fill(by_id(d, 'meta-body-template'), '{"text":"DRAFT_KEEP_1933"}')
        tab_click(d, '基础')
        time.sleep(0.5)
        tab_click(d, '响应解析')
        time.sleep(0.5)
        tab_click(d, '请求模板')
        check('F1 页签切换往返不丢未保存改动',
              combo_text(d, 0) == 'POST'
              and 'DRAFT_KEEP_1933' in (by_id(d, 'meta-body-template').get_attribute('value') or ''),
              {'method': combo_text(d, 0),
               'body': (by_id(d, 'meta-body-template').get_attribute('value') or '')[:60]})
        # 关闭时是否有未保存改动守卫（观察项）
        closed = cancel(d)
        check('F2 取消关闭即时生效（无未保存改动确认弹窗）', closed, closed)
        RESULTS.append({'item': 'F2-note 未保存改动守卫：当前实现无离开确认（观察项，见结论）',
                        'pass': True, 'detail': '取消直接关闭'})

        # ============ G. 保存失败态可见 ============
        inject_fetch(d, 'fail-put-api')
        open_edit(d, NAME2)
        fill(by_id(d, 'api-name'), 'SHOULD_NOT_SAVE_1933')
        L.clear_fetch_log(d)
        click_btn(d, '保存')
        time.sleep(1.1)
        toasts = read_toasts(d)
        toast_txt = ' | '.join(toasts)
        still_open = _api_dialog_open(d)
        shot(d, 'G01_save_fail_light')
        L.apply_theme(d, 'dark'); time.sleep(0.5); shot(d, 'G02_save_fail_dark')
        L.apply_theme(d, 'light'); time.sleep(0.4)
        check('G1 保存失败 toast 可见', '保存失败' in toast_txt, toast_txt)
        detG = get_api(d, api_id)
        check('G2 保存失败未写库', detG.get('name') == NAME2, detG.get('name'))
        restore_fetch(d)
        L.save_evidence('save_fail', {'toasts': toasts, 'dialog_still_open': still_open})
        RESULTS.append({'item': 'G-note 保存失败后弹窗状态', 'pass': True,
                        'detail': '弹窗仍开' if still_open else '弹窗已关闭（输入丢失，见结论）'})
        if _api_dialog_open(d):
            cancel(d)

        # ============ H. 加载态重放 ============
        goto_step2(d)  # 新页面清空 react-query 缓存，确保走真实 loading
        inject_fetch(d, 'delay-params')
        open_edit(d, NAME2)
        tab_click(d, '输出字段')
        t0 = time.time()
        shot(d, 'H01_output_loading_light')
        loading_txt = dialog_text(d)
        check('H1 输出字段加载态可见（慢请求）',
              '正在读取该算法类型的输出字段声明' in loading_txt,
              {'elapsed': round(time.time() - t0, 2),
               'hit': [l for l in loading_txt.split('\n') if '正在读取' in l]})
        time.sleep(4.8)  # 等慢请求落地，确认最终仍渲染
        oi3 = tabpanel_info(d, '输出字段')
        check('H2 慢请求完成后输出字段正常渲染', oi3 and oi3['rows'] == 9,
              oi3['rows'] if oi3 else oi3)
        restore_fetch(d)
        if _api_dialog_open(d):
            cancel(d)

        # ============ I. 错误态重放 ============
        goto_step2(d)  # 新页面清空缓存，避免旧的成功结果掩盖错误态
        inject_fetch(d, 'fail-params')
        open_edit(d, NAME2)
        tab_click(d, '输出字段')
        time.sleep(2.0)
        ei = tabpanel_info(d, '输出字段')
        check('I1 输出字段错误态可见（注入 500）',
              ei and '输出字段读取失败' in (ei['text'] or ''), (ei['text'] or '')[:160] if ei else ei)
        shot(d, 'I01_output_error_light')
        L.apply_theme(d, 'dark'); time.sleep(0.5); shot(d, 'I02_output_error_dark')
        L.apply_theme(d, 'light'); time.sleep(0.4)
        restore_fetch(d)
        if _api_dialog_open(d):
            cancel(d)

        goto_step2(d)
        inject_fetch(d, 'fail-mappings')
        open_edit(d, NAME2)
        tab_click(d, '映射')
        time.sleep(2.0)
        em = tabpanel_info(d, '映射')
        check('I3 映射错误态可见（注入 500）',
              em and '映射读取失败' in (em['text'] or ''), (em['text'] or '')[:160] if em else em)
        shot(d, 'I03_mapping_error_light')
        restore_fetch(d)
        if _api_dialog_open(d):
            cancel(d)

        # ============ J. Network 证据图 ============
        L.apply_theme(d, 'light')
        time.sleep(0.4)
        goto_step2(d)
        L.save_evidence('network', NET)
        network_overlay(d, NET[-2:] if NET else [])
        shot(d, 'J01_network_evidence')
        remove_overlay(d)

        # ============ K. 收尾：删自建 + 真实记录未变 ============
        st, _, raw = L.api_json(d, '/apis/%d' % api_id, 'DELETE')
        gone = find_api(d, NAME) is None and find_api(d, NAME2) is None
        check('K1 删除自建测试记录', st in (200, 204) and gone, {'st': st, 'raw': raw[:120]})
        created_ids = []
        real_after = get_api(d, 1)
        keys = ['name', 'meta', 'audio_config', 'default_max_process', 'description',
                'device_type', 'algorithm_type']
        diff = {k: (real_before.get(k), real_after.get(k)) for k in keys
                if real_before.get(k) != real_after.get(k)}
        check('K2 真实记录 id=1 未被改动', not diff, diff)

        L.save_evidence('readback', READBACK)
        L.save_evidence('results', {'name': NAME, 'api_id': api_id, 'results': RESULTS,
                                    'readback': READBACK})
        fails = [r for r in RESULTS if not r['pass']]
        print('\nREADBACK')
        for r in READBACK:
            print('  [%s] %-28s submitted=%r readback=%r %s'
                  % (r['tab'], r['field'], r['submitted'], r['readback'],
                     'OK' if r['match'] else 'MISMATCH'))
        print('\nSUMMARY %d/%d pass, fails=%s'
              % (len(RESULTS) - len(fails), len(RESULTS), [f['item'] for f in fails]))
        print('SHOTS', SHOTS)
        return 0 if not fails else 2
    finally:
        try:
            for i in created_ids:
                L.api_json(d, '/apis/%s' % i, 'DELETE')
        except Exception:
            pass
        try:
            d.quit()
        except Exception:
            pass


if __name__ == '__main__':
    sys.exit(main())
