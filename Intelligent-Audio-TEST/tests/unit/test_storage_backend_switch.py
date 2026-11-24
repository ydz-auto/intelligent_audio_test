# -*- coding: utf-8 -*-
"""存储后端可配置切换单测（COS / RustFS / 本地磁盘）。

覆盖：
  1. STORAGE_BACKEND 归一化与寻址风格推导（cos→virtual，rustfs/minio→path）
  2. OSSClient 把寻址风格落到 botocore Config（不再依赖 aws-config 文件）
  3. STORAGE_BACKEND=local 时全链路只落本地磁盘，不探测/不实例化 S3 客户端
"""
import os
from unittest.mock import MagicMock

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.infrastructure.config import (
    BaseConfig,
    normalize_storage_backend,
    resolve_addressing_style,
)
from shared.infrastructure.storage import Storage


def test_normalize_backend_aliases():
    assert normalize_storage_backend(None) == 'auto'
    assert normalize_storage_backend(' COS ') == 'cos'
    assert normalize_storage_backend('minio') == 'rustfs'
    assert normalize_storage_backend('disk') == 'local'
    assert normalize_storage_backend('unknown') == 'auto'


def test_addressing_style_by_backend():
    # COS 的 S3 接口只接受 virtual-hosted；RustFS/MinIO 用 path
    assert resolve_addressing_style('cos', '') == 'virtual'
    assert resolve_addressing_style('rustfs', '') == 'path'
    assert resolve_addressing_style('auto', '') == ''
    # 显式配置优先
    assert resolve_addressing_style('rustfs', 'virtual') == 'virtual'
    assert resolve_addressing_style('cos', 'path') == 'path'


def test_oss_client_applies_addressing_style(monkeypatch):
    from shared.clients.oss_client import OSSClient

    captured = []

    def fake_client(*_args, **kwargs):
        captured.append(kwargs)
        return MagicMock()

    monkeypatch.setattr('shared.clients.oss_client.boto3.client', fake_client)
    monkeypatch.setattr(OSSClient, '_ensure_buckets_exist', lambda self: None)
    monkeypatch.setattr(BaseConfig, 'STORAGE_BACKEND', 'cos')
    monkeypatch.setattr(BaseConfig, 'OSS_ADDRESSING_STYLE', 'virtual')
    monkeypatch.setattr(BaseConfig, 'OSS_ENDPOINT',
                        'https://cos.ap-shanghai.myqcloud.com')
    OSSClient._instance = None
    try:
        client = OSSClient()
        client._ensure_init()
        assert captured, '未创建 boto3 client'
        styles = [c['config'].s3.get('addressing_style') for c in captured]
        assert styles and all(s == 'virtual' for s in styles)
    finally:
        OSSClient._instance = None


def test_local_backend_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(BaseConfig, 'STORAGE_BACKEND', 'local')
    monkeypatch.setattr(BaseConfig, 'STORAGE_FALLBACK_ENABLED', False)
    monkeypatch.setattr(BaseConfig, 'STORAGE_LOCAL_ROOT',
                        str(tmp_path / 'storage_local'))
    monkeypatch.setattr(BaseConfig, 'LOCAL_STORAGE_ROOT',
                        str(tmp_path / 'cache'))
    # local 后端不得探测对象存储
    monkeypatch.setattr(
        Storage, '_oss_available',
        lambda self: (_ for _ in ()).throw(AssertionError('local 后端不应探测 OSS')))

    st = Storage()
    path = st.save_bytes(b'hello', 'temp', 'backend-check.txt', allow_fallback=False)
    assert path == 'local://temp/backend-check.txt'
    assert st.exists(path) is True
    assert st.load_bytes(path, allow_fallback=False) == b'hello'
    assert st.get_url(path) is None
    assert st.list_objects('temp') == ['backend-check.txt']
    st.delete(path)
    assert st.exists(path) is False
