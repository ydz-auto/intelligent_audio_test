# -*- coding: utf-8 -*-
"""INT-1962 回归：归档阈值硬编码不可关 → 归档开关配置化。

缺陷：``shared/utils/log_handler/_constants.py`` 把 ``LOG_ARCHIVE_THRESHOLD``
写死成 300000，没有任何 env 开关。主库 logs 恒超阈值，INT-1902 修好归档后
每次巡检都会真实调用 ``ArchiveLogs(dry_run=False)``，发版后无法让它停下来。

本文件固化四件事：

- env ``LOG_ARCHIVE_THRESHOLD`` 覆盖生效（阈值判定真的跟着 env 走）；
- 阈值 ``0``：``_check_and_archive()`` 直接返回，``get_log_count`` /
  ``archive_logs`` 零调用，且不留日志噪音；
- 负值同样禁用；
- 不设 env 时行为与改造前一致（缺省 300000、``total > threshold`` 才归档）。

不触主库、不触 :15000、不调 ``ArchiveLogs`` 真实链路（gRPC 全 fake）。
"""
import os
import tempfile

import pytest

# 共享配置在导入期校验必填环境变量；默认值用进程级临时文件库（本文件不触库，
# 仅满足导入校验），与同级 log handler 测试保持一致
os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int1962_threshold_') + '/threshold.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.infrastructure.config import (  # noqa: E402
    LOG_ARCHIVE_THRESHOLD_DEFAULT,
    get_log_archive_threshold,
)
from shared.utils.log_handler._archive_mixin import _ArchiveMixin  # noqa: E402


class _ArchiveHost(_ArchiveMixin):
    """只装配归档 mixin 的轻量宿主：不启 worker、不建队列、不起文件处理器。"""

    def __init__(self):
        self.clean_calls = 0

    def _clean_expired_archives(self):
        self.clean_calls += 1


@pytest.fixture()
def grpc_stub(monkeypatch):
    """fake gRPC 边界：get_log_count / archive_logs 全部本地承接。"""
    import shared.clients.grpc_clients as grpc_clients_mod

    state = {'total': 300001, 'count_calls': 0, 'archive_calls': 0}

    def _fake_get_log_count():
        state['count_calls'] += 1
        return {'total': state['total']}

    def _fake_archive_logs(days=30, dry_run=True):
        state['archive_calls'] += 1
        return {'groups': {}, 'remaining_count': 0}

    monkeypatch.setattr(grpc_clients_mod, 'get_log_count', _fake_get_log_count)
    monkeypatch.setattr(grpc_clients_mod, 'archive_logs', _fake_archive_logs)
    return state


@pytest.fixture()
def clean_env(monkeypatch):
    """清掉外部环境里可能存在的阈值设置，回到「不设 env」的部署默认。"""
    monkeypatch.delenv('LOG_ARCHIVE_THRESHOLD', raising=False)
    return monkeypatch


# ---------------------------------------------------------------- 配置读取

def test_default_threshold_without_env(clean_env):
    """不设 env：缺省 300000（与改造前写死的值一致）。"""
    assert LOG_ARCHIVE_THRESHOLD_DEFAULT == 300000
    assert get_log_archive_threshold() == 300000


def test_env_overrides_threshold(clean_env):
    """env 覆盖生效：正数、0、负数都按字面读出来。"""
    clean_env.setenv('LOG_ARCHIVE_THRESHOLD', '1000')
    assert get_log_archive_threshold() == 1000

    clean_env.setenv('LOG_ARCHIVE_THRESHOLD', '0')
    assert get_log_archive_threshold() == 0

    clean_env.setenv('LOG_ARCHIVE_THRESHOLD', '-5')
    assert get_log_archive_threshold() == -5


def test_invalid_or_empty_env_falls_back_to_default(clean_env):
    """空值 / 非整数：回落默认值，绝不让后台巡检线程因配置笔误抛异常。"""
    clean_env.setenv('LOG_ARCHIVE_THRESHOLD', '')
    assert get_log_archive_threshold() == LOG_ARCHIVE_THRESHOLD_DEFAULT

    clean_env.setenv('LOG_ARCHIVE_THRESHOLD', 'not-a-number')
    assert get_log_archive_threshold() == LOG_ARCHIVE_THRESHOLD_DEFAULT


# ---------------------------------------------------------------- 巡检行为

def test_threshold_zero_disables_archive_silently(grpc_stub, clean_env, capsys):
    """阈值 0：直接返回——不查计数、不上传、不删行、不打日志噪音。"""
    clean_env.setenv('LOG_ARCHIVE_THRESHOLD', '0')
    host = _ArchiveHost()
    host._check_and_archive()

    assert grpc_stub['count_calls'] == 0, '禁用归档时连 get_log_count 都不许调'
    assert grpc_stub['archive_calls'] == 0
    assert host.clean_calls == 0, '禁用归档时整条巡检直接返回'
    out, err = capsys.readouterr()
    assert out.strip() == '' and err.strip() == '', f'禁用后不得留日志噪音: {out}{err}'


def test_negative_threshold_disables_archive(grpc_stub, clean_env):
    """负值同样禁用（<= 0 语义）。"""
    clean_env.setenv('LOG_ARCHIVE_THRESHOLD', '-1')
    host = _ArchiveHost()
    host._check_and_archive()

    assert grpc_stub['count_calls'] == 0
    assert grpc_stub['archive_calls'] == 0


def test_custom_threshold_is_used_for_comparison(grpc_stub, clean_env, capsys):
    """env 阈值真的参与判定：total 介于两个阈值之间时，行为跟着 env 变。"""
    clean_env.setenv('LOG_ARCHIVE_THRESHOLD', '1000')
    grpc_stub['total'] = 800
    host = _ArchiveHost()
    host._check_and_archive()
    assert grpc_stub['archive_calls'] == 0, '低于 env 阈值不得归档'

    grpc_stub['total'] = 1500
    host._check_and_archive()
    assert grpc_stub['archive_calls'] == 1, '超过 env 阈值必须归档'
    out = capsys.readouterr().out
    assert 'exceeds threshold 1000' in out, out


def test_default_threshold_semantics_unchanged(grpc_stub, clean_env):
    """不设 env：300000 比较语义不变——等于阈值不归档，超过才归档。"""
    grpc_stub['total'] = 300000
    host = _ArchiveHost()
    host._check_and_archive()
    assert grpc_stub['archive_calls'] == 0

    grpc_stub['total'] = 300001
    host._check_and_archive()
    assert grpc_stub['archive_calls'] == 1
    assert host.clean_calls == 2, '未禁用归档时过期清理照常执行（与归档解耦）'
