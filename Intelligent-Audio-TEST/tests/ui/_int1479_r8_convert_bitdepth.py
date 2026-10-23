# -*- coding: utf-8 -*-
"""INT-1479 R8 · A2：位深度 24 bit 单独闭环（UX 审计遗留项）。

造自建音频（上传链路）→ UI 转 WAV / 44.1 kHz / 双声道 / 24 bit → 请求体 + GET 回读；
24 bit 20 Hz 带宽 = 44100*2*24 = 2,116,800 bps，回读 bitrate 与 size 佐证位深真实生效。
"""
import json
import os
import sys
import time

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _int1479_r4_lib as L  # noqa: E402
import _int1479_api as A  # noqa: E402
import _int1479_r8_convert as CV  # noqa: E402

SRC = r'D:\00_user_data\.cache\int1479_r8\assets\sig1479_conv.wav'
NAME = '接线测试_INT1479_位深.wav'


def upload():
    size = os.path.getsize(SRC)
    h = A.H()
    jh = {**h, 'Content-Type': 'application/json'}
    r = requests.post(A.API + '/audios/upload/init', headers=jh, json={}, timeout=60)
    task = (r.json().get('data') or {}).get('task_id')
    r = requests.post(A.API + '/audios/upload/register', headers=jh,
                      json={'task_id': task, 'files': [{'name': NAME, 'size': size,
                                                        'md5': '', 'relative_path': ''}]},
                      timeout=120)
    f = ((r.json().get('data') or {}).get('files') or [])[0]
    fid = f['file_id']
    with open(SRC, 'rb') as fh:
        data = fh.read()
    requests.post(A.API + '/audios/upload/chunk', headers=h,
                  data={'file_id': fid, 'chunk_index': '0', 'total_chunks': '1', 'task_id': task},
                  files={'chunk': ('chunk', data, 'application/octet-stream')}, timeout=180)
    body = {'file_id': fid, 'task_id': task, 'create_test_case': False, 'audio_type': 'dry',
            'algorithm_type': '', 'algorithm_params': [], 'algorithm_relations': [], 'tags': [],
            'inherit_tags': False, 'spl': 0, 'noise_audio_id': None, 'noise_spl': 0,
            'playback_device_id': None, 'description': '', 'asr_text': '', 'annotations': []}
    r = requests.post(A.API + '/audios/upload/merge', headers=jh, json=body, timeout=300)
    aid = (r.json().get('data') or {}).get('audio_id')
    print('UPLOAD', r.status_code, aid, flush=True)
    requests.put(A.API + '/audios/%s/metadata' % aid, headers=jh, json={'name': NAME}, timeout=120)
    return int(aid)


def main():
    out = {}
    aid = upload()
    c = L.connect()
    print('READY', CV.open_page(c, 'light'), flush=True)
    CV.search(c, '接线测试_INT1479_位深')
    time.sleep(3)
    print('ROWS', CV.rows(c), flush=True)
    print('MENU', CV.open_menu(c, NAME)); time.sleep(1.2)
    print('CONVERT', CV.menu(c, '转换格式')); time.sleep(2)
    for aria, label in (('目标格式', 'WAV'), ('目标采样率', '44.1 kHz'), ('声道数', '双声道'),
                        ('转换参数', '24 bit')):
        print('PICK', aria, label, CV.pick(c, aria, label), flush=True)
    out['dialog_text'] = CV.dialog_text(c).replace('\n', ' | ')[:700]
    out['shot'] = L.shot(c, 'r8-a4-convert-wav24-light')
    t0 = len(c.events)
    print('SUBMIT', CV.submit(c), flush=True)
    end = time.time() + 180
    while time.time() < end:
        time.sleep(2)
        c.pump()
        if not CV.dialog_text(c):
            break
    time.sleep(2)
    c.pump()
    reqs, resps = CV.net_since(c, t0)
    out['req'] = [r for r in reqs if r['u'].endswith('/convert')]
    out['resp'] = [r for r in resps if r['u'].endswith('/convert')]
    print('REQ', json.dumps(out['req'], ensure_ascii=False), flush=True)
    print('RESP', json.dumps(out['resp'], ensure_ascii=False), flush=True)
    st, info = CV.api_get(aid)
    out['readback'] = {k: info.get(k) for k in
                       ('id', 'name', 'format', 'size', 'sample_rate', 'channels', 'bitrate', 'duration')}
    out['expected_bitrate'] = 44100 * 2 * 24
    print('READBACK', json.dumps(out['readback'], ensure_ascii=False), flush=True)
    print('EXPECTED_BITRATE', out['expected_bitrate'], flush=True)
    out['shot_after'] = L.shot(c, 'r8-a5-convert-wav24-after-light')
    d = requests.delete('%s/audios/%s' % (A.API, aid), headers=A.H(), timeout=300)
    print('DELETE', aid, d.status_code, (d.text or '')[:120], flush=True)
    with open(os.path.join(L.OUT, 'r8_convert_bitdepth.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('DONE', flush=True)


if __name__ == '__main__':
    main()
