# -*- coding: utf-8 -*-
"""report_service ACL 小对象 TTL 缓存。

报告聚合按「每条测试结果」取设备 / API 等配置元数据（资源 key、版本号），同一批
配置在一次报告请求里被重复取几十到几百次（INT-1572 返工实测 case-averages 单次
277 次 GetDevice，10.8s）。这些配置在报告链路里只读且变化极少，按 id 做 TTL 缓存。

只缓存「取到了」的对象（负结果不缓存）：新建设备 / API 立即可见，避免配置刚建好
却因缓存显示成「未知设备」。并发安全，按插入顺序淘汰超出容量的条目。
"""
from __future__ import annotations

import copy
import threading
import time
from collections import OrderedDict
from typing import Any, Optional, Tuple


class TTLCache:
    """按 key 缓存任意对象，超过 TTL 或容量后淘汰。"""

    def __init__(self, ttl_seconds: float, max_entries: int) -> None:
        self._ttl = float(ttl_seconds)
        self._max_entries = max(int(max_entries), 1)
        self._data: "OrderedDict[str, Tuple[float, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._ttl > 0

    def get(self, key) -> Optional[Any]:
        """命中返回对象深拷贝，未命中 / 已过期返回 None。"""
        if not self.enabled:
            return None
        now = time.monotonic()
        with self._lock:
            entry = self._data.get(str(key))
            if entry is None:
                return None
            if now - entry[0] >= self._ttl:
                self._data.pop(str(key), None)
                return None
            self._data.move_to_end(str(key))
            return copy.deepcopy(entry[1])

    def set(self, key, value) -> None:
        if not self.enabled or value is None:
            return
        with self._lock:
            self._data[str(key)] = (time.monotonic(), copy.deepcopy(value))
            self._data.move_to_end(str(key))
            while len(self._data) > self._max_entries:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()
