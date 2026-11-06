# -*- coding: utf-8 -*-
"""tests/ui/utils/parallel_stack.py 端口段偏移（INT-581）单元测试。

并发 run（如 INT-569 前端回归日巡与功能卡验收同时实测）争用同一端口段时，
库存脚本 SHIFT 硬编码 +1000 无法换段。本测试验证新增的端口偏移参数：
- 默认段向后兼容（shift=1000 → 网关 6000 / 前端 6273）；
- --shift 整段联动（服务 HTTP/gRPC + 前端 5273+shift）；
- --frontend-port 显式覆盖（INT-553 临时变体：网关 :10000 / 前端 :8273）；
- 并发双栈 required_ports() 互不重叠（同跑不争端口）；
- 非默认段 PID/日志按 shift 分目录（stop/status 各管各段，互不踩）；
- configure() 优先级：CLI 参数 > UI_STACK_SHIFT/UI_STACK_FRONTEND_PORT
  环境变量 > 默认；
- PID 文件读写（新格式含 shift/frontend，旧单行格式兼容）；
- CLI 参数经 argparse 贯通到 required_ports()（subprocess status 冒烟）。
"""
import os
import subprocess
import sys

import pytest

from tests.ui.utils import parallel_stack as ps


@pytest.fixture(autouse=True)
def _restore_stack_globals():
    """configure() 会改写模块级端口段/PID/日志全局，测试后恢复默认态。"""
    before = (ps.SHIFT, ps.GATEWAY_HTTP, ps.FRONTEND_PORT, ps.PID_FILE, ps.LOG_DIR)
    yield
    ps.SHIFT, ps.GATEWAY_HTTP, ps.FRONTEND_PORT, ps.PID_FILE, ps.LOG_DIR = before


class TestDefaultBackwardCompat:
    def test_default_segment(self):
        assert ps.SHIFT == 1000
        assert ps.GATEWAY_HTTP == 6000
        assert ps.FRONTEND_PORT == 6273

    def test_default_required_ports_contain_gateway_and_frontend(self):
        ports = ps.required_ports()
        assert 6000 in ports
        assert 6273 in ports

    def test_shift_applies_to_base(self):
        assert ps._shift(5001) == 6001


class TestDualStackDisjointSegments:
    @pytest.mark.parametrize("shift_a,shift_b", [
        (1000, 2000),
        (1000, 5000),
        (2000, 5000),
        (3000, 6000),
        (1000, 3000),
    ])
    def test_required_ports_disjoint(self, shift_a, shift_b):
        """并发双栈：不同段的 required_ports() 必须零重叠，才不争端口。"""
        ps.configure(shift_a)
        ports_a = set(ps.required_ports())
        ps.configure(shift_b)
        ports_b = set(ps.required_ports())
        assert ports_a.isdisjoint(ports_b), (
            f'shift {shift_a} 与 {shift_b} 端口段重叠: '
            f'{sorted(ports_a & ports_b)}')


class TestFrontendDerivation:
    def test_frontend_follows_shift(self):
        ps.configure(shift=2000)
        assert ps.GATEWAY_HTTP == 7000
        assert ps.FRONTEND_PORT == 7273  # 5273 + 2000

    def test_int553_variant_frontend_override(self):
        # INT-553 验收临时变体：网关 :10000 / 前端 :8273
        ps.configure(shift=5000, frontend_port=8273)
        assert ps.GATEWAY_HTTP == 10000
        assert ps.FRONTEND_PORT == 8273

    def test_shift_5000_frontend_derived(self):
        ps.configure(shift=5000)
        assert ps.GATEWAY_HTTP == 10000
        assert ps.FRONTEND_PORT == 10273


class TestPidLogDirPerShift:
    def test_default_segment_paths(self):
        ps.configure(1000)
        assert ps.PID_FILE.endswith(os.path.join('tests', 'ui', '_ui_stack.pid'))
        assert ps.LOG_DIR.endswith(os.path.join('logs', 'ui_stack'))

    def test_shifted_segment_paths(self):
        ps.configure(2000)
        assert ps.PID_FILE.endswith(os.path.join('tests', 'ui', '_ui_stack2000.pid'))
        assert ps.LOG_DIR.endswith(os.path.join('logs', 'ui_stack', 'shift2000'))

    def test_back_to_default_restores_paths(self):
        ps.configure(2000)
        ps.configure(1000)
        assert ps.PID_FILE.endswith(os.path.join('tests', 'ui', '_ui_stack.pid'))
        assert ps.LOG_DIR.endswith(os.path.join('logs', 'ui_stack'))


class TestConfigurePrecedence:
    def test_env_shift_fallback(self, monkeypatch):
        monkeypatch.setenv('UI_STACK_SHIFT', '3000')
        ps.configure()
        assert ps.SHIFT == 3000
        assert ps.GATEWAY_HTTP == 8000
        assert ps.FRONTEND_PORT == 8273

    def test_cli_shift_wins_over_env(self, monkeypatch):
        monkeypatch.setenv('UI_STACK_SHIFT', '3000')
        ps.configure(shift=2000)
        assert ps.SHIFT == 2000

    def test_env_frontend_fallback(self, monkeypatch):
        monkeypatch.setenv('UI_STACK_FRONTEND_PORT', '8273')
        ps.configure(shift=1000)
        assert ps.FRONTEND_PORT == 8273

    def test_cli_frontend_wins_over_env(self, monkeypatch):
        monkeypatch.setenv('UI_STACK_FRONTEND_PORT', '8273')
        ps.configure(shift=5000, frontend_port=9000)
        assert ps.GATEWAY_HTTP == 10000
        assert ps.FRONTEND_PORT == 9000

    def test_invalid_env_shift_falls_back(self, monkeypatch):
        monkeypatch.setenv('UI_STACK_SHIFT', 'abc')
        ps.configure()
        assert ps.SHIFT == 1000


class TestPidCfg:
    def test_read_new_format(self, tmp_path):
        f = tmp_path / 'p.pid'
        f.write_text('12345\nshift=2000\nfrontend=7273\n', encoding='ascii')
        assert ps._read_pid_cfg(str(f)) == {
            'pid': 12345, 'shift': 2000, 'frontend': 7273}

    def test_read_old_single_line_format(self, tmp_path):
        f = tmp_path / 'p.pid'
        f.write_text('12345\n', encoding='ascii')
        assert ps._read_pid_cfg(str(f)) == {'pid': 12345}

    def test_read_missing_returns_empty(self, tmp_path):
        assert ps._read_pid_cfg(str(tmp_path / 'nope.pid')) == {}

    def test_stop_parses_multiline_pid(self, tmp_path, monkeypatch):
        """stop 从 PID 文件首行取 pid；新格式多行不破坏解析，taskkill 后删文件。"""
        f = tmp_path / '_ui_stack.pid'
        f.write_text('424242\nshift=2000\nfrontend=7273\n', encoding='ascii')
        monkeypatch.setattr(ps, 'PID_FILE', str(f))
        calls = []
        monkeypatch.setattr(ps.subprocess, 'run',
                            lambda *a, **k: calls.append(a[0]))
        ps.stop()
        assert calls and '424242' in calls[0]
        assert not os.path.exists(str(f))


class TestCliWiring:
    def test_status_shift_probes_correct_segment(self):
        """CLI --shift 经 argparse → configure → required_ports() 贯通。"""
        script = os.path.join('tests', 'ui', 'utils', 'parallel_stack.py')
        r = subprocess.run(
            [sys.executable, script, 'status', '--shift', '3456'],
            cwd=ps.PROJECT_ROOT, capture_output=True, text=True, timeout=30)
        assert r.returncode == 0, r.stderr
        assert '8456:' in r.stdout   # 网关 5000 + 3456
        assert '8729:' in r.stdout   # 前端 5273 + 3456
