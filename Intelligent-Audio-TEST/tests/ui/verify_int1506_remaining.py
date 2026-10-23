# -*- coding: utf-8 -*-
"""INT-1506 验收补测：批量轮次（浅/深色）+ LLM 参数卡/未匹配设备名（响应桩）。

复用 verify_int1506_acceptance.py 的浏览器/断言辅助（已在该脚本完成 ①②④ 真实数据核对）。
本脚本对真实库零写入。
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import verify_int1506_acceptance as V  # noqa: E402


def main():
    devices = V.api_get('/playback-devices?per_page=200')['data']['items']
    items, audio_case, one_case, two_pair = V.pick_cases()
    m = re.search(r'JG\d+', one_case['name'])
    single_kw = m.group(0) if m else one_case['name'][:8]
    V.log('audio case', audio_case['name'][:36], 'pair', [c['name'][:24] for c in two_pair],
          'single', one_case['name'][:24])

    # ── 批量轮次：浅色 ────────────────────────────────────────────────
    d = V.driver()
    try:
        V.set_theme(d, 'light')
        V.enter_cases(d)
        V.check_batch_rounds(d, 'HJ0', [audio_case['name']] + [c['name'] for c in two_pair], [1, 2])
        V.shot(d, 'batch_dimensions_light.png')
        V.close_dialogs(d)
        V.enter_cases(d)
        V.check_batch_rounds(d, single_kw, [one_case['name']], [1])
        V.close_dialogs(d)
    finally:
        d.quit()

    # ── 批量轮次：深色 ────────────────────────────────────────────────
    d = V.driver()
    try:
        V.set_theme(d, 'dark')
        V.enter_cases(d)
        V.check('⑤ 深色主题生效', d.execute_script(
            "return document.documentElement.classList.contains('dark')"))
        V.check_batch_rounds(d, 'HJ0', [audio_case['name']] + [c['name'] for c in two_pair], [1, 2])
        V.shot(d, 'batch_dimensions_dark.png')
        V.close_dialogs(d)
    finally:
        d.quit()

    # ── 响应桩：LLM 参数卡 + 未匹配判定 ──────────────────────────────
    d = V.driver(stub_case=True)
    try:
        V.enter_cases(d)
        V.open_drawer(d, audio_case['name'])
        V.check_dimension_stub(d)
        V.close_drawer(d)
        V.enter_cases(d)
        V.open_drawer(d, audio_case['name'])
        V.check_noise_devices(d, devices, expect_unmatched=True)
        V.shot(d, 'noise_unmatched_stub.png')
        V.close_drawer(d)
    finally:
        d.quit()

    V.log('RESULT', json.dumps(V.RESULTS, ensure_ascii=True))
    ok = all(V.RESULTS.values())
    V.log('ALL', 'PASS' if ok else 'FAIL')
    with open(os.path.join(V.ART, 'result_remaining.json'), 'w', encoding='utf-8') as fh:
        json.dump({'results': V.RESULTS, 'logs': V.LOGS}, fh, ensure_ascii=False, indent=1)
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
