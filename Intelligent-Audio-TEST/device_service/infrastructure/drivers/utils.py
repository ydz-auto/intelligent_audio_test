import time
import subprocess
import re
import functools
import threading
from typing import Callable

from shared.utils.log_handler import log_and_emit

_task_control_events = {}
_task_control_lock = threading.Lock()
# 任务控制事件兜底清理: 超过该时长未被活跃访问(=24h)的条目视为过期可安全删除,
# 防止调用方(客户端掉线等)未走 UnregisterTaskEvents 导致条目只增不减的内存泄漏。
_TASK_EVENT_TTL_SECONDS = 24 * 3600
_TASK_EVENTS_PRUNE_INTERVAL = 60  # 清理节流间隔(秒),避免每次 get 都全量扫描
_task_events_last_prune = 0.0

try:
    from hypium import UiDriver, BY as By, MatchPattern
except Exception as e:
    # 提升到 ERROR 级别：hypium 依赖 devicetest 包，缺失会导致所有鸿蒙设备初始化失败
    _hint = ""
    if "No module named 'devicetest'" in str(e):
        _hint = "（根因：devicetest 包未安装，请执行 pip install devicetest 或安装 DevEco Testing 框架）"
    log_and_emit(level='ERROR', module='DeviceDriver',
                 content=f"Failed to import hypium: {e}{_hint} → UiDriver=None，鸿蒙驱动将不可用")
    UiDriver = None
    By = None
    MatchPattern = None


def restart_uitest_daemon(device_sn):
    """重启设备端 uitest RPC 服务（RpcNotRunningError 恢复用）

    通过 hdc 执行: 先 kill 旧进程, 再 start-daemon singleness 启动新进程。
    """
    try:
        # 先清理旧进程
        subprocess.run(['hdc', '-t', device_sn, 'shell',
                        'pkill', '-f', 'uitest'],
                       check=False, timeout=10)
        time.sleep(1)
        # 启动新 daemon
        subprocess.run(['hdc', '-t', device_sn, 'shell',
                        'uitest', 'start-daemon', 'singleness'],
                       check=False, timeout=30)
        time.sleep(2)
        log_and_emit(level='INFO', module='DeviceDriver',
                     content=f"uitest daemon restarted for device {device_sn}")
        return True
    except Exception as e:
        log_and_emit(level='ERROR', module='DeviceDriver',
                     content=f"Failed to restart uitest daemon for {device_sn}: {e}")
        return False


def is_rpc_not_running_error(exc):
    """判断异常是否为 RPC 服务未运行（RpcNotRunningError）"""
    msg = str(exc).lower()
    return 'rpc' in msg and ('not running' in msg or 'not found' in msg or 'listening port' in msg)


def with_rpc_retry(max_retries=1):
    """装饰器: 捕获 RpcNotRunningError 时自动重启 uitest daemon 并重连重试

    Args:
        max_retries: RPC 恢复后最大重试次数, 默认 1 次
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            last_exc = None
            for attempt in range(max_retries + 1):
                try:
                    return func(self, *args, **kwargs)
                except Exception as e:
                    last_exc = e
                    if not is_rpc_not_running_error(e):
                        raise
                    if attempt >= max_retries:
                        raise
                    # 从 args 提取 device_sn (通常是第一个位置参数)
                    device_sn = None
                    if args:
                        device_sn = args[0]
                    elif 'device_sn' in kwargs:
                        device_sn = kwargs['device_sn']
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

def _prune_task_events_locked(now):
    """清理过期任务控制事件(保守兜底)。

    仅清理超过 TTL 未被活跃访问(注册/获取会刷新时间戳)的条目;正在运行的任务
    会持续 get 刷新,不受影响;长跑任务哪怕未 unregister,也因其持有 event 引用
    依然可控。带节流(至少间隔 60s 扫一次)。调用方必须持有 _task_control_lock。
    """
    global _task_events_last_prune
    if now - _task_events_last_prune < _TASK_EVENTS_PRUNE_INTERVAL:
        return
    _task_events_last_prune = now
    ttl = _TASK_EVENT_TTL_SECONDS
    for tid, ev in list(_task_control_events.items()):
        if now - ev.get('registered_at', now) > ttl:
            _task_control_events.pop(tid, None)
            log_and_emit(level='DEBUG', module='DeviceDriver',
                         content=f"清理过期任务控制事件(>24h未活跃): task_id={tid}")


def register_task_events(task_id, stop_event, pause_event=None):
    """注册任务的控制事件，供驱动实时获取"""
    global _task_control_events
    with _task_control_lock:
        _task_control_events[task_id] = {
            'stop_event': stop_event,
            'pause_event': pause_event,
            'registered_at': time.time()
        }
        _prune_task_events_locked(time.time())


def get_task_events(task_id):
    """获取任务的控制事件（实时获取最新引用）"""
    global _task_control_events
    with _task_control_lock:
        ev = _task_control_events.get(task_id)
        if ev is not None:
            # 活跃访问刷新时间戳,保证长生命周期任务不被误清理
            ev['registered_at'] = time.time()
        _prune_task_events_locked(time.time())
        return ev


def unregister_task_events(task_id):
    """注销任务的控制事件"""
    global _task_control_events
    with _task_control_lock:
        # pop 语义: 条目不存在时静默返回,避免重复注销抛 KeyError
        _task_control_events.pop(task_id, None)

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

