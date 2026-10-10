# -*- coding: utf-8 -*-
"""INT-102 run_all.py GBK 管道级联故障回归测试。

真实事故（2026-10-10 INT-95 实机验收）：中文 Windows（GBK）下
- run_all.py 转发线程 _stream 的 print 遇 GBK 外字符（errors='replace'
  产生的 U+FFFD 本身 GBK 也编不了）抛 UnicodeEncodeError 死亡，
  子进程 stdout PIPE 无人消化塞满；
- audio_service 用例自动创建的 DEBUG 日志经 log_and_emit 控制台直打
  sys.stdout.flush() 抛 OSError: [Errno 22] Invalid argument，
  merge(createTestCase=true) 直接 400「合并分片失败」。

本文件固化三条防线：
- log_handler 控制台直打在坏管道/受限编码下静默丢弃，不炸业务路径
- run_all.py _stream 转发线程 print 失败不停止读管道（消化到底）
- run_all.py 子进程环境强制 PYTHONUTF8=1（显式外部设置优先）
"""
import logging
import os
import sys
import tempfile
from types import SimpleNamespace

import pytest

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='int102_') + '/emit.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')


class _BrokenStream:
    """模拟坏管道：write/flush 一律抛 OSError（事故中的 Errno 22）。"""

    encoding = 'gbk'

    def write(self, s):
        raise OSError(22, 'Invalid argument')

    def flush(self):
        raise OSError(22, 'Invalid argument')

    def close(self):
        pass


class _GbkLimitedStream:
    """模拟 GBK 受限管道：U+FFFD 等 GBK 外字符抛 UnicodeEncodeError。"""

    encoding = 'gbk'

    def __init__(self):
        self.written = []

    def write(self, s):
        s.encode('gbk')  # 编不了即抛，行为等同 GBK TextIOWrapper
        self.written.append(s)
        return len(s)

    def flush(self):
        pass

    def close(self):
        pass


class _FakeChildStdout:
    def __init__(self, lines):
        self._lines = list(lines)
        self.closed = False

    def readline(self):
        if self._lines:
            return self._lines.pop(0)
        return b''

    def close(self):
        self.closed = True


@pytest.fixture()
def log_env(monkeypatch, tmp_path):
    """独立 DatabaseLogHandler：控制台打开、文件落 tmp、gRPC/归档 fake。

    归档巡检 fake 的原因同 test_log_handler_audit_emit.py：worker 批刷
    同步触发真实 gRPC 时机器上有驻留服务栈会阻塞 worker 30s+。
    """
    import shared.clients.grpc_clients as grpc_clients_mod
    import shared.clients.oss_client as oss_client_mod
    import shared.utils.log_handler._state as lh_state
    from shared.utils.log_handler import DatabaseLogHandler

    monkeypatch.setattr(
        grpc_clients_mod, 'batch_create_logs',
        lambda payload: [9000 + i for i in range(len(payload))])
    monkeypatch.setattr(grpc_clients_mod, 'get_log_count', lambda: {'total': 0})
    monkeypatch.setattr(
        grpc_clients_mod, 'archive_logs',
        lambda days=30, dry_run=False: {'groups': {}, 'remaining_count': 0})
    monkeypatch.setattr(oss_client_mod.oss, 'is_available', lambda: False)
    monkeypatch.chdir(tmp_path)

    prev = lh_state._global_db_handler
    if prev is not None:
        prev.queue.put(None)
        prev_worker = getattr(prev, 'worker_thread', None)
        if prev_worker is not None:
            prev_worker.join(timeout=2.0)

    handler = DatabaseLogHandler()
    handler._batch_size = 1
    handler.set_console_log(True)
    monkeypatch.setattr(lh_state, '_global_db_handler', handler)
    yield handler
    handler.queue.put(None)


class TestSafeConsolePrint:
    def test_normal_output_passes_through(self, capsys):
        from shared.utils.log_handler._console import safe_console_print
        safe_console_print('hello INT-102')
        assert 'hello INT-102' in capsys.readouterr().out

    def test_broken_stream_swallowed(self, monkeypatch):
        from shared.utils.log_handler._console import safe_console_print
        monkeypatch.setattr(sys, 'stdout', _BrokenStream())
        safe_console_print('should not raise')

    def test_broken_stderr_swallowed(self, monkeypatch):
        from shared.utils.log_handler._console import safe_console_print
        monkeypatch.setattr(sys, 'stderr', _BrokenStream())
        safe_console_print('should not raise', file=sys.stderr)


class TestLogAndEmitConsoleDefense:
    def test_debug_log_survives_broken_stdout(self, log_env, monkeypatch):
        """事故复现回归：坏管道上的 DEBUG 直打不得把 OSError 炸进业务路径。

        事故栈：audio_testcase_creation_service.py log_not_emit('DEBUG', ...)
        -> _api.py sys.stdout.flush() -> OSError: [Errno 22] -> merge 400。
        """
        from shared.utils.log_handler import log_not_emit
        monkeypatch.setattr(sys, 'stdout', _BrokenStream())
        log_not_emit('DEBUG', 'audio_controller',
                     'tc.algorithm_params={"algorithm_type": "ast"}',
                     category='audio')

    def test_log_survives_gbk_incompatible_stdout(self, log_env, monkeypatch):
        """GBK 管道遇 U+FFFD（errors='replace' 的产物）：问题行静默丢弃
        且不炸业务路径，后续可编码的正常行照常写出。"""
        from shared.utils.log_handler import log_and_emit
        stream = _GbkLimitedStream()
        monkeypatch.setattr(sys, 'stdout', stream)
        log_and_emit('INFO', 'audio_engine',
                     'decode fallback -> � trailing garbage',
                     category='audio')
        log_and_emit('INFO', 'audio_engine', 'recovered normal line',
                     category='audio')
        assert not any('�' in line for line in stream.written)
        assert any('recovered normal line' in line for line in stream.written), \
            '问题行丢弃后正常行不应被吞掉'

    def test_console_log_survives_broken_stdout(self, log_env, monkeypatch):
        """标准 logging 路径（emit -> _console_log）在坏管道上不得炸。"""
        monkeypatch.setattr(sys, 'stdout', _BrokenStream())
        log_env._console_log('INFO', '[mod] hello')

    def test_emit_internal_failure_survives_broken_stderr(self, log_env, monkeypatch):
        """emit 内部异常 + stderr 坏管道：兜底打印不得传播异常给调用方。"""
        monkeypatch.setattr(sys, 'stderr', _BrokenStream())
        record = logging.LogRecord('biz_mod', logging.INFO, '', 0, 'msg', (), None)
        record.module = 'biz_mod'

        def _boom(rec):
            raise RuntimeError('format exploded')

        monkeypatch.setattr(log_env, 'format', _boom)
        log_env.emit(record)  # 不应抛


class TestRunAllLauncher:
    def test_child_env_forces_pythonutf8(self):
        import run_all
        assert run_all.CHILD_ENV.get('PYTHONUTF8') == '1'

    def test_child_env_respects_explicit_setting(self, monkeypatch):
        import importlib
        monkeypatch.setenv('PYTHONUTF8', '0')
        import run_all
        reloaded = importlib.reload(run_all)
        try:
            assert reloaded.CHILD_ENV.get('PYTHONUTF8') == '0'
        finally:
            importlib.reload(run_all)  # 恢复默认注入，避免污染同进程后续读取

    def test_stream_keeps_draining_when_print_fails(self, monkeypatch):
        """转发线程 print 失败必须继续消化管道直到 EOF（INT-102 核心纪律）。"""
        from run_all import _stream

        lines = [b'line1\n', b'\xff\xfe broken utf8\n', b'line3\n']
        fake_child_stdout = _FakeChildStdout(lines)
        proc = SimpleNamespace(stdout=fake_child_stdout)
        monkeypatch.setattr(sys, 'stdout', _BrokenStream())

        _stream(proc, 'svc')  # 同步执行：不抛且消化完全部行

        assert fake_child_stdout.closed
        assert fake_child_stdout.readline() == b'', '管道未被消化到底'

    def test_stream_prints_forwarded_lines_on_healthy_stdout(self, monkeypatch, capsys):
        """正常 stdout 下转发行为不回退：内容照常输出。"""
        from run_all import _stream

        fake_child_stdout = _FakeChildStdout([b'health 200\n', b''])
        proc = SimpleNamespace(stdout=fake_child_stdout)

        _stream(proc, 'task_service')

        out = capsys.readouterr().out
        assert '[task_service] health 200' in out
