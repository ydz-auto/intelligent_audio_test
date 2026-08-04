"""事件管理器包。

将原 event_manager.py（单文件 ~36KB）按职责拆分为多个 mixin 模块，
对外通过 __init__ 重新导出 EventManager 类与 get_socketio 函数，
保持向后兼容（``from shared.utils.event_manager import EventManager`` 仍可正常使用）。
"""
from shared.utils.event_manager._common import get_socketio
from shared.utils.event_manager._manager import EventManager

__all__ = ['EventManager', 'get_socketio']
