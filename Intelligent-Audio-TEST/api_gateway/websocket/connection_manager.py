"""
WebSocket 连接管理器 —— FastAPI 原生 WebSocket 实现

替代 Flask-SocketIO 的 connect/disconnect/set_filter/subscribe_task/unsubscribe_task 事件。
管理 sid → WebSocket 映射、task_id → [sid] 房间、sid → filter。
"""
import asyncio
import threading
from typing import Dict, List, Set, Optional, Any
from datetime import datetime, timezone, timedelta

from fastapi import WebSocket


class ConnectionManager:
    """WebSocket 连接管理器（线程安全）"""

    def __init__(self):
        self._connections: Dict[str, WebSocket] = {}       # sid → WebSocket
        self._filters: Dict[str, dict] = {}                 # sid → filter dict
        self._sid_task: Dict[str, str] = {}                  # sid → subscribed task_id
        self._task_sids: Dict[str, Set[str]] = {}            # task_id → {sid}
        self._lock = threading.RLock()
        self._main_loop: Optional[asyncio.AbstractEventLoop] = None  # 主线程事件循环引用

    async def connect(self, sid: str, websocket: WebSocket):
        await websocket.accept()
        # 保存主线程事件循环，供后台线程的 broadcast_log_sync 使用
        if self._main_loop is None:
            try:
                self._main_loop = asyncio.get_running_loop()
            except RuntimeError:
                pass
        with self._lock:
            self._connections[sid] = websocket

    def disconnect(self, sid: str):
        with self._lock:
            self._connections.pop(sid, None)
            self._filters.pop(sid, None)
            task_id = self._sid_task.pop(sid, None)
            if task_id and task_id in self._task_sids:
                self._task_sids[task_id].discard(sid)
                if not self._task_sids[task_id]:
                    del self._task_sids[task_id]

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

    async def send_to_sid(self, sid: str, data: dict):
        """向指定 sid 发送数据"""
        with self._lock:
            ws = self._connections.get(sid)
        if ws:
            try:
                await ws.send_json(data)
            except Exception:
                pass

    async def broadcast_log(self, log_data: dict):
        """广播日志到匹配的 WebSocket 连接（由 log_handler 调用）"""
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

        # 1) 全量频道：按 sid 过滤精准下发
        matched_sids = self.match(log_data)
        for sid in matched_sids:
            await self.send_to_sid(sid, {'type': 'LOG_BATCH', 'data': [log_payload]})

        # 2) 任务频道：广播给订阅了该 task 的连接
        task_id = log_data.get('task_id')
        if task_id:
            task_sids = self.get_task_sids(str(task_id))
            for sid in task_sids:
                await self.send_to_sid(sid, {'taskId': str(task_id), 'log': log_payload})

    def broadcast_log_sync(self, log_data: dict):
        """同步版本的广播（从 log_handler 后台线程调用，需桥接到 async）"""
        # 优先使用保存的主线程事件循环
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
            # 没有 event loop，创建一个
            try:
                asyncio.run(self.broadcast_log(log_data))
            except Exception:
                pass

    async def emit(self, event: str, data: dict):
        """
        向前端推送事件（替代 Flask-SocketIO 的 socketio.emit）。
        如果 data 包含 task_id，优先发送给订阅了该 task 的连接；否则广播给所有连接。
        """
        task_id = data.get('task_id') if isinstance(data, dict) else None
        payload = {'event': event, 'data': data}

        with self._lock:
            targets = list(self._connections.keys())

        if task_id:
            task_sids = self.get_task_sids(str(task_id))
            if task_sids:
                targets = task_sids

        for sid in targets:
            await self.send_to_sid(sid, payload)

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
