# -*- coding: utf-8 -*-
"""transfer_agent 服务启动与 gRPC 端到端测试（INT-28 验收标准 1）。

- FastAPI app 可创建、/health 暴露服务与 zone
- gRPC server 可启动并监听注册端口（50101）
- gRPC 全链路：经 proto stub 调用 CreateTransfer → 验签失败语义透传
- gRPC 满片 4MB 传输可达（server/stub 两侧消息上限放开，审计 P3 回归锁定）

使用文件型 sqlite + 临时目录；不依赖外部 PostgreSQL / Redis / OSS。
"""
import hashlib
import json
import os
import socket
import sys

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')
os.environ.setdefault('TRANSFER_TOKEN_A_B', 'secret-ab')

import pytest
from fastapi.testclient import TestClient

import transfer_agent.app as app_module
from transfer_agent.domain.services.signature_service import SignatureService


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


@pytest.fixture(scope='module')
def db_env(tmp_path_factory):
    """文件型 sqlite（内存库不兼容共享连接池参数）。"""
    db_path = tmp_path_factory.mktemp('transfer_db') / 'transfer_check.db'
    old = os.environ.get('DATABASE_URL')
    os.environ['DATABASE_URL'] = f'sqlite:///{db_path.as_posix()}'
    yield os.environ['DATABASE_URL']
    if old is not None:
        os.environ['DATABASE_URL'] = old


def test_health_exposes_service_and_zone():
    client = TestClient(app_module.create_app())  # 不进 lifespan，不连 DB
    r = client.get('/health')
    assert r.status_code == 200
    body = r.json()
    assert body['service'] == 'transfer_agent'
    assert body['zone'] in ('A', 'B', 'C')
    assert body['status'] == 'ok'


def test_ports_registered_in_service_ports():
    from shared.config import service_ports
    assert service_ports.TRANSFER_AGENT_HTTP_PORT == 5010
    assert service_ports.TRANSFER_AGENT_GRPC_PORT == 50101


def test_grpc_server_end_to_end(db_env):
    """启动 gRPC server（ephemeral 端口）→ stub 调用 → 域错误语义经 gRPC 透传。"""
    from sqlalchemy import create_engine
    from shared.models import database as db
    from shared.models.database import Base
    from transfer_agent.infrastructure.persistence import models as po_models  # noqa: F401  注册 PO

    # 文件型 sqlite 手工绑线（shared init_db 的连接池参数与 sqlite 方言不兼容；
    # 生产部署为 PostgreSQL，走 init_db）
    db_path = os.environ['DATABASE_URL'].replace('sqlite:///', '', 1).replace('\\', '/')
    engine = create_engine(f'sqlite:///{db_path}')
    db._SessionFactory.configure(bind=engine)
    db._engine = engine
    Base.metadata.create_all(engine)

    from transfer_agent.interfaces.grpc.server import start_grpc_server

    port = _free_port()
    server = start_grpc_server(port=port)
    try:
        import grpc
        from shared.proto import transfer_agent_pb2 as transfer_pb
        from shared.proto import transfer_agent_pb2_grpc as transfer_grpc

        channel = grpc.insecure_channel(f'127.0.0.1:{port}')
        grpc.channel_ready_future(channel).result(timeout=10)
        stub = transfer_grpc.TransferAgentServiceStub(channel)

        # 未签名的创建请求 → 签名层明确拒绝（success=False + 错误码前缀）
        resp = stub.CreateTransfer(transfer_pb.CreateTransferRequest(
            transfer_id='grpc-t-1', pkg_type='DATA_SYNC', src_zone='A', dst_zone='B',
            category='audios', key='task_1/audio.wav',
            file_hash='sha256:' + 'a' * 64, file_size=100, ttl_seconds=3600,
            ephemeral=False, timestamp='2026-10-08T10:00:00+08:00',
            signature='bad-signature', token='secret-ab',
        ))
        assert resp.success is False
        assert 'TRANSFER_SIGNATURE_INVALID' in resp.message

        # 查询不存在的传输 → NOT_FOUND 语义（走真实 DB 查询）
        resp = stub.GetTransferStatus(transfer_pb.GetTransferStatusRequest(
            transfer_id='ghost', token='secret-ab',
        ))
        assert resp.success is False
        assert 'TRANSFER_PACKAGE_NOT_FOUND' in resp.message
        channel.close()
    finally:
        server.stop(0)
        db._engine = None
        db._SessionFactory.configure(bind=None)


class _UnreachableOSS:
    """OSS 不可达替身：驱动统一存储走本地降级分支，避免单元测试触网。"""

    def __getattr__(self, name):
        def _fail(*args, **kwargs):
            raise RuntimeError('OSS unreachable (stub)')
        return _fail


def test_grpc_full_chunk_transfer(db_env, tmp_path, monkeypatch):
    """审计 P3：满 4MB 分片经真实 gRPC 传输可达。

    grpcio 默认收发上限 4MiB，与默认满片大小相等 → 未放开上限时本链路必失败；
    server options 与 stub channel 两侧均需设置 max_*_message_length。
    """
    from sqlalchemy import create_engine
    from shared.models import database as db
    from shared.models.database import Base
    from shared.infrastructure import storage as storage_module
    from shared.infrastructure.config import BaseConfig
    from transfer_agent.infrastructure.persistence import models as po_models  # noqa: F401

    db_path = os.environ['DATABASE_URL'].replace('sqlite:///', '', 1).replace('\\', '/')
    engine = create_engine(f'sqlite:///{db_path}')
    db._SessionFactory.configure(bind=engine)
    db._engine = engine
    Base.metadata.create_all(engine)

    # 本地降级 + 隔离存储根目录
    monkeypatch.setattr(storage_module.storage, '_use_oss', lambda: False)
    monkeypatch.setattr(storage_module.storage, '_oss_client', _UnreachableOSS())
    monkeypatch.setattr(storage_module.storage, '_oss_checked', True)
    monkeypatch.setattr(storage_module.storage, '_oss_ok', False)
    monkeypatch.setattr(BaseConfig, 'STORAGE_LOCAL_ROOT', str(tmp_path / 'storage_root'))

    from transfer_agent.config.config import Config
    from transfer_agent.interfaces.grpc.server import start_grpc_server

    port = _free_port()
    server = start_grpc_server(port=port)
    try:
        import grpc
        from shared.proto import transfer_agent_pb2 as transfer_pb
        from shared.proto import transfer_agent_pb2_grpc as transfer_grpc

        max_bytes = Config.TRANSFER_GRPC_MAX_MESSAGE_MB * 1024 * 1024
        channel = grpc.insecure_channel(f'127.0.0.1:{port}', options=[
            ('grpc.max_send_message_length', max_bytes),
            ('grpc.max_receive_message_length', max_bytes),
        ])
        grpc.channel_ready_future(channel).result(timeout=10)
        stub = transfer_grpc.TransferAgentServiceStub(channel)

        payload = os.urandom(4 * 1024 * 1024)  # 恰为默认满片
        fields = dict(
            transfer_id='grpc-full-chunk', pkg_type='DATA_SYNC', src_zone='A',
            dst_zone='B', category='audios', key='task_1/big.bin',
            file_hash='sha256:' + hashlib.sha256(payload).hexdigest(),
            file_size=len(payload), ttl_seconds=3600,
            timestamp='2026-10-08T10:00:00+08:00',
        )
        fields['signature'] = SignatureService.compute_signature('secret-ab', **fields)

        resp = stub.CreateTransfer(transfer_pb.CreateTransferRequest(
            transfer_id=fields['transfer_id'], pkg_type=fields['pkg_type'],
            src_zone=fields['src_zone'], dst_zone=fields['dst_zone'],
            category=fields['category'], key=fields['key'],
            file_hash=fields['file_hash'], file_size=fields['file_size'],
            ttl_seconds=fields['ttl_seconds'], ephemeral=False,
            timestamp=fields['timestamp'], signature=fields['signature'],
            token='secret-ab',
        ))
        assert resp.success is True, resp.message

        # 满片上传（4MB 数据 + 元数据超 grpcio 默认上限，放开后应通过）
        resp = stub.UploadChunk(transfer_pb.UploadChunkRequest(
            transfer_id=fields['transfer_id'], chunk_index=0, data=payload,
            checksum=hashlib.sha256(payload).hexdigest(), token='secret-ab',
        ))
        assert resp.success is True, resp.message

        resp = stub.CompleteTransfer(transfer_pb.CompleteTransferRequest(
            transfer_id=fields['transfer_id'], token='secret-ab',
        ))
        assert resp.success is True, resp.message
        data = json.loads(resp.data)
        assert data['status'] == 'COMPLETED'
        # file_hash 校验通过后才提升到终桶，内容与声明一致
        assert storage_module.storage.load_bytes(data['final_path']) == payload
        channel.close()
    finally:
        server.stop(0)
        db._engine = None
        db._SessionFactory.configure(bind=None)
