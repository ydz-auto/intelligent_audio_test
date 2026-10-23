# -*- coding: utf-8 -*-
"""INT-1479 R8 前置：造自建音频（接线测试_INT1479_ 前缀）并起静态服务供 URL 导入。

- 生成 3 个内容各异的 3s/16k/mono WAV：
    A.wav            → 转换用例（会被转成 MP3）
    B.wav            → 批量标注用例（库里记录名 B，但拖入文件改名为别的内容副本）
    B_samecontent.wav→ 与 B 内容完全一致、文件名不同（证明按内容 MD5 而非文件名匹配）
- python -m http.server 8791 供 audio_service 经 host.docker.internal 拉取
"""
import json
import math
import os
import struct
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _int1479_api as A
import requests

PREFIX = '接线测试_INT1479_'
ASSET = r'D:\00_user_data\.cache\int1479_r8\assets'
URL_HOST = 'http://host.docker.internal:8791'


def make_wav(path, freq, seconds=3, gain=0.25):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        frames = bytearray()
        for i in range(16000 * seconds):
            v = int(gain * 32767 * math.sin(2 * math.pi * freq * i / 16000))
            frames += struct.pack('<h', v)
        w.writeframes(bytes(frames))


def create(name, local):
    url = '%s/%s' % (URL_HOST, os.path.basename(local))
    r = requests.post(A.API + '/audios/url-import', headers=A.H(),
                      json={'url': url, 'audio_type': 'dry'}, timeout=180)
    print('url-import', r.status_code, (r.text or '')[:300], flush=True)
    d = (r.json() or {}).get('data') or {}
    aid = d.get('id')
    assert aid, 'url-import 未返回 id'
    r2 = requests.put(A.API + '/audios/%s/metadata' % aid, headers=A.H(),
                      json={'name': name}, timeout=120)
    print('rename', r2.status_code, (r2.text or '')[:160], flush=True)
    assert r2.status_code == 200
    r3 = requests.get(A.API + '/audios/%s' % aid, headers=A.H(), timeout=120)
    info = (r3.json() or {}).get('data') or {}
    print('readback', json.dumps({k: info.get(k) for k in
                                  ('id', 'name', 'format', 'size', 'sample_rate', 'channels', 'bitrate')},
                                 ensure_ascii=False), flush=True)
    return aid, info


if __name__ == '__main__':
    a = os.path.join(ASSET, 'sig1479_conv.wav')
    b = os.path.join(ASSET, 'sig1479_ann.wav')
    make_wav(a, 440)
    make_wav(b, 880)
    # 同内容、不同文件名的副本（批量标注拖入用）
    bcopy = os.path.join(ASSET, '接线测试_INT1479_标注源_改名副本.wav')
    if not os.path.isfile(bcopy):
        with open(b, 'rb') as f:
            data = f.read()
        with open(bcopy, 'wb') as f:
            f.write(data)
    print('files', [os.path.basename(x) for x in (a, b, bcopy)], flush=True)
    id_a, info_a = create(PREFIX + '转换_A.wav', a)
    id_b, info_b = create(PREFIX + '标注_B.wav', b)
    out = {'id_a': id_a, 'id_b': id_b, 'info_a': info_a, 'info_b': info_b,
           'src_a': a, 'src_b': b, 'src_bcopy': bcopy}
    dst = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'artifacts', 'int1479_audio')
    os.makedirs(dst, exist_ok=True)
    with open(os.path.join(dst, 'r8_setup.json'), 'w', encoding='utf-8') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print('OK', id_a, id_b)
