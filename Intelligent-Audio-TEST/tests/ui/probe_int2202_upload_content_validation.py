# -*- coding: utf-8 -*-
"""INT-2202 上传/合并音频内容校验 —— 影子容器内真实链路探针。

运行方式（一次性容器 iat-int2202-verify，代码用本 worktree 的 audio_service 覆盖
镜像内 /app/audio_service）：容器内 ``python /app/tests/ui/probe_int2202_upload_content_validation.py``。

链路：api_gateway ASGI 应用（真实路由/中间件，TestClient）→ 真实 gRPC 客户端
（AUDIO_SERVICE_GRPC_PORT 指向本进程内起的 audio_service gRPC server）→
audio_service 应用服务/仓储（本 worktree 代码）→ 真实 Postgres 隔离测试库
intelligent_audio_test_test + 真实 RustFS。

用例（验收口径：merge 失败明细带原因、不落库；正常音频不受影响）：
  A 0 字节 .wav      → merge 400 音频内容无效、无 audio 记录、分片目录已清理
  B 纯文本改名 .wav  → merge 400 音频内容无效、无 audio 记录
  C 正常 WAV         → merge 200、入库 duration/sample_rate/channels 为真实探测值
  D 直传 0 字节      → complete-direct 400、无 audio 记录
  E 直传正常 WAV     → complete-direct 200、入库探测值正确

所有写库数据用「接线测试_INT2202_」前缀，脚本结束前删除（含 OSS 对象）。
"""
import io
import json
import os
import sys
import time
import wave

PREFIX = '接线测试_INT2202_'
RESULTS = []


def ok(results, step, status, body, extra=None):
    results.append({'step': step, 'http_status': status, 'body': body, 'extra': extra})
    return body


def make_wav(duration_ms=120, sample_rate=8000, channels=1):
    buf = io.BytesIO()
    n = int(sample_rate * duration_ms / 1000)
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b'\x00\x01' * n * channels)
    return buf.getvalue()


def upload_merge_chain(client, name, content):
    """init → register → chunk → merge，返回 (merge_resp, file_id, task_id)。"""
    r = client.post('/api/v1/audios/upload/init', json={})
    assert r.status_code == 200, (r.status_code, r.text)
    task_id = r.json()['data']['task_id']

    r = client.post('/api/v1/audios/upload/register', json={
        'task_id': task_id,
        'files': [{'name': name, 'size': len(content), 'md5': '', 'relative_path': ''}],
    })
    assert r.status_code == 200, (r.status_code, r.text)
    reg = r.json()['data']
    file_id = reg['files'][0]['file_id']
    total_chunks = reg['files'][0]['total_chunks']
    assert total_chunks == 1, total_chunks

    r = client.post('/api/v1/audios/upload/chunk',
                    data={'file_id': file_id, 'chunk_index': 0,
                          'total_chunks': total_chunks, 'task_id': task_id},
                    files={'chunk': ('blob', content, 'application/octet-stream')})
    assert r.status_code == 200, (r.status_code, r.text)

    r = client.post('/api/v1/audios/upload/merge',
                    json={'file_id': file_id, 'task_id': task_id})
    return r, file_id, task_id


def audio_names(client):
    r = client.get('/api/v1/audios', params={'keyword': PREFIX, 'page': 1, 'page_size': 100})
    if r.status_code != 200:
        return None, r.status_code, r.text
    body = r.json()
    data = body.get('data') or {}
    items = data.get('items') or data.get('list') or data.get('audios') or []
    return [it.get('name') for it in items], r.status_code, None


def main():
    from audio_service.interfaces.grpc.server import start_grpc_server
    grpc_server = start_grpc_server(port=int(os.environ.get('VERIFY_GRPC_PORT', '50952')))
    time.sleep(1.0)

    from fastapi.testclient import TestClient
    from api_gateway.app import create_app
    client = TestClient(create_app())

    out = {'scenarios': [], 'cleanup': {}}
    created_files = []

    def record(name, resp, extra=None):
        item = {'name': name, 'http_status': resp.status_code}
        try:
            item['body'] = resp.json()
        except Exception:
            item['body'] = resp.text
        if extra:
            item.update(extra)
        out['scenarios'].append(item)
        return item

    # ---- A 0 字节 .wav ----
    name_a = PREFIX + '零字节.wav'
    resp, file_id_a, task_a = upload_merge_chain(client, name_a, b'')
    chunk_dir_a = os.path.join(_base_upload_dir(), 'chunks', file_id_a)
    record('A 0字节.wav merge', resp, {'chunk_dir_exists_after': os.path.isdir(chunk_dir_a)})
    created_files.append(('task', task_a))

    # ---- B 纯文本改名 .wav ----
    name_b = PREFIX + '纯文本.wav'
    resp, file_id_b, task_b = upload_merge_chain(client, name_b, b'this is definitely not an audio payload')
    chunk_dir_b = os.path.join(_base_upload_dir(), 'chunks', file_id_b)
    record('B 纯文本.wav merge', resp, {'chunk_dir_exists_after': os.path.isdir(chunk_dir_b)})
    created_files.append(('task', task_b))

    # ---- C 正常 WAV ----
    name_c = PREFIX + '正常.wav'
    wav_bytes = make_wav()
    resp, file_id_c, task_c = upload_merge_chain(client, name_c, wav_bytes)
    rec = record('C 正常.wav merge', resp)
    audio_id_c = (resp.json().get('data') or {}).get('audio_id')
    created_files.append(('task', task_c))
    if audio_id_c:
        created_files.append(('audio', audio_id_c))

    # ---- F 合法 WAV 头但 0 帧（时长 0）----
    from shared.infrastructure.storage import storage
    name_f = PREFIX + '零时长.wav'
    empty_frames_wav = make_wav(duration_ms=0)
    resp, file_id_f, task_f = upload_merge_chain(client, name_f, empty_frames_wav)
    oss_key_f = f'audios/direct/{name_f[:-4]}.wav'
    record('F 0帧WAV merge', resp, {
        'chunk_dir_exists_after': os.path.isdir(
            os.path.join(_base_upload_dir(), 'chunks', file_id_f)),
        'oss_object_left': storage.exists(oss_key_f),
    })
    created_files.append(('task', task_f))

    # ---- G 同一任务混合：非法 + 合法，互不影响 ----
    r = client.post('/api/v1/audios/upload/init', json={})
    task_g = r.json()['data']['task_id']
    bad_g, good_g = PREFIX + '混合_坏.wav', PREFIX + '混合_好.wav'
    good_bytes = make_wav(duration_ms=200, sample_rate=16000)
    r = client.post('/api/v1/audios/upload/register', json={
        'task_id': task_g,
        'files': [
            {'name': bad_g, 'size': 10, 'md5': '', 'relative_path': ''},
            {'name': good_g, 'size': len(good_bytes), 'md5': '', 'relative_path': ''},
        ],
    })
    files_g = r.json()['data']['files']
    ids = {}
    for rec, content in zip(files_g, [b'0123456789', good_bytes]):
        ids[rec['filename']] = rec['file_id']
        client.post('/api/v1/audios/upload/chunk',
                    data={'file_id': rec['file_id'], 'chunk_index': 0,
                          'total_chunks': rec['total_chunks'], 'task_id': task_g},
                    files={'chunk': ('blob', content, 'application/octet-stream')})
    rg_bad = client.post('/api/v1/audios/upload/merge',
                         json={'file_id': ids[bad_g], 'task_id': task_g})
    rg_good = client.post('/api/v1/audios/upload/merge',
                          json={'file_id': ids[good_g], 'task_id': task_g})
    record('G1 混合批 坏文件 merge', rg_bad)
    record('G2 混合批 好文件 merge', rg_good)
    created_files.append(('task', task_g))
    if (rg_good.json().get('data') or {}).get('audio_id'):
        created_files.append(('audio', rg_good.json()['data']['audio_id']))

    # ---- 按名回读 ----
    names, st, err = audio_names(client)
    out['readback'] = {'http_status': st, 'names': names, 'error': err}

    # ---- D/E 直传 ----
    from shared.infrastructure.storage import storage
    tmpdir = '/tmp/int2202'
    os.makedirs(tmpdir, exist_ok=True)

    direct_key_bad = f'direct/{PREFIX}直传零字节.wav'
    p = os.path.join(tmpdir, 'bad.wav')
    open(p, 'wb').close()
    storage.save_file(p, 'audios', direct_key_bad)
    r = client.post('/api/v1/audios/upload/complete-direct', json={
        'oss_key': direct_key_bad, 'filename': PREFIX + '直传零字节.wav',
        'file_size': 0, 'md5': '', 'tags': [],
    })
    record('D 直传0字节 complete-direct', r)
    storage.delete(f'audios/{direct_key_bad}')

    direct_key_good = f'direct/{PREFIX}直传正常.wav'
    p2 = os.path.join(tmpdir, 'good.wav')
    with open(p2, 'wb') as f:
        f.write(wav_bytes)
    storage.save_file(p2, 'audios', direct_key_good)
    r = client.post('/api/v1/audios/upload/complete-direct', json={
        'oss_key': direct_key_good, 'filename': PREFIX + '直传正常.wav',
        'file_size': len(wav_bytes), 'md5': '', 'tags': [],
    })
    record('E 直传正常 complete-direct', r)
    direct_audio_id = (r.json().get('data') or {}).get('audio_id')
    if direct_audio_id:
        created_files.append(('audio', direct_audio_id))

    # ---- DB 落库核对 ----
    from shared.models.database import get_db_session
    from audio_service.infrastructure.persistence.models import Audio
    session = get_db_session()
    try:
        rows = session.query(Audio).filter(Audio.name.like(PREFIX + '%')).all()
        out['db_audios'] = [
            {'id': a.id, 'name': a.name, 'duration': a.duration,
             'sample_rate': a.sample_rate, 'channels': a.channels}
            for a in rows
        ]
    finally:
        session.close()

    # ---- 清理本探针写入的数据 ----
    cleanup = {'audio_deleted': 0, 'upload_file_deleted': 0,
               'upload_task_deleted': 0, 'upload_chunk_deleted': 0, 'oss_deleted': []}
    session = get_db_session()
    try:
        prefix_audios = session.query(Audio).filter(Audio.name.like(PREFIX + '%')).all()
        for a in prefix_audios:
            session.delete(a)
            cleanup['audio_deleted'] += 1
        session.commit()

        from audio_service.infrastructure.persistence.models import (
            UploadChunk, UploadFile, UploadTask,
        )
        files = session.query(UploadFile).filter(UploadFile.filename.like(PREFIX + '%')).all()
        file_ids = [f.id for f in files]
        task_ids = sorted({f.task_id for f in files if f.task_id})
        if file_ids:
            cleanup['upload_chunk_deleted'] = (
                session.query(UploadChunk).filter(UploadChunk.file_id.in_(file_ids))
                .delete(synchronize_session=False)
            )
            cleanup['upload_file_deleted'] = (
                session.query(UploadFile).filter(UploadFile.id.in_(file_ids))
                .delete(synchronize_session=False)
            )
        for tid in task_ids:
            cleanup['upload_task_deleted'] += (
                session.query(UploadTask).filter(UploadTask.id == tid)
                .delete(synchronize_session=False)
            )
        session.commit()
    except Exception as e:  # noqa: BLE001
        out['cleanup_error'] = repr(e)
    finally:
        session.close()

    for key in (f'audios/direct/{PREFIX}直传正常.wav',):
        try:
            storage.delete(key)
            cleanup['oss_deleted'].append(key)
        except Exception as e:  # noqa: BLE001
            cleanup['oss_deleted'].append(f'FAILED {key}: {e}')
    out['cleanup'] = cleanup

    # 清理后复核残留
    session = get_db_session()
    try:
        out['residual_audios'] = session.query(Audio).filter(Audio.name.like(PREFIX + '%')).count()
    finally:
        session.close()

    grpc_server.stop(0)
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


def _base_upload_dir():
    from audio_service.config.config import Config
    return getattr(Config, 'AUDIO_STORAGE_PATH',
                   os.path.join(os.environ.get('LOCAL_STORAGE_ROOT', './storage'), 'audios'))


if __name__ == '__main__':
    main()
