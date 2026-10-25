# -*- coding: utf-8 -*-
"""INT-1486 打回复测 N：两处修复（INT-1632 / INT-1633）在 15173 上的真实验收。

N1. api-health 窗失败态：长 DNS 错误全文可见、弹窗无横向溢出（clientWidth vs scrollWidth、
    子元素右边界不越界）、健康分 /「重新测试」/ 4 个键值行都在弹窗内；浅/深 + Network。
N2. 步骤二 5 个筛选 Select 关闭态：默认 + 选值后都显示中文 label（不再回退 value 'all'），
    并抽查筛选功能仍生效；浅/深。
环境：docker 15173（React）+ 15000（真实库）。
"""
import json, os, time, traceback

import verify_int1486_starttest_f as F

ART = F.ART
SUFFIX = str(int(time.time()))[-6:]
API_NAME = '接线测试_INT1486_NAPI_' + SUFFIX
REPORT = os.path.join(ART, 'rewalk_n_report.json')
report = {'checks': [], 'env': {}, 'filter_states': [], 'ui': {}, 'network': []}


def chk(name, ok, detail=''):
    report['checks'].append({'name': name, 'ok': bool(ok), 'detail': str(detail)[:1200]})
    print(('[PASS] ' if ok else '[FAIL] ') + name + (' | ' + str(detail)[:500] if detail else ''))
    return ok


def js(d, script, *args):
    return d.execute_script(script, *args)


def wait_step2(d, timeout=120):
    F.wait_step1(d)
    F.next_step(d)


def find_health_btn(d, name, timeout=90):
    end = time.time() + timeout
    while time.time() < end:
        els = [e for e in d.find_elements('css selector', f'[aria-label="连接测试 {name}"]') if e.is_displayed()]
        if els:
            return els[0]
        time.sleep(2)
    return None


def open_health(d, name):
    hb = find_health_btn(d, name)
    if hb is None:
        return None
    mark = F.log_mark(d)
    F.js_click(d, hb)
    try:
        F.WebDriverWait(d, 30).until(lambda x: bool(F.dialogs(x)))
        F.WebDriverWait(d, 150).until(lambda x: '重新测试' in F.dialog_text(x))
    except Exception:
        pass
    time.sleep(2)
    return mark


DIALOG_METRICS = r"""
const dlg = [...document.querySelectorAll('[role="dialog"]')].filter(function(e){
  const r = e.getBoundingClientRect();
  return r.width > 0 && r.height > 0 && getComputedStyle(e).display !== 'none';
}).pop();
if (!dlg) return {found: false};
const dr = dlg.getBoundingClientRect();
const cs = getComputedStyle(dlg);
const out = {
  found: true,
  text: dlg.innerText,
  clientWidth: dlg.clientWidth, scrollWidth: dlg.scrollWidth,
  clientHeight: dlg.clientHeight, scrollHeight: dlg.scrollHeight,
  rect: {left: dr.left, right: dr.right, top: dr.top, bottom: dr.bottom, width: dr.width},
  overflowX: cs.overflowX,
  hasHScroll: (dlg.scrollWidth - dlg.clientWidth) > 1,
  nodes: [], beyond: []
};
const nodes = dlg.querySelectorAll('*');
const want = ['健康分', '重新测试', '端点状态', 'HTTP 状态码', '响应时间', '错误信息'];
nodes.forEach(function(n){
  const t = (n.textContent || '').trim();
  const r = n.getBoundingClientRect();
  if (r.width === 0 && r.height === 0) return;
  const rec = {tag: n.tagName, cls: (n.className && String(n.className).slice(0,120)) || '',
               right: r.right, left: r.left, width: r.width,
               sw: n.scrollWidth, cw: n.clientWidth};
  // 元素自身横向溢出
  if (n.scrollWidth - n.clientWidth > 1) out.overflowing = out.overflowing || [];
  if (n.scrollWidth - n.clientWidth > 1) out.overflowing.push(rec);
  if (r.right > dr.right + 1 || r.left < dr.left - 1) out.beyond.push(rec);
  want.forEach(function(k){
    if (t === k) out.nodes.push({label: k, tag: n.tagName, left: r.left, right: r.right, top: r.top});
  });
});
// 错误文本块（含 pre-wrap 的元素）
const err = [...dlg.querySelectorAll('div')].filter(function(n){
  const s = getComputedStyle(n);
  return s.whiteSpace === 'pre-wrap' || s.wordBreak === 'break-all';
}).pop();
if (err) {
  const s = getComputedStyle(err), r = err.getBoundingClientRect();
  out.errorBlock = {text: err.innerText, whiteSpace: s.whiteSpace, wordBreak: s.wordBreak,
                    overflowWrap: s.overflowWrap, left: r.left, right: r.right,
                    sw: err.scrollWidth, cw: err.clientWidth};
}
const score = [...dlg.querySelectorAll('span')].filter(function(n){return (n.textContent||'').trim() === '健康分'})[0];
if (score && score.parentElement) {
  const r = score.parentElement.getBoundingClientRect();
  out.scoreRow = {text: score.parentElement.innerText.replace(/\s+/g,' ').trim(), left: r.left, right: r.right};
}
const dds = [...dlg.querySelectorAll('dd')].map(function(n){
  const r = n.getBoundingClientRect();
  return {text: (n.textContent||'').slice(0,160), left: r.left, right: r.right, sw: n.scrollWidth, cw: n.clientWidth};
});
out.dds = dds;
return out;
"""

FILTERS = [
    ('状态', 'w-28', '全部状态', [('online', '在线'), ('offline', '离线')]),
    ('实验室', 'w-32', '全部实验室', [('lab-a', '旗舰实验室'), ('lab-b', '车载实验室')]),
    ('系统类型', 'w-32', '全部系统', [('android', 'Android'), ('api', 'API 网关')]),
    ('厂商', 'w-32', '全部厂商', [('内部 ASR 组', '内部 ASR 组'), ('TTS 组', 'TTS 组')]),
    ('协议', 'w-32', '全部协议', [('http', 'HTTP'), ('websocket', 'WebSocket')]),
]


def filter_triggers(d):
    els = [e for e in d.find_elements('css selector', 'button[role="combobox"]') if e.is_displayed()]
    out = []
    for e in els:
        cls = e.get_attribute('class') or ''
        if 'w-28' in cls or 'w-32' in cls:
            out.append(e)
    return out


def options_now(d):
    return [e for e in d.find_elements('css selector', '[role="option"]') if e.is_displayed()]


def pick_option(d, label):
    for _ in range(20):
        opts = [e for e in options_now(d) if (e.text or '').strip() == label]
        if opts:
            F.js_click(d, opts[0])
            time.sleep(1.0)
            return True
        time.sleep(0.3)
    return False


def walk_filters(d, theme):
    trigs = filter_triggers(d)
    chk(f'{theme} 步骤二筛选 Select 数量=5', len(trigs) == 5, len(trigs))
    result = []
    for idx, (fname, _w, default_label, pick_list) in enumerate(FILTERS):
        if idx >= len(trigs):
            result.append({'filter': fname, 'error': 'trigger missing'})
            continue
        trg = trigs[idx]
        # 展开前记录选项条数
        F.js_click(d, trg)
        time.sleep(1.0)
        opts = [(e.text or '').strip() for e in options_now(d)]
        closed_default = (trg.text or '').strip()
        pick_val, pick_label = pick_list[0]
        ok_pick = pick_option(d, pick_label)
        time.sleep(1.0)
        # 选值后触发器的文本需要重新取（DOM 可能重渲染）
        trg2 = filter_triggers(d)[idx]
        after_text = (trg2.text or '').strip()
        # 复位到 all
        F.js_click(d, trg2)
        time.sleep(0.8)
        back_ok = pick_option(d, default_label)
        time.sleep(0.8)
        trg3 = filter_triggers(d)[idx]
        back_text = (trg3.text or '').strip()
        result.append({'filter': fname, 'options': opts, 'default_closed': closed_default,
                       'picked_value': pick_val, 'picked_label': pick_label, 'ok_pick': ok_pick,
                       'closed_after_pick': after_text, 'back_to_default_text': back_text,
                       'options_count': len(opts)})
        print('FILTER', fname, json.dumps(result[-1], ensure_ascii=False))
        chk(f'{theme} {fname} 关闭态默认=「{default_label}」', closed_default == default_label, repr(closed_default))
        chk(f'{theme} {fname} 选「{pick_label}」后关闭态显示中文 label', after_text == pick_label,
            f'value={pick_val!r} text={after_text!r}')
        chk(f'{theme} {fname} 复位后关闭态=「{default_label}」', back_text == default_label, repr(back_text))
    report['filter_states'].append({'theme': theme, 'filters': result})
    return result


def main():
    token = open(F.TOKEN_FILE).read().strip()

    # ---------- 环境核对 1 ----------
    try:
        st, h = F.api_req('GET', '/health', token, timeout=60)
    except Exception as e:
        st, h = 'ERR', {'error': str(e)}
    report['env']['health_start'] = h
    chk('env /health database=intelligent_audio_test',
        isinstance(h, dict) and h.get('database') == 'intelligent_audio_test', h)
    import urllib.request
    try:
        with urllib.request.urlopen('http://127.0.0.1:15173/', timeout=30) as resp:
            html = resp.read().decode('utf-8', 'replace')
        import re
        lib = re.findall(r'lib-react[^"\']*', html)
        report['env']['frontend_lib'] = lib
        chk('env 15173 是 React 构建（lib-react）', bool(lib), lib)
    except Exception as e:
        chk('env 15173 可达', False, e)

    # ---------- 建不可达端点 API ----------
    try:
        st, created = F.api_req('POST', '/api/v1/apis', token, {
            'name': API_NAME, 'description': 'INT-1486 复测 N', 'algorithm_type': 'voice_llm',
            'default_max_process': 5,
            'endpoints': [{'endpoint': 'https://int1486-not-exist-' + SUFFIX + '.invalid.example/api/v1/health-probe',
                           'name': None, 'max_process': 1, 'max_timeout': 30, 'max_audio_duration': 60,
                           'status': 'online', 'priority': 1, 'description': None}]})
    except Exception as e:
        st, created = 'ERR', {'error': str(e)}
    api_id = (created.get('data') or {}).get('id') if isinstance(created, dict) else None
    if api_id is None:
        # 已知怪癖：POST /apis 偶发 400 但已落库；按名称回查
        st_l, listed = F.api_req('GET', '/api/v1/apis?per_page=1000', token)
        items = (listed.get('data', listed) or {}).get('items', []) if isinstance(listed, dict) else []
        hit = [x for x in items if x.get('name') == API_NAME]
        api_id = hit[0]['id'] if hit else None
        report['env']['api_create_quirk'] = {'status': st, 'resolved_by': 'list', 'id': api_id}
    chk('前置 临时 API 创建（不可达端点）', api_id is not None, {'status': st, 'id': api_id})
    if api_id:
        report['apis'] = [{'id': api_id, 'name': API_NAME}]
    expected_error = ''
    if api_id:
        try:
            st, direct = F.api_req('POST', f'/api/v1/apis/{api_id}/health', token, {})
            direct_data = (direct.get('data') or {}) if isinstance(direct, dict) else {}
            expected_error = direct_data.get('error') or ''
        except Exception as e:
            st, direct_data = 'ERR', {'err': str(e)}
        report['env']['direct_health'] = {'status': st, 'status_field': direct_data.get('status'),
                                          'health_score': direct_data.get('health_score'),
                                          'error_len': len(expected_error)}
        chk('前置 后端 health 失败态返回长错误文本', len(expected_error) > 80, len(expected_error))
    if api_id is None:
        print('ABORT: 临时 API 未创建，无法重走 api-health')
        chk('N1/N2/N3 重走前置未满足', False, 'api_id is None')
        with open(REPORT, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        return

    d = F.make_driver(token)
    try:
        # ================= 浅色：api-health 失败态 =================
        wait_step2(d)
        mark = open_health(d, API_NAME)
        chk('N1 健康检查入口可点（浅色）', mark is not None)
        m = js(d, DIALOG_METRICS) or {}
        report['ui']['health_light'] = m
        F.shot(d, 'N_api_health_fail_light.png')
        if m.get('found'):
            dlg_el = F.dialogs(d)[-1]
            dlg_el.screenshot(os.path.join(ART, 'N_api_health_fail_dialog_light.png'))
        chk('N1 弹窗打开（连接测试结果）', m.get('found') and '连接测试结果' in (m.get('text') or ''))
        chk('N1 状态徽章=离线', '离线' in (m.get('text') or ''), (m.get('text') or '')[:120])
        chk('N1 健康分/重新测试/4 个键值行标签齐全',
            all(lbl in (m.get('text') or '') for lbl in ['健康分', '重新测试', '端点状态', 'HTTP 状态码', '响应时间', '错误信息']))
        dlg_err = ((m.get('errorBlock') or {}).get('text') or '').strip()
        chk('N1 错误全文可见（DNS 解析失败原文，长文本未被截断）',
            len(dlg_err) > 80 and 'HTTPSConnectionPool' in dlg_err
            and ('NameResolutionError' in dlg_err or 'Failed to resolve' in dlg_err
                 or 'Name or service not known' in dlg_err),
            {'len': len(dlg_err), 'head': dlg_err[:80]})
        chk('N1 弹窗「错误信息」行与错误块文本一致',
            bool(dlg_err) and dlg_err[:60] in (m.get('text') or ''),
            {'head': dlg_err[:60]})
        chk('N1 无横向溢出（scrollWidth<=clientWidth）',
            m.get('clientWidth') and m['scrollWidth'] <= m['clientWidth'] + 1,
            {'clientWidth': m.get('clientWidth'), 'scrollWidth': m.get('scrollWidth'),
             'hasHScroll': m.get('hasHScroll')})
        chk('N1 无子元素越出弹窗左右边界', m.get('found') and not m.get('beyond'), m.get('beyond', [])[:5])
        eb = m.get('errorBlock') or {}
        chk('N1 错误块 pre-wrap + break-all', eb.get('whiteSpace') == 'pre-wrap' and eb.get('wordBreak') == 'break-all', eb)
        chk('N1 错误块自身无横向溢出', bool(eb) and eb.get('sw', 0) <= eb.get('cw', 0) + 1, {'sw': eb.get('sw'), 'cw': eb.get('cw')})
        chk('N1 健康分/重新测试/4 个 dd 都在弹窗内',
            len(m.get('nodes') or []) >= 6 and len(m.get('dds') or []) == 4,
            {'nodes': [n.get('label') for n in (m.get('nodes') or [])], 'dds': len(m.get('dds') or [])})
        # 按钮与得分行的右边界
        sc = m.get('scoreRow') or {}
        chk('N1 健康分文本完整（100 而非 1）', '100' in (sc.get('text') or ''), sc)
        ents = F.log_entries(d, mark, keys=('/health', '/apis/'))
        report['network'] = [{'method': e['method'], 'status': e['status'], 'url': e['url'],
                              'res': (e.get('resBody') or '')[:600]} for e in ents]
        health_reqs = [e for e in ents if e['method'] == 'POST' and '/health' in e['url']]
        chk('N1 Network 抓到 POST /apis/{id}/health 200',
            bool(health_reqs) and health_reqs[-1]['status'] == 200,
            [(e['method'], e['status'], e['url']) for e in ents])
        F.close_dialog(d)

        # ================= 浅色：5 个筛选关闭态 =================
        wait_step2(d)
        walk_filters(d, '浅色')
        # 功能抽查：按该 API 的真实 status 校验筛选仍然生效
        _, apis_now = F.api_req('GET', '/api/v1/apis?per_page=1000', token)
        me = [x for x in (((apis_now.get('data', apis_now) or {}).get('items', [])) if isinstance(apis_now, dict) else [])
              if x.get('id') == api_id]
        api_status = (me[0].get('status') if me else None)
        report['env']['api_status_after_fail'] = api_status

        def visible_card():
            return len([e for e in d.find_elements('css selector', f'[aria-label="连接测试 {API_NAME}"]') if e.is_displayed()])

        F.js_click(d, filter_triggers(d)[0]); time.sleep(0.8); pick_option(d, '在线'); time.sleep(1.2)
        n_online = visible_card()
        F.js_click(d, filter_triggers(d)[0]); time.sleep(0.8); pick_option(d, '离线'); time.sleep(1.2)
        n_offline = visible_card()
        F.js_click(d, filter_triggers(d)[0]); time.sleep(0.8); pick_option(d, '全部状态'); time.sleep(1.2)
        n_all = visible_card()
        expect = ({'在线': 0, '离线': 1} if api_status == 'offline'
                  else {'在线': 1, '离线': 0} if api_status == 'online'
                  else {'在线': 1, '离线': 1})
        chk('N2 状态筛选仍生效（按 API 真实 status 对照）',
            n_online == expect['在线'] and n_offline == expect['离线'] and n_all >= 1,
            {'api_status': api_status, 'online': n_online, 'offline': n_offline, 'all': n_all})
        F.shot(d, 'N_step2_filters_light.png')

        # ================= 深色：同源 reload 后重走 =================
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','dark')")
        wait_step2(d)
        chk('N3 深色主题生效',
            d.execute_script("return document.documentElement.classList.contains('dark')") is True,
            d.execute_script("return document.documentElement.className"))
        walk_filters(d, '深色')
        F.shot(d, 'N_step2_filters_dark.png')
        mark = open_health(d, API_NAME)
        m = js(d, DIALOG_METRICS) or {}
        report['ui']['health_dark'] = m
        F.shot(d, 'N_api_health_fail_dark.png')
        if m.get('found'):
            F.dialogs(d)[-1].screenshot(os.path.join(ART, 'N_api_health_fail_dialog_dark.png'))
        chk('N3 深色弹窗无横向溢出', m.get('found') and m['scrollWidth'] <= m['clientWidth'] + 1,
            {'cw': m.get('clientWidth'), 'sw': m.get('scrollWidth')})
        dlg_err_dark = ((m.get('errorBlock') or {}).get('text') or '').strip()
        chk('N3 深色错误全文 + 4 dd 齐全',
            len(dlg_err_dark) > 80 and 'HTTPSConnectionPool' in dlg_err_dark
            and len(m.get('dds') or []) == 4, {'len': len(dlg_err_dark), 'dds': len(m.get('dds') or [])})
        chk('N3 深色无子元素越界', not m.get('beyond'), (m.get('beyond') or [])[:3])
        F.close_dialog(d)
        d.execute_script("localStorage.setItem('iatp:theme:v1:mode','light')")

    except Exception:
        traceback.print_exc()
        try:
            F.shot(d, 'N_error.png')
        except Exception:
            pass
    finally:
        d.quit()
        # ---------- 清理 ----------
        for it in report.get('apis', []):
            try:
                print('CLEAN api', it['id'], F.api_req('DELETE', f"/api/v1/apis/{it['id']}", token))
            except Exception as e:
                print('CLEAN api ERR', it['id'], e)
        try:
            st2, apis_left = F.api_req('GET', '/api/v1/apis?per_page=1000', token)
            left = [x for x in ((apis_left.get('data', apis_left) or {}).get('items', []) if isinstance(apis_left, dict) else [])
                    if x.get('id') == api_id]
            chk('数据卫生 临时 API 已删（列表中不存在）', not left, {'left': left})
        except Exception as e:
            chk('数据卫生 临时 API 已删（列表中不存在）', False, 'list err: %s' % e)
        try:
            st, h2 = F.api_req('GET', '/health', token, timeout=20)
            report['env']['health_end'] = h2
            chk('env 交付前 /health database=intelligent_audio_test',
                isinstance(h2, dict) and h2.get('database') == 'intelligent_audio_test', h2)
        except Exception as e:
            chk('env 交付前 /health 可达', False, e)
        with open(REPORT, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        failed = [c['name'] for c in report['checks'] if not c['ok']]
        print('SUMMARY', json.dumps({'failed': failed, 'checks': len(report['checks'])}, ensure_ascii=False)[:2000])


if __name__ == '__main__':
    main()
