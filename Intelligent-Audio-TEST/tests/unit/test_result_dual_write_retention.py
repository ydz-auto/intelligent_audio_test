# -*- coding: utf-8 -*-
"""执行产物双写 / 冷存保留 / 执行器冷读接口的最小回归测试（2026-11-28）。"""
import os
import time

import pytest

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.infrastructure.config import BaseConfig
from shared.infrastructure.storage import storage


@pytest.fixture
def cold_env(tmp_path, monkeypatch):
    cold_root = tmp_path / 'cold'
    monkeypatch.setattr(BaseConfig, 'STORAGE_BACKEND', 'local', raising=False)
    monkeypatch.setattr(BaseConfig, 'STORAGE_LOCAL_ROOT', str(tmp_path / 'local'), raising=False)
    monkeypatch.setattr(BaseConfig, 'RESULT_DUAL_WRITE_ENABLED', True, raising=False)
    monkeypatch.setattr(
        BaseConfig, 'RESULT_DUAL_WRITE_CATEGORIES', 'case_result,ref_params', raising=False)
    monkeypatch.setenv('RESULT_LOCAL_ROOT', str(cold_root))
    return tmp_path, cold_root


def test_dual_write_cold_copy_and_local_read(cold_env):
    _root, cold_root = cold_env
    path = storage.save_bytes(b'payload', 'case_result', 't1/c1/d1/a.bin')
    cold_file = cold_root / 'case_result' / 't1/c1/d1/a.bin'
    assert path == 'local://case_result/t1/c1/d1/a.bin'
    assert cold_file.is_file()
    assert storage.load_bytes(path) == b'payload'


def test_local_retention_365_days(cold_env, monkeypatch):
    _root, cold_root = cold_env
    from shared.infrastructure import result_retention

    monkeypatch.setattr(BaseConfig, 'RESULT_LOCAL_RETENTION_DAYS', 365, raising=False)
    old_file = cold_root / 'case_result' / 't1/c1/d1/old.bin'
    new_file = cold_root / 'case_result' / 't1/c1/d1/new.bin'
    old_file.parent.mkdir(parents=True, exist_ok=True)
    old_file.write_bytes(b'old')
    new_file.write_bytes(b'new')
    old_ts = time.time() - 400 * 86400
    os.utime(old_file, (old_ts, old_ts))

    stats = result_retention.sweep_local_results()

    assert stats['deleted'] == 1
    assert not old_file.exists()
    assert new_file.exists()


def test_artifact_servicer_list_read_and_traversal(cold_env):
    _root, cold_root = cold_env
    from shared.proto import artifact_service_pb2 as pb
    from device_service.interfaces.grpc.artifact_servicer import ArtifactServiceServicer

    target = cold_root / 'case_result' / 't1/c1/d1/a.bin'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b'abc')

    servicer = ArtifactServiceServicer()
    listed = servicer.ListArtifacts(
        pb.ListArtifactsRequest(category='case_result', prefix='t1/c1'))
    assert [item.key for item in listed.items] == ['t1/c1/d1/a.bin']

    chunks = b''.join(
        chunk.data for chunk in
        servicer.ReadArtifact(pb.ReadArtifactRequest(
            category='case_result', key='t1/c1/d1/a.bin')))
    assert chunks == b'abc'

    with pytest.raises(ValueError):
        from device_service.interfaces.grpc.artifact_servicer import _resolve_path
        _resolve_path('case_result', '../etc/passwd')


def test_reference_snapshot_key_from_result_path():
    from shared.utils.result_data_store import _reference_key_from_result_path

    assert _reference_key_from_result_path(
        'oss://case_result/t1/c1/d1/result_data.json'
    ) == 't1/c1/d1/reference_params.json'
    assert _reference_key_from_result_path('local://case_result/t1/c1/d1/result_data.json') \
        == 't1/c1/d1/reference_params.json'
    assert _reference_key_from_result_path('D:/legacy/result_data.json') == ''
