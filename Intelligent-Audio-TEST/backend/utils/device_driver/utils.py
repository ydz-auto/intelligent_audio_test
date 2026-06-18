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

