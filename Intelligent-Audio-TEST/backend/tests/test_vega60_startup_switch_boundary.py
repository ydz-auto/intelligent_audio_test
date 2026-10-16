# -*- coding: utf-8 -*-
"""VEGA-60 验收用例：调度器启动开关两处**方向相反**的边界缺陷（VEGA-42 审计 O3 / O4）。

本文件是纯本地检查（不连数据库、不动 ExecutionEngine 单例），钉住两条边界语义：

**O3 —— 闸关进程里 ``_stop_scheduler()`` 不得空指针**
``scheduler_stop_event`` 只在 ``_init_scheduler()`` 内创建；闸关进程（测试/迁移脚本里的
``create_app()``）从不调用它 → 该属性恒为 ``None``。修复前 ``_stop_scheduler()`` 直接
``.set()`` 抛 ``AttributeError``；而 ``_scheduler_loop`` 对同一属性有 ``is None`` 保护
—— **同一属性两处保护不对称**本身就是缺陷信号。这里同时钉住：
  * 闸关态两处调用（``_stop_scheduler`` / ``shutdown``）不抛异常且不伪造状态；
  * 闸开态语义不被削弱（能 stop：stop_event 置位、线程退出）；
  * 两处保护对称（结构性断言）；
  * **不得**用 ``try/except`` 吞掉 ``AttributeError``（issue 明确禁止）。

**O4 —— 服务入口不得被外部遗留的关闭值静默关掉**
``run.py`` 原用 ``os.environ.setdefault``，调用 shell 里遗留 ``TASK_SCHEDULER_ON_STARTUP=false``
时不会被覆盖 → 真实服务静默不启调度器（违反 VEGA-42 红线）。这里钉住强制赋值形态的
**行为**（覆盖为 true 且留痕告警），并做反向验证：退回 setdefault 写法时本检查必须失败。

反向可失败：见 :func:`test_stop_scheduler_old_form_still_raises` 与
:func:`test_run_py_old_setdefault_form_is_detected`。
"""
import ast
import os
import threading

import pytest

_TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(os.path.dirname(_TESTS_DIR))
_ENGINE_PY = os.path.join(_PROJECT_ROOT, 'backend', 'services', 'execution',
                          'execution_engine.py')
_RUN_PY = os.path.join(_PROJECT_ROOT, 'run.py')
_STARTUP_SWITCHES = ('RECOVERY_SWEEP_ON_STARTUP', 'TASK_SCHEDULER_ON_STARTUP')
_FORCER = '_force_service_startup_switch'


def _read(path):
    with open(path, 'r', encoding='utf-8-sig') as f:
        return f.read()


def _engine_tree():
    return ast.parse(_read(_ENGINE_PY), filename=_ENGINE_PY)


def _function_node(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f'{_ENGINE_PY} 里找不到 {name}()，本检查已失效')


def _compile_function(source, name, filename='<extracted>'):
    """把源码里名为 name 的函数单独编译到隔离命名空间并返回它。"""
    tree = ast.parse(source, filename=filename)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            module = ast.Module(body=[node], type_ignores=[])
            namespace = {'os': os, 'threading': threading}
            exec(compile(module, filename, 'exec'), namespace)
            return namespace[name]
    raise AssertionError(f'{filename} 里找不到 {name}()，本检查已失效')


class _GatedOffEngine:
    """闸关进程的引擎状态：``_init_scheduler()`` 从未被调用。

    用 ``object.__new__`` 造裸对象，绝不碰 ``ExecutionEngine`` 单例——``shutdown()``
    会永久关掉单例的线程池，在测试进程里调用会污染同会话的其它用例。
    """

    def __init__(self):
        from backend.services.execution.execution_engine import ExecutionEngine
        self._engine = object.__new__(ExecutionEngine)
        e = self._engine
        # 闸关态：调度器相关属性都是 __new__ 里的初值
        e.scheduler_stop_event = None
        e.scheduler_event = threading.Event()
        e.scheduler_thread = None
        e._scheduler_initialized = False
        # shutdown() 会碰到的线程池/执行器（置 None 走短路分支）
        e.api_task_pool = None
        e.device_control_pool = None
        e.audio_playback_pool = None
        e.api_executors = {}
        # _log 必须绑在**引擎对象**上（shutdown 走 self._log），否则会落到真实现去写库
        e.logs = []
        e._log = lambda **kw: e.logs.append(kw)


def test_stop_scheduler_is_none_safe_in_gated_off_process():
    """O3：闸关进程下 ``_stop_scheduler()`` 不得抛 ``AttributeError``。"""
    g = _GatedOffEngine()
    assert g._engine.scheduler_stop_event is None, '前置：闸关进程里该属性应为 None'

    g._engine._stop_scheduler()  # 修复前这里 AttributeError: 'NoneType' has no 'set'

    # 保护不得伪造状态：闸关时不该"顺手"造出 Event / 线程
    assert g._engine.scheduler_stop_event is None, \
        'O3 的保护不得伪造 scheduler_stop_event（闸关进程里它必须保持 None）'
    assert g._engine.scheduler_thread is None
    assert g._engine._scheduler_initialized is False


def test_shutdown_is_none_safe_in_gated_off_process():
    """O3：闸关进程下 ``shutdown()``（内部走 ``_stop_scheduler``）同样不得抛。"""
    g = _GatedOffEngine()
    g._engine.shutdown()
    assert any('执行引擎已关闭' in str(kw.get('content', '')) for kw in g._engine.logs), \
        'shutdown() 应当走到最后一步的"执行引擎已关闭"日志，说明中途没炸'


def test_stop_scheduler_old_form_still_raises():
    """O3 反向可失败：退回"无 None 保护"的旧写法，同一个闸关对象必须抛 AttributeError。

    旧写法（VEGA-60 修复前的 ``_stop_scheduler`` 开头）钉在这里：若有人把保护删掉，
    上面两条用例立刻变红；若这个反向用例自己变绿（不再抛），说明反向验证失效。
    """
    old_source = (
        'import threading\n'
        'def _stop_scheduler(self):\n'
        '    self.scheduler_stop_event.set()\n'
        '    self.scheduler_event.set()\n'
        '    if self.scheduler_thread is not None and self.scheduler_thread.is_alive():\n'
        '        self.scheduler_thread.join(timeout=5)\n'
    )
    old_stop = _compile_function(old_source, '_stop_scheduler', '<old_stop_scheduler>')
    g = _GatedOffEngine()
    with pytest.raises(AttributeError):
        old_stop(g._engine)


def test_stop_scheduler_does_not_swallow_via_try_except():
    """O3：不得用 ``try/except`` 吞掉 ``AttributeError``（issue 明确要求）。"""
    fn = _function_node(_engine_tree(), '_stop_scheduler')
    for node in ast.walk(fn):
        if not isinstance(node, ast.Try):
            continue
        for inner in ast.walk(node):
            if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Attribute) \
                    and inner.func.attr == 'set' \
                    and isinstance(inner.func.value, ast.Attribute) \
                    and inner.func.value.attr == 'scheduler_stop_event':
                raise AssertionError(
                    '_stop_scheduler 把 scheduler_stop_event.set() 包进了 try/except：'
                    '那是吞异常，会把真问题藏起来（VEGA-60/O3 明确禁止）'
                )


def test_scheduler_stop_event_guard_is_symmetric():
    """O3：同一属性 ``scheduler_stop_event`` 的两处保护必须对称（都是 None 判据）。"""

    def _guards_none(fn_name):
        fn = _function_node(_engine_tree(), fn_name)
        for node in ast.walk(fn):
            if not isinstance(node, ast.Compare) or not node.ops:
                continue
            if not isinstance(node.ops[0], (ast.Is, ast.IsNot)):
                continue
            if not any(isinstance(c, ast.Constant) and c.value is None
                       for c in node.comparators):
                continue
            if any(isinstance(x, ast.Attribute) and x.attr == 'scheduler_stop_event'
                   for x in ast.walk(node.left)):
                return True
        return False

    assert _guards_none('_scheduler_loop'), \
        '_scheduler_loop 缺少 scheduler_stop_event 的 None 保护'
    assert _guards_none('_stop_scheduler'), (
        '_stop_scheduler 缺少 scheduler_stop_event 的 None 保护——'
        '同一属性两处保护不对称即 VEGA-60/O3 的缺陷形态'
    )


def test_stop_scheduler_still_stops_a_running_scheduler():
    """O3 闸开侧：保护不得削弱真实服务语义——stop_event 置位、线程退出。"""
    from backend.services.execution.execution_engine import ExecutionEngine

    e = object.__new__(ExecutionEngine)
    e.scheduler_stop_event = threading.Event()
    e.scheduler_event = threading.Event()
    e.scheduler_thread = None
    logs = []

    def _log(**kwargs):
        logs.append(kwargs)

    e._log = _log
    stop_flag = threading.Event()

    def _loop():
        # 模拟 _scheduler_loop 的退出条件
        while not e.scheduler_stop_event.is_set():
            stop_flag.wait(timeout=0.05)

    e.scheduler_thread = threading.Thread(target=_loop, name='VEGA60TestScheduler', daemon=True)
    e.scheduler_thread.start()
    assert e.scheduler_thread.is_alive()

    e._stop_scheduler()

    assert e.scheduler_stop_event.is_set(), '闸开侧 stop 后 stop_event 必须置位'
    assert not e.scheduler_thread.is_alive(), '闸开侧 stop 后调度线程必须退出'
    assert any('任务调度器已停止' in str(kw.get('content', '')) for kw in logs), \
        '闸开侧 stop 仍应留"任务调度器已停止"日志（保护不得削弱真实语义）'


# --------------------------------------------------------------------------- O4


def _read_run_py():
    return _read(_RUN_PY)


def _run_py_forcer():
    """run.py 里 ``_force_service_startup_switch`` 的真实函数本体（隔离编译，不导入 run.py）。"""
    return _compile_function(_read_run_py(), _FORCER, _RUN_PY)


@pytest.mark.parametrize('external', ['false', '0', 'no', 'FALSE', 'False', '1', 'TRUE', ''])
def test_run_py_forcer_overrides_any_external_value(monkeypatch, capsys, external):
    """O4：外部 shell 遗留任何取值时，服务入口都必须把开关强制覆盖为 ``true``。

    ``''``/``'1'``/``'TRUE'`` 也在内——判据只看"存在即覆盖+留痕"，不看外部取值
    "算不算关闭"（on 值判据只有 backend/config/config.py 一份，不在这里再写一套）。
    """
    force = _run_py_forcer()
    for name in _STARTUP_SWITCHES:
        monkeypatch.setenv(name, external)
        force(name)
        assert os.environ[name] == 'true', (
            f'外部遗留 {name}={external!r} 时 run.py 没有覆盖为 true：'
            f'真实服务会静默丢失该启动语义（VEGA-60/O4）'
        )
    out = capsys.readouterr().out
    for name in _STARTUP_SWITCHES:
        assert f'外部已设置 {name}' in out, (
            f'覆盖 {name} 时未留痕告警：用户显式传了关闭值却看到服务照常启用，'
            f'是另一种静默（VEGA-60/O4 要求"明确告警"）'
        )


def test_run_py_forcer_is_silent_when_external_value_absent(monkeypatch, capsys):
    """O4：外部未设置时不得告警（常规启动路径的行为不能被这次修复改动）。"""
    force = _run_py_forcer()
    for name in _STARTUP_SWITCHES:
        monkeypatch.delenv(name, raising=False)
    for name in _STARTUP_SWITCHES:
        force(name)
        assert os.environ[name] == 'true'
    assert '[WARN]' not in capsys.readouterr().out, \
        '外部没有设置开关时不应产生告警（常规路径行为应保持不变）'


def test_run_py_old_setdefault_form_is_detected(monkeypatch):
    """O4 反向可失败：退回 ``os.environ.setdefault`` 写法时，本判据必须判为失败。

    这是"退回旧写法时失败"的原文——旧写法在外部遗留 false 时**不覆盖**，缺陷复现。
    """
    old_source = (
        'import os\n'
        'def _force_service_startup_switch(name):\n'
        "    os.environ.setdefault(name, 'true')\n"
    )
    old_force = _compile_function(old_source, _FORCER, '<old_run_py_forcer>')
    monkeypatch.setenv('TASK_SCHEDULER_ON_STARTUP', 'false')
    old_force('TASK_SCHEDULER_ON_STARTUP')
    assert os.environ['TASK_SCHEDULER_ON_STARTUP'] == 'false', (
        'setdefault 写法本应保留外部的 false（VEGA-60/O4 的缺陷形态）；'
        '这里若变成 true，说明反向验证本身失效了'
    )


def test_run_py_uses_force_assignment_not_setdefault():
    """O4：run.py 里不得再出现 ``os.environ.setdefault`` 形态的启动开关。"""
    tree = ast.parse(_read_run_py(), filename=_RUN_PY)
    offenders = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != 'setdefault':
            continue
        target = node.func.value
        if not (isinstance(target, ast.Attribute) and target.attr == 'environ'):
            continue
        if node.args and isinstance(node.args[0], ast.Constant) \
                and node.args[0].value in _STARTUP_SWITCHES:
            offenders.add(node.args[0].value)
    assert not offenders, (
        f'run.py 仍用 os.environ.setdefault 打开 {sorted(offenders)}：'
        f'调用 shell 里遗留的 false/0 不会被覆盖（VEGA-60/O4）'
    )
