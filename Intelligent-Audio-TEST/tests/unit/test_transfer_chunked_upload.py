# -*- coding: utf-8 -*-
"""transfer_agent 发送侧编排与 ACL 出站客户端单元测试（INT-28）。

- ChunkedUploadService：打包(sha256)→create→分片跳过已收(断点续传)→重试(指数退避)→complete
- RemoteTransferClient：HTTP 响应/错误码到领域错误的转译（防腐层）

不依赖真实网络：客户端以替身注入 / requests.Response 构造。
"""
import hashlib
import os

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from transfer_agent.application.services.chunked_upload_service import (
    ChunkedUploadService,
)
from transfer_agent.domain.errors import (
    PackageExpiredError,
    SignatureInvalidError,
    TransferError,
)
from transfer_agent.domain.services.signature_service import SignatureService
from transfer_agent.infrastructure.acl.remote_transfer_client import RemoteTransferClient

TOKENS = {'A_B': 'secret-ab'}


class FakeRemoteClient:
    """远端 transfer_agent 替身：记录调用序列，模拟已收分片与故障注入。"""

    def __init__(self):
        self.created = None
        self.chunks = {}          # index -> checksum
        self.completed = False
        self.fail_indexes = {}    # index -> 失败次数（之后成功）
        self.calls = []

    def create_transfer(self, fields):
        self.calls.append('create')
        self.created = dict(fields)
        return {'transfer_id': fields['transfer_id'], 'status': 'CREATED'}

    def get_transfer_status(self, transfer_id):
        self.calls.append('status')
        return {'transfer_id': transfer_id, 'received_chunks': sorted(self.chunks)}

    def upload_chunk(self, transfer_id, chunk_index, data, checksum):
        self.calls.append(f'chunk:{chunk_index}')
        if chunk_index in self.fail_indexes and self.fail_indexes[chunk_index] > 0:
            self.fail_indexes[chunk_index] -= 1
            raise TransferError('模拟瞬时故障')
        self.chunks[chunk_index] = checksum
        return {'transfer_id': transfer_id, 'received_chunks': sorted(self.chunks)}

    def complete_transfer(self, transfer_id):
        self.calls.append('complete')
        self.completed = True
        return {'transfer_id': transfer_id, 'status': 'COMPLETED'}


@pytest.fixture
def payload_file(tmp_path):
    payload = os.urandom(10 * 1024)  # 10KB
    path = tmp_path / 'result.wav'
    path.write_bytes(payload)
    return str(path), payload


def make_service(client, **overrides):
    return ChunkedUploadService(
        client=client,
        signature_service=SignatureService(TOKENS),
        chunk_size=4 * 1024,
        backoff_seconds=0.01,  # 测试加速
        **overrides,
    )


class TestChunkedUploadService:
    def test_send_file_full_chain(self, payload_file):
        path, payload = payload_file
        client = FakeRemoteClient()
        result = make_service(client).send_file(
            local_path=path, pkg_type='EVAL_REQUEST', src_zone='A', dst_zone='B',
            category='case-result', key='task_1/case_2/dev_3/result.wav',
            meta={'task_id': 'task_1'}, ttl_seconds=1800,
        )
        assert client.completed
        assert client.created['file_hash'] == 'sha256:' + hashlib.sha256(payload).hexdigest()
        assert client.created['file_size'] == len(payload)
        assert client.created['meta'] == {'task_id': 'task_1'}
        assert len(client.chunks) == 3  # 10KB / 4KB → 3 片
        assert result['status'] == 'COMPLETED'
        # 调用顺序：create → status → chunks → complete
        assert client.calls[0] == 'create' and client.calls[1] == 'status'
        assert client.calls[-1] == 'complete'
        # create 携带可验签的签名
        assert len(client.created['signature']) == 64

    def test_resume_skips_received_chunks(self, payload_file):
        path, payload = payload_file
        client = FakeRemoteClient()
        # 预置远端已收第 0 片（断点续传场景）
        client.chunks[0] = hashlib.sha256(payload[:4 * 1024]).hexdigest()
        svc = make_service(client)
        svc.send_file(
            local_path=path, pkg_type='DATA_SYNC', src_zone='A', dst_zone='B',
            category='case-result', key='task_1/data.bin',
        )
        chunk_calls = [c for c in client.calls if c.startswith('chunk:')]
        assert 'chunk:0' not in chunk_calls          # 已收分片跳过
        assert 'chunk:1' in chunk_calls and 'chunk:2' in chunk_calls

    def test_retry_with_backoff_then_success(self, payload_file):
        path, payload = payload_file
        client = FakeRemoteClient()
        client.fail_indexes[1] = 2                   # 第 1 片前两次失败
        svc = make_service(client)
        svc.send_file(
            local_path=path, pkg_type='DATA_SYNC', src_zone='A', dst_zone='B',
            category='case-result', key='task_1/data.bin',
        )
        assert client.completed                      # 重试后最终成功
        assert [c for c in client.calls if c == 'chunk:1'].count('chunk:1') == 3

    def test_retry_exhausted_raises(self, payload_file):
        path, payload = payload_file
        client = FakeRemoteClient()
        client.fail_indexes[1] = 99                  # 始终失败
        svc = make_service(client)
        with pytest.raises(TransferError):
            svc.send_file(
                local_path=path, pkg_type='DATA_SYNC', src_zone='A', dst_zone='B',
                category='case-result', key='task_1/data.bin',
            )
        assert not client.completed

    def test_missing_route_token_rejected(self, payload_file):
        path, _ = payload_file
        svc = ChunkedUploadService(
            client=FakeRemoteClient(),
            signature_service=SignatureService({}),  # 未配置任何 token
        )
        from transfer_agent.domain.errors import AccessTokenInvalidError
        with pytest.raises(AccessTokenInvalidError):
            svc.send_file(
                local_path=path, pkg_type='DATA_SYNC', src_zone='A', dst_zone='B',
                category='case-result', key='task_1/data.bin',
            )


class TestRemoteTransferClientTranslation:
    """ACL 防腐层：远端 HTTP 响应 → 领域错误转译。"""

    @staticmethod
    def _response(status_code=200, payload=None):
        import json as _json
        from types import SimpleNamespace
        return SimpleNamespace(
            status_code=status_code,
            text=_json.dumps(payload or {}),
            json=lambda: payload or {},
        )

    def test_success_returns_data(self):
        client = RemoteTransferClient('http://remote', token='t')
        client._session = _FakeSession(self._response(200, {'success': True, 'data': {'a': 1}}))
        assert client.get_transfer_status('x') == {'a': 1}

    def test_error_code_translated_to_domain_error(self):
        client = RemoteTransferClient('http://remote', token='t')
        client._session = _FakeSession(self._response(410, {
            'success': False,
            'detail': {'code': 'TRANSFER_PACKAGE_EXPIRED', 'message': '超时'},
        }))
        with pytest.raises(PackageExpiredError):
            client.get_transfer_status('x')

    def test_signature_error_translated(self):
        client = RemoteTransferClient('http://remote', token='t')
        client._session = _FakeSession(self._response(401, {
            'success': False,
            'detail': {'code': 'TRANSFER_SIGNATURE_INVALID', 'message': '验签失败'},
        }))
        with pytest.raises(SignatureInvalidError):
            client.create_transfer({})

    def test_unknown_error_generic(self):
        client = RemoteTransferClient('http://remote', token='t')
        client._session = _FakeSession(self._response(500, {'success': False}))
        with pytest.raises(TransferError):
            client.get_transfer_status('x')


class _FakeSession:
    def __init__(self, response):
        self._response = response

    def request(self, method, url, timeout=None, **kwargs):
        return self._response
