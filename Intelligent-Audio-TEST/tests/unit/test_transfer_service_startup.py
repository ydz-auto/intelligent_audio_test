# -*- coding: utf-8 -*-
"""transfer_agent 服务启动与 gRPC 端到端测试（INT-28 验收标准 1）。

- FastAPI app 可创建、/health 暴露服务与 zone
- gRPC server 可启动并监听注册端口（50101）
- gRPC 全链路：经 proto stub 调用 CreateTransfer → 验签失败语义透传

使用文件型 sqlite + 临时目录；不依赖外部 PostgreSQL / Redis / OSS。
"""
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
