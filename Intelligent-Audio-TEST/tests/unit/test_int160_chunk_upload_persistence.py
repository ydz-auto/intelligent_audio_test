# -*- coding: utf-8 -*-
"""INT-160 音频分片上传链端到端回归

修复的两个缺陷：
1. 网关/服务分片内容键不匹配：网关发送 `chunk_data`，服务读取
   `chunk_content` → 内容永远为 None → 分片不落盘（空文件），chunk 响应
   却报成功。修复：网关统一发送 `chunk_content`；服务对缺失内容显式 400。
2. 文件级计数不持久化：`get_upload_file/get_upload_task` 返回脱离会话的
   Entity 副本，mixin 在副本上 `+=` 永远不写库 → `upload_files.completed_chunks
   / uploaded_size / status` 恒 0/pending，merge 恒 400「还有分片未上传完成」。
   修复：进度经仓储 `update_upload_file_progress / update_upload_task_progress`
   回写 PO；重传同序号分片不重复计数；响应在提交后重查实体。

覆盖：
1. 分片上传持久化：upload_files / upload_tasks / upload_chunks 落库值与
   响应一致，分片字节落盘
2. 重传同序号分片幂等（计数不重复累加，chunk_size 回写）
3. 分片上传 → merge → 建音频 端到端（转码服务打桩，验证合并文件字节）
4. 缺少分片内容显式 400
5. 网关契约：upload_chunk 向 ACL 传递 `chunk_content` 键（防键名再漂移）
"""
import base64
import os
import tempfile

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int160_') + '/chunk.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles

from shared.models.database import Base, get_engine, init_db
from audio_service.infrastructure.persistence.models import (
    Audio,
    UploadFile,
    UploadChunk,
    UploadTask,
)


@compiles(BigInteger, 'sqlite')
def _render_bigint_as_integer_sqlite(type_, compiler, **kw):
    """SQLite 不支持 BigInteger 主键自增，建表时渲染为 INTEGER。"""
    return 'INTEGER'


@pytest.fixture(scope='module', autouse=True)
def _db():
    init_db()
    engine = get_engine()
    Base.metadata.create_all(engine, tables=[
        UploadTask.__table__, UploadFile.__table__,
        UploadChunk.__table__, Audio.__table__,
    ])
    yield


@pytest.fixture()
def service():
    from audio_service.application.services.audio_upload.service import AudioUploadService
    return AudioUploadService()


def _init_task(service):
    res = service.init_upload_task({})
    assert res['success'], res
    return res['data']['task_id']


def _register(service, task_id, size, name='测试音频.wav'):
    res = service.register_upload_file({
        'task_id': task_id,
        'files': [{'name': name, 'size': size, 'md5': ''}],
    })
    assert res['success'], res
    return res['data']['files'][0]


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode('ascii')


class TestChunkUploadPersistence:
    """缺陷 2：文件级计数/状态持久化"""

    def test_chunk_counters_persisted_and_response_consistent(self, service, tmp_path,
                                                              monkeypatch):
        monkeypatch.setattr(
            'audio_service.config.config.Config.AUDIO_STORAGE_PATH', str(tmp_path))
        task_id = _init_task(service)
        # 10MB+1 → total_chunks=2，用小载荷即可驱动多分片计数
        reg = _register(service, task_id, 10 * 1024 * 1024 + 1)
        file_id, total = reg['file_id'], reg['total_chunks']
        assert total == 2

        res = service.upload_chunk({
            'file_id': file_id, 'chunk_index': 0, 'total_chunks': total,
            'task_id': task_id, 'chunk_content': _b64(b'A' * 1000),
        })
        assert res['success'], res
        assert res['data']['completed_chunks'] == 1
        assert res['data']['uploaded_size'] == 1000

        # 库中值与响应一致（原缺陷：响应 1 库中 0）
        f = service.repo.get_upload_file(file_id)
        assert f.completed_chunks == 1
        assert f.uploaded_size == 1000
        assert f.status.value == 'uploading'
        t = service.repo.get_upload_task(task_id)
        assert t.uploaded_size == 1000
        assert t.completed_files == 0
        assert t.status.value == 'uploading'

        # 分片字节真实落盘（原缺陷：内容键不匹配 → 空文件/目录不建）
        chunk0 = service.repo.get_upload_chunk(file_id, 0)
        assert chunk0 is not None
        assert chunk0.chunk_size == 1000
        from shared.models.database import get_db_session
        chunk_po = get_db_session().query(UploadChunk).filter_by(
            file_id=file_id, chunk_index=0).first()
        with open(chunk_po.stored_path, 'rb') as fh:
            assert fh.read() == b'A' * 1000

        res2 = service.upload_chunk({
            'file_id': file_id, 'chunk_index': 1, 'total_chunks': total,
            'task_id': task_id, 'chunk_content': _b64(b'B' * 500),
        })
        assert res2['success'], res2
        f = service.repo.get_upload_file(file_id)
        assert f.completed_chunks == 2
        assert f.uploaded_size == 1500
        assert f.status.value == 'completed'
        t = service.repo.get_upload_task(task_id)
        assert t.completed_files == 1
        assert t.uploaded_size == 1500
        assert t.status.value == 'completed'

    def test_duplicate_chunk_upload_is_idempotent(self, service, tmp_path, monkeypatch):
        monkeypatch.setattr(
            'audio_service.config.config.Config.AUDIO_STORAGE_PATH', str(tmp_path))
        task_id = _init_task(service)
        reg = _register(service, task_id, 10 * 1024 * 1024 + 1)
        file_id, total = reg['file_id'], reg['total_chunks']

        for payload in (b'A' * 1000, b'X' * 800):  # 第二次为重传（体积不同）
            res = service.upload_chunk({
                'file_id': file_id, 'chunk_index': 0, 'total_chunks': total,
                'task_id': task_id, 'chunk_content': _b64(payload),
            })
            assert res['success'], res

        f = service.repo.get_upload_file(file_id)
        assert f.completed_chunks == 1, '重传同序号分片不得重复计数'
        assert f.uploaded_size == 800, '重传后按最新分片大小计'
        chunk0 = service.repo.get_upload_chunk(file_id, 0)
        assert chunk0.chunk_size == 800
        from shared.models.database import get_db_session
        chunk_po = get_db_session().query(UploadChunk).filter_by(
            file_id=file_id, chunk_index=0).first()
        with open(chunk_po.stored_path, 'rb') as fh:
            assert fh.read() == b'X' * 800

    def test_missing_chunk_content_rejected(self, service, tmp_path, monkeypatch):
        monkeypatch.setattr(
            'audio_service.config.config.Config.AUDIO_STORAGE_PATH', str(tmp_path))
        task_id = _init_task(service)
        reg = _register(service, task_id, 190 * 1024)
        file_id = reg['file_id']

        res = service.upload_chunk({
            'file_id': file_id, 'chunk_index': 0,
            'total_chunks': reg['total_chunks'], 'task_id': task_id,
        })
        assert not res['success']
        assert res['code'] == 400

        f = service.repo.get_upload_file(file_id)
        assert f.completed_chunks == 0
        assert f.uploaded_size == 0
        assert service.repo.get_upload_chunk(file_id, 0) is None


class TestChunkMergeE2E:
    """分片上传 → merge → 建音频 端到端（转码服务打桩）"""

    def test_chunk_upload_then_merge_creates_audio(self, service, tmp_path, monkeypatch):
        monkeypatch.setattr(
            'audio_service.config.config.Config.AUDIO_STORAGE_PATH', str(tmp_path))

        from audio_service.application.services.audio_upload.transcoding_service import (
            audio_transcoding_service,
        )

        def fake_transcode(final_path, upload_file):
            return {
                'final_path': final_path,
                'file_size': os.path.getsize(final_path),
                'duration': 1.0,
                'sample_rate': 44100,
                'channels': 1,
                'bitrate': 16 * 44100,
            }

        monkeypatch.setattr(audio_transcoding_service,
                            'transcode_and_extract_metadata', fake_transcode)

        payload = b'RIFF____WAVEfmt ' + b'\x00' * 64
        task_id = _init_task(service)
        reg = _register(service, task_id, len(payload))
        file_id = reg['file_id']

        res = service.upload_chunk({
            'file_id': file_id, 'chunk_index': 0,
            'total_chunks': reg['total_chunks'], 'task_id': task_id,
            'chunk_content': _b64(payload),
        })
        assert res['success'], res

        merged = service.merge_chunks({'file_id': file_id, 'task_id': task_id})
        assert merged['success'], merged
        assert merged['data']['audio_id']

        audio = service.repo.get_audio(merged['data']['audio_id'])
        assert audio is not None
        assert audio.filename == '测试音频.wav'

        # 合并文件字节 == 分片内容
        with open(audio.file_path, 'rb') as fh:
            assert fh.read() == payload

        f = service.repo.get_upload_file(file_id)
        assert f.status.value == 'completed'
        assert f.completed_chunks == reg['total_chunks']


class TestGatewayChunkContentKey:
    """缺陷 1：网关向 ACL 传递 chunk_content 键（防键名再漂移）"""

    def test_gateway_forwards_chunk_content(self, monkeypatch):
        from api_gateway.infrastructure import request_adapter  # noqa: F401
        from api_gateway.infrastructure.request_adapter import request
        from api_gateway.middleware import RequestAdapterMiddleware
        from api_gateway.application.services.audio import audio_upload_service as gw_mod

        class _CaptureAcl:
            data = None

            def upload_chunk(self, data):
                type(self).data = data
                return {'success': True, 'data': {'file_id': data['file_id']},
                        'message': 'ok', 'code': 200}

        app = FastAPI()
        app.add_middleware(RequestAdapterMiddleware)

        @app.post('/upload-chunk')
        def upload_chunk():
            return gw_mod.AudioUploadService.upload_chunk()

        captured = _CaptureAcl()
        monkeypatch.setattr(gw_mod, '_audio_acl', captured)
        resp = TestClient(app).post(
            '/upload-chunk',
            data={'file_id': 'f-1', 'chunk_index': '0', 'total_chunks': '1',
                  'task_id': 't-1'},
            files={'chunk': ('part0.wav', b'BIN0', 'audio/wav')},
        )
        assert resp.status_code == 200

        data = _CaptureAcl.data
        assert data is not None
        assert data['chunk_content'] == _b64(b'BIN0')
        assert 'chunk_data' not in data
