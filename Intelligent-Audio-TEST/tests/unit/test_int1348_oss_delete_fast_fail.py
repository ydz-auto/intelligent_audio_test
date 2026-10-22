# -*- coding: utf-8 -*-
"""OSS 管理类操作短超时单测（INT-1348）。

DELETE /audios/{id} 偶发 60s 挂起 + 网关 DEADLINE_EXCEEDED 400 的根因：
OSSClient.delete_object 复用主客户端 read_timeout=60 × 3 次重试，OSS 不可达/
响应慢时把调用悬挂到网关 gRPC 60s 截止之后（DB 记录已删但响应超时）。

本测试验证：
1. localhost endpoint 统一改写 127.0.0.1（避免 ::1/IPv4 解析歧义悬挂）；
2. 管理类短超时客户端（admin_client）read_timeout/connect_timeout/重试收紧；
3. delete_object 走 admin_client，对「accept 但不应答」的黑盒服务端数秒内快速失败；
4. storage.delete 在 OSS 删除失败时仍快速返回并清理本地降级副本（上层 DB 删除不受影响）。
"""
import os
import socket
import threading
import time
from unittest.mock import MagicMock

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

import shared.infrastructure.storage as storage_mod
from shared.clients.oss_client import OSSClient, _normalize_endpoint
from shared.infrastructure.config import BaseConfig


class _BlackHoleServer:
    """accept 连接但永不响应 —— 模拟 OSS 端点响应慢 / 假死。"""

    def __init__(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(('127.0.0.1', 0))
        self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        self._stop = False
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def _accept_loop(self):
        while not self._stop:
            try:
                conn, _ = self.sock.accept()
                # 保持连接不读不写不应答，模拟响应假死；连接由 daemon 线程持有
                conn.settimeout(60)
            except OSError:
                return

    def close(self):
        self._stop = True
        try:
            self.sock.close()
        except OSError:
            pass


@pytest.fixture(autouse=True)
def _reset_oss_singleton():
    OSSClient._instance = None
    yield
    OSSClient._instance = None


class TestNormalizeEndpoint:
    def test_localhost_rewritten_to_ipv4(self):
        assert _normalize_endpoint('http://localhost:9000') == 'http://127.0.0.1:9000'
        assert _normalize_endpoint('https://localhost:9000') == 'https://127.0.0.1:9000'
        assert _normalize_endpoint('http://localhost') == 'http://127.0.0.1'

    def test_non_localhost_unchanged(self):
        assert _normalize_endpoint('http://127.0.0.1:9000') == 'http://127.0.0.1:9000'
        assert _normalize_endpoint('http://rustfs:9000') == 'http://rustfs:9000'
        assert _normalize_endpoint('http://s3.amazonaws.com') == 'http://s3.amazonaws.com'


class TestAdminClient:
    def test_admin_client_short_timeout_and_used_by_delete(self, monkeypatch):
        client_configs = []

        def fake_boto3_client(*args, **kwargs):
            client_configs.append(kwargs)
            return MagicMock()

        monkeypatch.setattr('boto3.client', fake_boto3_client)
        monkeypatch.setattr(BaseConfig, 'OSS_ADMIN_READ_TIMEOUT_SECONDS', 5)
        monkeypatch.setattr(BaseConfig, 'OSS_ADMIN_CONNECT_TIMEOUT_SECONDS', 3)
        monkeypatch.setattr(BaseConfig, 'OSS_ADMIN_MAX_ATTEMPTS', 2)

        client = OSSClient()
        client._ensure_init()

        assert len(client_configs) == 2
        main_cfg = client_configs[0]['config']
        admin_cfg = client_configs[1]['config']
        # 主客户端保持长超时（上传/下载大文件需要），管理客户端收紧
        assert main_cfg.read_timeout == 60
        assert main_cfg.retries == {'max_attempts': 3, 'mode': 'standard'}
        assert admin_cfg.read_timeout == 5
        assert admin_cfg.retries == {'max_attempts': 2, 'mode': 'standard'}
        assert admin_cfg.connect_timeout == 3

        # delete_object 走 admin_client，不碰主客户端
        client.delete_object('audios', 'k')
        client._admin_client.delete_object.assert_called_once_with(
            Bucket='audios', Key='k')
        client._client.delete_object.assert_not_called()

    def test_delete_object_fast_fails_on_unresponsive_oss(self, monkeypatch):
        server = _BlackHoleServer()
        try:
            monkeypatch.setattr(
                BaseConfig, 'OSS_ENDPOINT', f'http://127.0.0.1:{server.port}')
            # 收紧超时让测试快速完成：read=1s × max_attempts=1
            monkeypatch.setattr(BaseConfig, 'OSS_ADMIN_READ_TIMEOUT_SECONDS', 1)
            monkeypatch.setattr(BaseConfig, 'OSS_ADMIN_CONNECT_TIMEOUT_SECONDS', 1)
            monkeypatch.setattr(BaseConfig, 'OSS_ADMIN_MAX_ATTEMPTS', 1)
            monkeypatch.setattr(OSSClient, '_ensure_buckets_exist',
                                lambda self: None)

            start = time.monotonic()
            with pytest.raises(Exception):
                OSSClient().delete_object('audios', 'test_key')
            elapsed = time.monotonic() - start
            # 快速失败：绝不能像主客户端那样 60s×重试悬挂
            assert elapsed < 15, f'delete_object 未快速失败，耗时 {elapsed:.1f}s'
        finally:
            server.close()


class TestStorageDeleteFastFail:
    def test_delete_returns_quickly_and_cleans_local_copy(self, tmp_path,
                                                         monkeypatch):
        class _FastFailOSS:
            def delete_object(self, category, key):
                raise OSError('OSS unreachable')

        monkeypatch.setattr(storage_mod.storage, '_oss_client', _FastFailOSS())
        monkeypatch.setattr(BaseConfig, 'STORAGE_LOCAL_ROOT', str(tmp_path))

        local = tmp_path / 'audios' / 'direct' / 'test' / 'x.wav'
        local.parent.mkdir(parents=True, exist_ok=True)
        local.write_bytes(b'data')

        start = time.monotonic()
        storage_mod.storage.delete('oss://audios/direct/test/x.wav')
        elapsed = time.monotonic() - start

        assert elapsed < 5
        # OSS 删除失败不影响本地降级副本清理，storage.delete 不向上抛异常
        assert not local.exists()
