# -*- coding: utf-8 -*-
"""INT-1902 回归：log_worker 归档巡检恒报 NameError。

缺陷：``_archive_old_logs`` 内调用 ``archive_logs(...)``，但该名字只在
``_check_and_archive`` 里局部导入，本方法作用域内不存在 → 每轮巡检必然
``NameError: name 'archive_logs' is not defined``；异常被外层 ``except``
吞成一行 ``ARCHIVE ERROR``，冷数据自动归档与过期归档清理从未执行。

本文件固化三件事：

- ``archive_logs`` 在 ``_archive_old_logs`` 作用域内可用（gRPC 全 fake，
  不连真实 task_service）；
- 归档与过期清理各自 ``try/except``：归档失败不得阻断清理；
- 阈值以内不触发归档。

不触主库、不触 :15000、不调 ``ArchiveLogs`` 真实链路。
"""
import os
import tempfile

import pytest

# 共享配置在导入期校验必填环境变量；默认值用进程级临时文件库（本文件不触库，
# 仅满足导入校验），与同级 log handler 测试保持一致
os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int1902_archive_') + '/archive.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.utils.log_handler._archive_mixin import _ArchiveMixin


class _ArchiveHost(_ArchiveMixin):
    """只装配归档 mixin 的轻量宿主：不启 worker、不建队列、不起文件处理器。"""

    def __init__(self):
        self.clean_calls = 0
        self.clean_raises = None

    def _clean_expired_archives(self):
        self.clean_calls += 1
        if self.clean_raises is not None:
            raise self.clean_raises


@pytest.fixture()
def grpc_stub(monkeypatch):
    """fake gRPC 边界：get_log_count / archive_logs 全部本地承接。"""
    import shared.clients.grpc_clients as grpc_clients_mod

    state = {'total': 300001, 'archive_calls': 0, 'archive_raises': None,
             'days': None, 'dry_run': None}

    def _fake_get_log_count():
        return {'total': state['total']}

    def _fake_archive_logs(days=30, dry_run=True):
        state['archive_calls'] += 1
        state['days'] = days
        state['dry_run'] = dry_run
        if state['archive_raises'] is not None:
            raise state['archive_raises']
        return {'groups': {}, 'remaining_count': 0}

    monkeypatch.setattr(grpc_clients_mod, 'get_log_count', _fake_get_log_count)
    monkeypatch.setattr(grpc_clients_mod, 'archive_logs', _fake_archive_logs)
    return state


def test_archive_logs_resolved_and_cleanup_runs(grpc_stub, capsys):
    """超过阈值：archive_logs 被调用 1 次、无 ARCHIVE ERROR、清理同轮执行。"""
    host = _ArchiveHost()
    host._check_and_archive()

    out = capsys.readouterr().out
    assert grpc_stub['archive_calls'] == 1, '超过阈值时必须真实调用 archive_logs'
    # 修复前这里必然是 NameError
    assert 'ARCHIVE ERROR' not in out, out
    assert "'archive_logs' is not defined" not in out, out
    assert host.clean_calls == 1, '归档巡检同轮必须执行过期归档清理'
    # 归档口径不变：热数据保留天数 + 真实执行（非 dry_run）
    assert grpc_stub['days'] == 7 and grpc_stub['dry_run'] is False


def test_archive_failure_does_not_block_cleanup(grpc_stub, capsys):
    """归档抛异常：打印 ARCHIVE ERROR，但过期清理仍被执行（解耦）。"""
    grpc_stub['archive_raises'] = RuntimeError('task_service unavailable')
    host = _ArchiveHost()
    host._check_and_archive()

    out = capsys.readouterr().out
    assert grpc_stub['archive_calls'] == 1
    assert 'ARCHIVE ERROR' in out
    assert 'task_service unavailable' in out
    assert host.clean_calls == 1, '归档失败不得阻断过期归档清理'


def test_below_threshold_skips_archive(grpc_stub):
    """低于阈值：不归档，但清理照常执行。"""
    grpc_stub['total'] = 1
    host = _ArchiveHost()
    host._check_and_archive()

    assert grpc_stub['archive_calls'] == 0
    assert host.clean_calls == 1


def test_cleanup_failure_reported_separately(grpc_stub, capsys):
    """清理自身失败：单独告警，不影响同轮已完成的归档。"""
    host = _ArchiveHost()
    host.clean_raises = OSError('oss unreachable')
    host._check_and_archive()

    out = capsys.readouterr().out
    assert grpc_stub['archive_calls'] == 1
    assert 'ARCHIVE ERROR' not in out, '清理失败不应误报为归档失败'
    assert 'ARCHIVE CLEANUP ERROR' in out
    assert 'oss unreachable' in out
