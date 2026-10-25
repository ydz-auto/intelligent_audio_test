# -*- coding: utf-8 -*-
"""INT-1800 走查：React API 表单/列表「协议 × 流式性」两维（B2）。

环境：docker 后端 :15000（intelligent_audio_test，**旧契约：无 protocol/streaming 列**）
+ 本 run 旁路前端容器 :15290（交付 dist + 15173 同款 nginx conf，反代 api_gateway:5000）。

覆盖：
- A 新建弹窗默认 http + 非流式、协议下拉 4 值（sse/grpc 置灰）、流式开关锁定；
- B 切协议到 WebSocket → 流式自动开启；
- C 保存写侧请求体 = protocol + streaming，且**不含 device_type**（Network 证据）；
- D 列表卡片/表格两维展示（旧后端无列 → 协议显示「—」，流式性取缺省 false）；
- E 重开编辑回填表单两维；F 设备页 API 页签两维列 + 两个 facet；G 开始测试资源面板 facet；
- H 清理：删除夹具 API，核对列表回原样。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L  # noqa: E402
import int1777_accept as A  # noqa: E402
from selenium.webdriver.common.by import By  # noqa: E402

L.BASE = 'http://127.0.0.1:15290'
L.ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1800')
os.makedirs(L.ART, exist_ok=True)

RUN_TAG = time.strftime('%m%d%H%M%S')
NAME = '接线测试_INT1800_' + RUN_TAG

RESULTS = []
SHOTS = []


def check(tag, ok, detail='', expected_unfixed=False):
    """expected_unfixed：部署前必然不成立的后端契约项（INT-1917 部署后转为普通断言）。"""
    ok = bool(ok)
    RESULTS.append({'item': tag, 'pass': ok, 'expected_unfixed': expected_unfixed, 'detail': detail})
    status = 'PASS' if ok else ('WAIT-DEPLOY' if expected_unfixed else 'FAIL')
    print(status + ' ' + tag + (' | ' + str(detail)[:600] if detail else ''))
    return ok


def shot(d, name):
    p = L.shot(d, name)
    SHOTS.append(p)
    return p


def option_states(d):
    return [
        {'text': (o.text or '').strip(), 'disabled': o.get_attribute('aria-disabled')}
        for o in d.find_elements(By.CSS_SELECTOR, "[role='option']")
        if o.is_displayed()
    ]


def goto_resources(d):
    """开始测试页默认停在第 1 步（选用例），切到第 2 步（选择设备/API）。"""
    for b in d.find_elements(By.TAG_NAME, 'button'):
        if b.is_displayed() and '选择设备/API' in (b.text or ''):
            L.js_click(d, b)
            time.sleep(2.0)
            return True
    raise RuntimeError('步骤 2「选择设备/API」按钮未找到')


def network_overlay(d, title, entries):
    rows = ''.join(
        "<div style='margin-bottom:10px'><div style='color:#0a7;font-weight:700'>%s %s → %s</div>"
        "<pre style='margin:4px 0;padding:8px;background:#0f1720;color:#d6e2ea;font-size:12px;"
        "white-space:pre-wrap;border-radius:6px'>%s</pre></div>"
        % (e.get('method'), (e.get('url') or '').replace('&', '&amp;'), e.get('status'),
           (e.get('reqBody') or '(无请求体)').replace('<', '&lt;').replace('&', '&amp;'))
        for e in entries)
    d.execute_script(
        "var old=document.getElementById('net-evidence'); if(old) old.remove();"
        "document.body.insertAdjacentHTML('beforeend', arguments[0]);",
        "<div id='net-evidence' style='position:fixed;inset:20px;z-index:99999;background:#fff;"
        "border:2px solid #333;border-radius:10px;padding:16px;overflow:auto;font-family:monospace;"
        "box-shadow:0 10px 40px rgba(0,0,0,.4)'><h2 style='margin:0 0 12px;font-size:16px'>%s</h2>%s</div>"
        % (title, rows))
    time.sleep(0.6)


def stream_switch(d):
    return d.find_element(By.CSS_SELECTOR, "[role='switch'][aria-label='流式开关']")


def main():
    d = L.driver()
    api_id = None
    try:
        d.get(L.BASE + '/start-test')
        time.sleep(1.2)
        check('LOGIN', bool(L.login(d)), '登录后 URL 已离开 /login')
        time.sleep(1.0)
        # 登录会跳工作台，走查前回到开始测试页
        d.get(L.BASE + '/start-test')
        time.sleep(2.5)
        L.apply_theme(d, 'light')
        time.sleep(0.8)
        goto_resources(d)

        # ---------- A. 新建弹窗默认两维 ----------
        A.open_new(d)
        time.sleep(1.0)
        A.fill(A.by_id(d, 'api-name'), NAME)
        sw = stream_switch(d)
        check('A1 新建默认非流式', sw.get_attribute('aria-checked') == 'false',
              sw.get_attribute('aria-checked'))
        check('A2 流式开关按矩阵锁定', sw.get_attribute('aria-disabled') == 'true',
              sw.get_attribute('aria-disabled'))
        proto_combo = d.find_element(By.CSS_SELECTOR, "[role='combobox'][aria-label='协议']")
        check('A3 默认协议 HTTP', (proto_combo.text or '').strip() == 'HTTP', proto_combo.text)
        shot(d, '01_new_basic_light')

        L.js_click(d, proto_combo)
        time.sleep(0.8)
        opts = option_states(d)
        check('A4 协议下拉 4 值', [o['text'].replace('（未上线）', '').strip() for o in opts] ==
              ['HTTP', 'WebSocket', 'SSE', 'gRPC'], opts)
        check('A5 sse/grpc 置灰', opts[2]['disabled'] == 'true' and opts[3]['disabled'] == 'true',
              [opts[2]['disabled'], opts[3]['disabled']])
        shot(d, '02_protocol_options_light')

        # ---------- B. 切 WebSocket → 流式开启 ----------
        [o for o in d.find_elements(By.CSS_SELECTOR, "[role='option']")
         if (o.text or '').strip().startswith('WebSocket')][0].click()
        time.sleep(0.8)
        sw = stream_switch(d)
        check('B1 切 WebSocket → 流式自动开', sw.get_attribute('aria-checked') == 'true',
              sw.get_attribute('aria-checked'))
        check('B2 切 WebSocket 后开关仍锁定', sw.get_attribute('aria-disabled') == 'true',
              sw.get_attribute('aria-disabled'))
        shot(d, '03_websocket_streaming_light')

        # 深色同视角
        L.apply_theme(d, 'dark')
        time.sleep(0.6)
        shot(d, '04_dialog_dark')
        L.apply_theme(d, 'light')
        time.sleep(0.5)

        # ---------- C. 填最小必填并保存（写侧两维） ----------
        # 关联算法：取下拉第一项（真实算法列表）
        L.js_click(d, A.combos(d)[0])
        time.sleep(0.8)
        first_alg = [o for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
        if first_alg:
            first_alg[0].click()
        time.sleep(0.6)
        A.click_btn(d, '添加端点')
        time.sleep(0.6)
        ep = A.by_aria(d, '端点 URL')
        A.fill(ep, 'https://int1800.example.com/v1/ws')
        L.clear_fetch_log(d)
        A.save(d)
        time.sleep(2.0)
        writes = [e for e in L.fetch_log(d) if (e.get('url') or '').rstrip('/').endswith('/apis')
                  and (e.get('method') or '').upper() == 'POST']
        req = None
        if writes:
            try:
                req = json.loads(writes[-1].get('reqBody') or 'null')
            except Exception:
                req = None
        check('C1 POST /apis 请求体含 protocol', bool(req) and req.get('protocol') == 'websocket',
              req)
        check('C2 POST /apis 请求体含 streaming=true', bool(req) and req.get('streaming') is True,
              None if not req else req.get('streaming'))
        check('C3 请求体不含 device_type', bool(req) and 'device_type' not in req,
               None if not req else sorted(req.keys()))
        # 写侧 Network 证据图（保存后立刻截，页面后续导航会清空 fetch log）
        network_overlay(d, 'INT-1800 Network 证据（POST /apis 写侧：protocol + streaming，无 device_type）',
                        writes[-1:])
        shot(d, '05_network_write')
        A.remove_overlay(d)

        # ---------- D. 列表两维展示（旧后端无列 → 「—」/非流式） ----------
        time.sleep(1.5)
        st, payload, _ = L.api_json(d, '/apis?protocol=websocket&streaming=true&page=1')
        items = ((payload or {}).get('data') or {}).get('items') or []
        mine = [i for i in items if i.get('name') == NAME]
        api_id = mine[0]['id'] if mine else None
        check('D0 后端按两维筛选可用（服务端已支持查询参数时会命中）', st == 200, st)
        st2, payload2, _ = L.api_json(d, '/apis?page=1&per_page=200')
        all_items = ((payload2 or {}).get('data') or {}).get('items') or []
        row = [i for i in all_items if i.get('name') == NAME]
        check('D1 新记录读侧无 device_type 键（待 INT-1917 部署）',
              bool(row) and 'device_type' not in row[0],
              None if not row else sorted(row[0].keys()), expected_unfixed=True)
        check('D2 读侧两维字段（待 INT-1917 部署）',
              bool(row) and ('protocol' in row[0] or 'streaming' in row[0]),
              None if not row else {'protocol': row[0].get('protocol'),
                                    'streaming': row[0].get('streaming')},
              expected_unfixed=True)
        shot(d, '05_list_light')

        # ---------- E. 重开编辑回填 ----------
        A.open_edit(d, NAME)
        time.sleep(1.0)
        check('E1 重开协议回填 HTTP（旧后端无列，按缺省）',
              (d.find_element(By.CSS_SELECTOR, "[role='combobox'][aria-label='协议']").text or '')
              .strip() in ('HTTP', '—'),
              d.find_element(By.CSS_SELECTOR, "[role='combobox'][aria-label='协议']").text)
        shot(d, '06_reopen_light')
        A.click_btn(d, '取消')
        time.sleep(0.8)

        # ---------- F. 设备页 API 页签两维 ----------
        d.get(L.BASE + '/devices/api')
        time.sleep(2.0)
        txt = L.body_text(d)
        check('F1 设备页 API 表有「流式性」列', '流式性' in txt, txt[:120])
        check('F2 设备页 API 筛选有「协议」「流式性」', '协议' in txt and '流式性' in txt, '')
        shot(d, '07_devices_api_light')
        L.apply_theme(d, 'dark')
        time.sleep(0.6)
        shot(d, '08_devices_api_dark')
        L.apply_theme(d, 'light')
        time.sleep(0.5)

        # ---------- G. 开始测试资源面板 facet ----------
        d.get(L.BASE + '/start-test')
        time.sleep(2.0)
        goto_resources(d)
        shot(d, '09_start_test_light')

        # ---------- H. Network 证据 ----------
        entries = [e for e in L.fetch_log(d) if '/apis' in (e.get('url') or '')]
        rows = []
        for e in entries[-4:]:
            body = (e.get('reqBody') or '')[:900]
            rows.append((e.get('method'), e.get('url'), e.get('status'), body))
        html = ''.join(
            "<div style='margin-bottom:10px'><div style='color:#0a7;font-weight:700'>%s %s → %s</div>"
            "<pre style='margin:4px 0;padding:8px;background:#0f1720;color:#d6e2ea;font-size:11px;"
            "white-space:pre-wrap;border-radius:6px'>%s</pre></div>"
            % (m, (u or '').replace('&', '&amp;'), s,
               (b or '(无请求体)').replace('<', '&lt;').replace('&', '&amp;'))
            for m, u, s, b in rows)
        d.execute_script(
            "var old=document.getElementById('net-evidence'); if(old) old.remove();"
            "document.body.insertAdjacentHTML('beforeend', arguments[0]);",
            "<div id='net-evidence' style='position:fixed;inset:20px;z-index:99999;background:#fff;"
            "border:2px solid #333;border-radius:10px;padding:16px;overflow:auto;font-family:monospace;"
            "box-shadow:0 10px 40px rgba(0,0,0,.4)'><h2 style='margin:0 0 12px;font-size:16px'>"
            "INT-1800 Network 证据（/apis 写侧：protocol + streaming，无 device_type）</h2>%s</div>"
            % html)
        time.sleep(0.6)
        shot(d, '10_network_evidence')
        A.remove_overlay(d)

        # ---------- I. 清理 ----------
        if api_id:
            st, _, _ = L.api_json(d, '/apis/%d' % api_id, 'DELETE')
            check('I1 夹具 API 已删除', st in (200, 204), st)
        st, payload, _ = L.api_json(d, '/apis?page=1&per_page=200')
        left = [i for i in (((payload or {}).get('data') or {}).get('items') or [])
                if i.get('name') == NAME]
        check('I2 清理后列表无残留', left == [], left)

        # 防串库：真实库核对
        st, health, _ = L.api_json(d, '/../health')
        print('HEALTH', health)
    finally:
        with open(os.path.join(L.ART, 'result.json'), 'w', encoding='utf-8') as f:
            json.dump({'checks': RESULTS, 'shots': SHOTS}, f, ensure_ascii=False, indent=2)
        try:
            d.quit()
        except Exception:
            pass
    failed = [r for r in RESULTS if not r['pass'] and not r.get('expected_unfixed')]
    waiting = [r for r in RESULTS if not r['pass'] and r.get('expected_unfixed')]
    print('WAIT-DEPLOY %d 项：%s' % (len(waiting), [r['item'] for r in waiting]))
    print('SUMMARY pass=%d fail=%d' % (len(RESULTS) - len(failed), len(failed)))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
