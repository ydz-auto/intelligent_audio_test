# -*- coding: utf-8 -*-
"""用例批量操作幂等存储（Redis 实现）— INT-75。

键空间：idempotency:testcase_batch:{key}，记录两态：
- 占位态 {'status': 'processing'}：SET NX 原子写入，防并发重复执行；
  TTL 取保留上限（防进程崩溃后占位永久卡死，到期自愈可重试）
- 完成态 {'status': 'completed', 'response': {...}}：执行成功后整体覆盖，
  TTL 窗口内同键重复提交直接回放响应，不重复执行

降级约定：Redis 不可用时 lookup 返回 None、reserve 放行、complete/release
静默失败——幂等退化为不生效，不阻塞业务主流程（与 EventBus 降级口径一致）。
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from task_service.domain.repositories.idempotency_repository import IdempotencyRepositoryABC

logger = logging.getLogger(__name__)

_KEY_PREFIX = 'idempotency:testcase_batch:'

_PROCESSING_RECORD = {'status': 'processing'}


class RedisIdempotencyStore(IdempotencyRepositoryABC):
    """基于 Redis SET NX / GET / SET EX / DEL 的幂等键存储。"""

    @staticmethod
    def _client():
        from shared.utils.redis_pubsub import RedisPubSub
        return RedisPubSub().redis_client

    def lookup(self, key: str) -> Optional[dict]:
        try:
            raw = self._client().get(_KEY_PREFIX + key)
        except Exception as e:
            logger.warning("[IdempotencyStore] lookup 降级放行（Redis 不可用）: %s", e)
            return None
        if not raw:
            return None
        try:
            if isinstance(raw, bytes):
                raw = raw.decode('utf-8')
            return json.loads(raw)
        except Exception:
            logger.warning("[IdempotencyStore] lookup 记录解析失败，按无记录处理 key=%s", key)
            return None

    def reserve(self, key: str, ttl_seconds: int) -> bool:
        try:
            ok = self._client().set(
                _KEY_PREFIX + key, json.dumps(_PROCESSING_RECORD), nx=True, ex=int(ttl_seconds)
            )
            return bool(ok)
        except Exception as e:
            logger.warning("[IdempotencyStore] reserve 降级放行（Redis 不可用）: %s", e)
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
            logger.warning("[IdempotencyStore] complete 写入失败（不影响业务结果）: %s", e)

    def release(self, key: str) -> None:
        try:
            self._client().delete(_KEY_PREFIX + key)
        except Exception as e:
            logger.warning("[IdempotencyStore] release 失败 key=%s: %s", key, e)


redis_idempotency_store = RedisIdempotencyStore()
