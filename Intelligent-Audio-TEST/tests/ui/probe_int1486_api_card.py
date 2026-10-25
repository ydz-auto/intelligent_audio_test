# -*- coding: utf-8 -*-
"""INT-1486 探针 3：自建临时 API 在步骤一是否渲染出「选择 API」勾选框（只读观察 + 临时 API 清理）。"""
import json, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_int1486_starttest_f as F  # noqa: E402

NAME = '接线测试_INT1486_KAPI_' + str(int(time.time()))[-6:]
out = {}


def main():
    token = open(F.TOKEN_FILE).read().strip()
    st, hc = F.api_req('POST', '/api/v1/apis', token, {
        'name': NAME, 'description': 'INT-1486 探针临时', 'algorithm_type': 'voice_llm',
        'default_max_process': 5,
        'endpoints': [{'endpoint': 'https://example.test/int1486-k', 'name': None, 'max_process': 1,
                       'max_timeout': 30, 'max_audio_duration': 60, 'status': 'online', 'priority': 1,
                       'description': None}]})
    api_id = (hc.get('data') or {}).get('id') if isinstance(hc, dict) else None
    out['created'] = {'status': st, 'id': api_id}
    d = F.make_driver(token)
    try:
        d.get(F.BASE + '/start-test')
        F.wait_text(d, '按分组', 90)
        for t in (5, 10, 20, 35):
            time.sleep(t if t == 5 else t - (5 if t == 10 else 10 if t == 20 else 20))
            snap = {}
            snap['labels_sel'] = [e.get_attribute('aria-label') for e in
                                  d.find_elements('css selector', '[aria-label^="选择"]')
                                  if e.get_attribute('aria-label')]
            snap['labels_api'] = [e.get_attribute('aria-label') for e in
                                  d.find_elements('css selector', '[aria-label*="API"]')
                                  if e.get_attribute('aria-label')]
            snap['body_has_name'] = NAME in (d.execute_script('return document.body.innerText') or '')
            snap['body_has_test_prefix'] = '接线测试_INT1486_KAPI' in (d.execute_script('return document.body.innerText') or '')
            out[f't{t}'] = snap
        # 滚到底部，触发懒渲染后再查
        d.execute_script('window.scrollTo(0, document.body.scrollHeight)')
        time.sleep(3)
        out['after_scroll_labels'] = [e.get_attribute('aria-label') for e in
                                      d.find_elements('css selector', '[aria-label*="API"]')
                                      if e.get_attribute('aria-label')]
        out['after_scroll_body_has_name'] = NAME in (d.execute_script('return document.body.innerText') or '')
        # 打印包含 API 名称的卡片文本
        cards = d.find_elements('css selector', '[data-slot="card"]')
        out['card_texts'] = [c.text.replace('\n', ' | ')[:160] for c in cards][:20]
        F.shot(d, 'probe3_api_cards.png')
    finally:
        d.quit()
        if api_id:
            out['cleanup'] = F.api_req('DELETE', f'/api/v1/apis/{api_id}', token)
        with open(os.path.join(F.ART, 'probe3.json'), 'w', encoding='utf-8') as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == '__main__':
    main()
