# -*- coding: utf-8 -*-
"""INT-2177 返工探针②：自建音频 + 自建用例 + 批量标注后台刷新（INT-2042）。

链路：upload init→register→chunk→merge 建「接线测试_走查B2_」音频 →
建引用该音频的用例 → 连续 3 批 POST /audios/batch/annotations →
核对接口毫秒级返回 + audio_service 后台「关联用例参考参数刷新完成 用例=N」。

用法：
  python tests/verify/int2177_audio.py upload
  python tests/verify/int2177_audio.py annotate <audio_id> <case_id> <n>
  python tests/verify/int2177_audio.py cleanup <audio_id> <case_id>
"""
import base64
import hashlib
import io
import json
import os
import secrets
import sys
import time
import wave

import httpx

BASE = 'http://localhost:15000/api/v1'
USER = '接线测试_admin'
PASSWORD = 'JieXianTest@2026'


def login(client):
    info = client.get('/auth/login/encryption-key').json()
    if isinstance(info.get('data'), dict) and info['data'].get('kid'):
        info = info['data']
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    pub = serialization.load_pem_public_key(info['public_key'].encode())
    ct = base64.b64encode(pub.encrypt(
        PASSWORD.encode(),
        padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()),
                     algorithm=hashes.SHA256(), label=None))).decode()
    body = client.post('/auth/login', data={
        'username': USER, 'password_encrypted': ct,
        'encryption_key_id': info['kid']}).json()
    data = body.get('data') if isinstance(body.get('data'), dict) else body
    return {'Authorization': f"Bearer {data['access_token']}"}


def make_wav():
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b'\x00\x01' * 1600)
    return buf.getvalue() + b'INT2177-' + secrets.token_hex(8).encode()


def do_upload(c):
    content = make_wav()
    md5 = hashlib.md5(content).hexdigest()
    name = f'接线测试_走查B2_音频_{int(time.time())}.wav'
    d = c.post('/audios/upload/init', json={}).json().get('data') or {}
    task_id = d.get('taskId') or d.get('task_id')
    body = c.post('/audios/upload/register', json={
        'taskId': task_id,
        'files': [{'name': name, 'size': len(content), 'md5': md5,
                   'relativePath': 'int2177/' + name}]}).json()
    f = ((body.get('data') or {}).get('files') or [{}])[0]
    fid = f.get('fileId') or f.get('file_id')
    total = f.get('totalChunks') or f.get('total_chunks')
    chunk_size = f.get('chunkSize') or f.get('chunk_size')
    print('init task', task_id, 'file', fid, 'chunks', total, 'chunk_size', chunk_size)
    for i in range(total):
        sl = content[i * chunk_size:(i + 1) * chunk_size]
        r = c.post('/audios/upload/chunk',
                   data={'file_id': fid, 'chunk_index': str(i),
                         'total_chunks': str(total), 'task_id': task_id},
                   files={'chunk': (f'chunk_{i}', sl)})
        assert r.status_code == 200, r.text[:300]
    r = c.post('/audios/upload/merge', json={'file_id': fid, 'task_id': task_id})
    print('merge', r.status_code, r.text[:400])
    audio_id = ((r.json().get('data') or {}).get('audio_id')
                or (r.json().get('data') or {}).get('audioId'))
    print('AUDIO_ID', audio_id, 'NAME', name)
    return audio_id, name


def main():
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    c = httpx.Client(base_url=BASE, timeout=120, trust_env=False)
    h = login(c)
    c.headers.update(h)
    cmd = sys.argv[1]
    if cmd == 'upload':
        do_upload(c)
    elif cmd == 'annotate':
        audio_id, case_id, n = int(sys.argv[2]), sys.argv[3], int(sys.argv[4])
        payload = {'items': [{'audio_id': audio_id, 'annotations': [
            {'code': 'int2177_probe', 'format': 'json',
             'data': {'text': f'接线测试_走查B2_标注_{n}_{secrets.token_hex(2)}'}}]}],
            'algorithm_type': 'voice_llm', 'refresh_test_cases': True}
        t0 = time.time()
        r = c.post('/audios/batch/annotations', json=payload)
        dt = time.time() - t0
        print(f'batch#{n} status={r.status_code} elapsed={dt*1000:.0f}ms body={r.text[:400]}')
    elif cmd == 'cleanup':
        print('delete audio', sys.argv[2], c.delete(f'/audios/{sys.argv[2]}').status_code)
        if len(sys.argv) > 3:
            print('delete case', sys.argv[3], c.delete(f'/testcases/{sys.argv[3]}').status_code)


if __name__ == '__main__':
    main()
