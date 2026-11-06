# -*- coding: utf-8 -*-
"""transfer_agent 存储适配器守卫测试（INT-28 审计 P2/P4）。

- delete_transit_file 严格 transit 域判定：解析 scheme 后 category 段全等比较，
  子串碰撞（local://case-results/transit_report.wav）不得绕过删除门槛
- merge_chunks 只落 transit 暂存、promote_file 移动到终桶：
  file_hash 校验通过前终桶不被触碰（先暂存 → 校验 → 提升 时序的存储侧保证）

本地降级模式（patch 掉 OSS 探测），不依赖真实 OSS / 网络。
"""
import hashlib
import os

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from shared.infrastructure.config import BaseConfig
from shared.infrastructure.storage import storage as shared_storage
from transfer_agent.infrastructure.storage.transfer_storage import TransferStorageAdapter


class _UnreachableOSS:
    """OSS 不可达替身：任何方法调用即抛错，驱动统一存储走本地降级分支。"""

    def __getattr__(self, name):
        def _fail(*args, **kwargs):
            raise RuntimeError('OSS unreachable (stub)')
        return _fail


@pytest.fixture
def local_storage(tmp_path, monkeypatch):
    """强制本地降级模式 + 隔离存储根目录。"""
    monkeypatch.setattr(shared_storage, '_use_oss', lambda: False)
    monkeypatch.setattr(shared_storage, '_oss_client', _UnreachableOSS())
    monkeypatch.setattr(shared_storage, '_oss_checked', True)
    monkeypatch.setattr(shared_storage, '_oss_ok', False)
    monkeypatch.setattr(BaseConfig, 'STORAGE_LOCAL_ROOT', str(tmp_path / 'storage_root'))
    return TransferStorageAdapter()


class TestDeleteTransitGate:
    """P4：删除门槛 — 仅 scheme 解析后 category 段全等 transit 才放行。"""

    def test_transit_paths_allowed(self, local_storage, monkeypatch):
        deleted = []
        monkeypatch.setattr(shared_storage, 'delete', lambda p: deleted.append(p))
        local_storage.delete_transit_file('oss://transit/t-1/merged.pkg')
        local_storage.delete_transit_file('local://transit/t-1/chunks/000000.chunk')
        assert sorted(deleted) == [
            'local://transit/t-1/chunks/000000.chunk',
            'oss://transit/t-1/merged.pkg',
        ]

    def test_substring_trap_rejected(self, local_storage, monkeypatch):
        # key 含 "transit" 子串但 category 是持久桶 → 拒绝（子串匹配曾放行）
        deleted = []
        monkeypatch.setattr(shared_storage, 'delete', lambda p: deleted.append(p))
        for path in (
            'local://case-results/transit_report.wav',
            'oss://audios/transit/x.bin',
            'oss://transit-backup/x.bin',
            'transit/no-scheme.bin',
        ):
            local_storage.delete_transit_file(path)
        assert deleted == []

    def test_empty_path_noop(self, local_storage, monkeypatch):
        deleted = []
        monkeypatch.setattr(shared_storage, 'delete', lambda p: deleted.append(p))
        local_storage.delete_transit_file('')
        assert deleted == []


class TestStageThenPromote:
    """P2：合并只落 transit 暂存，校验通过后经 promote 移动到终桶。"""

    def test_merge_stages_into_transit_not_final(self, local_storage):
        payload = b'12345678' * 4  # 两片
        local_storage.save_chunk('t-1', 0, payload[:16])
        local_storage.save_chunk('t-1', 1, payload[16:])
        staged_path, sha = local_storage.merge_chunks('t-1', 2)
        assert staged_path.startswith('oss://transit/t-1/') or \
            staged_path.startswith('local://transit/t-1/')
        assert staged_path.endswith('merged.pkg')
        assert sha == hashlib.sha256(payload).hexdigest()
        assert shared_storage.exists(staged_path)

    def test_promote_moves_staged_to_final(self, local_storage):
        payload = b'abcdef' * 8
        local_storage.save_chunk('t-1', 0, payload)
        staged_path, _ = local_storage.merge_chunks('t-1', 1)
        final_path = local_storage.promote_file(staged_path, 'audios', 'task_1/a.wav')
        assert final_path in ('oss://audios/task_1/a.wav', 'local://audios/task_1/a.wav')
        assert shared_storage.exists(final_path)
        assert not shared_storage.exists(staged_path)          # 移动语义：暂存回收
        assert shared_storage.load_bytes(final_path) == payload

    def test_failed_validation_leaves_final_untouched(self, local_storage):
        # 完整时序演练：暂存存在时终桶同 key 原对象保持原样（失败路径不触碰终桶）
        shared_storage.save_bytes(
            b'ORIGINAL', 'audios', 'task_1/a.wav',
        )
        local_storage.save_chunk('t-2', 0, b'corrupted')
        staged_path, _ = local_storage.merge_chunks('t-2', 1)
        # 模拟 handler 验 hash 失败：仅回收暂存
        local_storage.delete_transit_file(staged_path)
        assert shared_storage.load_bytes('oss://audios/task_1/a.wav') == b'ORIGINAL'
        assert not shared_storage.exists(staged_path)

    def test_chunk_key_cannot_escape_storage_root(self, local_storage, tmp_path):
        # transfer_id 白名单（实体层强制）之外，分片 key 由服务端构造，不带穿越形态
        local_storage.save_chunk('t-3', 0, b'data')
        path = shared_storage.build_path('transit', 't-3/chunks/000000.chunk')
        assert shared_storage.exists(path)
        root = str(tmp_path / 'storage_root')
        for cur, _dirs, files in os.walk(root):
            assert '..' not in cur
            for f in files:
                assert '..' not in f
