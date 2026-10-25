# -*- coding: utf-8 -*-
"""INT-1778 验收：React API 编辑弹窗「响应解析 / 输出字段 / 映射」三个页签（母卡 INT-1750 C5-2）。

环境：docker 后端 15000（intelligent_audio_test）+ 本 run 旁路前端容器 15288
（交付 dist + 15173 同款 nginx conf，反代 api_gateway）。

覆盖：
- 响应解析：C0 裁定口径提示 + 判定徽章、8 个键可填、非法 JSON 拦截、保存重开回填一致、
  未触碰 meta 不发 meta；
- 输出字段：只读列 + 算法类型级横幅 + 去算法配置跳转 + 空态；数据来自
  GET /algorithm/params?param_type=api（Network 证据）；
- 映射：只读行 + 横幅；数据来自 GET /algorithm/mappings?source_type=api（Network 证据）。

夹具（均「接线测试_」前缀，run 结束删除）：
- 测试 API（经弹窗「新增 API」建）；
- 一条 direction=output 的 API 参数 + 一条 source=api 的评估映射。
  ⚠ 参数/映射走的是算法配置页同一个写端点（POST /algorithm/params、POST /algorithm/mappings）：
  算法编辑 Sheet 当前会加载 voice_llm 的**已存在未发布草稿**（api_params/device_params 均为 0），
  在那里点「发布」会把已发布的 12 个参数整份覆盖成空——夹具改由接口建，避免破坏主库算法定义。
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import int1643_lib as L  # noqa: E402
import int1777_accept as A  # noqa: E402  复用弹窗/卡片/取数助手
from selenium.webdriver.common.by import By  # noqa: E402

L.BASE = 'http://127.0.0.1:15288'
L.ART = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1778')
os.makedirs(L.ART, exist_ok=True)

RUN_TAG = time.strftime('%m%d%H%M%S')
NAME = '接线测试_INT1778_' + RUN_TAG
PARAM_CODE = 'int1778_test_out'
DIMENSION_ID = 121
TARGET_PARAM = 'is_reject'

RESULTS = []
SHOTS = []


def check(tag, ok, detail=''):
    RESULTS.append({'item': tag, 'pass': bool(ok), 'detail': detail})
    print(('PASS ' if ok else 'FAIL ') + tag + (' | ' + str(detail)[:400] if detail else ''))
    return ok


def shot(d, name):
    p = L.shot(d, name)
    SHOTS.append(p)
    return p


# ---------------- 夹具（接口层） ----------------

def ensure_output_param(d):
    st, payload, raw = L.api_json(d, '/algorithm/params?algorithm_type=voice_llm&param_type=api')
    items = ((payload or {}).get('data') or {}).get('items') or []
    for it in items:
        if it.get('param_code') == PARAM_CODE:
            L.api_json(d, '/algorithm/params/%s' % it['id'], 'DELETE')
    body = {
        'param_type_source': 'api',
        'algorithm_type': 'voice_llm',
        'param_code': PARAM_CODE,
        'param_name': '接线测试_输出字段',
        'label': '接线测试_标签',
        'param_type': 'text',
        'direction': 'output',
        'ui_order': 990,
    }
    st, payload, raw = L.api_json(d, '/algorithm/params', 'POST', body)
    new_id = ((payload or {}).get('data') or {}).get('id')
    return st, new_id, raw


def ensure_mapping(d):
    st, payload, raw = L.api_json(d, '/algorithm/mappings?algorithm_type=voice_llm&source_type=api')
    for it in ((payload or {}).get('data') or {}).get('items') or []:
        if it.get('source_param') == PARAM_CODE:
            L.api_json(d, '/algorithm/mappings/%s' % it['id'], 'DELETE')
    body = {
        'algorithm_type': 'voice_llm',
        'source_type': 'api',
        'source_param': PARAM_CODE,
        'source_direction': 'output',
        'dimension_id': DIMENSION_ID,
        'target_param': TARGET_PARAM,
        'transform_type': 'uppercase',
    }
    st, payload, raw = L.api_json(d, '/algorithm/mappings', 'POST', body)
    new_id = ((payload or {}).get('data') or {}).get('id')
    return st, new_id, raw


def cleanup_fixtures(d, api_id):
    out = {}
    st, payload, _ = L.api_json(d, '/algorithm/mappings?algorithm_type=voice_llm&source_type=api')
    for it in ((payload or {}).get('data') or {}).get('items') or []:
        if it.get('source_param') == PARAM_CODE:
            out['mapping'] = L.api_json(d, '/algorithm/mappings/%s' % it['id'], 'DELETE')[0]
    st, payload, _ = L.api_json(d, '/algorithm/params?algorithm_type=voice_llm&param_type=api')
    for it in ((payload or {}).get('data') or {}).get('items') or []:
        if it.get('param_code') == PARAM_CODE:
            out['param'] = L.api_json(d, '/algorithm/params/%s' % it['id'], 'DELETE')[0]
    if api_id:
        out['api'] = L.api_json(d, '/apis/%d' % api_id, 'DELETE')[0]
    return out


# ---------------- 页面步骤 ----------------

def goto_start_test(d):
    d.get(L.BASE + '/start-test')
    time.sleep(5)
    steps = [b for b in d.find_elements(By.TAG_NAME, 'button')
             if b.is_displayed() and '选择设备' in (b.text or '')]
    if steps:
        L.js_click(d, steps[0])
        time.sleep(3.5)


def create_api(d):
    A.open_new(d)
    A.fill(A.by_id(d, 'api-name'), NAME)
    L.js_click(d, A.combos(d)[0])
    time.sleep(0.8)
    opts = [o for o in d.find_elements(By.CSS_SELECTOR, "[role='option']") if o.is_displayed()]
    L.js_click(d, opts[0])
    time.sleep(0.6)
    A.fill(A.by_id(d, 'max-process'), '3')
    A.fill(A.by_id(d, 'api-desc'), 'INT-1778 验收自建 API')
    A.click_btn(d, '添加端点')
    time.sleep(0.6)
    A.fill(A.by_aria(d, '端点 URL'), 'https://api.example.com/v1/asr')
    A.save(d)


def response_tab_controls(d):
    return {
        'result_parser': A.by_id(d, 'meta-result-parser'),
        'asr_mapping': A.by_id(d, 'meta-asr-mapping'),
        'trans_mapping': A.by_id(d, 'meta-trans-mapping'),
        'sentence_end_mapping': A.by_id(d, 'meta-sentence-end-mapping'),
        'session_end_mapping': A.by_id(d, 'meta-session-end-mapping'),
        'error_code_mapping': A.by_id(d, 'meta-error-code-mapping'),
        'error_msg_mapping': A.by_id(d, 'meta-error-msg-mapping'),
    }


def fill_response(d):
    c = response_tab_controls(d)
    A.fill(c['result_parser'], '{"asr_text_path":"data.text","trans_text_path":"data.translation"}')
    A.fill(c['asr_mapping'], 'data.asr.text')
    A.fill(c['trans_mapping'], 'data.translation')
    A.fill(c['sentence_end_mapping'], 'data.is_end')
    A.fill(c['session_end_mapping'], 'data.finished')
    A.fill(c['error_code_mapping'], 'data.code')
    A.fill(c['error_msg_mapping'], 'data.msg')
    # append_mode = 是
    L.js_click(d, A.by_aria(d, '流式结果拼接（append_mode）'))
    time.sleep(0.7)
    for o in d.find_elements(By.CSS_SELECTOR, "[role='option']"):
        if o.is_displayed() and '逐句结束追加拼接' in (o.text or ''):
            L.js_click(d, o)
            break
    time.sleep(0.5)


def read_response(d):
    out = {}
    for key, el in response_tab_controls(d).items():
        out[key] = el.get_attribute('value')
    out['append_mode'] = (A.by_aria(d, '流式结果拼接（append_mode）').text or '').strip()
    return out


def find_writes(d, method='PUT'):
    return [e for e in L.fetch_log(d)
            if e.get('method') == method and '/apis' in (e.get('url') or '')
            and '/health' not in (e.get('url') or '')]


def dialog_has(d, text):
    return text in A.dialog_text(d)


def main():
    d = L.driver()
    api_id = None
    try:
        print('LOGIN ->', L.login(d))

        # ---------- 0. 夹具 ----------
        goto_start_test(d)
        for it in A.api_list(d):
            if (it.get('name') or '').startswith('接线测试_INT1778_'):
                L.api_json(d, '/apis/%s' % it.get('id'), 'DELETE')
                print('cleaned stale', it.get('name'))
        st, param_id, raw = ensure_output_param(d)
        check('0.1 建输出字段夹具（direction=output）', st in (200, 201) and bool(param_id),
              {'st': st, 'id': param_id, 'raw': raw[:160]})
        st2, mapping_id, raw2 = ensure_mapping(d)
        check('0.2 建映射夹具（source_type=api）', st2 in (200, 201) and bool(mapping_id),
              {'st': st2, 'id': mapping_id, 'raw': raw2[:160]})

        create_api(d)
        goto_start_test(d)
        items = [it for it in A.api_list(d) if it.get('name') == NAME]
        check('0.3 自建测试 API 已落库', bool(items), items[:1])
        api_id = items[0]['id'] if items else None

        # ---------- A. 响应解析页签 ----------
        A.open_edit(d, NAME)
        A.tab_click(d, '响应解析')
        time.sleep(2.5)
        txt = A.dialog_text(d)
        check('A1 C0 裁定口径提示出现', 'C0 裁定口径' in txt, txt[:200])
        check('A2 判定徽章：voice_llm 已声明输出字段 → 不兜底',
              '已声明' in txt and '本页解析器不兜底' in txt, [l for l in txt.split('\n') if '兜底' in l][:3])
        check('A3 提示未写成系统当前行为', '系统当前' not in txt and '目前' not in txt, '')
        ctrls = response_tab_controls(d)
        check('A4 8 个键可填', len(ctrls) == 7 and
              bool(A.by_aria(d, '流式结果拼接（append_mode）')), sorted(ctrls.keys()))
        shot(d, '01_response_light')

        # 非法 JSON 拦截
        A.fill(ctrls['result_parser'], '{bad json')
        L.clear_fetch_log(d)
        A.click_btn(d, '保存')
        time.sleep(2.0)
        check('A5 非法 JSON 拦截保存（弹窗不关）', A._api_dialog_open(d), '')
        check('A6 非法 JSON 错误文案', 'JSON 格式不正确' in A.dialog_text(d), '')
        check('A7 非法 JSON 未发出写请求', not find_writes(d), L.fetch_log(d)[-3:])

        # 正常填写并保存
        fill_response(d)
        read_before = read_response(d)
        L.clear_fetch_log(d)
        A.save(d)
        writes = find_writes(d)
        body = json.loads(writes[0]['reqBody']) if writes and writes[0].get('reqBody') else {}
        meta = body.get('meta') or {}
        expect_meta = {
            'result_parser': {'asr_text_path': 'data.text', 'trans_text_path': 'data.translation'},
            'asr_mapping': 'data.asr.text',
            'trans_mapping': 'data.translation',
            'sentence_end_mapping': 'data.is_end',
            'session_end_mapping': 'data.finished',
            'error_code_mapping': 'data.code',
            'error_msg_mapping': 'data.msg',
            'append_mode': True,
        }
        check('A8 保存请求带 8 个 meta 键', all(k in meta for k in expect_meta), sorted(meta.keys()))
        check('A9 保存 meta 值正确', meta == expect_meta, meta)

        detail = A.get_api(d, api_id)
        check('A10 GET /apis 回写一致', (detail.get('meta') or {}) == expect_meta,
              sorted((detail.get('meta') or {}).keys()))

        # 重开回填
        A.open_edit(d, NAME)
        A.tab_click(d, '响应解析')
        time.sleep(1.5)
        read_after = read_response(d)
        json_ok = json.loads(read_after['result_parser']) == expect_meta['result_parser']
        rest_ok = all(read_after[k] == expect_meta[k] for k in (
            'asr_mapping', 'trans_mapping', 'sentence_end_mapping',
            'session_end_mapping', 'error_code_mapping', 'error_msg_mapping'))
        check('A11 重开回填一致（8 键）', json_ok and rest_ok and
              '是（逐句结束追加拼接）' in read_after['append_mode'],
              {'parsed': json_ok, 'rest': rest_ok, 'append': read_after['append_mode']})
        shot(d, '02_response_reopen_light')

        # 未触碰 meta 不发 meta
        A.tab_click(d, '基础')
        A.fill(A.by_id(d, 'api-desc'), 'INT-1778 只改描述')
        L.clear_fetch_log(d)
        A.save(d)
        writes = find_writes(d)
        body2 = json.loads(writes[0]['reqBody']) if writes and writes[0].get('reqBody') else {}
        check('A12 未触碰 meta → 请求体不带 meta', 'meta' not in body2, sorted(body2.keys()))
        detail2 = A.get_api(d, api_id)
        check('A13 未触碰 meta 保存后 8 键仍在', (detail2.get('meta') or {}) == expect_meta,
              sorted((detail2.get('meta') or {}).keys()))

        # ---------- B. 输出字段页签 ----------
        A.open_edit(d, NAME)
        L.clear_fetch_log(d)
        A.tab_click(d, '输出字段')
        time.sleep(2.5)
        txt = A.dialog_text(d)
        check('B1 算法类型级横幅', '算法类型级声明，本类型下所有 API 共用' in txt, '')
        check('B2 去算法配置入口存在', A.btn(d, '去算法配置', exact=False) is not None, '')
        rows = [r for r in d.find_elements(By.CSS_SELECTOR, "[role='dialog'] tbody tr")]
        row_text = '\n'.join((r.text or '') for r in rows)
        check('B3 新增的输出字段可见（C2 后 field_path 有值）',
              PARAM_CODE in row_text and '接线测试_标签' in row_text, row_text[:300])
        check('B4 既有输出字段可见（response_audio，field_path 未落库显示 —）',
              'response_audio' in row_text, row_text[:300])
        check('B5 只渲染 output 行（input_text 不在表内）', 'input_text' not in row_text, '')
        params_req = [e for e in L.fetch_log(d) if '/algorithm/params' in (e.get('url') or '')]
        check('B6 Network：GET /algorithm/params?…&param_type=api',
              any('param_type=api' in (e.get('url') or '') for e in params_req), params_req[-2:])
        shot(d, '03_output_light')

        # 跳转
        L.js_click(d, A.btn(d, '去算法配置', exact=False))
        time.sleep(3)
        check('B7 去算法配置跳转生效', '/AlgorithmConfig' in d.current_url, d.current_url)

        # ---------- C. 映射页签 ----------
        goto_start_test(d)
        A.open_edit(d, NAME)
        L.clear_fetch_log(d)
        A.tab_click(d, '映射')
        time.sleep(2.5)
        txt = A.dialog_text(d)
        check('C1 算法类型级横幅', '算法类型级声明，本类型下所有 API 共用' in txt, '')
        drows = '\n'.join((r.text or '') for r in d.find_elements(By.CSS_SELECTOR, "[role='dialog'] tbody tr"))
        check('C2 映射行可见（源参数/目标维度/目标参数/转换）',
              PARAM_CODE in drows and '拒识成功数量' in drows and TARGET_PARAM in drows and 'uppercase' in drows,
              drows[:400])
        map_req = [e for e in L.fetch_log(d) if '/algorithm/mappings' in (e.get('url') or '')]
        check('C3 Network：GET /algorithm/mappings?…&source_type=api',
              any('source_type=api' in (e.get('url') or '') for e in map_req), map_req[-2:])
        shot(d, '04_mapping_light')

        # ---------- D. 深色截图 ----------
        L.apply_theme(d, 'dark')
        time.sleep(0.8)
        shot(d, '05_mapping_dark')
        A.tab_click(d, '响应解析')
        time.sleep(1.0)
        shot(d, '06_response_dark')
        A.tab_click(d, '输出字段')
        time.sleep(1.0)
        shot(d, '07_output_dark')

        # ---------- E. Network 证据图 ----------
        L.apply_theme(d, 'light')
        time.sleep(0.5)
        entries = []
        for e in L.fetch_log(d):
            u = e.get('url') or ''
            if '/algorithm/params' in u or '/algorithm/mappings' in u:
                entries.append({'method': e.get('method'), 'url': u, 'status': e.get('status'),
                                'reqBody': None,
                                'resBody': (e.get('resBody') or '')[:600]})
        # 覆盖网络证据图里的标题
        rows_html = ''.join(
            "<div style='margin-bottom:10px'><div style='color:#0a7;font-weight:700'>%s %s → %s</div>"
            "<pre style='margin:4px 0;padding:8px;background:#0f1720;color:#d6e2ea;font-size:11px;"
            "white-space:pre-wrap;border-radius:6px'>%s</pre></div>"
            % (e['method'], e['url'].replace('&', '&amp;'), e['status'],
               (e['resBody'] or '').replace('<', '&lt;').replace('&', '&amp;'))
            for e in entries[-3:])
        d.execute_script(
            "var old=document.getElementById('net-evidence'); if(old) old.remove();"
            "document.body.insertAdjacentHTML('beforeend', arguments[0]);",
            "<div id='net-evidence' style='position:fixed;inset:20px;z-index:99999;background:#fff;"
            "border:2px solid #333;border-radius:10px;padding:16px;overflow:auto;font-family:monospace;"
            "box-shadow:0 10px 40px rgba(0,0,0,.4)'><h2 style='margin:0 0 12px;font-size:16px'>"
            "INT-1778 Network 证据（算法参数 / 映射读取）</h2>%s</div>" % rows_html)
        time.sleep(0.6)
        shot(d, '08_network_evidence')
        A.remove_overlay(d)

        # ---------- F. 收尾 ----------
        A.click_btn(d, '取消')
        time.sleep(1.2)
        clean = cleanup_fixtures(d, api_id)
        api_id = None
        check('F1 夹具已清理', all(v in (200, 204) for v in clean.values()) or not clean, clean)
        st, payload, _ = L.api_json(d, '/algorithm/mappings?algorithm_type=voice_llm&source_type=api')
        left = ((payload or {}).get('data') or {}).get('items') or []
        check('F2 映射夹具删除后为 0 行', len(left) == 0, left)

        fails = [r for r in RESULTS if not r['pass']]
        L.save_evidence('results', {'name': NAME, 'api_id': api_id, 'results': RESULTS})
        print('\nSUMMARY %d/%d pass, fails=%s' % (len(RESULTS) - len(fails), len(RESULTS),
                                                  [f['item'] for f in fails]))
        print('SHOTS', SHOTS)
        return 0 if not fails else 2
    finally:
        try:
            cleanup_fixtures(d, api_id)
        except Exception as e:
            print('cleanup skipped', e)
        d.quit()


if __name__ == '__main__':
    sys.exit(main())
