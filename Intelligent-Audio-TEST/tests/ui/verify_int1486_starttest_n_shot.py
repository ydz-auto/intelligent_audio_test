# -*- coding: utf-8 -*-
"""INT-1486 复测 N：深色步骤二筛选截图补拍（带真实卡片 + 选值后的关闭态 label）。"""
import json, os, time, traceback

import verify_int1486_starttest_f as F
import verify_int1486_starttest_n as N

ART = F.ART
SUFFIX = str(int(time.time()))[-6:]
API_NAME = '接线测试_INT1486_NSHOT_' + SUFFIX
report = {'checks': [], 'env': {}}
N.report = report


def main():
    token = open(F.TOKEN_FILE).read().strip()
    st, h = F.api_req('GET', '/health', token, timeout=60)
    N.chk('env /health database=intelligent_audio_test',
          isinstance(h, dict) and h.get('database') == 'intelligent_audio_test', h)
    st, created = F.api_req('POST', '/api/v1/apis', token, {
        'name': API_NAME, 'description': 'INT-1486 深色截图', 'algorithm_type': 'voice_llm',
        'default_max_process': 5,
        'endpoints': [{'endpoint': 'https://int1486-shot-' + SUFFIX + '.invalid.example/api/v1/x',
                       'name': None, 'max_process': 1, 'max_timeout': 30, 'max_audio_duration': 60,
                       'status': 'online', 'priority': 1, 'description': None}]}, timeout=180)
    api_id = (created.get('data') or {}).get('id') if isinstance(created, dict) else None
    if api_id is None:
        _, listed = F.api_req('GET', '/api/v1/apis?per_page=1000', token, timeout=180)
        items = (listed.get('data', listed) or {}).get('items', []) if isinstance(listed, dict) else []
        hit = [x for x in items if x.get('name') == API_NAME]
        api_id = hit[0]['id'] if hit else None
    N.chk('前置 API 就绪', api_id is not None, {'id': api_id})
    d = None
    try:
        d = F.make_driver(token)
        d.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': "try{localStorage.setItem('iatp:theme:v1:mode','dark')}catch(e){}"})
        N.wait_step2(d)
        end = time.time() + 300
        while time.time() < end:
            if [e for e in d.find_elements('css selector', f'[aria-label="连接测试 {API_NAME}"]') if e.is_displayed()]:
                break
            time.sleep(5)
        N.chk('深色主题', d.execute_script("return document.documentElement.classList.contains('dark')") is True)
        F.js_click(d, N.filter_triggers(d)[0]); time.sleep(1)
        N.pick_option(d, '在线'); time.sleep(1.5)
        trig = N.filter_triggers(d)[0]
        N.chk('深色状态筛选关闭态显示「在线」', (trig.text or '').strip() == '在线', trig.text)
        F.shot(d, 'N_step2_filters_dark_selected.png')
        F.js_click(d, N.filter_triggers(d)[0]); time.sleep(1)
        N.pick_option(d, '全部状态'); time.sleep(1.5)
        N.chk('深色复位「全部状态」', (N.filter_triggers(d)[0].text or '').strip() == '全部状态')
        F.shot(d, 'N_step2_filters_dark.png')
    except Exception:
        traceback.print_exc()
    finally:
        try:
            d.quit()
        except Exception:
            pass
        for attempt in range(3):
            try:
                print('CLEAN', F.api_req('DELETE', f'/api/v1/apis/{api_id}', token, timeout=180))
                break
            except Exception as e:
                print('CLEAN ERR', e); time.sleep(5)
        try:
            _, left = F.api_req('GET', '/api/v1/apis?per_page=1000', token, timeout=180)
            items = (left.get('data', left) or {}).get('items', []) if isinstance(left, dict) else []
            N.chk('数据卫生 无本卡残留 API', not [x for x in items if (x.get('name') or '').startswith('接线测试_INT1486_')],
                  [x.get('name') for x in items])
        except Exception as e:
            N.chk('数据卫生 清理核对失败', False, e)
        with open(os.path.join(ART, 'rewalk_n_shot_report.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print('SUMMARY_SHOT', json.dumps({'failed': [c['name'] for c in report['checks'] if not c['ok']],
                                          'checks': len(report['checks'])}, ensure_ascii=False))


if __name__ == '__main__':
    main()
