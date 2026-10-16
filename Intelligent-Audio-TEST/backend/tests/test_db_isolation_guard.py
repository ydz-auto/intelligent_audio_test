# -*- coding: utf-8 -*-
"""VEGA-35 防回归：测试进程不得触碰共享（生产）库。

背景（VEGA-25 实测事故）：pytest 收集阶段会 import 每个测试模块，
模块级一次裸 ``create_app()`` 就会落到 ``config['default'] = DevelopmentConfig``
→ 生产库 ``intelligent_audio_test``，并顺带执行 app.py 的启动恢复扫描，
把别人正在跑的评估刷成 ``error_message='服务重启导致评估中断'`` 的 failed。

本文件是纯本地检查（不连数据库），拦三类回归：

1. ``backend/tests/`` 下任何 ``create_app(...)`` 调用必须显式指定 ``"testing"``；
2. 启动恢复扫描默认关闭（只由服务入口 run.py 打开），且 run.py 确实打开了它
   —— 保证"测试不扫"的同时不削弱真实服务重启的收尾语义；
3. 任务调度器（VEGA-42）同样只在服务入口启动，且 run.py 确实打开了它
   —— 调度器是 3s 轮询的守护线程，会自行拾取/推进共享库里的 pending 任务。
"""
import ast
import os
import re

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_TESTS_DIR))
_TESTING_ARG = 'testing'
_APP_PY = os.path.join(_PROJECT_ROOT, 'backend', 'app.py')
_SCHEDULER_GATE = '_should_start_task_scheduler'


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


def _scheduler_init_calls_with_guards(tree):
    """产出 app.py 里每个 ``_init_scheduler()`` 调用及其外层 ``if`` 条件节点。

    只有 ``if`` 体算"被闸住"；``else`` 分支不算（那里执行等于没闸）。
    条件以 **AST 节点**（而非源码字符串）返回，交给 :func:`_is_exact_scheduler_gate`
    做严格比对——字符串包含式匹配会被 ``or True`` 这类包装绕过（见该函数说明）。
    """
    found = []

    def visit(node, guards):
        if isinstance(node, ast.If):
            for child in node.body:
                visit(child, guards + [node.test])
            for child in node.orelse:
                visit(child, guards)
            return
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                and node.func.attr == '_init_scheduler':
            found.append((node.lineno, list(guards)))
        for child in ast.iter_child_nodes(node):
            visit(child, guards)

    visit(tree, [])
    return found


def _is_exact_scheduler_gate(test):
    """该 ``if`` 条件是否**恰好**是一次 ``_should_start_task_scheduler(...)`` 调用。

    不接受任何包装：``_should_start_task_scheduler(app) or True``、
    ``True and _should_start_task_scheduler(app)``、``not _should_start_task_scheduler(app)``
    的 if 体都会执行调度器启动，必须判为"未闸住"。

    VEGA-42 审计观察 O1：原实现用 ``_SCHEDULER_GATE in ast.unparse(node.test)``
    做子串匹配，上述包装写法都含该子串，于是被判成"已闸住"——接线检查静默失效
    （运行期那半也拦不住：闸门函数本身仍返回 False，但 if 体照样执行）。
    这里改为按节点严格比对，堵掉该绕过面。
    """
    return (
        isinstance(test, ast.Call)
        and isinstance(test.func, ast.Name)
        and test.func.id == _SCHEDULER_GATE
    )


def test_task_scheduler_never_starts_outside_service_entry():
    """非服务入口不启动调度器（VEGA-42）。

    调度器是 3s 轮询的守护线程，会自行拾取并推进共享库里的 pending 任务，
    比恢复扫描更主动；它必须和恢复扫描一样被闸住，绝不能无条件启动。

    两重检查：
    1. 接线（静态 AST）：``backend/app.py`` 里每个 ``_init_scheduler()`` 都必须
       落在 ``_should_start_task_scheduler(...)`` 的 if 体内，且该条件必须**恰好**
       是这次闸门调用（不接受 ``or True`` / ``True and ...`` 之类的包装）——
       把它改回无条件调用、挪进 else、或给条件加包装，本检查立即失败；
    2. 判据（运行期）：pytest 进程内即便开关被打开，判据也必须返回 False。
    """
    with open(_APP_PY, 'r', encoding='utf-8-sig') as f:
        tree = ast.parse(f.read(), filename=_APP_PY)

    calls = _scheduler_init_calls_with_guards(tree)
    assert calls, (
        f'{os.path.relpath(_APP_PY, _PROJECT_ROOT)} 里找不到 _init_scheduler() 调用，'
        '本检查已失效（启动路径变了就请同步本用例）'
    )

    ungated = [lineno for lineno, guards in calls
               if not any(_is_exact_scheduler_gate(g) for g in guards)]
    assert not ungated, (
        f'backend/app.py:{ungated} 的 _init_scheduler() 不在 {_SCHEDULER_GATE}(...) 闸门内'
        '（或闸门条件被包装过），裸 create_app() 会对着共享库起 3s 轮询的调度器线程（VEGA-42）'
    )

    from backend.app import _is_test_process, _should_start_task_scheduler

    assert _is_test_process() is True

    class _FakeApp:
        config = {'TASK_SCHEDULER_ON_STARTUP': True}

    assert _should_start_task_scheduler(_FakeApp()) is False


def test_scheduler_gate_predicate_rejects_wrapped_conditions():
    """闸门判据自身反向可失败（VEGA-42 审计观察 O1）。

    纯本地、不连库、不改仓库任何文件：直接喂合成源码片段给判据函数。
    对每种写法断言"判据是否认为已闸住"，把 O1 那个绕过面钉死在用例里——
    将来谁把 :func:`_is_exact_scheduler_gate` 退回子串匹配，本用例立即失败。
    """
    gate = '_should_start_task_scheduler(app)'
    call = 'execution_engine._init_scheduler()'
    gated_body = f'        {call}'      # if 体内（8 空格）
    bare_body = f'    {call}'           # 裸调用（4 空格）

    cases = {
        f'if {gate}:': True,                        # 正确接线
        f'if {gate} or True:': False,               # O1：or True 绕过
        f'if True and {gate}:': False,              # O1 同类：and 包装
        f'if not {gate}:': False,                   # 取反后 if 体照跑
        f'if bool({gate}):': False,                 # 函数包装
        'if True:': False,                          # 与闸门无关的条件
    }

    for header, expected in cases.items():
        snippet = f'def _f():\n    {header}\n{gated_body}\n'
        tree = ast.parse(snippet)
        calls = _scheduler_init_calls_with_guards(tree)
        assert len(calls) == 1, f'片段解析异常：{header}'
        _, guards = calls[0]
        actual = any(_is_exact_scheduler_gate(g) for g in guards)
        assert actual is expected, (
            f'判据对 {header!r} 的判定应为 {expected}，实际 {actual}'
            '——包装过的条件必须判为未闸住（VEGA-42 O1）'
        )

    # 无条件调用：压根没有外层 if，必须判为未闸住
    tree = ast.parse(f'def _f():\n{bare_body}\n')
    _, guards = _scheduler_init_calls_with_guards(tree)[0]
    assert not any(_is_exact_scheduler_gate(g) for g in guards)


def test_task_scheduler_is_off_by_default():
    """任务调度器默认关闭：任何配置下都不该默认对着库起 3s 轮询线程。"""
    if os.environ.get('TASK_SCHEDULER_ON_STARTUP'):
        pytest.skip('本进程显式设置了 TASK_SCHEDULER_ON_STARTUP，跳过"默认关闭"断言')
    from backend.config.config import config

    for name in ('default', 'development', 'production', 'testing'):
        assert config[name].TASK_SCHEDULER_ON_STARTUP is False, (
            f'config[{name!r}].TASK_SCHEDULER_ON_STARTUP 应为 False（VEGA-42）'
        )


def test_service_entrypoint_enables_task_scheduler():
    """唯一的服务入口 run.py 必须显式打开调度器开关。

    否则真实服务起来后没人拾取 pending 任务（VEGA-42 红线：加闸只能是
    "让测试/脚本不起"，不能变成"谁都不起"）。
    """
    with open(os.path.join(_PROJECT_ROOT, 'run.py'), 'r', encoding='utf-8') as f:
        source = f.read()
    assert re.search(
        r"os\.environ\.setdefault\(\s*['\"]TASK_SCHEDULER_ON_STARTUP['\"]\s*,\s*['\"]true['\"]",
        source, re.IGNORECASE,
    ), 'run.py 未显式打开 TASK_SCHEDULER_ON_STARTUP，真实服务将不再拾取 pending 任务'
    assert source.index('TASK_SCHEDULER_ON_STARTUP') < source.index('from backend.app import'), \
        'TASK_SCHEDULER_ON_STARTUP 必须在 import backend.app 之前设置'
