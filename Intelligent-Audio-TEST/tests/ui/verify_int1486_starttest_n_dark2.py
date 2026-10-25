# -*- coding: utf-8 -*-
"""INT-1486 复测 N（深色 api-health 补测）：深色筛选关闭态已过（见 rewalk_n_dark_report.json），
上一轮深色 api-health 失败是后端重启后 API 列表长时间空载（卡片骨架），不是产品缺陷。本脚本只补这一窗。
"""
import json, os, time, traceback
import urllib.request, re

import verify_int1486_starttest_f as F
import verify_int1486_starttest_n as N

ART = F.ART
REPORT = os.path.join(ART, 'rewalk_n_dark_health_report.json')
PREFIX = '接线测试_INT1486_'


def pick_or_create_api(token):
    _, listed = F.api_req('GET', '/api/v1/apis?per_page=1000', token, timeout=180)
    items = (listed.get('data', listed) or {}).get('items', []) if isinstance(listed, dict) else []
    mine = [x for x in items if (x.get('name') or '').startswith(PREFIX)]
    if mine:
        return mine[0]['id'], mine[0]['name'], 'reused'
    suffix = str(int(time.time()))[-6:]
    name = PREFIX + 'NDARK2_' + suffix
    st, created = F.api_req('POST', '/api/v1/apis', token, {
        'name': name, 'description': 'INT-1486 复测 N 深色', 'algorithm_type': 'voice_llm',
        'default_max_process': 5,
        'endpoints': [{'endpoint': 'https://int1486-not-exist-' + suffix + '.invalid.example/api/v1/health-probe',
                       'name': None, 'max_process': 1, 'max_timeout': 30, 'max_audio_duration': 60,
                       'status': 'online', 'priority': 1, 'description': None}]}, timeout=180)
    aid = (created.get('data') or {}).get('id') if isinstance(created, dict) else None
    return aid, name, 'created(%s)' % st


def main():
    token = open(F.TOKEN_FILE).read().strip()
    try:
        st, h = F.api_req('GET', '/health', token, timeout=60)
    except Exception as e:
        st, h = 'ERR', {'error': str(e)}
    N.report['env']['health_start'] = h
    N.chk('env /health database=intelligent_audio_test',
          isinstance(h, dict) and h.get('database') == 'intelligent_audio_test', h)
    with urllib.request.urlopen('http://127.0.0.1:15173/', timeout=30) as resp:
        html = resp.read().decode('utf-8', 'replace')
    lib = re.findall(r'lib-react[^"\']*', html)
    N.report['env']['frontend_lib'] = lib
    N.chk('env 15173 是 React 构建（lib-react）', bool(lib), lib)

    api_id, api_name, how = pick_or_create_api(token)
    N.chk('前置 临时 API 就绪', api_id is not None, {'id': api_id, 'name': api_name, 'how': how})
    if api_id:
        N.report['apis'] = [{'id': api_id, 'name': api_name}]

    d = None
    try:
        d = F.make_driver(token)
        d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': "try{localStorage.setItem('iatp:theme:v1:mode','dark')}catch(e){}"})
        N.wait_step2(d)
        N.chk('N3 深色主题生效（同源 load 后）',
              d.execute_script("return document.documentElement.classList.contains('dark')") is True,
              d.execute_script("return document.documentElement.className"))
        # 等 API 卡片真正出数（后端慢时可能是骨架占位）
        hb = None
        end = time.time() + 300
        tries = 0
        while time.time() < end and hb is None:
            any_card = [e for e in d.find_elements('css selector', '[aria-label^="连接测试 "]') if e.is_displayed()]
            mine = [e for e in d.find_elements('css selector', f'[aria-label="连接测试 {api_name}"]') if e.is_displayed()]
            if mine:
                hb = mine[0]
                break
            tries += 1
            if tries % 4 == 0:
                print('RELOAD step2 (cards=%d)' % len(any_card))
                N.wait_step2(d)
            else:
                time.sleep(5)
        N.chk('N3 深色 API 卡片渲染（连接测试入口）', hb is not None, {'elapsed_tries': tries})

        if hb is not None:
            mark = F.log_mark(d)
            F.js_click(d, hb)
            try:
                F.WebDriverWait(d, 30).until(lambda x: bool(F.dialogs(x)))
                F.WebDriverWait(d, 180).until(lambda x: '重新测试' in F.dialog_text(x))
            except Exception:
                pass
            time.sleep(2)
            m = N.js(d, N.DIALOG_METRICS) or {}
            N.report['ui']['health_dark'] = m
            F.shot(d, 'N_api_health_fail_dark.png')
            if m.get('found'):
                F.dialogs(d)[-1].screenshot(os.path.join(ART, 'N_api_health_fail_dialog_dark.png'))
            N.chk('N3 深色弹窗打开', m.get('found') and '连接测试结果' in (m.get('text') or ''))
            N.chk('N3 深色无横向溢出（scrollWidth<=clientWidth）',
                  m.get('found') and m['scrollWidth'] <= m['clientWidth'] + 1,
                  {'cw': m.get('clientWidth'), 'sw': m.get('scrollWidth'), 'hasHScroll': m.get('hasHScroll')})
            N.chk('N3 深色无子元素越界', m.get('found') and not m.get('beyond'), (m.get('beyond') or [])[:3])
            dlg_err = ((m.get('errorBlock') or {}).get('text') or '').strip()
            N.chk('N3 深色错误全文可见（长 DNS 文本）+ 4 个 dd',
                  len(dlg_err) > 80 and 'HTTPSConnectionPool' in dlg_err and len(m.get('dds') or []) == 4,
                  {'len': len(dlg_err), 'dds': len(m.get('dds') or [])})
            eb = m.get('errorBlock') or {}
            N.chk('N3 深色错误块 pre-wrap + break-all',
                  eb.get('whiteSpace') == 'pre-wrap' and eb.get('wordBreak') == 'break-all', eb)
            sc = m.get('scoreRow') or {}
            N.chk('N3 深色健康分完整（100）', '100' in (sc.get('text') or ''), sc)
            ents = F.log_entries(d, mark, keys=('/health',))
            N.report['network_dark'] = [{'method': e['method'], 'status': e['status'], 'url': e['url']} for e in ents]
            N.chk('N3 深色 Network 抓到 POST /apis/{id}/health 200',
                  bool([e for e in ents if e['method'] == 'POST' and '/health' in e['url'] and e['status'] == 200]),
                  [(e['method'], e['status'], e['url']) for e in ents])
            F.close_dialog(d)
    except Exception:
        traceback.print_exc()
        try:
            F.shot(d, 'N_dark2_error.png')
        except Exception:
            pass
    finally:
        try:
            d.quit()
        except Exception:
            pass
        for it in N.report.get('apis', []):
            for attempt in range(3):
                try:
                    print('CLEAN api', it['id'], attempt, F.api_req('DELETE', f"/api/v1/apis/{it['id']}", token, timeout=180))
                    break
                except Exception as e:
                    print('CLEAN ERR', attempt, e)
                    time.sleep(5)
        try:
            _, apis_left = F.api_req('GET', '/api/v1/apis?per_page=1000', token, timeout=180)
            left = [x for x in ((apis_left.get('data', apis_left) or {}).get('items', []) if isinstance(apis_left, dict) else [])
                    if x.get('id') == api_id]
            N.chk('数据卫生 临时 API 已删（列表中不存在）', not left, {'left': left})
        except Exception as e:
            N.chk('数据卫生 临时 API 已删（列表中不存在）', False, 'err %s' % e)
        try:
            st, h2 = F.api_req('GET', '/health', token, timeout=30)
            N.report['env']['health_end'] = h2
            N.chk('env 交付前 /health database=intelligent_audio_test',
                  isinstance(h2, dict) and h2.get('database') == 'intelligent_audio_test', h2)
        except Exception as e:
            N.chk('env 交付前 /health 可达', False, e)
        with open(REPORT, 'w', encoding='utf-8') as f:
            json.dump(N.report, f, ensure_ascii=False, indent=2)
        failed = [c['name'] for c in N.report['checks'] if not c['ok']]
        print('SUMMARY_DARK2', json.dumps({'failed': failed, 'checks': len(N.report['checks'])}, ensure_ascii=False)[:2000])


if __name__ == '__main__':
    main()
