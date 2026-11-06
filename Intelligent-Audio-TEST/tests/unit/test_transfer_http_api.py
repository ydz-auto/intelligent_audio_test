# -*- coding: utf-8 -*-
"""transfer_agent HTTP 收包接口契约测试（INT-28）。

用替身 handler 注入（monkeypatch），经 FastAPI TestClient 走真实路由栈，
验证 /internal/transfer/* 的响应结构（success/data、detail{code,message}）与
HTTP 状态码映射 —— 这是跨区 RemoteTransferClient（ACL）所依赖的线上契约。

不依赖 DB / OSS：lifespan 不触发（不使用 with 上下文）。
"""
import hashlib
import os

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from fastapi.testclient import TestClient

import transfer_agent.interfaces.api.routes as routes_module
from transfer_agent.domain.errors import PackageExpiredError, SignatureInvalidError
from transfer_agent.domain.services.signature_service import SignatureService
from tests.unit.test_transfer_handlers import (
    FakeChunkRepo,
    FakeRecordRepo,
    FakeStorage,
    TransferCommandHandler,
    TransferQueryHandler,
    make_create_cmd,
    upload_all,
)

TOKENS = {'A_B': 'secret-ab'}
CHUNK = 8


@pytest.fixture
def client(monkeypatch):
    handler = TransferCommandHandler(
        record_repo=FakeRecordRepo(), chunk_repo=FakeChunkRepo(), storage=FakeStorage(),
        signature_service=SignatureService(TOKENS),
        ttl_bounds=(60, 7 * 86400), default_chunk_size=CHUNK,
    )
    query = TransferQueryHandler(
        record_repo=FakeRecordRepo(), chunk_repo=FakeChunkRepo(),
        signature_service=SignatureService(TOKENS),
    )
    # 共享同一份替身仓储
    handler._record_repo = query._record_repo = FakeRecordRepo()
    handler._chunk_repo = query._chunk_repo = FakeChunkRepo()
    monkeypatch.setattr(routes_module, '_command_handler', handler)
    monkeypatch.setattr(routes_module, '_query_handler', query)

    import transfer_agent.app as app_module
    return TestClient(app_module.create_app())


class TestTransferHttpApi:
    def test_full_chain_over_http(self, client):
        cmd = make_create_cmd()
        body = {
            'transfer_id': cmd.transfer_id, 'pkg_type': cmd.pkg_type,
            'src_zone': cmd.src_zone, 'dst_zone': cmd.dst_zone,
            'category': cmd.category, 'key': cmd.key,
            'file_hash': cmd.file_hash, 'file_size': cmd.file_size,
            'ttl_seconds': cmd.ttl_seconds, 'ephemeral': cmd.ephemeral,
            'timestamp': cmd.timestamp, 'signature': cmd.signature,
            'meta': {},
        }
        r = client.post('/internal/transfer/packages', json=body,
                        headers={'X-Transfer-Token': 'secret-ab'})
        assert r.status_code == 200
        assert r.json()['success'] is True
        assert r.json()['data']['total_chunks'] == 3

        # 分片上传（raw body + header 元数据）
        payload = b'12345678901234567890'
        for i in (0, 1, 2):
            block = payload[i * 8:(i + 1) * 8]
            r = client.post(
                f'/internal/transfer/chunks?transfer_id={cmd.transfer_id}&chunk_index={i}',
                content=block,
                headers={
                    'X-Transfer-Token': 'secret-ab',
                    'X-Chunk-Checksum': hashlib.sha256(block).hexdigest(),
                    'Content-Type': 'application/octet-stream',
                },
            )
            assert r.status_code == 200
            assert r.json()['data']['received_chunks'] == [0, 1, 2][:i + 1]

        # 状态查询（断点续传契约）— 完成前查询已收分片
        r = client.get(f'/internal/transfer/packages/{cmd.transfer_id}',
                       headers={'X-Transfer-Token': 'secret-ab'})
        assert r.status_code == 200
        assert r.json()['data']['received_chunks'] == [0, 1, 2]

        # 完成
        r = client.post(f'/internal/transfer/packages/{cmd.transfer_id}/complete',
                        headers={'X-Transfer-Token': 'secret-ab'})
        assert r.status_code == 200
        assert r.json()['data']['status'] == 'COMPLETED'

        # 完成后分片清单清空（分片已合并回收）
        r = client.get(f'/internal/transfer/packages/{cmd.transfer_id}',
                       headers={'X-Transfer-Token': 'secret-ab'})
        assert r.status_code == 200
        assert r.json()['data']['received_chunks'] == []

    def test_missing_token_maps_to_401(self, client):
        # 路由/字段合法但缺 X-Transfer-Token 头 → 访问控制层 401
        cmd = make_create_cmd()
        body = {
            'transfer_id': cmd.transfer_id, 'pkg_type': cmd.pkg_type,
            'src_zone': cmd.src_zone, 'dst_zone': cmd.dst_zone,
            'category': cmd.category, 'key': cmd.key,
            'file_hash': cmd.file_hash, 'file_size': cmd.file_size,
            'ttl_seconds': cmd.ttl_seconds, 'ephemeral': cmd.ephemeral,
            'timestamp': cmd.timestamp, 'signature': cmd.signature, 'meta': {},
        }
        r = client.post('/internal/transfer/packages', json=body)
        assert r.status_code == 401
        assert r.json()['detail']['code'] == 'TRANSFER_ACCESS_TOKEN_INVALID'

    def test_signature_failure_maps_to_401_with_code(self, client):
        body = {
            'transfer_id': 't-x', 'pkg_type': 'DATA_SYNC', 'src_zone': 'A',
            'dst_zone': 'B', 'category': 'audios', 'key': 'k',
            'file_hash': 'sha256:' + 'a' * 64, 'file_size': 20,
            'ttl_seconds': 3600, 'ephemeral': False,
            'timestamp': '2026-10-08T10:00:00+08:00', 'signature': 'bad',
        }
        r = client.post('/internal/transfer/packages', json=body,
                        headers={'X-Transfer-Token': 'secret-ab'})
        assert r.status_code == 401
        assert r.json()['detail']['code'] == 'TRANSFER_SIGNATURE_INVALID'

    def test_unknown_package_maps_to_404(self, client):
        r = client.get('/internal/transfer/packages/ghost',
                       headers={'X-Transfer-Token': 'secret-ab'})
        assert r.status_code == 404
        assert r.json()['detail']['code'] == 'TRANSFER_PACKAGE_NOT_FOUND'

    def test_expired_maps_to_410(self, client, monkeypatch):
        handler = routes_module._command_handler
        handler.create_transfer(make_create_cmd())
        pkg = handler.record_repo.find_by_transfer_id('t-1')
        from datetime import datetime, timedelta, timezone
        pkg.created_at = datetime.now(timezone(timedelta(hours=8))) - timedelta(seconds=120)
        pkg.expires_at = pkg.created_at + timedelta(seconds=60)
        r = client.post(
            '/internal/transfer/chunks?transfer_id=t-1&chunk_index=0',
            content=b'12345678',
            headers={'X-Transfer-Token': 'secret-ab', 'X-Chunk-Checksum': 'x'},
        )
        assert r.status_code == 410
        assert r.json()['detail']['code'] == 'TRANSFER_PACKAGE_EXPIRED'

    def test_chunk_body_over_limit_rejected_before_read(self, client):
        # 审计 P7：先校验 Content-Length 再读 body，超大请求体不进内存、未认证也拒绝
        from transfer_agent.config.config import Config
        r = client.post(
            '/internal/transfer/chunks?transfer_id=t-1&chunk_index=0',
            content=b'x' * (Config.TRANSFER_CHUNK_SIZE + 1),
            headers={'X-Transfer-Token': '', 'X-Chunk-Checksum': 'x'},
        )
        assert r.status_code == 413
        assert r.json()['detail']['code'] == 'TRANSFER_CHUNK_SIZE_INVALID'
