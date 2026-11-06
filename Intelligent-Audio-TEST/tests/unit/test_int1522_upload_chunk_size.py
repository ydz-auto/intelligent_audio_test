# -*- coding: utf-8 -*-
"""INT-1522 回归 — 上传分片 chunk_size 必须低于网关→audio_service 的 gRPC 收包上限。

缺陷：register 硬编码 chunk_size=10MB，客户端按此切片后，分片内容经网关 base64
（×4/3 膨胀）塞进 protobuf string 字段，8MB 文件 → 单分片 ≈11.18MB wire，被
audio_service gRPC 默认 4MiB 收包上限拒收：

    RESOURCE_EXHAUSTED ... Received message larger than max (11184977 vs. 4194304)

修复：chunk_size 改为配置项 AUDIO_UPLOAD_CHUNK_SIZE_MB（默认 2MB，wire ≈2.73MB），
同时把 audio_service gRPC 服务端收发上限按 BaseConfig.GRPC_MAX_MESSAGE_MB 放大，
消除「客户端 64MB / 服务端 4MB」的两端不一致。

覆盖：
1. register 下发的 chunk_size 来自配置，且分片数按文件大小正确计算；
2. 该 chunk_size 满片经网关 b64+JSON 后的 wire 体积 < gRPC 默认 4MiB（同时验证
   旧值 10MB 确实超限——缺陷可复现的量化依据）；
3. 配置项可按环境覆盖；
4. audio_service gRPC 服务端 options 跟随 GRPC_MAX_MESSAGE_MB，且高于 4MiB 默认；
5. 满片 chunk 走 service 落盘 + 计数推进（分片内容不再被体积问题挡在 gRPC 外）。
"""
import base64
import json
import os
import tempfile

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int1522_') + '/chunk.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from sqlalchemy import BigInteger
from sqlalchemy.ext.compiler import compiles

from shared.models.database import Base, get_engine, init_db
from shared.infrastructure.config import BaseConfig
from audio_service.config.config import Config
from audio_service.infrastructure.persistence.models import (
    Audio,
    UploadChunk,
    UploadFile,
    UploadTask,
)

# grpcio 默认收发上限（缺陷发生时服务端实际生效值）
GRPC_DEFAULT_LIMIT = 4 * 1024 * 1024


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


def _register(service, task_id, size, name='INT1522_测试音频.wav'):
    res = service.register_upload_file({
        'task_id': task_id,
        'files': [{'name': name, 'size': size, 'md5': ''}],
    })
    assert res['success'], res
    return res['data']['files'][0]


def _configured_chunk_size() -> int:
    return max(1, int(Config.AUDIO_UPLOAD_CHUNK_SIZE_MB)) * 1024 * 1024


def _gateway_wire_size(chunk_bytes: int) -> int:
    """网关 UploadChunk 在 protobuf data 字段里的实际字节数。

    网关 audio_upload_service 把分片 base64 后放入 dict，grpc proxy 以
    json.dumps(...) 写入 proto 的 string 字段（见 api_gateway/infrastructure/
    grpc_proxies/audio/config_command_mixin.py:205）。
    """
    data = {
        'file_id': 'f' * 36,
        'chunk_index': 0,
        'total_chunks': 1,
        'task_id': 't' * 36,
        'chunk_content': base64.b64encode(b'\x00' * chunk_bytes).decode('ascii'),
    }
    return len(json.dumps(data, ensure_ascii=False, default=str).encode('utf-8'))


class TestChunkSizeContract:
    """register 下发的 chunk_size 与 gRPC 收包上限的契约"""

    def test_register_chunk_size_comes_from_config(self, service):
        chunk_size = _configured_chunk_size()
        assert chunk_size == 2 * 1024 * 1024, '默认分片大小应为 2MB（INT-1522）'

        task_id = _init_task(service)
        file_size = 25 * 1024 * 1024
        reg = _register(service, task_id, file_size)

        assert reg['chunk_size'] == chunk_size
        assert reg['total_chunks'] == (file_size + chunk_size - 1) // chunk_size == 13

    def test_full_chunk_wire_size_below_grpc_default_limit(self):
        chunk_size = _configured_chunk_size()
        wire = _gateway_wire_size(chunk_size)
        assert wire < GRPC_DEFAULT_LIMIT, (
            f'满片 {chunk_size}B base64 后 {wire}B 超 gRPC 默认收包上限 '
            f'{GRPC_DEFAULT_LIMIT}B')

        # 量化复现原缺陷：旧值 10MB 的满片必然超限（8MB 文件首片即 11.18MB）
        assert _gateway_wire_size(10 * 1024 * 1024) > GRPC_DEFAULT_LIMIT
        assert _gateway_wire_size(8 * 1024 * 1024) > GRPC_DEFAULT_LIMIT

    def test_chunk_size_overridable_by_config(self, service, monkeypatch):
        monkeypatch.setattr(Config, 'AUDIO_UPLOAD_CHUNK_SIZE_MB', 1)
        task_id = _init_task(service)
        file_size = 2 * 1024 * 1024 + 512 * 1024
        reg = _register(service, task_id, file_size)

        assert reg['chunk_size'] == 1024 * 1024
        assert reg['total_chunks'] == 3


class TestAudioGrpcServerMessageLimit:
    """audio_service gRPC 服务端收发上限跟随共享配置（对齐 task_service）"""

    def test_server_options_follow_grpc_max_message_mb(self):
        from audio_service.interfaces.grpc.server import _server_options

        opts = dict(_server_options())
        expected = BaseConfig.GRPC_MAX_MESSAGE_MB * 1024 * 1024
        assert opts['grpc.max_receive_message_length'] == expected
        assert opts['grpc.max_send_message_length'] == expected
        # 必须高于 grpcio 默认 4MiB，否则大分片在服务端被 RESOURCE_EXHAUSTED
        assert opts['grpc.max_receive_message_length'] > GRPC_DEFAULT_LIMIT

    def test_server_options_track_config(self, monkeypatch):
        from audio_service.interfaces.grpc.server import _server_options

        monkeypatch.setattr(BaseConfig, 'GRPC_MAX_MESSAGE_MB', 16)
        opts = dict(_server_options())
        assert opts['grpc.max_receive_message_length'] == 16 * 1024 * 1024
        assert opts['grpc.max_send_message_length'] == 16 * 1024 * 1024


class TestFullChunkUpload:
    """满片（= register 下发的 chunk_size）可正常落盘并推进计数"""

    def test_full_size_chunk_uploaded_and_counted(self, service, tmp_path, monkeypatch):
        monkeypatch.setattr(
            'audio_service.config.config.Config.AUDIO_STORAGE_PATH', str(tmp_path))
        chunk_size = _configured_chunk_size()
        file_size = chunk_size + 1024          # 两片：满片 + 尾巴

        task_id = _init_task(service)
        reg = _register(service, task_id, file_size)
        assert reg['total_chunks'] == 2

        payload = b'\x00\x01' * (chunk_size // 2)          # 恰好 chunk_size 字节
        assert len(payload) == chunk_size

        res = service.upload_chunk({
            'file_id': reg['file_id'], 'chunk_index': 0,
            'total_chunks': reg['total_chunks'], 'task_id': task_id,
            'chunk_content': base64.b64encode(payload).decode('ascii'),
        })
        assert res['success'], res
        assert res['data']['completed_chunks'] == 1
        assert res['data']['uploaded_size'] == chunk_size

        f = service.repo.get_upload_file(reg['file_id'])
        assert f.completed_chunks == 1
        assert f.uploaded_size == chunk_size
