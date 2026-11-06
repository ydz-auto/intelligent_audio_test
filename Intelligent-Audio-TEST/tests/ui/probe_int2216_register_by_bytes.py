# -*- coding: utf-8 -*-
"""INT-2216 RegisterAudioByBytes —— 进程内真实 gRPC 链路探针。

宿主 audio_service 未刷新前（宿主启动器指向主 clone），本探针用**本 worktree 的
代码**起一个只注册 AudioConfigService 的临时 gRPC server（独立端口，不占 50052），
用真实 gRPC 客户端直连，落库到独立 scratch 库，核对请求/响应原文与 SELECT 行。

链路：grpc 客户端 → 真实 servicer（AudioConfigServiceServicer）→ handler →
AudioUploadService.register_audio_by_bytes → 转码/落存储 → 仓储 → Postgres。

运行前先建 scratch 库（不要用主库）：
  docker exec intelligent-audio-test-postgres-1 psql -U intelligent_audio_test \
      -c 'CREATE DATABASE int2216_probe'
  set PROBE_DATABASE_URL=postgresql://intelligent_audio_test:***@localhost:5432/int2216_probe
  python tests/ui/probe_int2216_register_by_bytes.py

用例（卡面验收标准 1~4 + 导入端前置条件）：
  A 新 md5 + 合法 wav     → 新 id，DB 行 name/format/size/md5/duration 齐全
  B 同 md5 再登记          → 同 id、reused=true、audios 行数不增
  C md5 与字节不一致       → success=false + 原因，无新增行
  D 空字节 / 纯文本 .wav   → success=false + 原因，无新增行
  E 同名不同 md5           → 允许新建（去重维度只认 md5）
  F GetAudioByMD5 回查     → 按 md5 命中 A 的 id（导入端复用前置）

所有写入行用「接线测试_INT2216_」前缀，脚本结束前删除（含本地存储对象）。
"""
import base64
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import wave

PROBE_DB = os.environ.get('PROBE_DATABASE_URL')
if PROBE_DB:
    os.environ['DATABASE_URL'] = PROBE_DB
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

PREFIX = '接线测试_INT2216_'
GRPC_PORT = int(os.environ.get('PROBE_GRPC_PORT', '55162'))
STORAGE_ROOT = os.environ.get('PROBE_STORAGE_ROOT') or tempfile.mkdtemp(prefix='int2216_probe_store_')
UPLOAD_ROOT = os.path.join(tempfile.mkdtemp(prefix='int2216_probe_upload_'), 'audios')
USER_ID = '2216'


class _LocalFakeStorage:
    """storage 的本地副本（探针不发网络请求；落盘即是真实文件）。"""

    def __init__(self, root):
        self.root = root

    def _path(self, key):
        return os.path.join(self.root, key.replace('/', os.sep))

    def exists(self, key):
        return os.path.exists(self._path(key))

    def save_file(self, local_path, category, key, **kwargs):
        dst = self._path(f'{category}/{key}')
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(local_path, dst)
        return dst

    def load_file(self, path, local_path=None, **kwargs):
        src = self._path(path)
        if local_path is None:
            local_path = tempfile.mktemp(suffix='.wav')
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        shutil.copy2(src, local_path)
        return local_path

    def delete(self, path):
        p = self._path(path)
        if os.path.exists(p):
            os.remove(p)


def _wav_bytes(duration_ms=120, sample_rate=8000, channels=1):
    frames = int(sample_rate * duration_ms / 1000)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(b'\x00\x01' * frames * channels)
    return buf.getvalue()


def _b64(data):
    return base64.b64encode(data).decode('ascii')


def _make_server():
    import grpc
    from concurrent import futures
    from shared.infrastructure.grpc_interceptors import (
        server_db_scope_interceptor, server_user_context_interceptor,
    )
    from shared.proto import audio_service_pb2_grpc as pbg
    from audio_service.interfaces.grpc.servicers import AudioConfigServiceServicer

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=4),
        interceptors=[server_db_scope_interceptor, server_user_context_interceptor],
    )
    pbg.add_AudioConfigServiceServicer_to_server(AudioConfigServiceServicer(), server)
    server.add_insecure_port(f'[::]:{GRPC_PORT}')
    server.start()
    return server


def main():
    from shared.models.database import Base, get_engine, init_db
    from audio_service.infrastructure.persistence.models import Audio

    init_db(pool_size=5)
    Base.metadata.create_all(get_engine(), tables=[Audio.__table__])

    from audio_service.config.config import Config
    Config.AUDIO_STORAGE_PATH = UPLOAD_ROOT
    from audio_service.application.services.audio_upload import transcoding_service as ts_mod
    fake_storage = _LocalFakeStorage(STORAGE_ROOT)
    ts_mod.storage = fake_storage

    # 统计缓存刷新属网关域，探针聚焦登记链路（与 url_import 同一调用点，已由既有链路覆盖）
    from audio_service.application.services.audio_upload.register_by_bytes_mixin import (
        AudioRegisterByBytesMixin,
    )
    AudioRegisterByBytesMixin._refresh_stats_after_register = lambda self, audio_id: None

    server = _make_server()
    import grpc
    from shared.proto import audio_service_pb2 as pb
    from shared.proto import audio_service_pb2_grpc as pbg

    channel = grpc.insecure_channel(f'localhost:{GRPC_PORT}')
    stub = pbg.AudioConfigServiceStub(channel)
    metadata = [('x-user-id', USER_ID)]

    out = {'grpc_port': GRPC_PORT, 'database': os.environ.get('DATABASE_URL', '').split('@')[-1],
           'scenarios': [], 'db_rows': [], 'cleanup': {}}

    def call(step, data):
        request = pb.RegisterAudioByBytesRequest(
            data=json.dumps(data, ensure_ascii=False))
        resp = stub.RegisterAudioByBytes(request, metadata=metadata, timeout=120)
        item = {
            'step': step,
            'request_data_keys': sorted(data.keys()),
            'response': {'success': resp.success, 'message': resp.message,
                         'data': json.loads(resp.data) if resp.data else None},
        }
        out['scenarios'].append(item)
        return item['response']

    def db_rows_for(name):
        from sqlalchemy import text
        from shared.models.database import get_db_session
        session = get_db_session()
        rows = session.execute(text(
            'SELECT id, name, format, size, md5, duration, sample_rate, channels, '
            'audio_type, visibility, created_by_user_id, file_path '
            'FROM audios WHERE name = :n ORDER BY id'), {'n': name}).mappings().all()
        return [dict(r) for r in rows]

    def count_rows():
        from sqlalchemy import text
        from shared.models.database import get_db_session
        return get_db_session().execute(
            text('SELECT count(*) FROM audios WHERE name LIKE :p'),
            {'p': PREFIX + '%'}).scalar()

    # ---- A 新 md5 + 合法 wav ----
    name_a = PREFIX + '正常.wav'
    wav_a = _wav_bytes(duration_ms=120)
    md5_a = hashlib.md5(wav_a).hexdigest()
    resp_a = call('A 新md5登记', {
        'name': name_a, 'format': 'wav', 'size': len(wav_a), 'md5': md5_a,
        'content_b64': _b64(wav_a), 'audio_type': 'dry', 'source_filename': name_a,
    })
    audio_id_a = (resp_a.get('data') or {}).get('id')
    rows_a = db_rows_for(name_a)
    out['scenarios'][-1]['db_rows'] = rows_a
    if rows_a:
        fp = rows_a[0]['file_path']
        stored_md5 = (hashlib.md5(open(fp, 'rb').read()).hexdigest()
                      if os.path.isfile(fp) else None)
        out['scenarios'][-1]['stored_file'] = {
            'exists': os.path.isfile(fp),
            'size': os.path.getsize(fp) if os.path.isfile(fp) else None,
            'md5_of_stored_bytes': stored_md5,
            'matches_input_md5': stored_md5 == md5_a,
            'matches_input_size': (os.path.getsize(fp) == len(wav_a))
            if os.path.isfile(fp) else False,
        }
    out['db_rows'].extend(rows_a)

    # ---- B 同 md5 再登记（换名）----
    resp_b = call('B 同md5幂等复用', {
        'name': PREFIX + '改名尝试.wav', 'format': 'wav', 'size': len(wav_a),
        'md5': md5_a, 'content_b64': _b64(wav_a), 'audio_type': 'dry',
        'source_filename': PREFIX + '改名尝试.wav',
    })
    out['scenarios'][-1]['same_id'] = (resp_b.get('data') or {}).get('id') == audio_id_a
    out['scenarios'][-1]['row_count_after'] = count_rows()

    # ---- C md5 与字节不一致 ----
    before_c = count_rows()
    call('C md5不一致拒绝', {
        'name': PREFIX + 'md5错.wav', 'format': 'wav', 'size': len(wav_a),
        'md5': 'f' * 32, 'content_b64': _b64(wav_a), 'source_filename': PREFIX + 'md5错.wav',
    })
    out['scenarios'][-1]['row_count_delta'] = count_rows() - before_c

    # ---- D1 空字节 ----
    before_d = count_rows()
    call('D1 空字节拒绝', {
        'name': PREFIX + '空.wav', 'format': 'wav', 'size': 0,
        'md5': hashlib.md5(b'').hexdigest(), 'content_b64': '',
        'source_filename': PREFIX + '空.wav',
    })
    out['scenarios'][-1]['row_count_delta'] = count_rows() - before_d

    # ---- D2 纯文本伪装 .wav ----
    text_bytes = '这不是音频内容'.encode('utf-8')
    before_d2 = count_rows()
    call('D2 非音频拒绝', {
        'name': PREFIX + '纯文本.wav', 'format': 'wav', 'size': len(text_bytes),
        'md5': hashlib.md5(text_bytes).hexdigest(), 'content_b64': _b64(text_bytes),
        'source_filename': PREFIX + '纯文本.wav',
    })
    out['scenarios'][-1]['row_count_delta'] = count_rows() - before_d2

    # ---- E 同名不同 md5 ----
    name_e = PREFIX + '同名.wav'
    wav_e1 = _wav_bytes(duration_ms=100, sample_rate=8000)
    wav_e2 = _wav_bytes(duration_ms=200, sample_rate=16000)
    call('E1 同名首个', {
        'name': name_e, 'format': 'wav', 'size': len(wav_e1),
        'md5': hashlib.md5(wav_e1).hexdigest(), 'content_b64': _b64(wav_e1),
        'source_filename': name_e,
    })
    call('E2 同名不同md5', {
        'name': name_e, 'format': 'wav', 'size': len(wav_e2),
        'md5': hashlib.md5(wav_e2).hexdigest(), 'content_b64': _b64(wav_e2),
        'source_filename': name_e,
    })
    rows_e = db_rows_for(name_e)
    out['scenarios'][-1]['db_rows'] = rows_e
    out['db_rows'].extend(rows_e)

    # ---- F GetAudioByMD5 回查（导入端「先查 md5 再登记」前置）----
    resp_f = stub.GetAudioByMD5(
        pb.GetAudioByMD5Request(data=json.dumps({'md5_list': [md5_a]})),
        metadata=metadata, timeout=60)
    out['get_by_md5'] = {
        'success': resp_f.success,
        'data': json.loads(resp_f.data) if resp_f.data else None,
        'hits_registered_id': (json.loads(resp_f.data) or {}).get(md5_a, {}).get('id') == audio_id_a,
    }

    # ---- 清理：删本探针写入的行与存储对象 ----
    from sqlalchemy import text
    from shared.models.database import get_db_session
    session = get_db_session()
    stored = [r['file_path'] for r in out['db_rows'] if r.get('file_path')]
    deleted = session.execute(
        text('DELETE FROM audios WHERE name LIKE :p'), {'p': PREFIX + '%'}).rowcount
    session.commit()
    out['cleanup']['rows_deleted'] = deleted
    out['cleanup']['files_deleted'] = 0
    for fp in stored:
        try:
            if os.path.isfile(fp):
                os.remove(fp)
                out['cleanup']['files_deleted'] += 1
        except Exception as exc:  # noqa: BLE001
            out['cleanup'].setdefault('file_errors', []).append(f'{fp}: {exc}')
    out['cleanup']['residual_rows'] = count_rows()

    channel.close()
    server.stop(0)
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))


if __name__ == '__main__':
    sys.exit(main())
