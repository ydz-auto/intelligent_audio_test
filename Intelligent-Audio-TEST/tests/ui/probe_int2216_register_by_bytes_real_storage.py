# -*- coding: utf-8 -*-
"""INT-2216 复核探针：RegisterAudioByBytes 走真实 OSS（rustfs）+ scratch Postgres。

与 `probe_int2216_register_by_bytes.py`（本地假存储）互补：验收标准 1 要求
`file_path` 能被 `storage_load_bytes` 读回且字节一致，本探针**不替换 storage**，
强制 `STORAGE_FALLBACK_ENABLED=false`（OSS 不可用直接报错，不静默降级），
登记后按共享存储 API 读回比对，再清理行与对象。

前置：先建 scratch 库（不要用主库）：
  docker exec intelligent-audio-test-postgres-1 psql -U intelligent_audio_test \\
      -c 'CREATE DATABASE int2216_verify TEMPLATE template0'

运行（宿主 rustfs endpoint/凭据取自 docker compose 默认值）：
  VERIFY_DATABASE_URL=postgresql://intelligent_audio_test:***@localhost:5432/int2216_verify \\
  OSS_ENDPOINT=http://127.0.0.1:9000 OSS_ACCESS_KEY=intelligent_audio_test \\
  OSS_SECRET_KEY=*** OSS_BUCKET_NAME=intelligent-audio-test \\
  OSS_KEY_PREFIX=intelligent_audio_test PYTHONPATH=. \\
  python tests/ui/probe_int2216_register_by_bytes_real_storage.py

覆盖：A 新 md5（真实 OSS 往返 + 行字段）、B 同 md5 幂等复用、C md5 不一致拒绝、
D 0 帧合帧 wav（duration=0）拒绝且不留 OSS 对象、E 大写 md5 命中复用。
写入行统一「接线测试_INT2216_存储核对_」前缀，结束删行与对象，跑完可 DROP scratch 库。
"""
import base64
import hashlib
import io
import json
import os
import sys
import wave

DATABASE_URL = os.environ.get('VERIFY_DATABASE_URL')
if not DATABASE_URL:
    raise SystemExit('need VERIFY_DATABASE_URL')
os.environ['DATABASE_URL'] = DATABASE_URL
os.environ['STORAGE_FALLBACK_ENABLED'] = 'false'

GRPC_PORT = int(os.environ.get('VERIFY_GRPC_PORT', '55317'))
PREFIX = '接线测试_INT2216_存储核对_'


def wav_bytes(duration_ms=120, sample_rate=8000, channels=1):
    frames = int(sample_rate * duration_ms / 1000)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b'\x00\x01' * frames * channels)
    return buf.getvalue()


def main():
    from shared.models.database import Base, get_engine, init_db, get_db_session
    from audio_service.infrastructure.persistence.models import Audio
    from sqlalchemy import text

    init_db(pool_size=3)
    Base.metadata.create_all(get_engine(), tables=[Audio.__table__])

    from audio_service.application.services.audio_upload.register_by_bytes_mixin import (
        AudioRegisterByBytesMixin,
    )
    # 统计缓存刷新属网关域，与本命令落库语义无关
    AudioRegisterByBytesMixin._refresh_stats_after_register = lambda self, audio_id: None

    import grpc
    from concurrent import futures
    from shared.infrastructure.grpc_interceptors import (
        server_db_scope_interceptor, server_user_context_interceptor,
    )
    from shared.proto import audio_service_pb2 as pb, audio_service_pb2_grpc as pbg
    from audio_service.interfaces.grpc.servicers import AudioConfigServiceServicer
    from shared.infrastructure.storage import storage, storage_load_bytes

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=2),
        interceptors=[server_db_scope_interceptor, server_user_context_interceptor],
    )
    pbg.add_AudioConfigServiceServicer_to_server(AudioConfigServiceServicer(), server)
    server.add_insecure_port(f'[::]:{GRPC_PORT}')
    server.start()

    out = {'database': DATABASE_URL.split('@')[-1], 'scenarios': [], 'cleanup': {}}
    channel = grpc.insecure_channel(f'localhost:{GRPC_PORT}')
    stub = pbg.AudioConfigServiceStub(channel)
    meta = [('x-user-id', '2216')]

    def call(data):
        resp = stub.RegisterAudioByBytes(
            pb.RegisterAudioByBytesRequest(data=json.dumps(data, ensure_ascii=False)),
            metadata=meta, timeout=180)
        return {'success': resp.success, 'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None}

    def count_rows():
        return get_db_session().execute(
            text('SELECT count(*) FROM audios WHERE name LIKE :p'),
            {'p': PREFIX + '%'}).scalar()

    created_paths = []
    try:
        content = wav_bytes(duration_ms=120)
        md5 = hashlib.md5(content).hexdigest()
        name = PREFIX + '正常.wav'

        # --- 1. 新 md5 登记，真实 OSS 落盘 ---
        r1 = call({'name': name, 'format': 'wav', 'size': len(content), 'md5': md5,
                   'content_b64': base64.b64encode(content).decode(),
                   'audio_type': 'dry', 'source_filename': name})
        d1 = r1['data'] or {}
        if d1.get('file_path'):
            created_paths.append(d1['file_path'])
        rows = get_db_session().execute(text(
            'SELECT id,name,format,size,md5,duration,sample_rate,channels,'
            'audio_type,visibility,created_by_user_id,file_path FROM audios '
            'WHERE name=:n ORDER BY id'), {'n': name}).mappings().all()
        row = dict(rows[0]) if rows else None

        stored_ok = None
        if row and row['file_path']:
            try:
                stored = storage_load_bytes(row['file_path'])
                stored_ok = {
                    'file_path': row['file_path'],
                    'scheme_oss': str(row['file_path']).startswith('oss://'),
                    'size': len(stored),
                    'md5_of_stored': hashlib.md5(stored).hexdigest(),
                    'matches_input_md5': hashlib.md5(stored).hexdigest() == md5,
                    'matches_input_size': len(stored) == len(content),
                }
            except Exception as exc:  # noqa: BLE001
                stored_ok = {'file_path': row['file_path'], 'load_error': repr(exc)}

        # --- 2. 同 md5 幂等复用（换名，不新增行/对象） ---
        r2 = call({'name': PREFIX + '改名.wav', 'format': 'wav',
                   'size': len(content), 'md5': md5,
                   'content_b64': base64.b64encode(content).decode()})
        out['scenarios'].append({'A 新md5登记': r1, 'db_row': row,
                                 'storage_roundtrip': stored_ok})
        out['scenarios'].append({
            'B 同md5复用': r2,
            'same_id': (r2['data'] or {}).get('id') == d1.get('id'),
            'reused': (r2['data'] or {}).get('reused'),
            'rows_with_prefix': count_rows(),
        })

        # --- 3. md5 与字节不一致：400，不落库 ---
        before = count_rows()
        r3 = call({'name': PREFIX + '错md5.wav', 'format': 'wav',
                   'size': len(content), 'md5': 'f' * 32,
                   'content_b64': base64.b64encode(content).decode()})
        out['scenarios'].append({'C md5不一致': r3, 'row_delta': count_rows() - before})

        # --- 4. 0 帧合法 wav（duration=0）：400，不落行、不留 OSS 对象 ---
        zero = wav_bytes(duration_ms=0)
        zname = PREFIX + '零帧.wav'
        before = count_rows()
        r4 = call({'name': zname, 'format': 'wav', 'size': len(zero),
                   'md5': hashlib.md5(zero).hexdigest(),
                   'content_b64': base64.b64encode(zero).decode()})
        out['scenarios'].append({
            'D 0帧wav': r4, 'row_delta': count_rows() - before,
            'input_bytes': len(zero),
            'oss_object_left': storage.exists('audios/direct/' + zname),
        })

        # --- 5. 大写入参 md5：接受并命中既有记录 ---
        r5 = call({'name': PREFIX + '大写md5.wav', 'format': 'wav',
                   'size': len(content), 'md5': md5.upper(),
                   'content_b64': base64.b64encode(content).decode()})
        out['scenarios'].append({
            'E 大写md5': r5,
            'hit_existing_id': (r5['data'] or {}).get('id') == d1.get('id'),
            'reused': (r5['data'] or {}).get('reused'),
        })
    finally:
        # 清理：行 + 存储对象
        session = get_db_session()
        deleted = session.execute(text('DELETE FROM audios WHERE name LIKE :p'),
                                  {'p': PREFIX + '%'}).rowcount
        session.commit()
        out['cleanup']['rows_deleted'] = deleted
        out['cleanup']['objects'] = []
        for p in created_paths:
            try:
                existed = storage.exists(p)
                storage.delete(p)
                out['cleanup']['objects'].append(
                    {'path': p, 'existed': existed, 'exists_after': storage.exists(p)})
            except Exception as exc:  # noqa: BLE001
                out['cleanup']['objects'].append({'path': p, 'error': repr(exc)})
        out['cleanup']['residual_rows'] = count_rows()
        channel.close()
        server.stop(0)

    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == '__main__':
    sys.exit(main())
