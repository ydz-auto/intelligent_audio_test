# -*- coding: utf-8 -*-
"""设备批量操作幂等存储（Redis 实现，INT-80）。

键空间：idempotency:device_batch:{key}，两态记录（processing/completed），
模式对齐 task_service 幂等存储（INT-75）。
降级约定：Redis 不可用时 lookup 返回 None、reserve 放行、complete/release
静默失败——幂等退化为不生效，不阻塞业务主流程。
"""
from __future__ import annotations

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_KEY_PREFIX = 'idempotency:device_batch:'

_PROCESSING_RECORD = {'status': 'processing'}


class RedisDeviceIdempotencyStore:
    """基于 Redis SET NX / GET / SET EX / DEL 的设备批量幂等键存储。"""

    @staticmethod
    def _client():
        from shared.utils.redis_pubsub import RedisPubSub
        return RedisPubSub().redis_client

    def lookup(self, key: str) -> Optional[dict]:
        try:
            raw = self._client().get(_KEY_PREFIX + key)
        except Exception as e:
            logger.warning("[DeviceIdempotencyStore] lookup 降级放行（Redis 不可用）: %s", e)
            return None
        if not raw:
            return None
        try:
            if isinstance(raw, bytes):
                raw = raw.decode('utf-8')
            return json.loads(raw)
        except Exception:
            logger.warning("[DeviceIdempotencyStore] lookup 记录解析失败，按无记录处理 key=%s", key)
            return None

    def reserve(self, key: str, ttl_seconds: int) -> bool:
        try:
            ok = self._client().set(
                _KEY_PREFIX + key, json.dumps(_PROCESSING_RECORD), nx=True, ex=int(ttl_seconds)
            )
            return bool(ok)
        except Exception as e:
            logger.warning("[DeviceIdempotencyStore] reserve 降级放行（Redis 不可用）: %s", e)
            return True

    def complete(self, key: str, response: dict, ttl_seconds: int) -> None:
        try:
            record = {'status': 'completed', 'response': response}
            self._client().set(
                _KEY_PREFIX + key,
                json.dumps(record, ensure_ascii=False, default=str),
                ex=int(ttl_seconds),
            )
        except Exception as e:
            logger.warning("[DeviceIdempotencyStore] complete 写入失败（不影响业务结果）: %s", e)

    def release(self, key: str) -> None:
        try:
            self._client().delete(_KEY_PREFIX + key)
        except Exception as e:
            logger.warning("[DeviceIdempotencyStore] release 失败 key=%s: %s", key, e)


redis_device_idempotency_store = RedisDeviceIdempotencyStore()
