"""
Socket.IO 服务端 —— 兼容前端 socket.io-client

前端连两个命名空间：
- '/'        （默认）：监听 task_progress / report_generated / secondary_compare_generated / import_progress
- '/ws/logs'          ：监听 task_log，emit subscribe_task / unsubscribe_task / set_filter

本模块替代旧的 ConnectionManager（原生 WebSocket），底层用 python-socketio。
对外暴露 sio_app（ASGI 子应用，挂到 FastAPI）和 ws_manager（兼容旧 API）。

UC-1001（INT-69）：任务订阅采用 Socket.IO 原生房间 room=task:{task_id}
（enter_room/leave_room），替代进程内 sid 映射逐 sid 推送 —— 多 api_gateway
实例下各副本只需向本副本已连接的房间投递，断连清理由 socket.io 原生完成。
"""
import asyncio
import logging
import threading
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta

import socketio

_logger = logging.getLogger(__name__)

# 任务房间名前缀（原生房间，room=task:{task_id}）
TASK_ROOM_PREFIX = 'task:'


def task_room(task_id) -> str:
    """task_id → Socket.IO 房间名"""
    return f'{TASK_ROOM_PREFIX}{task_id}'


class _SocketIOCompatManager:
    """
    旧 ConnectionManager 的兼容替身。

    保留 set_filter / subscribe_task / unsubscribe_task / match 等业务逻辑，
    底层连接/发送委托给 socketio.AsyncServer，任务订阅用原生房间。
    """

    def __init__(self, sio: socketio.AsyncServer):
        self._sio = sio
        self._filters: Dict[str, dict] = {}                 # sid → filter
        self._lock = threading.RLock()
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

    def set_filter(self, sid: str, filt: Optional[dict]):
        with self._lock:
            self._filters[sid] = filt or {}

    def get_filter(self, sid: str) -> Optional[dict]:
        with self._lock:
            return self._filters.get(sid)

    async def subscribe_task(self, sid: str, task_id: str):
        """订阅任务 → 加入原生房间 task:{task_id}"""
        await self._sio.enter_room(sid, task_room(task_id), namespace='/ws/logs')

    async def unsubscribe_task(self, sid: str):
        """退订任务 → 离开该 sid 在 '/ws/logs' 上的全部 task 房间"""
        for room in self._sio.rooms(sid, namespace='/ws/logs') or []:
            if isinstance(room, str) and room.startswith(TASK_ROOM_PREFIX):
                await self._sio.leave_room(sid, room, namespace='/ws/logs')

    def match(self, log_data: dict) -> List[str]:
        """返回通过过滤器的 sid 列表"""
        level = (log_data.get('level') or '').upper()
        module = (log_data.get('module') or '').upper()
        content = log_data.get('content') or ''
        log_task_id = log_data.get('task_id')
        matched = []
        with self._lock:
            filters = dict(self._filters)
        for sid, filt in filters.items():
            if not filt:
                matched.append(sid)
                continue
            levels = filt.get('levels')
            if levels:
                if level not in [l.upper() for l in levels]:
                    continue
            modules = filt.get('modules')
            if modules:
                if module not in [m.upper() for m in modules]:
                    continue
            kw = filt.get('keyword')
            if kw and kw not in content:
                continue
            ftid = filt.get('task_id')
            if ftid and str(log_task_id) != str(ftid):
                continue
            matched.append(sid)
        return matched

    # ── 事件绑定（由 sio_app 的 connect/disconnect 回调调用）──────────
    def on_connect(self, sid: str, namespace: str):
        if self._main_loop is None:
            try:
                self._main_loop = asyncio.get_running_loop()
            except RuntimeError as e:
                _logger.debug("on_connect 获取运行中事件循环失败: %s", e)

    def on_disconnect(self, sid: str, namespace: str):
        with self._lock:
            self._filters.pop(sid, None)
        # task 房间成员关系由 socket.io 断连时原生清理，无需手工维护

    # ── 推送 API（被事件转发线程调用）──────────────────────────────
    async def broadcast_log(self, log_data: dict):
        """推送 task_log 到 '/ws/logs' 命名空间。

        入参为 EventBus TASK_LOG 事件 payload：{'log_payload': {...}, 'task_id': ...}
        （兼容直接传扁平日志 dict）。任务日志投递原生房间 task:{task_id}；
        set_filter 命中的连接按过滤器逐 sid 下发（房间投递 skip_sid 去重）；
        无任务上下文的系统/审计日志沿用广播语义。
        """
        payload = log_data.get('log_payload') if isinstance(log_data, dict) else None
        if not isinstance(payload, dict):
            payload = log_data
        task_id = log_data.get('task_id') or payload.get('task_id')
        wire = {
            'task_id': str(task_id) if task_id else None,
            'log': payload,
        }

        matched_sids = self.match(payload)
        if task_id:
            room = task_room(task_id)
            try:
                if matched_sids:
                    # 房间投递跳过已按过滤器命中的 sid，避免重复下发
                    await self._sio.emit('task_log', wire, room=room,
                                         skip_sid=matched_sids, namespace='/ws/logs')
                    for sid in matched_sids:
                        await self._sio.emit('task_log', wire, to=sid, namespace='/ws/logs')
                else:
                    await self._sio.emit('task_log', wire, room=room, namespace='/ws/logs')
            except Exception as _e:
                _logger.debug("emit task_log to room=%s failed: %s", room, _e)
        else:
            if matched_sids:
                for sid in matched_sids:
                    try:
                        await self._sio.emit('task_log', wire, to=sid, namespace='/ws/logs')
                    except Exception as _e:
                        _logger.debug("emit task_log to sid=%s failed: %s", sid, _e)
            else:
                try:
                    await self._sio.emit('task_log', wire, namespace='/ws/logs')
                except Exception as _e:
                    _logger.debug("broadcast task_log failed: %s", _e)

    def broadcast_log_sync(self, log_data: dict):
        """同步版本（从事件转发线程调用，桥接到 async）"""
        loop = self._main_loop
        if loop is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self.broadcast_log(log_data), loop)
                return
            except Exception as _e:
                _logger.debug("broadcast_log_sync via main loop failed: %s", _e)
        # 回退：尝试获取当前线程的事件循环
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(self.broadcast_log(log_data), loop)
            else:
                loop.run_until_complete(self.broadcast_log(log_data))
        except RuntimeError:
            try:
                asyncio.run(self.broadcast_log(log_data))
            except Exception as _e:
                _logger.debug("broadcast_log_sync fallback failed: %s", _e)

    async def emit(self, event: str, data: dict):
        """向前端推送事件（默认命名空间 '/'，广播语义）"""
        try:
            await self._sio.emit(event, data, namespace='/')
        except Exception as _e:
            _logger.debug("emit event=%s failed: %s", event, _e)

    def emit_sync(self, event: str, data: dict):
        """同步版本的事件推送（从后台线程调用，桥接到 async）"""
        loop = self._main_loop
        if loop is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self.emit(event, data), loop)
                return
            except Exception as _e:
                _logger.debug("emit_sync event=%s via main loop failed: %s", event, _e)
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(self.emit(event, data), loop)
            else:
                loop.run_until_complete(self.emit(event, data))
        except RuntimeError:
            try:
                asyncio.run(self.emit(event, data))
            except Exception as _e:
                _logger.debug("emit_sync fallback failed: %s", _e)


# ── 创建全局 Socket.IO server + ASGI app ──────────────────────────
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    ping_interval=25,
    ping_timeout=20,
)
sio_app = socketio.ASGIApp(sio)

# 兼容管理器（业务逻辑层）
ws_manager = _SocketIOCompatManager(sio)


# ── 事件注册 ──────────────────────────────────────────────────────
@sio.on('connect', namespace='/')
async def _on_connect_main(sid, environ, auth=None):
    ws_manager.on_connect(sid, '/')


@sio.on('disconnect', namespace='/')
async def _on_disconnect_main(sid, *args, **kwargs):
    ws_manager.on_disconnect(sid, '/')


@sio.on('connect', namespace='/ws/logs')
async def _on_connect_logs(sid, environ, auth=None):
    ws_manager.on_connect(sid, '/ws/logs')


@sio.on('disconnect', namespace='/ws/logs')
async def _on_disconnect_logs(sid, *args, **kwargs):
    ws_manager.on_disconnect(sid, '/ws/logs')


@sio.on('subscribe_task', namespace='/ws/logs')
async def _on_subscribe(sid, data):
    task_id = str((data or {}).get('task_id', ''))
    if task_id:
        await ws_manager.subscribe_task(sid, task_id)


@sio.on('unsubscribe_task', namespace='/ws/logs')
async def _on_unsubscribe(sid, data):
    await ws_manager.unsubscribe_task(sid)


@sio.on('set_filter', namespace='/ws/logs')
async def _on_set_filter(sid, data):
    ws_manager.set_filter(sid, data)
