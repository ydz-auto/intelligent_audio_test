# -*- coding: utf-8 -*-
"""INT-2215 用例 ZIP 导入回导音频 —— 进程内真实链路探针。

不依赖 docker :15000 与宿主 audio_service（50052），全部用**本 worktree 的代码**
在独立端口（≥55170）起两段真实 gRPC server，落库到一次性 scratch 库：

  网关 TestCaseImportService → AudioAclRepositoryImpl → gRPC
    → AudioConfigServiceServicer（INT-2216 真实 servicer / handler / 转码落存储）
  → gRPC → TestCaseConfigServiceServicer / TaskDataServiceServicer（真实落库 test_cases）

场景（对应卡面端到端六条的前五条的可离线部分）：
  S1 无音频 → 按 md5 登记 → 用例 config 全口径 id 重写（含干扰人/噪音）
  S2 同 md5 复用 → 不新增 audios 行
  S3 同 audio_id 不同 md5 → 不按 id 绑定，按 md5 映射到正确 id
  S4 单条登记失败（包内字节被篡改 → md5_mismatch）→ 该用例行级错误、不落库，其余照常
  S5 预览同包：不报假缺失、不登记（audios 行数不变）

运行（scratch 库自动创建、结束 DROP）：
  set PROBE_PG_ADMIN_URL=postgresql://intelligent_audio_test:intelligent_audio_test666@localhost:5432/postgres
  python tests/ui/probe_int2215_import_audio_remap.py
"""
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import uuid
import wave
import zipfile

PREFIX = '接线测试_INT2215_'
AUDIO_PORT = int(os.environ.get('PROBE_AUDIO_PORT', '55171'))
TASK_PORT = int(os.environ.get('PROBE_TASK_PORT', '55172'))
SCRATCH_DB = os.environ.get('PROBE_DB_NAME') or f'int2215_probe_{uuid.uuid4().hex[:8]}'
ADMIN_URL = os.environ.get('PROBE_PG_ADMIN_URL')
USER_ID = '2215'

STORAGE_ROOT = os.environ.get('PROBE_STORAGE_ROOT') or tempfile.mkdtemp(prefix='int2215_store_')
UPLOAD_ROOT = os.path.join(tempfile.mkdtemp(prefix='int2215_upload_'), 'audios')


def _log(msg):
    print(msg, flush=True)


# ----------------------------------------------------------------------
# scratch 库
# ----------------------------------------------------------------------
def _create_scratch_db():
    """CREATE DATABASE ... TEMPLATE template0（collation 与主库实例对齐，用后 DROP）。"""
    if not ADMIN_URL:
        raise SystemExit('需要 PROBE_PG_ADMIN_URL（指向 postgres 维护库）')
    from sqlalchemy import create_engine, text
    admin = create_engine(ADMIN_URL, isolation_level='AUTOCOMMIT')
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS {SCRATCH_DB}'))
        conn.execute(text(
            f'CREATE DATABASE {SCRATCH_DB} TEMPLATE template0 ENCODING \'UTF8\''))
    admin.dispose()
    base, _sep, _db = ADMIN_URL.rpartition('/')
    return f'{base}/{SCRATCH_DB}'


def _drop_scratch_db():
    from sqlalchemy import create_engine, text
    admin = create_engine(ADMIN_URL, isolation_level='AUTOCOMMIT')
    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS {SCRATCH_DB} WITH (FORCE)'))
    admin.dispose()


# ----------------------------------------------------------------------
# 本地存储替身（探针不发网络请求，落盘即真实文件）
# ----------------------------------------------------------------------
class _LocalFakeStorage:
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


def _wav_bytes(duration_ms=120, sample_rate=8000, channels=1, seed=0):
    frames = int(sample_rate * duration_ms / 1000)
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(bytes([seed % 251]) * frames * channels * 2)
    return buf.getvalue()


# ----------------------------------------------------------------------
# gRPC servers
# ----------------------------------------------------------------------
def _start_servers():
    import grpc
    from concurrent import futures
    from shared.infrastructure.grpc_interceptors import (
        server_db_scope_interceptor, server_user_context_interceptor,
    )
    from shared.proto import audio_service_pb2_grpc as audio_pbg
    from shared.proto import task_service_pb2_grpc as task_pbg
    from audio_service.interfaces.grpc.servicers import AudioConfigServiceServicer
    from task_service.interfaces.grpc.testcase_config import TestCaseConfigServiceServicer
    from task_service.interfaces.grpc.task_data_service import TaskDataServiceServicer

    def _server(port):
        server = grpc.server(
            futures.ThreadPoolExecutor(max_workers=8),
            interceptors=[server_db_scope_interceptor, server_user_context_interceptor],
        )
        server.add_insecure_port(f'[::]:{port}')
        return server

    audio_server = _server(AUDIO_PORT)
    audio_pbg.add_AudioConfigServiceServicer_to_server(AudioConfigServiceServicer(), audio_server)
    audio_server.start()

    task_server = _server(TASK_PORT)
    task_pbg.add_TestCaseConfigServiceServicer_to_server(
        TestCaseConfigServiceServicer(), task_server)
    task_pbg.add_TaskDataServiceServicer_to_server(TaskDataServiceServicer(), task_server)
    task_server.start()
    return audio_server, task_server


# ----------------------------------------------------------------------
# 用例包构造
# ----------------------------------------------------------------------
def _build_zip(cases, audio_files):
    buf = io.BytesIO()
    manifest_audios = []
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('testcases.json', json.dumps({'test_cases': cases}, ensure_ascii=False))
        for item in audio_files:
            path = f"audios/{item['id']}.wav"
            content = item.get('package_bytes', item['bytes'])
            zf.writestr(path, content)
            manifest_audios.append({
                'id': item['id'], 'name': item['name'], 'file': path,
                'md5': item['md5'], 'size': len(content), 'format': 'wav',
            })
        zf.writestr('manifest.json', json.dumps({
            'format': 'intelligent-audio-testcase-package', 'version': '1.1',
            'total_count': len(cases), 'audio_file_count': len(manifest_audios),
            'missing_audio_count': 0, 'missing_audio_ids': [],
            'audios': manifest_audios,
        }, ensure_ascii=False))
    return buf.getvalue()


class _FakeRequest:
    def __init__(self, files):
        self.state = type('_State', (), {'_files': files})()


class _FakeUpload:
    def __init__(self, filename, data):
        self.filename = filename
        self.file = io.BytesIO(data)


def _run_service(monkeypatch_target, method, data):
    from api_gateway.infrastructure.request_adapter import set_current_request
    set_current_request(_FakeRequest({'file': _FakeUpload('probe.zip', data)}))
    try:
        payload, code = getattr(monkeypatch_target, method)()
    finally:
        set_current_request(None)
    return payload, code


# ----------------------------------------------------------------------
def main():
    out = {'scratch_db': SCRATCH_DB, 'ports': {'audio': AUDIO_PORT, 'task': TASK_PORT},
           'checks': [], 'scenarios': {}, 'cleanup': {}}

    def check(name, cond, detail=''):
        out['checks'].append({'name': name, 'ok': bool(cond), 'detail': str(detail)})
        _log(('PASS ' if cond else 'FAIL ') + name + (f' | {detail}' if detail else ''))

    scratch_url = _create_scratch_db()
    # 端口/库必须在导入网关与 shared.clients 之前确定（channel 地址在 import 时冻结）
    os.environ['DATABASE_URL'] = scratch_url
    os.environ.setdefault('OSS_ACCESS_KEY', 'test')
    os.environ.setdefault('OSS_SECRET_KEY', 'test')
    os.environ['AUDIO_SERVICE_HOST'] = 'localhost'
    os.environ['AUDIO_SERVICE_GRPC_PORT'] = str(AUDIO_PORT)
    os.environ['TASK_SERVICE_HOST'] = 'localhost'
    os.environ['TASK_SERVICE_GRPC_PORT'] = str(TASK_PORT)

    servers = []
    try:
        from shared.models.database import Base, get_db_session, get_engine, init_db
        from audio_service.infrastructure.persistence.models import (  # noqa: F401
            Audio, AudioAlgorithmRelation, AudioAnnotation, AudioPlaybackHistory, AudioTag,
            UploadChunk, UploadFile, UploadTask,
        )
        from task_service.infrastructure.persistence import models as task_models  # noqa: F401

        init_db(pool_size=5)
        Base.metadata.create_all(get_engine())

        from audio_service.config.config import Config
        Config.AUDIO_STORAGE_PATH = UPLOAD_ROOT
        from audio_service.application.services.audio_upload import transcoding_service as ts_mod
        ts_mod.storage = _LocalFakeStorage(STORAGE_ROOT)

        from audio_service.application.services.audio_upload.register_by_bytes_mixin import (
            AudioRegisterByBytesMixin,
        )
        AudioRegisterByBytesMixin._refresh_stats_after_register = lambda self, audio_id: None

        servers = _start_servers()
        from shared.infrastructure.user_context import set_current_user_id
        set_current_user_id(int(USER_ID))

        db = get_db_session()
        from sqlalchemy import text

        def _count(sql, params=None):
            return db.execute(text(sql), params or {}).scalar()

        def audio_rows(ids):
            if not ids:
                return []
            rows = db.execute(text(
                'SELECT id, name, md5, size, format, duration, file_path '
                'FROM audios WHERE id = ANY(:ids) ORDER BY id'), {'ids': list(ids)}).mappings().all()
            return [dict(r) for r in rows]

        def case_rows(ids):
            if not ids:
                return []
            rows = db.execute(text(
                'SELECT id, name, config FROM test_cases WHERE id = ANY(:ids) ORDER BY name'),
                {'ids': list(ids)}).mappings().all()
            return [dict(r) for r in rows]

        from api_gateway.application.services.testcase.testcase_import_service import (
            TestCaseImportService,
        )

        # ---------- 目标库预置：S2 同 md5 已有；S3 同 id 不同 md5 ----------
        reuse_bytes = _wav_bytes(duration_ms=150, seed=1)
        reuse_md5 = hashlib.md5(reuse_bytes).hexdigest()
        reuse_path = os.path.join(UPLOAD_ROOT, 'seed_reuse.wav')
        os.makedirs(UPLOAD_ROOT, exist_ok=True)
        open(reuse_path, 'wb').write(reuse_bytes)
        db.execute(text(
            "INSERT INTO audios (name, original_filename, file_path, size, duration, format, "
            "md5, audio_type, deleted, visibility, created_at, updated_at) VALUES "
            "(:n, :n, :p, :s, 0.15, 'wav', :m, 'dry', false, 'shared', now(), now())"),
            {'n': PREFIX + '目标已有同md5.wav', 'p': reuse_path, 's': len(reuse_bytes), 'm': reuse_md5})
        db.commit()
        reuse_id = _count("SELECT id FROM audios WHERE name = :n",
                          {'n': PREFIX + '目标已有同md5.wav'})

        wrong_bytes = _wav_bytes(duration_ms=180, seed=2)
        wrong_path = os.path.join(UPLOAD_ROOT, 'seed_wrong_id.wav')
        open(wrong_path, 'wb').write(wrong_bytes)
        db.execute(text(
            "INSERT INTO audios (name, original_filename, file_path, size, duration, format, "
            "md5, audio_type, deleted, visibility, created_at, updated_at) VALUES "
            "(:n, :n, :p, :s, 0.18, 'wav', :m, 'dry', false, 'shared', now(), now())"),
            {'n': PREFIX + '目标同id不同md5.wav', 'p': wrong_path,
             's': len(wrong_bytes), 'm': hashlib.md5(wrong_bytes).hexdigest()})
        db.commit()
        wrong_id = _count("SELECT id FROM audios WHERE name = :n",
                          {'n': PREFIX + '目标同id不同md5.wav'})

        audio_before = _count('SELECT count(*) FROM audios')

        # ---------- 包内音频 ----------
        s1_bytes = _wav_bytes(duration_ms=120, seed=3)
        s1_md5 = hashlib.md5(s1_bytes).hexdigest()
        s3_bytes = _wav_bytes(duration_ms=210, sample_rate=16000, seed=4)
        s3_md5 = hashlib.md5(s3_bytes).hexdigest()
        s4_bytes = _wav_bytes(duration_ms=130, seed=5)
        s4_md5 = hashlib.md5(s4_bytes).hexdigest()

        source_s1 = 7000001
        source_s2 = 7000002
        source_s3 = wrong_id          # 与目标库既有 id 撞号，但 md5 不同
        source_s4 = 7000004

        cases = [
            {   # S1：无音频 → 登记 → 全口径重写
                'name': PREFIX + 'S1_无音频登记',
                'group': PREFIX + '分组',
                'config': {
                    'rounds': [{'round_number': 1, 'audios': [
                        {'audio_id': source_s1, 'spl': 60,
                         'interferers': [{'audio_id': source_s1, 'spl': 40}]}],
                        'backgroundNoise': {'audio_id': source_s1, 'spl': 25}}],
                    'background_noise': {'audio_id': source_s1, 'spl': 30},
                },
            },
            {   # S2：同 md5 复用
                'name': PREFIX + 'S2_同md5复用',
                'group': PREFIX + '分组',
                'config': {'rounds': [{'round_number': 1, 'audios': [
                    {'audio_id': source_s2, 'spl': 60}]}]},
            },
            {   # S3：同 id 不同 md5 → 按 md5 映射
                'name': PREFIX + 'S3_同id不同md5',
                'group': PREFIX + '分组',
                'config': {'rounds': [{'round_number': 1, 'audios': [
                    {'audio_id': source_s3, 'spl': 60}]}]},
            },
            {   # S4：包内字节被篡改（manifest md5 与字节不一致）→ 行级错误
                'name': PREFIX + 'S4_篡改失败',
                'group': PREFIX + '分组',
                'config': {'rounds': [{'round_number': 1, 'audios': [
                    {'audio_id': source_s4, 'spl': 60}]}]},
            },
        ]
        audio_files = [
            {'id': source_s1, 'name': PREFIX + '包内S1.wav', 'bytes': s1_bytes, 'md5': s1_md5},
            {'id': source_s2, 'name': PREFIX + '包内S2.wav', 'bytes': reuse_bytes, 'md5': reuse_md5},
            {'id': source_s3, 'name': PREFIX + '包内S3.wav', 'bytes': s3_bytes, 'md5': s3_md5},
            {'id': source_s4, 'name': PREFIX + '包内S4.wav', 'bytes': s4_bytes, 'md5': 'f' * 32,
             'package_bytes': s4_bytes},
        ]
        package = _build_zip(cases, audio_files)

        # ---------- S5 预览：只读 ----------
        preview_payload, preview_code = _run_service(
            TestCaseImportService, 'preview_import', package)
        audio_after_preview = _count('SELECT count(*) FROM audios')
        preview_errors = (preview_payload.get('data') or {}).get('errors') or []
        out['scenarios']['preview'] = {
            'code': preview_code, 'errors': preview_errors,
            'audio_rows_delta': audio_after_preview - audio_before,
        }
        check('S5 预览不报假缺失（包内音频视为可用）',
              not any('不存在' in str(e) for e in preview_errors), preview_errors)
        check('S5 预览不登记音频（audios 行数不变）',
              audio_after_preview == audio_before,
              f'{audio_before}->{audio_after_preview}')

        # ---------- 正式导入 ----------
        import_payload, import_code = _run_service(
            TestCaseImportService, 'import_cases', package)
        receipt = import_payload.get('data') or {}
        out['scenarios']['import'] = {
            'code': import_code, 'receipt': receipt, 'message': import_payload.get('message'),
        }
        check('导入回执 200', import_code == 200, preview_errors)
        check('S1/S2/S3 导入成功、S4 行级错误',
              receipt.get('imported_count') == 3 and len(receipt.get('errors') or []) == 1,
              receipt.get('errors'))
        check('S4 错误原因为登记失败（md5_mismatch）',
              any('md5_mismatch' in str(e) for e in (receipt.get('errors') or [])),
              receipt.get('errors'))
        check('回执音频汇总：登记 2（S1 无音频 + S3 同id不同md5）/ 复用 1（S2 同md5）',
              receipt.get('audio_registered_count') == 2
              and receipt.get('audio_reused_count') == 1,
              {k: receipt.get(k) for k in ('audio_registered_count', 'audio_reused_count')})

        # ---------- 落库核对 ----------
        cases_in_db = case_rows([
            row['id'] for row in db.execute(text(
                'SELECT id FROM test_cases WHERE name LIKE :p ORDER BY name'),
                {'p': PREFIX + '%'}).mappings().all()])
        by_name = {row['name']: row for row in cases_in_db}
        out['scenarios']['test_cases'] = [
            {'name': row['name'], 'config': row['config']} for row in cases_in_db]
        check('test_cases 落库 3 条（S4 不落库）',
              len(cases_in_db) == 3, [r['name'] for r in cases_in_db])

        s1_case = by_name.get(PREFIX + 'S1_无音频登记')
        s1_config = (s1_case or {}).get('config') or {}
        s1_round = (s1_config.get('rounds') or [{}])[0]
        s1_ids = {
            'round_audio': ((s1_round.get('audios') or [{}])[0]).get('audio_id'),
            'interferer': (((s1_round.get('audios') or [{}])[0].get('interferers') or [{}])[0]).get('audio_id'),
            'round_noise': (s1_round.get('backgroundNoise') or {}).get('audio_id'),
            'top_noise': (s1_config.get('background_noise') or {}).get('audio_id'),
        }
        registered_id = None
        if s1_ids['round_audio']:
            registered_id = int(s1_ids['round_audio'])
            rows = audio_rows([registered_id])
            out['scenarios']['registered_audio'] = rows
            stored_md5 = None
            if rows and os.path.isfile(rows[0]['file_path']):
                stored_md5 = hashlib.md5(open(rows[0]['file_path'], 'rb').read()).hexdigest()
            check('S1 登记出的 audios 行 md5 与包内字节一致',
                  bool(rows) and rows[0]['md5'] == s1_md5 and stored_md5 == s1_md5,
                  {'row_md5': (rows or [{}])[0].get('md5'), 'stored_md5': stored_md5})
        check('S1 config 全口径重写（播放/干扰人/轮次噪音/顶层噪音 同 id）',
              len({v for v in s1_ids.values()}) == 1 and registered_id not in (None, source_s1),
              s1_ids)

        s2_case = by_name.get(PREFIX + 'S2_同md5复用')
        s2_config = (s2_case or {}).get('config') or {}
        s2_audio_id = (((s2_config.get('rounds') or [{}])[0].get('audios') or [{}])[0]).get('audio_id')
        check('S2 复用目标库既有 id，不重复登记',
              s2_audio_id == reuse_id, {'rewritten': s2_audio_id, 'expected': reuse_id})

        s3_case = by_name.get(PREFIX + 'S3_同id不同md5')
        s3_config = (s3_case or {}).get('config') or {}
        s3_audio_id = (((s3_config.get('rounds') or [{}])[0].get('audios') or [{}])[0]).get('audio_id')
        check('S3 不按 audio_id 错绑，按 md5 新建/映射到另一条',
              s3_audio_id != wrong_id and s3_audio_id is not None,
              {'source': wrong_id, 'rewritten': s3_audio_id})
        if s3_audio_id:
            rows = audio_rows([int(s3_audio_id)])
            check('S3 映射到的音频 md5 与包内一致',
                  bool(rows) and rows[0]['md5'] == s3_md5, rows)
            out['scenarios']['s3_audio'] = rows

        check('S4 不落库', (PREFIX + 'S4_篡改失败') not in by_name, list(by_name))

        audio_after = _count('SELECT count(*) FROM audios')
        check('audios 行数 = 预置 2 + S1 新增 1 + S3 新增 1',
              audio_after - audio_before == 2, f'{audio_before}->{audio_after}')

    finally:
        # 清理：自建用例 / 分组 / 音频 + 存储对象
        try:
            from sqlalchemy import text
            from shared.models.database import get_db_session
            db = get_db_session()
            db.execute(text('DELETE FROM test_cases WHERE name LIKE :p'), {'p': PREFIX + '%'})
            db.execute(text('DELETE FROM audios WHERE name LIKE :p'), {'p': PREFIX + '%'})
            db.commit()
            out['cleanup']['residual_cases'] = db.execute(
                text('SELECT count(*) FROM test_cases WHERE name LIKE :p'),
                {'p': PREFIX + '%'}).scalar()
            out['cleanup']['residual_audios'] = db.execute(
                text('SELECT count(*) FROM audios WHERE name LIKE :p'),
                {'p': PREFIX + '%'}).scalar()
        except Exception as exc:  # noqa: BLE001
            out['cleanup']['error'] = str(exc)
        for server in servers:
            server.stop(0)
        shutil.rmtree(STORAGE_ROOT, ignore_errors=True)
        shutil.rmtree(os.path.dirname(UPLOAD_ROOT), ignore_errors=True)
        try:
            _drop_scratch_db()
            out['cleanup']['scratch_db_dropped'] = True
        except Exception as exc:  # noqa: BLE001
            out['cleanup']['drop_error'] = str(exc)

    failed = [c for c in out['checks'] if not c['ok']]
    out['summary'] = {'total': len(out['checks']), 'failed': len(failed)}
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
