"""
Socket.IO 服务端 —— 兼容前端 socket.io-client

前端连两个命名空间：
- '/'        （默认）：监听 task_progress / report_generated / secondary_compare_generated
- '/ws/logs'          ：监听 task_log，emit subscribe_task / unsubscribe_task / set_filter

本模块替代旧的 ConnectionManager（原生 WebSocket），底层用 python-socketio。
对外暴露 sio_app（ASGI 子应用，挂到 FastAPI）和 ws_manager（兼容旧 API）。
"""
import asyncio
import threading
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta

import socketio


class _SocketIOCompatManager:
    """
    旧 ConnectionManager 的兼容替身。

    保留 set_filter / subscribe_task / unsubscribe_task / match 等业务逻辑，
    底层连接/发送改为委托给 socketio.AsyncServer。
    """

    def __init__(self, sio: socketio.AsyncServer):
        self._sio = sio
        self._filters: Dict[str, dict] = {}                 # sid → filter
        self._sid_task: Dict[str, str] = {}                  # sid → subscribed task_id
        self._task_sids: Dict[str, set] = {}                 # task_id → {sid}
        self._lock = threading.RLock()
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None

    def set_filter(self, sid: str, filt: Optional[dict]):
        with self._lock:
            self._filters[sid] = filt or {}

    def get_filter(self, sid: str) -> Optional[dict]:
        with self._lock:
            return self._filters.get(sid)

    def subscribe_task(self, sid: str, task_id: str):
        with self._lock:
            old_task = self._sid_task.get(sid)
            if old_task and old_task in self._task_sids:
                self._task_sids[old_task].discard(sid)
            self._sid_task[sid] = task_id
            if task_id not in self._task_sids:
                self._task_sids[task_id] = set()
            self._task_sids[task_id].add(sid)

    def unsubscribe_task(self, sid: str):
        with self._lock:
            task_id = self._sid_task.pop(sid, None)
            if task_id and task_id in self._task_sids:
                self._task_sids[task_id].discard(sid)

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

    def get_task_sids(self, task_id: str) -> List[str]:
        with self._lock:
            return list(self._task_sids.get(task_id, set()))

    # ── 事件绑定（由 sio_app 的 connect/disconnect 回调调用）──────────
    def on_connect(self, sid: str, namespace: str):
        if self._main_loop is None:
            try:
                self._main_loop = asyncio.get_running_loop()
            except RuntimeError:
                pass

    def on_disconnect(self, sid: str, namespace: str):
        with self._lock:
            self._filters.pop(sid, None)
            task_id = self._sid_task.pop(sid, None)
            if task_id and task_id in self._task_sids:
                self._task_sids[task_id].discard(sid)

    # ── 推送 API（被 log_handler 后台线程调用）──────────────────────
    async def broadcast_log(self, log_data: dict):
        """广播日志到匹配的连接：'/ws/logs' 命名空间推 task_log 事件"""
        log_payload = {
            "id": log_data.get('id'),
            "time": log_data.get('_ws_time') or datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S'),
            "level": log_data.get('level'),
            "module": log_data.get('module'),
            "content": log_data.get('content'),
            "mark": "",
            "task_id": log_data.get('task_id'),
            "test_case_id": log_data.get('test_case_id'),
            "category": log_data.get('category'),
            "source": log_data.get('source'),
        }

        # 1) 按过滤器精准下发到 '/ws/logs' 命名空间
        matched_sids = self.match(log_data)
        if matched_sids:
            # 有过滤器时，只发给匹配的 sid
            for sid in matched_sids:
                try:
                    await self._sio.emit('task_log', log_payload, to=sid, namespace='/ws/logs')
                except Exception:
                    pass
        else:
            # 没有客户端设过 filter → 广播给 '/ws/logs' 命名空间所有连接
            try:
                await self._sio.emit('task_log', log_payload, namespace='/ws/logs')
            except Exception:
                pass

        # 2) 订阅了 task_id 的连接也推一份
        task_id = log_data.get('task_id')
        if task_id:
            task_sids = self.get_task_sids(str(task_id))
            for sid in task_sids:
                try:
                    await self._sio.emit('task_log', log_payload, to=sid, namespace='/ws/logs')
                except Exception:
                    pass

    def broadcast_log_sync(self, log_data: dict):
        """同步版本（从 log_handler 后台线程调用，桥接到 async）"""
        loop = self._main_loop
        if loop is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self.broadcast_log(log_data), loop)
                return
            except Exception:
                pass
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
            except Exception:
                pass

    async def emit(self, event: str, data: dict):
        """向前端推送事件（默认命名空间 '/'）。如 data 含 task_id，发给订阅该 task 的连接"""
        task_id = data.get('task_id') if isinstance(data, dict) else None
        targets = None
        if task_id:
            targets = self.get_task_sids(str(task_id))
        try:
            if targets:
                for sid in targets:
                    await self._sio.emit(event, data, to=sid, namespace='/')
            else:
                await self._sio.emit(event, data, namespace='/')
        except Exception:
            pass

    def emit_sync(self, event: str, data: dict):
        """同步版本的事件推送（从后台线程调用，桥接到 async）"""
        loop = self._main_loop
        if loop is not None and loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self.emit(event, data), loop)
                return
            except Exception:
                pass
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.run_coroutine_threadsafe(self.emit(event, data), loop)
            else:
                loop.run_until_complete(self.emit(event, data))
        except RuntimeError:
            try:
                asyncio.run(self.emit(event, data))
            except Exception:
                pass


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
        ws_manager.subscribe_task(sid, task_id)


@sio.on('unsubscribe_task', namespace='/ws/logs')
async def _on_unsubscribe(sid, data):
    ws_manager.unsubscribe_task(sid)


@sio.on('set_filter', namespace='/ws/logs')
async def _on_set_filter(sid, data):
    ws_manager.set_filter(sid, data)
