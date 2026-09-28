import time
import subprocess
import re
import functools
import threading
from typing import Callable

from backend.utils.web.log_handler import log_and_emit

_task_control_events = {}
_task_control_lock = threading.Lock()

try:
    from hypium import UiDriver, BY as By, MatchPattern
except Exception as e:
    log_and_emit(level='DEBUG', module='DeviceDriver', content=f"Failed to import hypium: {e}")
    UiDriver = None
    By = None
    MatchPattern = None


def restart_uitest_daemon(device_sn):
    """重启设备端 uitest RPC 服务（RpcNotRunningError 恢复用）

    通过 hdc 执行: ui restart 重启 RPC 服务, 并轮询等待端口 8012 重新监听。
    """
    try:
        subprocess.run(['hdc', '-t', device_sn, 'shell',
                        'ui', 'restart'],
                       check=False, timeout=30)
        # 轮询等待 RPC 端口重新监听(ui restart 后 daemon 需要数秒起来)
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                r = subprocess.run(
                    ['hdc', '-t', device_sn, 'shell', 'netstat', '-atn', '|', 'grep', ':8012'],
                    capture_output=True, text=True, timeout=5)
                if 'LISTEN' in (r.stdout or '') and ':8012' in (r.stdout or ''):
                    log_and_emit(level='INFO', module='DeviceDriver',
                                 content=f"uitest daemon restarted for device {device_sn}")
                    return True
            except Exception:
                pass
            time.sleep(1)
        log_and_emit(level='ERROR', module='DeviceDriver',
                     content=f"uitest daemon restart 后 RPC 端口 8012 仍未监听: {device_sn}")
        return False
    except Exception as e:
        log_and_emit(level='ERROR', module='DeviceDriver',
                     content=f"Failed to restart uitest daemon for {device_sn}: {e}")
        return False


def ensure_uitest_rpc_healthy(device_sn):
    """确保设备端 uitest RPC(端口 8012)存活；已死则 ui restart 恢复。

    背景: find_component 等 UI 调用失败时, hypium 内部的 MultiModeComponentFinder 会把
    RPC 异常吞掉并走 dumpLayout 兜底(返回 None 而不是抛异常), 后端拿不到 RPC 异常,
    with_rpc_retry 无法触发 ui restart。因此在进入 with_rpc_retry 且有缓存驱动时,
    先主动探测 RPC 端口, 已死直接 ui restart, 避免 hypium 自身每步 7-8s 的无效重连。

    Returns:
        True: RPC 存活, 或状态未知(hdc 自身失败, 不擅自重启)
        False: 已尝试 ui restart, 调用方需重连 driver
    """
    try:
        r = subprocess.run(
            ['hdc', '-t', device_sn, 'shell', 'netstat', '-atn', '|', 'grep', ':8012'],
            capture_output=True, text=True, timeout=5)
        out = r.stdout or ''
        if 'LISTEN' in out and ':8012' in out:
            return True
        if r.returncode != 0 and not out.strip():
            # hdc 自身失败(设备断线等), 无法判断, 不擅自重启
            return True
    except Exception:
        return True
    log_and_emit(level='WARNING', module='DeviceDriver',
                 content=f"uitest RPC 端口 8012 未监听, 执行 ui restart 恢复: {device_sn}")
    return restart_uitest_daemon(device_sn)


def is_rpc_not_running_error(exc):
    """判断异常是否为 RPC 服务未运行（RpcNotRunningError）"""
    msg = str(exc).lower()
    return 'rpc' in msg and (
        'not running' in msg
        or 'not found' in msg
        or 'listening port' in msg
        or 'reconnect' in msg
        or 'rpc service' in msg
    )


def with_rpc_retry(max_retries=1):
    """装饰器: 捕获 RpcNotRunningError 时自动重启 uitest daemon 并重连重试

    Args:
        max_retries: RPC 恢复后最大重试次数, 默认 1 次
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            last_exc = None
            # 从 args 提取 device_sn (通常是第一个位置参数)
            device_sn = None
            if args:
                device_sn = args[0]
            elif 'device_sn' in kwargs:
                device_sn = kwargs['device_sn']
            # 已有缓存驱动时先探测 RPC 存活: find_component 等失败时 hypium 内部会把 RPC
            # 异常吞掉走 dumpLayout 兜底, 后端拿不到异常无法触发重试, 故主动探测恢复
            if device_sn:
                cached = getattr(self, '_drivers', None)
                if cached and device_sn in cached:
                    try:
                        if not ensure_uitest_rpc_healthy(device_sn):
                            if hasattr(self, '_reconnect_driver'):
                                self._reconnect_driver(device_sn)
                    except Exception:
                        pass
            for attempt in range(max_retries + 1):
                try:
                    return func(self, *args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if not is_rpc_not_running_error(e):
                        raise
                    if attempt >= max_retries:
                        raise
                    if not device_sn:
                        raise
                    _task_id = getattr(self, '_task_id', None)
                    _test_case_id = getattr(self, '_test_case_id', None)
                    log_and_emit(level='WARNING', module='DeviceDriver',
                                 content=f"RpcNotRunningError detected in {func.__name__}, "
                                         f"restarting uitest daemon for {device_sn} "
                                         f"(attempt {attempt + 1}/{max_retries + 1})",
                                 task_id=_task_id, test_case_id=_test_case_id)
                    # 重启 daemon
                    if not restart_uitest_daemon(device_sn):
                        raise
                    # 重连 driver
                    if hasattr(self, '_reconnect_driver'):
                        self._reconnect_driver(device_sn)
            raise last_exc
        return wrapper
    return decorator

try:
    import uiautomator2 as u2
except Exception as e:
    log_and_emit(level='DEBUG', module='DeviceDriver', content=f"Failed to import uiautomator2: {e}")
    u2 = None

try:
    import wda
except Exception as e:
    log_and_emit(level='DEBUG', module='DeviceDriver', content=f"Failed to import facebook-wda: {e}")
    wda = None

def register_task_events(task_id, stop_event, pause_event=None):
    """注册任务的控制事件，供驱动实时获取"""
    global _task_control_events
    with _task_control_lock:
        _task_control_events[task_id] = {
            'stop_event': stop_event,
            'pause_event': pause_event
        }

def get_task_events(task_id):
    """获取任务的控制事件（实时获取最新引用）"""
    global _task_control_events
    with _task_control_lock:
        return _task_control_events.get(task_id)

def unregister_task_events(task_id):
    """注销任务的控制事件"""
    global _task_control_events
    with _task_control_lock:
        if task_id in _task_control_events:
            del _task_control_events[task_id]

def check_stop(operation_name: str = "", check_pause: bool = True):
    """
    装饰器：自动检查停止/暂停事件并在触发时提前返回
    
    用法:
        @check_stop("initialize")
        def initialize(self, device_sn):
            ...
    
    支持的返回值类型:
        - bool: 返回 False
        - dict: 返回 {"asr": "Stopped", "translation": "Stopped"}
        - str: 返回 "Stopped"
        - None: 直接返回
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            # 检查是否处于模拟模式
            if hasattr(self, '_mock_mode') and self._mock_mode:
                # 模拟模式下返回默认值
                sig = func.__annotations__.get('return')
                if sig is bool or sig == 'bool':
                    return True
                elif sig is dict or sig == 'dict':
                    return {"asr": "Mock ASR", "translation": "Mock Translation"}
                elif sig is str or sig == 'str':
                    return "Mock Result"
                return None

            events = self._get_events()
            if events is None or not isinstance(events, dict):
                stop_event = None
                pause_event = None
            else:
                stop_event = events.get('stop_event')
                pause_event = events.get('pause_event')

            # 检查停止事件
            if stop_event and stop_event.is_set():
                _task_id = getattr(self, '_task_id', None)
                _test_case_id = getattr(self, '_test_case_id', None)
                log_and_emit(level='INFO', module='DeviceDriver', 
                           content=f"Task stopped during {operation_name} operation",
                           task_id=_task_id, test_case_id=_test_case_id)
                # 根据函数返回类型返回相应的停止值
                sig = func.__annotations__.get('return')
                if sig is bool or sig == 'bool':
                    return False
                elif sig is dict or sig == 'dict':
                    return {"asr": "Stopped", "translation": "Stopped"}
                elif sig is str or sig == 'str':
                    return "Stopped"
                return

            # 检查暂停事件
            if check_pause and pause_event and not pause_event.is_set():
                _task_id = getattr(self, '_task_id', None)
                _test_case_id = getattr(self, '_test_case_id', None)
                log_and_emit(level='INFO', module='DeviceDriver', 
                           content=f"Task paused during {operation_name} operation",
                           task_id=_task_id, test_case_id=_test_case_id)
                while not pause_event.is_set():
                    time.sleep(0.1)
                    # 暂停期间也要检查停止事件
                    if stop_event and stop_event.is_set():
                        log_and_emit(level='INFO', module='DeviceDriver', 
                                   content=f"Task stopped during {operation_name} operation",
                                   task_id=_task_id, test_case_id=_test_case_id)
                        sig = func.__annotations__.get('return')
                        if sig is bool or sig == 'bool':
                            return False
                        elif sig is dict or sig == 'dict':
                            return {"asr": "Stopped", "translation": "Stopped"}
                        elif sig is str or sig == 'str':
                            return "Stopped"
                        return

            return func(self, *args, **kwargs)

        return wrapper

    return decorator

def _get_default_return(func: Callable):
    """获取函数的默认返回值"""
    sig = func.__annotations__.get('return')
    if sig is bool or sig == 'bool':
        return False
    elif sig is dict or sig == 'dict':
        return {"asr": "Stopped", "translation": "Stopped"}
    elif sig is str or sig == 'str':
        return "Stopped"
    return None

