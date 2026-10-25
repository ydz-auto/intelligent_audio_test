# -*- coding: utf-8 -*-
"""INT-1486 探针 4：步骤二自建 API 卡片 DOM——列出所有含该 API 名称的 aria-label 元素及其可见性/尺寸。"""
import json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int1486_starttest_f as F  # noqa: E402

NAME = '接线测试_INT1486_PAPI_' + str(int(time.time()))[-6:]
out = {}


def main():
    token = open(F.TOKEN_FILE).read().strip()
    st, hc = F.api_req('POST', '/api/v1/apis', token, {
        'name': NAME, 'description': 'INT-1486 探针4', 'algorithm_type': 'voice_llm',
        'default_max_process': 5,
        'endpoints': [{'endpoint': 'https://example.test/int1486-p', 'name': None, 'max_process': 1,
                       'max_timeout': 30, 'max_audio_duration': 60, 'status': 'online', 'priority': 1,
                       'description': None}]})
    api_id = (hc.get('data') or {}).get('id') if isinstance(hc, dict) else None
    out['created'] = {'status': st, 'id': api_id, 'body': str(hc)[:200]}
    d = F.make_driver(token)
    try:
        F.wait_step1(d)
        # 进步骤二
        F.next_step(d)
        time.sleep(6)
        # 等到设备卡渲染
        for _ in range(30):
            if d.find_elements('css selector', f'[aria-label="选择设备 {F.DEVICE_NAME}"]'):
                break
            time.sleep(2)
        time.sleep(6)
        els = d.find_elements('css selector', '[aria-label]')
        rows = []
        for e in els:
            lab = e.get_attribute('aria-label') or ''
            if NAME in lab or ('API' in lab and ('选择' in lab or '连接' in lab or '全选' in lab)):
                try:
                    rows.append({'label': lab, 'tag': e.tag_name,
                                 'role': e.get_attribute('role'),
                                 'displayed': e.is_displayed(),
                                 'size': e.size,
                                 'cls': (e.get_attribute('class') or '')[:60]})
                except Exception as ex:
                    rows.append({'label': lab, 'err': str(ex)})
        out['elements'] = rows
        out['body_has_name'] = NAME in (d.execute_script('return document.body.innerText') or '')
        out['body_api_lines'] = [ln for ln in (d.execute_script('return document.body.innerText') or '').splitlines()
                                 if 'API' in ln or '接线测试' in ln][:20]
        F.shot(d, 'probe4_step2_api.png')
        # 滚到 API 区
        try:
            card = d.find_element('css selector', f'[aria-label="连接测试 {NAME}"]')
            d.execute_script('arguments[0].scrollIntoView({block:"center"})', card)
            time.sleep(2)
            F.shot(d, 'probe4_step2_api_scrolled.png')
        except Exception as ex:
            out['scroll_err'] = str(ex)
    finally:
        d.quit()
        if api_id:
            F.api_req('DELETE', f'/api/v1/apis/{api_id}', token)
        with open(os.path.join(F.ART, 'probe4.json'), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
