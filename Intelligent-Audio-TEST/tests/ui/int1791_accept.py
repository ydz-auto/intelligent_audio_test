# -*- coding: utf-8 -*-
"""INT-1791（A3）验收：请求模板页签内的 gRPC / SSE 协议区块。

环境（环境铁律）：docker 真实栈。后端 api_gateway :15000（库 intelligent_audio_test）；
前端用本卡交付 dist 起旁路 nginx 容器（默认 :15293，`REACT_BASE` 可覆盖）。

覆盖（卡面 §五 走查表）：
  #1 列表 → 编辑，选协议：请求模板区块随协议切换（逐协议断言控件集合；SSE 断言没有 body_template）
  #2 填完当前协议组 → 切到别的协议 → 切回：已填值仍在
  #4 取消 / 关闭后重开：草稿清空
  #5 非法配置提交：gRPC 必填缺失 / SSE retry 越界 → 前端拦截，弹窗不关、不写请求
  #6 存量 HTTP / WS 编辑：控件集合零变化
  #7 协议下拉：四协议均放行（与后端六组合同表）
  #3 保存 → 重开回填：**WAIT-DEPLOY**（:15000 仍是 B1 之前的栈，无 protocol / streaming 两列），
      脚本内显式 skip 并打印原因，禁止静默跳过。
  上传控件：POST /apis/proto（INT-1952）未部署 → 断言 404 如实报错、object_key 不回填。

自建数据只用「接线测试_」前缀，run 结束前删除；真实 API 只读。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from selenium.webdriver.common.by import By  # noqa: E402
from selenium.webdriver.common.keys import Keys  # noqa: E402

import int1643_lib as L  # noqa: E402

L.BASE = os.environ.get('REACT_BASE', 'http://127.0.0.1:15293')
API_ROOT = os.environ.get('API_ROOT', 'http://127.0.0.1:15000')
L.ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1791')
os.makedirs(L.ART, exist_ok=True)

RUN_TAG = time.strftime('%m%d%H%M%S')
NAME = '接线测试_INT1791_' + RUN_TAG
PROTO_LABEL = {'http': 'HTTP', 'websocket': 'WebSocket', 'grpc': 'gRPC', 'sse': 'SSE'}

RESULTS = []
SHOTS = []
SKIPS = []
NET = []


def check(tag, ok, detail=''):
    RESULTS.append({'item': tag, 'pass': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + tag + (' | ' + str(detail)[:400] if detail else ''))
    return ok


def skip(tag, reason):
    SKIPS.append({'item': tag, 'reason': reason})
    print('SKIP ' + tag + ' | ' + reason)


def shot(drv, name):
    p = L.shot(drv, name)
    SHOTS.append(p)
    return p


# ---------------- 弹窗与控件助手 ----------------

def dlg(drv):
    for _ in range(6):
        try:
            ds = [e for e in drv.find_elements(By.CSS_SELECTOR, "[role='dialog']") if e.is_displayed()]
            return ds[-1] if ds else None
        except Exception:
            time.sleep(0.4)
    return None


def dialog_open(drv):
    return drv.execute_script("""
        const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
        return Array.from(document.querySelectorAll("[role='dialog']")).filter(vis)
            .some(d => !!d.querySelector('#api-name') || (d.innerText || '').includes('请求模板'));
    """)


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
            time.sleep(0.7)
            return t
    raise RuntimeError('tab not found: %s' % label)


def pick_protocol(drv, protocol):
    """基础页签里按 aria-label='协议' 选协议（base-ui Select）。"""
    tab_click(drv, '基础')
    el = dlg(drv).find_element(By.CSS_SELECTOR, "[aria-label='协议']")
    drv.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    L.js_click(drv, el)
    time.sleep(0.7)
    want = PROTO_LABEL[protocol]
    opts = [o for o in drv.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
    target = None
    for o in opts:
        if (o.text or '').strip() == want:
            target = o
            break
    if target is None:
        for o in opts:
            if want in (o.text or ''):
                target = o
                break
    if target is None:
        raise RuntimeError('protocol option %r not in %r' % (want, [o.text for o in opts]))
    L.js_click(drv, target)
    time.sleep(0.8)


def visible_controls(drv):
    """当前可见 tabpanel 内的控件盘点（按 id / aria-label 精确判定）。"""
    return drv.execute_script("""
        const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
            return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
        const panels = Array.from(document.querySelectorAll("[role='tabpanel']")).filter(vis);
        const p = panels[panels.length - 1];
        if (!p) return { panel: false };
        const has = sel => !!p.querySelector(sel);
        const txt = p.innerText || '';
        return {
          panel: true,
          body_template: has('#meta-body-template'),
          proto_key: has("[aria-label='proto_object_key']"),
          proto_sha: has("[aria-label='proto_sha256']"),
          grpc_service: has("[aria-label='service']"),
          grpc_method: has("[aria-label='method']"),
          grpc_method_kind: has("[aria-label='method_kind']"),
          grpc_upload_btn: Array.from(p.querySelectorAll('button'))
              .some(b => (b.innerText || '').includes('上传 .proto')),
          sse_method: has("[aria-label='SSE 请求方法']"),
          sse_event_field: has('#sse-event-name-field'),
          sse_reconnect: has("[aria-label='SSE 重连开关']"),
          sse_retry: has('#sse-retry'),
          sse_idle: has('#sse-idle'),
          sse_duration: has('#sse-duration'),
          ws_headers_hint: txt.includes('WS 请求头') || txt.includes('未配置 WS 请求头'),
          http_headers: txt.includes('请求头'),
          session_config: has('#meta-session-config'),
          sse_note: txt.includes('句子结束 / 会话结束标记在「响应解析」页签'),
          text: txt.slice(0, 400),
        };
    """)


def body_template_value(drv):
    return drv.execute_script(
        "const el=document.querySelector('#meta-body-template'); return el ? el.value : null;")


def set_react_value(drv, selector, value):
    """React 受控输入：走原生 setter + input 事件（send_keys 在数字输入上会触发隐式提交）。"""
    return drv.execute_script("""
        const el = document.querySelector(arguments[0]);
        if (!el) return false;
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
        setter.call(el, arguments[1]);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        return el.value;
    """, selector, value)


def set_textarea_value(drv, selector, value):
    return drv.execute_script("""
        const el = document.querySelector(arguments[0]);
        if (!el) return false;
        const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value').set;
        setter.call(el, arguments[1]);
        el.dispatchEvent(new Event('input', { bubbles: true }));
        return el.value;
    """, selector, value)


# ---------------- 业务步骤 ----------------

def goto_apis_panel(drv):
    drv.get(L.BASE + '/start-test')
    time.sleep(5)
    steps = [b for b in drv.find_elements(By.TAG_NAME, 'button')
             if b.is_displayed() and '选择设备' in (b.text or '')]
    if not steps:
        raise RuntimeError('step2 button not found')
    L.js_click(drv, steps[0])
    time.sleep(3.5)


def open_edit(drv, api_name):
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
    for _ in range(24):
        time.sleep(0.5)
        if dialog_open(drv):
            time.sleep(0.8)
            return
    raise RuntimeError('edit dialog not open')


def cancel(drv):
    if not dialog_open(drv):
        return True
    click_btn(drv, '取消')
    for _ in range(12):
        time.sleep(0.4)
        if not dialog_open(drv):
            return True
    return False


def api_puts(drv):
    out = []
    for e in L.fetch_log(drv):
        u = e.get('url') or ''
        if (e.get('method') in ('POST', 'PUT')) and '/apis' in u \
                and '/health' not in u and '/stop-test' not in u:
            out.append({'method': e.get('method'), 'url': u, 'status': e.get('status')})
    return out


def create_fixture(drv):
    body = {
        'name': NAME,
        'algorithm_type': 'voice_llm',
        'description': 'INT-1791 A3 协议区块验收夹具',
        'default_max_process': 2,
        'endpoints': [{
            'endpoint': 'https://api.example.com/v1/asr',
            'name': 'INT1791',
            'priority': 1,
            'max_process': 2,
            'max_timeout': 30,
            'max_audio_duration': 60,
            'status': 'online',
        }],
    }
    st, payload, raw = L.api_json(drv, '/apis', 'POST', body)
    data = (payload or {}).get('data') or payload or {}
    api_id = data.get('id')
    return st, api_id, raw[:200]


# ---------------- 主流程 ----------------

def main():
    import urllib.request
    try:
        with urllib.request.urlopen(API_ROOT + '/health', timeout=10) as r:
            health = json.loads(r.read().decode('utf-8'))
        db = health.get('database') or (health.get('data') or {}).get('database')
        print('HEALTH database=%s' % db)
        if db != 'intelligent_audio_test':
            raise RuntimeError('非真实库栈（database=%s），本 run 结论作废' % db)
    except Exception as exc:  # noqa: BLE001
        print('ABORT 后端健康检查失败: %s' % exc)
        return 3

    d = L.driver()
    api_id = None
    real_names = []
    try:
        L.login(d)
        st, items_payload, raw = L.api_json(d, '/apis?page=1&page_size=200')
        items = ((items_payload or {}).get('data') or {}).get('items') or []
        real_names = [i.get('name') for i in items]
        has_protocol = bool(items) and ('protocol' in (items[0] or {}))
        check('A1 GET /apis 可用', st == 200 and bool(items), {'status': st, 'n': len(items)})
        if has_protocol:
            check('A2 协议 / 流式性两列已部署', True, 'protocol/streaming 在列表项里')
        else:
            skip('A2 协议 / 流式性两列已部署',
                 'WAIT-DEPLOY：列表项仍是 device_type + meta 形态（B1 未部署，INT-1917 backlog）→ '
                 '保存 / 回填类断言本轮一律 WAIT-DEPLOY，只给渲染与交互证据')

        st, api_id, raw = create_fixture(d)
        check('A3 建夹具 API（接线测试_ 前缀）', st in (200, 201) and api_id, {'status': st, 'id': api_id, 'raw': raw})

        goto_apis_panel(d)
        open_edit(d, NAME)
        check('B1 编辑弹窗打开', dialog_open(d))

        # ---------- #7 协议下拉四值均可选 ----------
        tab_click(d, '基础')
        el = dlg(d).find_element(By.CSS_SELECTOR, "[aria-label='协议']")
        L.js_click(d, el)
        time.sleep(0.7)
        opts = [{'text': (o.text or '').strip(), 'disabled': o.get_attribute('aria-disabled')}
                for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
        L.js_click(d, el)
        time.sleep(0.4)
        check('B2 协议下拉 4 项均可选（与后端六组合同表）',
              len(opts) == 4 and all(o['disabled'] != 'true' for o in opts), opts)

        # ---------- #1 逐协议区块显隐 ----------
        expect = {
            'http': dict(body_template=True, proto_key=False, sse_method=False),
            'websocket': dict(body_template=False, proto_key=False, sse_method=False),
            'grpc': dict(body_template=False, proto_key=True, grpc_service=True,
                         grpc_method=True, grpc_method_kind=True, grpc_upload_btn=True),
            'sse': dict(body_template=False, proto_key=False, sse_method=True,
                        sse_event_field=True, sse_reconnect=True, sse_retry=True,
                        sse_idle=True, sse_duration=True, sse_note=True),
        }
        for proto in ['http', 'websocket', 'grpc', 'sse']:
            pick_protocol(d, proto)
            tab_click(d, '请求模板')
            info = visible_controls(d)
            ok = info.get('panel') and all(info.get(k) == v for k, v in expect[proto].items())
            check('#1 %s 协议区块控件集合' % proto, ok, info)
            if proto == 'sse':
                check('#1 SSE 不显示 body_template（A2 执行侧从不读）',
                      info.get('body_template') is False, info)
                check('#1 SSE 不显示会话配置 / 节奏控制',
                      info.get('session_config') is False, info)
            if proto in ('grpc', 'sse'):
                check('#1 %s 无 HTTP 请求体模板控件' % proto,
                      info.get('body_template') is False, info)
            L.apply_theme(d, 'light')
            time.sleep(0.4)
            shot(d, 'C_%s_request_light' % proto)
            L.apply_theme(d, 'dark')
            time.sleep(0.4)
            shot(d, 'C_%s_request_dark' % proto)
            L.apply_theme(d, 'light')
            time.sleep(0.3)

        # ---------- #2 切协议不丢值 ----------
        pick_protocol(d, 'http')
        tab_click(d, '请求模板')
        set_textarea_value(d, '#meta-body-template', '{"text":"{{text}}"}')
        time.sleep(0.4)
        pick_protocol(d, 'grpc')
        tab_click(d, '请求模板')
        pick_protocol(d, 'http')
        tab_click(d, '请求模板')
        time.sleep(0.3)
        back = body_template_value(d)
        check('#2 切到 gRPC 再切回 HTTP：body_template 值仍在',
              back == '{"text":"{{text}}"}', back)

        # ---------- #5 gRPC 必填缺失拦截保存 ----------
        pick_protocol(d, 'grpc')
        tab_click(d, '请求模板')
        L.clear_fetch_log(d)
        click_btn(d, '保存')
        time.sleep(1.6)
        text = (dlg(d).text or '') if dialog_open(d) else ''
        puts = api_puts(d)
        check('#5 gRPC 必填缺失：弹窗不关 + 控件上报错',
              dialog_open(d) and '缺少 proto 文件引用' in text
              and '请填写或选择 service' in text and '请填写或选择 method' in text,
              {'err': '缺少 proto 文件引用' in text, 'text': text[:200]})
        check('#5 gRPC 拦截后未发出写请求', not puts, puts)
        # 把报错滚到可视区：截图要能看见「定位到控件」的提示
        d.execute_script(
            "const p = Array.from(document.querySelectorAll('p'))"
            ".find(x => (x.innerText||'').includes('缺少 proto 文件引用'));"
            "if (p) p.scrollIntoView({block:'center'});")
        time.sleep(0.5)
        shot(d, 'D_grpc_validation_light')

        # ---------- 上传接口未上线：404 如实报错、不回填 object_key ----------
        L.clear_fetch_log(d)
        proto_path = os.path.join(L.ART, 'int1791_demo.proto')
        with open(proto_path, 'w', encoding='utf-8') as f:
            f.write('syntax = "proto3";\npackage demo;\nmessage Req { string text = 1; }\n'
                    'service Echo { rpc Say (Req) returns (Req); }\n')
        file_input = dlg(d).find_element(By.CSS_SELECTOR, "input[type='file']")
        file_input.send_keys(proto_path)
        for _ in range(20):
            time.sleep(0.5)
            if d.find_elements(By.XPATH, "//p[contains(text(),'上传失败')]"):
                break
        upload_call = [e for e in L.fetch_log(d) if '/apis/proto' in (e.get('url') or '')]
        key_val = d.execute_script(
            "const el=document.querySelector(\"[aria-label='proto_object_key']\"); return el ? el.value : null;")
        check('#2b 上传接口未上线：POST /apis/proto 实际返回错误且如实展示',
              bool(upload_call) and upload_call[-1].get('status') in (404, 405),
              upload_call)
        check('#2b 未回填假 object_key', key_val == '', key_val)
        shot(d, 'E_proto_upload_not_live_light')

        # ---------- #5 SSE retry 越界拦截 ----------
        pick_protocol(d, 'sse')
        tab_click(d, '请求模板')
        set_react_value(d, '#sse-retry', '60001')
        time.sleep(0.4)
        L.clear_fetch_log(d)
        click_btn(d, '保存')
        time.sleep(1.6)
        text = (dlg(d).text or '') if dialog_open(d) else ''
        puts = api_puts(d)
        check('#5 SSE retry_ms 越界：弹窗不关 + 字段报错',
              dialog_open(d) and '重连退避上限（retry_ms）必须在 0-60000 之间' in text,
              text[:200])
        check('#5 SSE 拦截后未发出写请求', not puts, puts)
        d.execute_script(
            "const p = Array.from(document.querySelectorAll('p'))"
            ".find(x => (x.innerText||'').includes('必须在 0-60000 之间'));"
            "if (p) p.scrollIntoView({block:'center'});")
        time.sleep(0.5)
        shot(d, 'F_sse_validation_light')

        # ---------- #4 取消后重开不残留 ----------
        check('#4 取消关闭弹窗', cancel(d))
        open_edit(d, NAME)
        tab_click(d, '请求模板')
        time.sleep(0.5)
        info = visible_controls(d)
        check('#4 重开后回到协议缺省（无 body_template 残留值 / 无上次错误）',
              info.get('panel') and '重连退避上限' not in (info.get('text') or ''),
              (info.get('text') or '')[:160])
        cancel(d)

        # ---------- #3 保存 → 重开回填 ----------
        if has_protocol:
            check('#3 保存 / 回填（部署后补测）', False, 'unexpected: 已部署却未执行')
        else:
            skip('#3 保存 → 重开回填（grpc / sse / http / ws）',
                 'WAIT-DEPLOY：:15000 的 GET /apis 列表项无 protocol / streaming（B1 未部署，INT-1917 backlog），'
                 '写侧会拒新键；本轮只给渲染与交互证据，不记保存证据')
        skip('#3 sse 列保存回填',
             'WAIT-DEPLOY：同上（sse 与其它协议同口径，非 sse 特有限制）')

        # ---------- #6 存量 HTTP / WS 编辑回归 ----------
        real_name = next((n for n in real_names if n and not n.startswith('接线测试_')), None)
        if real_name:
            goto_apis_panel(d)
            open_edit(d, real_name)
            tab_click(d, '请求模板')
            info = visible_controls(d)
            check('#6 存量 API 编辑：请求模板仍是 HTTP 组，无 gRPC / SSE 控件',
                  info.get('panel') and info.get('proto_key') is False
                  and info.get('sse_method') is False,
                  info)
            shot(d, 'G_legacy_http_request_light')
            cancel(d)
        else:
            skip('#6 存量 API 回归', '列表里没有非「接线测试_」前缀的 API')

        # ---------- Network 证据 ----------
        L.save_evidence('results', {'name': NAME, 'api_id': api_id, 'results': RESULTS,
                                    'skips': SKIPS, 'shots': SHOTS, 'fetch_log': L.fetch_log(d)})
        check('Z 截图数量 ≥ 8（四协议 × 浅/深）', len([s for s in SHOTS if s.endswith('.png')]) >= 8,
              len(SHOTS))
    finally:
        try:
            if api_id:
                L.api_json(d, '/apis/%s' % api_id, 'DELETE')
                print('CLEANUP deleted api %s' % api_id)
        except Exception as exc:  # noqa: BLE001
            print('CLEANUP failed: %s' % exc)
        try:
            d.quit()
        except Exception:
            pass

    fails = [r for r in RESULTS if not r['pass']]
    print('\nSUMMARY %d/%d pass, skips=%d, fails=%s'
          % (len(RESULTS) - len(fails), len(RESULTS), len(SKIPS),
             [f['item'] for f in fails]))
    print('SHOTS', SHOTS)
    return 0 if not fails else 2


if __name__ == '__main__':
    sys.exit(main())
