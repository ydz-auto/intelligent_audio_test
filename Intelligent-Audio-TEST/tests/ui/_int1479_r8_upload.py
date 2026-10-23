# -*- coding: utf-8 -*-
"""INT-1479 R8：用真实上传链路（init→register→chunk→merge）造带 md5 的自建音频。

URL 导入不落 md5（后端缺口），而 INT-1582 的按内容 MD5 匹配需要 md5 有值；
上传链路经 audio_service 落库，验证其是否写入 md5。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _int1479_api as A
import requests

SRC = r'D:\00_user_data\.cache\int1479_r8\assets\sig1479_ann.wav'


def main():
    name = '接线测试_INT1479_标注_上传.wav'
    size = os.path.getsize(SRC)
    h = A.H()
    r = requests.post(A.API + '/audios/upload/init', headers={**h, 'Content-Type': 'application/json'},
                      json={}, timeout=60)
    print('init', r.status_code, r.text[:200])
    task = (r.json().get('data') or {}).get('task_id')
    r = requests.post(A.API + '/audios/upload/register', headers={**h, 'Content-Type': 'application/json'},
                      json={'task_id': task,
                            'files': [{'name': name, 'size': size, 'md5': '', 'relative_path': ''}]},
                      timeout=120)
    print('register', r.status_code, r.text[:400])
    files = (r.json().get('data') or {}).get('files') or []
    if not files:
        print('NO FILES -> 环境缺口')
        return 2
    f = files[0]
    fid = f.get('file_id')
    chunk_size = int(f.get('chunk_size') or 5 * 1024 * 1024)
    total = int(f.get('total_chunks') or 1)
    with open(SRC, 'rb') as fh:
        data = fh.read()
    for i in range(total):
        part = data[i * chunk_size:(i + 1) * chunk_size]
        rr = requests.post(A.API + '/audios/upload/chunk', headers=h,
                           data={'file_id': fid, 'chunk_index': str(i), 'total_chunks': str(total),
                                 'task_id': task},
                           files={'chunk': ('chunk', part, 'application/octet-stream')}, timeout=180)
        print('chunk', i, rr.status_code, rr.text[:160])
    body = {
        'file_id': fid, 'task_id': task, 'create_test_case': False,
        'audio_type': 'dry', 'algorithm_type': '', 'algorithm_params': [],
        'algorithm_relations': [], 'tags': [], 'inherit_tags': False,
        'spl': 0, 'noise_audio_id': None, 'noise_spl': 0, 'playback_device_id': None,
        'description': '', 'asr_text': '', 'annotations': [],
    }
    r = requests.post(A.API + '/audios/upload/merge', headers={**h, 'Content-Type': 'application/json'},
                      json=body, timeout=300)
    print('merge', r.status_code, r.text[:400])
    aid = (r.json().get('data') or {}).get('audio_id')
    print('AUDIO_ID', aid)
    if aid:
        r = requests.put(A.API + '/audios/%s/metadata' % aid, headers=h,
                         json={'name': name}, timeout=120)
        print('rename', r.status_code, r.text[:160])
        print('AUDIO_ID=' + str(aid))


if __name__ == '__main__':
    sys.exit(main() or 0)
