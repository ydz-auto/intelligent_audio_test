from flask import Blueprint, Response, request, stream_with_context
import json
import time
import threading
from datetime import datetime, timezone, timedelta

# 创建 SSE 蓝图
sse_bp = Blueprint('sse_bp', __name__)

# SSE 客户端连接管理
class SSEManager:
    def __init__(self):
        self.clients = {}
        self.lock = threading.RLock()
        self.last_event_id = 0
    
    def add_client(self, client_id, callback):
        """添加新的 SSE 客户端"""
        with self.lock:
            self.clients[client_id] = callback
    
    def remove_client(self, client_id):
        """移除 SSE 客户端"""
        with self.lock:
            if client_id in self.clients:
                del self.clients[client_id]
    
    def get_clients(self):
        """获取所有 SSE 客户端"""
        with self.lock:
            return list(self.clients.items())
    
    def get_next_event_id(self):
        """获取下一个事件 ID"""
        with self.lock:
            self.last_event_id += 1
            return self.last_event_id

# 创建全局 SSE 管理器实例
sse_manager = SSEManager()

# 事件缓存，用于新连接时发送最近的事件
class EventCache:
    def __init__(self, max_size=100):
        self.cache = []
        self.max_size = max_size
        self.lock = threading.RLock()
    
    def add_event(self, event_type, data):
        """添加事件到缓存"""
        with self.lock:
            event = {
                'id': sse_manager.get_next_event_id(),
                'type': event_type,
                'data': data,
                'timestamp': datetime.now(timezone(timedelta(hours=8)))
            }
            self.cache.append(event)
            if len(self.cache) > self.max_size:
                self.cache.pop(0)
    
    def get_recent_events(self, since_id=None):
        """获取最近的事件"""
        with self.lock:
            if since_id is None:
                return self.cache
            return [event for event in self.cache if event['id'] > since_id]

# 创建全局事件缓存实例
event_cache = EventCache()

def format_sse(data, event=None, event_id=None):
    """格式化 SSE 事件"""
    messages = []
    if event_id:
        messages.append(f"id: {event_id}")
    if event:
        messages.append(f"event: {event}")
    if isinstance(data