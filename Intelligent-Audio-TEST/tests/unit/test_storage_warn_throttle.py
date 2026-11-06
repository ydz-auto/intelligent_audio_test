# -*- coding: utf-8 -*-
"""统一存储 OSS 失败告警限频单测（INT-84）。

OSS 异常期间 save/load 每次访问都会失败告警 —— 同操作原因 5 分钟窗口内
最多 1 条 WARNING，其余降级 DEBUG；不同原因不互相抑制，窗口过期重新告警。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import time

import pytest

import shared.infrastructure.storage as storage_mod


@pytest.fixture(autouse=True)
def _clean_warn_state():
    storage_mod._oss_warn_state.clear()
    yield
    storage_mod._oss_warn_state.clear()


@pytest.fixture
def sink(monkeypatch):
    calls = []
    monkeypatch.setattr(storage_mod, 'log_not_emit',
                        lambda level, module, msg, **kw: calls.append((level, msg)))
    return calls


class TestOssWarnThrottle:
    def test_same_reason_only_one_warning_in_window(self, sink):
        for _ in range(10):
            storage_mod._warn_oss_throttled(
                'load_bytes OSS failed, try local: OSS unreachable', category='audios')
        warnings = [c for c in sink if c[0] == 'WARNING']
        debugs = [c for c in sink if c[0] == 'DEBUG']
        assert len(warnings) == 1
        assert len(debugs) == 9

    def test_different_reason_not_suppressed(self, sink):
        storage_mod._warn_oss_throttled(
            'load_bytes OSS failed, try local: err-a', category='audios')
        storage_mod._warn_oss_throttled(
            'save_bytes OSS failed, fallback to local: err-a', category='audios')
        warnings = [c for c in sink if c[0] == 'WARNING']
        assert len(warnings) == 2

    def test_window_expiry_logs_new_warning(self, sink):
        storage_mod._warn_oss_throttled(
            'load_bytes OSS failed, try local: err-a', category='audios')
        reason = 'load_bytes OSS failed, try local'
        storage_mod._oss_warn_state[reason] = time.monotonic() - 301
        storage_mod._warn_oss_throttled(
            'load_bytes OSS failed, try local: err-a', category='audios')
        warnings = [c for c in sink if c[0] == 'WARNING']
        assert len(warnings) == 2
