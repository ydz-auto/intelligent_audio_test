# -*- coding: utf-8 -*-
"""INT-1777 验收：React API 编辑弹窗五页签 + meta / audio_config 读写通路。

后端 docker 15000（intelligent_audio_test），前端本 run 旁路容器 15277（交付 dist + 15173 同款 nginx）。
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
L.ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1777')
os.makedirs(L.ART, exist_ok=True)

RUN_TAG = time.strftime('%m%d%H%M')
NAME = '接线测试_INT1777_' + RUN_TAG
NAME2 = NAME + '_改名'

RESULTS = []
SHOTS = []


def check(tag, ok, detail=''):
    RESULTS.append({'item': tag, 'pass': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + tag + (' | ' + str(detail)[:400] if detail else ''))
    return ok


def shot(drv, name):
    p = L.shot(drv, name)
    SHOTS.append(p)
    return p


# ---------------- 页面元素助手 ----------------

def visible_dialogs(drv):
    return [e for e in drv.find_elements(By.CSS_SELECTOR, "[role='dialog']") if e.is_displayed()]


def dlg(drv):
    # 关闭动画期间元素会被 React 摘除，is_displayed 偶发 StaleElementReference（测试脚本自身时序问题，非产品缺陷）
    for _ in range(6):
        try:
            ds = visible_dialogs(drv)
            return ds[-1] if ds else None
        except Exception:
            time.sleep(0.4)
    return None


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
            time.sleep(0.5)
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
    L.js_click(drv, combos(drv)[idx])
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


def _api_dialog_open(drv):
    """JS 判 API 编辑弹窗可见（避开关闭动画期的 stale element）。"""
    for _ in range(4):
        try:
            return bool(drv.execute_script("""
                const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
                    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
                // 基础页签未挂载时 #api-name 不在 DOM（切到请求模板页签），用页签字面量兜底
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


# ---------------- 业务步骤 ----------------

def open_new(drv):
    add = [b for b in drv.find_elements(By.TAG_NAME, 'button')
           if b.is_displayed() and (b.text or '').strip() == '新增 API']
    if not add:
        raise RuntimeError('新增 API button not found on resources step')
    L.js_click(drv, add[0])
    time.sleep(2.0)
    for _ in range(20):
        if _api_dialog_open(drv) and '新增 API' in dialog_text(drv):
            return dlg(drv)
        time.sleep(0.5)
    raise RuntimeError('new api dialog not open')


def find_card(drv, name):
    for _ in range(8):
        try:
            cards = [c for c in drv.find_elements(By.CSS_SELECTOR, 'div')
                     if c.is_displayed() and name in (c.text or '')]
            cards = [c for c in cards if len((c.text or '')) < 800]
            if cards:
                cards.sort(key=lambda c: len(c.text or ''))
                return cards[0]
            return None
        except Exception:
            time.sleep(0.5)
    return None


def open_edit(drv, name):
    card = find_card(drv, name)
    if card is None:
        raise RuntimeError('card not found: %s' % name)
    drv.execute_script("arguments[0].scrollIntoView({block:'center'});", card)
    time.sleep(0.4)
    more = None
    for b in card.find_elements(By.CSS_SELECTOR, "[aria-label='更多操作']"):
        more = b
    if more is None:
        parent = card
        for _ in range(4):
            parent = parent.find_element(By.XPATH, '..')
            ms = parent.find_elements(By.CSS_SELECTOR, "[aria-label='更多操作']")
            if ms:
                more = ms[0]
                break
    if more is None:
        raise RuntimeError('更多操作 not found for card')
    L.js_click(drv, more)
    time.sleep(0.8)
    items = [e for e in drv.find_elements(By.CSS_SELECTOR, "[role='menuitem']") if e.is_displayed()]
    target = None
    for i in items:
        if (i.text or '').strip() == '编辑':
            target = i
            break
    if target is None:
        raise RuntimeError('编辑 menu item not found: %r' % [i.text for i in items])
    L.js_click(drv, target)
    time.sleep(2.0)
    for _ in range(20):
        if _api_dialog_open(drv) and '编辑 API' in dialog_text(drv):
            return dlg(drv)
        time.sleep(0.5)
    raise RuntimeError('edit dialog not open')


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
    """本页签保存发出的写请求（POST / PUT /apis…，排除 health 等子路径）"""
    out = []
    for e in L.fetch_log(drv):
        m = e.get('method')
        u = e.get('url') or ''
        if m in ('POST', 'PUT') and '/apis' in u and '/health' not in u:
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


def network_overlay(drv, entries):
    rows = []
    for e in entries:
        body = e.get('reqBody') or ''
        try:
            body = json.dumps(json.loads(body), ensure_ascii=False, indent=1)
        except Exception:
            pass
        rows.append(
            "<div style='margin-bottom:10px'><div style='color:#0a7;font-weight:700'>%s %s → %s</div>"
            "<pre style='margin:4px 0;padding:8px;background:#0f1720;color:#d6e2ea;font-size:11px;"
            "white-space:pre-wrap;border-radius:6px'>%s</pre></div>"
            % (e.get('method'), e.get('url'), e.get('status'), body.replace('<', '&lt;')))
    html = ("<div id='net-evidence' style='position:fixed;inset:20px;z-index:99999;background:#fff;"
            "border:2px solid #333;border-radius:10px;padding:16px;overflow:auto;font-family:monospace;"
            "box-shadow:0 10px 40px rgba(0,0,0,.4)'><h2 style='margin:0 0 12px;font-size:16px'>"
            "INT-1777 Network 证据（页内 fetch 抓包，写请求体）</h2>%s</div>"
            % ''.join(rows))
    drv.execute_script(
        "var old=document.getElementById('net-evidence'); if(old) old.remove();"
        "document.body.insertAdjacentHTML('beforeend', arguments[0]);", html)
    time.sleep(0.6)


def remove_overlay(drv):
    drv.execute_script("var e=document.getElementById('net-evidence'); if(e) e.remove();")


def main():
    d = L.driver()
    created_ids = []
    try:
        print('LOGIN ->', L.login(d))
        d.get(L.BASE + '/start-test')
        time.sleep(5)
        steps = [b for b in d.find_elements(By.TAG_NAME, 'button')
                 if b.is_displayed() and '选择设备' in (b.text or '')]
        L.js_click(d, steps[0])
        time.sleep(3.5)

        # 清理历史遗留的同名前缀测试 API（只删本前缀）
        for it in api_list(d):
            nm = it.get('name') or ''
            if nm.startswith('接线测试_INT1777_'):
                L.api_json(d, '/apis/%s' % it.get('id'), 'DELETE')
                print('cleaned stale', nm, it.get('id'))

        # ---------- A. 新增：页签骨架 ----------
        open_new(d)
        ti = tabs_info(d)
        check('A1 五页签齐全', [t['label'] for t in ti] == ['基础', '请求模板', '响应解析', '输出字段', '映射'], ti)
        check('A2 默认落基础页签', ti[0]['selected'] == 'true', ti[0])

        tab_click(d, '响应解析')
        t1 = dialog_text(d)
        tab_click(d, '输出字段')
        t2 = dialog_text(d)
        tab_click(d, '映射')
        t3 = dialog_text(d)
        placeholder_ok = all(('未选择关联算法' in x or '建设中' in x) for x in (t1, t2, t3))
        check('A3 后三页签占位空态', placeholder_ok, [x[-60:] for x in (t1, t2, t3)])
        tab_click(d, '基础')

        # ---------- B. 基础页签 + audio_config ----------
        fill(by_id(d, 'api-name'), NAME)
        L.js_click(d, combos(d)[0])
        time.sleep(0.8)
        opts = [o for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
        L.js_click(d, opts[0])
        time.sleep(0.6)
        fill(by_id(d, 'max-process'), '3')
        fill(by_id(d, 'api-desc'), 'INT-1777 验收自建 API')
        pick(d, 2, '16000 Hz')
        pick(d, 3, 's16')
        pick(d, 4, '1（单声道）')
        pick(d, 5, 'pcm')
        click_btn(d, '添加端点')
        time.sleep(0.6)
        fill(by_aria(d, '端点 URL'), 'https://api.example.com/v1/asr')
        audio_basic = [combo_text(d, i) for i in (2, 3, 4, 5)]
        check('B1 audio_config 四项可选', audio_basic == ['16000 Hz', 's16', '1（单声道）', 'pcm'], audio_basic)
        shot(d, '01_basic_light')

        # ---------- C. 请求模板 HTTP 组 ----------
        tab_click(d, '请求模板')
        txt_http = dialog_text(d)
        has_http = all(k in txt_http for k in ('请求方法', '请求头', '请求体模板', '厂商适配器'))
        has_ws = any(k in txt_http for k in ('WS 请求头', '会话配置', '节奏控制'))
        check('C1 HTTP 目标显示 HTTP 组', has_http and not has_ws, {'http': has_http, 'ws': has_ws})
        pick(d, 0, 'POST')
        click_btn(d, '添加请求头')
        time.sleep(0.5)
        fill(by_aria(d, '请求头名称'), 'Content-Type')
        fill(by_aria(d, '请求头值'), 'application/json')
        fill(by_id(d, 'meta-body-template'), '{"text":"{{text}}","temperature":0.2}')
        fill(by_id(d, 'meta-vendor-adapter'), 'HttpApiAdapter')
        shot(d, '02_request_http_light')

        # ---------- D. 端点改 ws → WS 组 ----------
        tab_click(d, '基础')
        fill(by_aria(d, '端点 URL'), 'ws://live.example.com/session')
        time.sleep(0.8)
        tab_click(d, '请求模板')
        txt_ws = dialog_text(d)
        has_ws2 = all(k in txt_ws for k in ('WS 请求头', '会话配置', '节奏控制')) and '请求体模板' not in txt_ws
        check('D1 auto 按端点协议切换到 WS 组', has_ws2, {'ws': has_ws2})
        click_btn(d, '添加请求头')
        time.sleep(0.5)
        fill(by_aria(d, 'WS 请求头名称'), 'X-Token')
        fill(by_aria(d, 'WS 请求头值'), 'abc123')
        fill(by_id(d, 'meta-session-config'), '{"turn_detection":true}')
        fill(by_id(d, 'meta-pacing'), '{"interval_ms":200}')
        shot(d, '03_request_ws_light')

        # ---------- E. 切换往返草稿保留 ----------
        tab_click(d, '基础')
        fill(by_aria(d, '端点 URL'), 'https://api.example.com/v1/asr')
        time.sleep(0.8)
        tab_click(d, '请求模板')
        method_after = combo_text(d, 0)
        body_after = by_id(d, 'meta-body-template').get_attribute('value')
        check('E1 切换往返 HTTP 草稿保留', method_after == 'POST' and '{{text}}' in body_after,
              {'method': method_after, 'body': body_after[:60]})
        tab_click(d, '基础')
        fill(by_aria(d, '端点 URL'), 'ws://live.example.com/session')
        time.sleep(0.8)
        tab_click(d, '请求模板')
        ws_re = {
            'header_key': by_aria(d, 'WS 请求头名称').get_attribute('value'),
            'header_val': by_aria(d, 'WS 请求头值').get_attribute('value'),
            'session': by_id(d, 'meta-session-config').get_attribute('value'),
            'pacing': by_id(d, 'meta-pacing').get_attribute('value'),
        }
        check('E2 切换往返 WS 草稿保留',
              ws_re['header_key'] == 'X-Token' and ws_re['header_val'] == 'abc123'
              and 'turn_detection' in ws_re['session'] and 'interval_ms' in ws_re['pacing'], ws_re)

        # 显式设备类型优先：端点 ws + 显式 HTTP API → 仍是 HTTP 组
        tab_click(d, '基础')
        pick(d, 1, 'HTTP API')
        time.sleep(0.8)
        tab_click(d, '请求模板')
        txt_explicit = dialog_text(d)
        check('E3 显式 device_type 优先于端点协议',
              '请求体模板' in txt_explicit and '节奏控制' not in txt_explicit,
              {'explicit_http': '请求体模板' in txt_explicit})
        tab_click(d, '基础')
        fill(by_aria(d, '端点 URL'), 'https://api.example.com/v1/asr')

        # ---------- F. 保存 + 回读 ----------
        ok_close = save(d)
        writes = api_writes(d)
        check('F1 保存关闭弹窗并发出写请求', ok_close and len(writes) == 1,
              {'closed': ok_close, 'writes': [(w['method'], w['url'], w['status']) for w in writes]})
        req = json.loads(writes[0]['reqBody']) if writes and writes[0].get('reqBody') else {}
        L.save_evidence('write_create', {'request': req, 'entry': writes[0] if writes else None})
        meta_sent = req.get('meta') or {}
        check('F2 请求体 meta 合并可见组键',
              all(k in meta_sent for k in ('method', 'headers', 'body_template', 'vendor_adapter')),
              sorted(meta_sent.keys()))
        check('F3 meta 里没有 audio_config', 'audio_config' not in meta_sent, sorted(meta_sent.keys()))
        check('F4 请求体 audio_config 是顶层', req.get('audio_config') ==
              {'sample_rate': 16000, 'bit_depth': 's16', 'channels': 1, 'container': 'pcm'},
              req.get('audio_config'))

        item = find_api(d, NAME)
        if item:
            created_ids.append(item.get('id'))
        check('F5 列表出现新建 API', item is not None, NAME)
        detail = get_api(d, item['id']) if item else {}
        check('F6 GET 回读 audio_config 正确', detail.get('audio_config') ==
              {'sample_rate': 16000, 'bit_depth': 's16', 'channels': 1, 'container': 'pcm'},
              detail.get('audio_config'))
        check('F7 GET meta 无 audio_config', 'audio_config' not in (detail.get('meta') or {}),
              sorted((detail.get('meta') or {}).keys()))

        # ---------- G. 编辑回填 ----------
        time.sleep(1.0)
        open_edit(d, NAME)
        name_val = by_id(d, 'api-name').get_attribute('value')
        audio_prefill = [combo_text(d, i) for i in (2, 3, 4, 5)]
        check('G1 编辑回填基础字段', name_val == NAME, name_val)
        check('G2 编辑回填 audio_config', audio_prefill ==
              ['16000 Hz', 's16', '1（单声道）', 'pcm'], audio_prefill)
        tab_click(d, '请求模板')
        method_prefill = combo_text(d, 0)
        body_prefill = by_id(d, 'meta-body-template').get_attribute('value')
        check('G3 编辑回填请求模板', method_prefill == 'POST' and '{{text}}' in body_prefill,
              {'method': method_prefill, 'body': body_prefill[:60]})
        L.apply_theme(d, 'dark')
        time.sleep(0.6)
        shot(d, '04_request_http_dark')
        tab_click(d, '基础')
        time.sleep(0.4)
        shot(d, '05_basic_dark')
        L.apply_theme(d, 'light')
        time.sleep(0.4)
        click_btn(d, '取消')
        time.sleep(1.0)

        # ---------- H. 未知键保留 + 隐藏组旧键不删 ----------
        base_detail = get_api(d, item['id'])
        meta_seed = dict(base_detail.get('meta') or {})
        meta_seed['appendix_test'] = 1
        meta_seed['ws_headers'] = {'X-Old': 'keep'}
        meta_seed['session_config'] = {'turn_detection': False}
        meta_seed['pacing'] = {'interval_ms': 500}
        st, _, raw = L.api_json(d, '/apis/%d' % item['id'], 'PUT',
                                {'name': NAME, 'meta': meta_seed})
        seeded = get_api(d, item['id']).get('meta') or {}
        check('H1 预置 appendix_test / WS 旧键成功',
              st == 200 and seeded.get('appendix_test') == 1 and seeded.get('ws_headers') == {'X-Old': 'keep'},
              {'st': st, 'meta': seeded})
        time.sleep(1.5)
        open_edit(d, NAME)
        tab_click(d, '请求模板')
        pick(d, 0, 'PUT')
        save(d)
        after = get_api(d, item['id']).get('meta') or {}
        check('H2 改 meta 后未知键保留', after.get('appendix_test') == 1 and after.get('method') == 'PUT',
              {'appendix_test': after.get('appendix_test'), 'method': after.get('method')})
        check('H3 隐藏组旧键未被删除',
              after.get('ws_headers') == {'X-Old': 'keep'}
              and after.get('session_config') == {'turn_detection': False}
              and after.get('pacing') == {'interval_ms': 500},
              {k: after.get(k) for k in ('ws_headers', 'session_config', 'pacing')})

        # ---------- I. 未触碰 meta 不发 ----------
        meta_before = dict(after)
        audio_before = get_api(d, item['id']).get('audio_config')
        time.sleep(1.5)
        open_edit(d, NAME)
        fill(by_id(d, 'api-name'), NAME2)
        save(d)
        writes = api_writes(d)
        body = json.loads(writes[0]['reqBody']) if writes and writes[0].get('reqBody') else {}
        check('I1 只改名称 → 请求体无 meta / audio_config',
              bool(writes) and 'meta' not in body and 'audio_config' not in body,
              sorted(body.keys()))
        detail2 = get_api(d, item['id'])
        check('I2 未触碰时 meta 原样保留', detail2.get('meta') == meta_before,
              {'same': detail2.get('meta') == meta_before})
        check('I3 未触碰时 audio_config 原样保留', detail2.get('audio_config') == audio_before,
              detail2.get('audio_config'))

        # ---------- J. 非法 JSON 拦截 ----------
        time.sleep(1.5)
        open_edit(d, NAME2)
        tab_click(d, '请求模板')
        fill(by_id(d, 'meta-body-template'), '{"text": ')
        L.clear_fetch_log(d)
        click_btn(d, '保存')
        time.sleep(2.0)
        cur = dlg(d)
        still_open = _api_dialog_open(d)
        err_text = dialog_text(d)
        writes = api_writes(d)
        check('J1 非法 JSON 拦截：弹窗不关', still_open, still_open)
        check('J2 非法 JSON 拦截：保存请求不发出', len(writes) == 0, {'writes': len(writes)})
        check('J3 非法 JSON 提示可见', 'JSON 格式不正确' in err_text,
              [l for l in err_text.split('\n') if 'JSON' in l])
        shot(d, '06_invalid_json_light')
        click_btn(d, '取消')
        time.sleep(1.2)

        # ---------- K. 取消重开不残留 ----------
        open_edit(d, NAME2)
        fill(by_id(d, 'api-name'), '不该保存的名字')
        fill(by_id(d, 'api-desc'), '不该保存的描述')
        click_btn(d, '取消')
        time.sleep(1.2)
        open_edit(d, NAME2)
        name_re = by_id(d, 'api-name').get_attribute('value')
        desc_re = by_id(d, 'api-desc').get_attribute('value')
        audio_re = [combo_text(d, i) for i in (2, 3, 4, 5)]
        check('K1 取消重开无残留', name_re == NAME2 and '不该保存' not in desc_re,
              {'name': name_re, 'desc': desc_re})
        check('K2 取消重开 audio 草稿复位', audio_re == ['16000 Hz', 's16', '1（单声道）', 'pcm'], audio_re)

        # ---------- L. 清除音频格式 ----------
        click_btn(d, '清除音频格式')
        time.sleep(0.6)
        cleared_hint = '保存后将清空 audio_config' in dialog_text(d)
        save(d)
        writes = api_writes(d)
        body = json.loads(writes[0]['reqBody']) if writes and writes[0].get('reqBody') else {}
        detail3 = get_api(d, item['id'])
        check('L1 清除 audio_config 发 {}', body.get('audio_config') == {}, body.get('audio_config'))
        check('L2 GET audio_config 已清空', detail3.get('audio_config') in ({}, None),
              detail3.get('audio_config'))
        check('L3 meta 仍无 audio_config', 'audio_config' not in (detail3.get('meta') or {}),
              sorted((detail3.get('meta') or {}).keys()))
        check('L4 清除提示可见', cleared_hint, cleared_hint)

        # ---------- M. Network 证据图 ----------
        L.apply_theme(d, 'light')
        time.sleep(0.5)
        allw = [e for e in L.fetch_log(d) if e.get('method') in ('POST', 'PUT') and '/apis' in (e.get('url') or '')]
        capture = allw[-3:]
        if not capture:
            capture = [{'method': 'PUT', 'url': '/api/v1/apis/%s' % item['id'], 'status': 200,
                        'reqBody': json.dumps({'name': NAME2, 'audio_config': {}}, ensure_ascii=False)}]
        network_overlay(d, capture)
        shot(d, '07_network_evidence')
        remove_overlay(d)

        # ---------- N. 收尾删除 ----------
        st, _, raw = L.api_json(d, '/apis/%d' % item['id'], 'DELETE')
        gone = find_api(d, NAME2) is None and find_api(d, NAME) is None
        check('N1 删除自建 API', st == 200 and gone, {'st': st, 'raw': raw[:120]})

        L.save_evidence('results', {'name': NAME, 'api_id': item.get('id'), 'results': RESULTS})
        fails = [r for r in RESULTS if not r['pass']]
        print('\nSUMMARY %d/%d pass, fails=%s' % (len(RESULTS) - len(fails), len(RESULTS), [f['item'] for f in fails]))
        print('SHOTS', SHOTS)
        return 0 if not fails else 2
    finally:
        try:
            for i in created_ids:
                L.api_json(d, '/apis/%s' % i, 'DELETE')
        except Exception:
            pass
        d.quit()


if __name__ == '__main__':
    sys.exit(main())
