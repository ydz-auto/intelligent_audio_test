# -*- coding: utf-8 -*-
"""INT-2456 T2 强隔离运行时可见性探测（拍板#2 / 方案 07 §7）。

结论必须可答：缺 runsc/firecracker 时报 unavailable，且 T2 请求落
T2_RUNTIME_UNAVAILABLE（见 tests/agent_sandbox/test_sandbox_contract.py），
不得静默降级 T1。
"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from agent_service.infrastructure.sandbox import t2_runtime


def _which(path):
    return lambda name: path


def test_missing_runtime_reports_unavailable(monkeypatch):
    monkeypatch.setattr(t2_runtime.shutil, 'which', _which(None))
    status = t2_runtime.probe_t2_runtime('runsc')
    assert status.available is False
    assert status.as_health()['status'] == t2_runtime.T2_RUNTIME_UNAVAILABLE
    assert 'runsc' in status.detail


def test_installed_runtime_reports_available(monkeypatch):
    monkeypatch.setattr(t2_runtime.shutil, 'which', _which('/usr/local/bin/runsc'))

    class _Result:
        returncode = 0
        stdout = b'runsc version release-20260101.0\nbuilt with go1.22'
        stderr = b''

    monkeypatch.setattr(t2_runtime.subprocess, 'run',
                        lambda *a, **k: _Result())
    status = t2_runtime.probe_t2_runtime('runsc')
    assert status.available is True
    assert status.binary_path == '/usr/local/bin/runsc'
    assert status.as_health()['status'] == t2_runtime.T2_RUNTIME_AVAILABLE
    assert 'runsc version' in status.detail


def test_runtime_that_cannot_run_reports_unavailable(monkeypatch):
    monkeypatch.setattr(t2_runtime.shutil, 'which', _which('/usr/local/bin/runsc'))

    class _Result:
        returncode = 2
        stdout = b''
        stderr = b'permission denied'

    monkeypatch.setattr(t2_runtime.subprocess, 'run',
                        lambda *a, **k: _Result())
    status = t2_runtime.probe_t2_runtime('runsc')
    assert status.available is False
    assert 'permission denied' in status.detail


def test_probe_exception_reports_unavailable(monkeypatch):
    monkeypatch.setattr(t2_runtime.shutil, 'which', _which('/usr/local/bin/runsc'))

    def boom(*_a, **_k):
        raise OSError('exec format error')

    monkeypatch.setattr(t2_runtime.subprocess, 'run', boom)
    status = t2_runtime.probe_t2_runtime('runsc')
    assert status.available is False
    assert 'exec format error' in status.detail


def test_default_runtime_is_runsc(monkeypatch):
    monkeypatch.setattr(t2_runtime.shutil, 'which', _which(None))
    status = t2_runtime.probe_t2_runtime()
    assert status.runtime == t2_runtime.DEFAULT_T2_RUNTIME == 'runsc'


def test_runtime_name_is_passed_through(monkeypatch):
    """调用方传 AGENT_T2_RUNTIME（firecracker）时按该名字探测。"""
    monkeypatch.setattr(t2_runtime.shutil, 'which', _which(None))
    status = t2_runtime.probe_t2_runtime('firecracker')
    assert status.runtime == 'firecracker'


def test_health_payload_shape(monkeypatch):
    monkeypatch.setattr(t2_runtime.shutil, 'which', _which(None))
    payload = t2_runtime.probe_t2_runtime().as_health()
    assert set(payload) == {'runtime', 'status', 'binary', 'detail'}
