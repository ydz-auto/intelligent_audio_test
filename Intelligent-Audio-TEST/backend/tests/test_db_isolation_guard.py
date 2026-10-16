# -*- coding: utf-8 -*-
"""VEGA-35 防回归：测试进程不得触碰共享（生产）库。

背景（VEGA-25 实测事故）：pytest 收集阶段会 import 每个测试模块，
模块级一次裸 ``create_app()`` 就会落到 ``config['default'] = DevelopmentConfig``
→ 生产库 ``intelligent_audio_test``，并顺带执行 app.py 的启动恢复扫描，
把别人正在跑的评估刷成 ``error_message='服务重启导致评估中断'`` 的 failed。

本文件是纯本地检查（不连数据库），拦两类回归：

1. ``backend/tests/`` 下任何 ``create_app(...)`` 调用必须显式指定 ``"testing"``；
2. 启动恢复扫描默认关闭（只由服务入口 run.py 打开），且 run.py 确实打开了它
   —— 保证"测试不扫"的同时不削弱真实服务重启的收尾语义。
"""
import ast
import os
import re

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_TESTS_DIR))
_TESTING_ARG = 'testing'


def _iter_test_modules():
    """backend/tests/ 下所有测试模块（含 conftest.py）。"""
    for name in sorted(os.listdir(_TESTS_DIR)):
        if name.endswith('.py'):
            yield os.path.join(_TESTS_DIR, name)


def _create_app_calls(tree):
    """遍历 AST，产出所有 create_app(...) 调用节点。"""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            name = func.attr
        else:
            name = getattr(func, 'id', None)
        if name == 'create_app':
            yield node


def _targets_testing(call):
    """该调用是否显式指向 testing 配置（位置参数或 config_name 关键字）。"""
    first = call.args[0] if call.args else None
    if isinstance(first, ast.Constant) and first.value == _TESTING_ARG:
        return True
    for kw in call.keywords:
        if kw.arg == 'config_name' and isinstance(kw.value, ast.Constant) \
                and kw.value.value == _TESTING_ARG:
            return True
    return False


def test_tests_never_create_app_without_testing_config():
    """backend/tests/ 里的 create_app(...) 必须显式传 "testing"。

    裸 create_app() / create_app('development') 会连上共享库，必须拦住。
    """
    offenders = []
    for path in _iter_test_modules():
        # utf-8-sig：部分测试文件带 BOM，直接 utf-8 解析会 SyntaxError
        with open(path, 'r', encoding='utf-8-sig') as f:
            tree = ast.parse(f.read(), filename=path)
        for call in _create_app_calls(tree):
            if not _targets_testing(call):
                offenders.append(f'{os.path.relpath(path, _PROJECT_ROOT)}:{call.lineno}')
    assert not offenders, (
        'backend/tests/ 里出现未指定 testing 配置的 create_app()，会连上共享/生产库：\n  '
        + '\n  '.join(offenders)
    )


def test_recovery_sweep_is_off_by_default():
    """启动恢复扫描默认关闭：任何配置下都不该默认去改写共享库状态。"""
    if os.environ.get('RECOVERY_SWEEP_ON_STARTUP'):
        pytest.skip('本进程显式设置了 RECOVERY_SWEEP_ON_STARTUP，跳过"默认关闭"断言')
    from backend.config.config import config

    for name in ('default', 'development', 'production', 'testing'):
        assert config[name].RECOVERY_SWEEP_ON_STARTUP is False, (
            f'config[{name!r}].RECOVERY_SWEEP_ON_STARTUP 应为 False（VEGA-35）'
        )


def test_recovery_sweep_is_never_run_in_test_process():
    """即使开关被打开，pytest 进程也不扫（app.py 的第二道闸）。"""
    from backend.app import _is_test_process, _should_run_recovery_sweep

    assert _is_test_process() is True

    class _FakeApp:
        config = {'RECOVERY_SWEEP_ON_STARTUP': True}

    assert _should_run_recovery_sweep(_FakeApp()) is False


def test_service_entrypoint_enables_recovery_sweep():
    """唯一的服务入口 run.py 必须显式打开恢复扫描。

    否则真实服务重启后遗留的 pending/queued/running 任务永远不会被收尾为 failed
    （VEGA-35 红线：加开关只能是"让测试不扫"，不能变成"谁都不扫"）。
    """
    with open(os.path.join(_PROJECT_ROOT, 'run.py'), 'r', encoding='utf-8') as f:
        source = f.read()
    assert re.search(
        r"os\.environ\.setdefault\(\s*['\"]RECOVERY_SWEEP_ON_STARTUP['\"]\s*,\s*['\"]true['\"]",
        source, re.IGNORECASE,
    ), 'run.py 未显式打开 RECOVERY_SWEEP_ON_STARTUP，服务重启恢复语义会丢失'
    # 必须在导入 backend.app 之前设置（配置类在导入时求值）
    assert source.index('RECOVERY_SWEEP_ON_STARTUP') < source.index('from backend.app import'), \
        'RECOVERY_SWEEP_ON_STARTUP 必须在 import backend.app 之前设置'
