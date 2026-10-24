# -*- coding: utf-8 -*-
"""预签名 URL 公共 endpoint 单测（INT-1710 验收 P1-5，实现卡 INT-1719）。

docker 真实栈里 compose 各服务的 OSS_ENDPOINT 是服务名 http://rustfs:9000，
它被签进预签名 URL 后交给宿主浏览器 → net::ERR_NAME_NOT_RESOLVED
（用例管理 → 用例行「预览音频」提示「音频播放失败」）。宿主侧 audio_service
因为 endpoint 本身就是 127.0.0.1:9000 才恰好可用——差别只在生成方。

修法：新增 OSS_PUBLIC_ENDPOINT（对浏览器/第三方暴露的地址）与独立签名客户端，
三个预签名方法改用它签名；其余读写仍走内部 endpoint（容器内 S3 流量不绕宿主 NAT）。
不用「生成后替换 URL 前缀」的补丁：SigV4 下 Host 参与签名，换 host 会 403。

基线（无 OSS_PUBLIC_ENDPOINT 支持）上本组用例失败：三个方法签出的 host 恒为
rustfs:9000；修复后通过。
"""
import os
import subprocess
import sys
from urllib.parse import urlsplit
from unittest.mock import MagicMock

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.clients.oss_client import OSSClient
from shared.infrastructure.config import BaseConfig

INTERNAL_ENDPOINT = 'http://rustfs:9000'
PUBLIC_ENDPOINT = 'http://127.0.0.1:9000'


def _netloc(url: str) -> str:
    return urlsplit(url).netloc


@pytest.fixture(autouse=True)
def _isolated_oss_client(monkeypatch):
    """单例 + 自动建桶隔离：只验证 endpoint 选择与签名结果，不连真实 OSS。"""
    OSSClient._instance = None
    monkeypatch.setattr(OSSClient, '_ensure_buckets_exist', lambda self: None)
    yield
    OSSClient._instance = None


def _make_client(monkeypatch, internal: str, public: str) -> OSSClient:
    monkeypatch.setattr(BaseConfig, 'OSS_ENDPOINT', internal)
    # raising=False：基线代码没有该字段，这样失败落在 host 断言上（可读的红），
    # 而不是 setattr 的 AttributeError；修复后字段存在，语义不变。
    monkeypatch.setattr(BaseConfig, 'OSS_PUBLIC_ENDPOINT', public, raising=False)
    client = OSSClient()
    client._ensure_init()
    return client


def _presign_all_three(client: OSSClient):
    return (
        client.get_presigned_url('audios', 'direct/url_src_A_6.wav'),
        client.get_upload_presigned_url('audios', 'direct/up.wav'),
        client.get_part_upload_presigned_url('audios', 'direct/part.wav', 'upload-id-1', 1),
    )


class TestPresignUsesPublicEndpoint:
    def test_all_three_presign_methods_use_public_host(self, monkeypatch):
        client = _make_client(monkeypatch, INTERNAL_ENDPOINT, PUBLIC_ENDPOINT)

        get_url, put_url, part_url = _presign_all_three(client)

        assert _netloc(get_url) == '127.0.0.1:9000'
        assert _netloc(put_url) == '127.0.0.1:9000'
        assert _netloc(part_url) == '127.0.0.1:9000'
        # 关键路径没被丢掉：仍是同一 bucket/对象路径
        assert 'url_src_A_6.wav' in get_url
        assert 'direct/up.wav' in put_url
        assert 'part.wav' in part_url
        # 独立签名客户端，不能与内部主客户端混用
        assert client._presign_client is not client._client

    def test_empty_public_endpoint_falls_back_to_internal(self, monkeypatch):
        """宿主/单机部署：OSS_PUBLIC_ENDPOINT 空串 → 回落 OSS_ENDPOINT，零行为变化。"""
        client = _make_client(monkeypatch, INTERNAL_ENDPOINT, '')

        get_url, put_url, part_url = _presign_all_three(client)

        assert _netloc(get_url) == 'rustfs:9000'
        assert _netloc(put_url) == 'rustfs:9000'
        assert _netloc(part_url) == 'rustfs:9000'
        # 回落时不额外建客户端，直接复用主客户端
        assert client._presign_client is client._client

    def test_public_endpoint_default_is_empty_when_unset(self):
        """进程内「未设」= 读到的空串：干净环境里 import 配置得到 ''。

        BaseConfig 的字段在 import 时固化，所以「未设」只能在子进程里验证。
        """
        env = {
            k: v for k, v in os.environ.items()
            if k not in ('OSS_PUBLIC_ENDPOINT',)
        }
        env.setdefault('DATABASE_URL', 'sqlite://')
        env.setdefault('OSS_ACCESS_KEY', 'test')
        env.setdefault('OSS_SECRET_KEY', 'test')
        code = ('from shared.infrastructure.config import BaseConfig; '
                'print(repr(BaseConfig.OSS_PUBLIC_ENDPOINT))')
        out = subprocess.run(
            [sys.executable, '-c', code], env=env, cwd=os.getcwd(),
            capture_output=True, text=True, timeout=120,
        )
        assert out.returncode == 0, out.stderr
        assert out.stdout.strip() == repr('')

    def test_localhost_public_endpoint_normalized_to_ipv4(self, monkeypatch):
        """公共 endpoint 写 localhost 时仍按 _normalize_endpoint 归一为 127.0.0.1。"""
        client = _make_client(monkeypatch, INTERNAL_ENDPOINT, 'http://localhost:9000')

        get_url, put_url, part_url = _presign_all_three(client)

        assert _netloc(get_url) == '127.0.0.1:9000'
        assert _netloc(put_url) == '127.0.0.1:9000'
        assert _netloc(part_url) == '127.0.0.1:9000'

    def test_public_equal_internal_reuses_main_client(self, monkeypatch):
        """两者一致（含仅尾斜杠差异）时不重复建客户端。"""
        client = _make_client(monkeypatch, PUBLIC_ENDPOINT, PUBLIC_ENDPOINT + '/')
        assert client._presign_client is client._client


class TestInternalTrafficStaysInternal:
    def test_read_write_and_admin_use_internal_endpoints_only(self, monkeypatch):
        client_configs = []

        def fake_boto3_client(*args, **kwargs):
            client_configs.append(kwargs)
            return MagicMock()

        monkeypatch.setattr('boto3.client', fake_boto3_client)
        client = _make_client(monkeypatch, INTERNAL_ENDPOINT, PUBLIC_ENDPOINT)

        # 三个客户端的 endpoint 选择：主客户端 + 预签名客户端 + 管理短超时客户端
        assert [c['endpoint_url'] for c in client_configs] == [
            INTERNAL_ENDPOINT, PUBLIC_ENDPOINT, INTERNAL_ENDPOINT]

        # 读写 / 管理操作不碰公共 endpoint（容器内流量不绕宿主 NAT）
        client.upload_bytes(b'data', 'audios', 'direct/x.wav')
        client.download_bytes('audios', 'direct/x.wav')
        client.exists('audios', 'direct/x.wav')
        client.delete_object('audios', 'direct/x.wav')

        main_client = client._client
        admin_client = client._admin_client
        presign_client = client._presign_client

        assert main_client.upload_fileobj.call_count == 1
        assert main_client.get_object.call_count == 1
        assert admin_client.head_object.call_count == 1
        assert admin_client.delete_object.call_count == 1

        for method in ('upload_fileobj', 'get_object', 'head_object', 'delete_object'):
            getattr(presign_client, method).assert_not_called()
        assert presign_client.generate_presigned_url.call_count == 0

    def test_presign_never_touches_main_or_admin_client(self, monkeypatch):
        client_configs = []

        def fake_boto3_client(*args, **kwargs):
            client_configs.append(kwargs)
            return MagicMock()

        monkeypatch.setattr('boto3.client', fake_boto3_client)
        client = _make_client(monkeypatch, INTERNAL_ENDPOINT, PUBLIC_ENDPOINT)

        _presign_all_three(client)

        assert client._presign_client.generate_presigned_url.call_count == 3
        assert client._client.generate_presigned_url.call_count == 0
        assert client._admin_client.generate_presigned_url.call_count == 0
        # 初始化 3 个客户端后不应再多建
        assert len(client_configs) == 3
