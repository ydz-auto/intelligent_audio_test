# -*- coding: utf-8 -*-
"""系统选项应用服务（INT-620）。

CQRS 边界：
- get_all（读侧）：全量 KV 拉取 = 库中已存行 ∪ 领域默认基线（未落库键回退
  默认、显式写入空值覆盖默认——与前端 use-system-options 按默认值类型安全
  解析的口径一致），读侧不产生写副作用。
- upsert（写侧）：单键 upsert，成功后发布 CONFIG_EVENTS / SYSTEM_OPTION_CHANGED
  （命令侧只写并发布事件；Redis 不可用时降级只打日志不阻塞业务）。
"""
import logging
from typing import Dict

from api_gateway.domain.entities.system_option import (
    SYSTEM_OPTION_DEFAULTS,
    SystemOptionValue,
)
from api_gateway.domain.repositories.system_option_repository import SystemOptionRepository
from api_gateway.infrastructure.system_option_repository import SystemOptionRepositoryImpl
from api_gateway.utils.response import error_response, success_response
from shared.utils.redis_pubsub import EventBus, EventChannel, EventType

logger = logging.getLogger(__name__)


class SystemOptionService:
    """系统选项应用服务（读侧 Query / 写侧 Command）。"""

    _repo: SystemOptionRepository = SystemOptionRepositoryImpl()

    @classmethod
    def get_all(cls):
        """全量 KV 拉取（读侧）：已存行 ∪ 领域默认基线。"""
        try:
            stored = cls._repo.get_all()
            merged = {**SYSTEM_OPTION_DEFAULTS, **stored}
            return success_response(data=merged)
        except Exception as e:
            logger.warning("读取系统选项失败", exc_info=True)
            return error_response(message=f"读取系统选项失败: {e}")

    @classmethod
    def upsert(cls, key: str, value: SystemOptionValue):
        """单键写入（写侧）：upsert 后发布 CONFIG_EVENTS 事件。"""
        try:
            cls._repo.upsert(key, value)
            cls._publish_changed(key)
            return success_response(message="设置已更新")
        except Exception as e:
            logger.warning("写入系统选项失败 key=%s", key, exc_info=True)
            return error_response(message=f"写入系统选项失败: {e}")

    @staticmethod
    def _publish_changed(key: str):
        """CQRS 命令侧发布系统选项变更事件（CONFIG_EVENTS 通道）。"""
        try:
            EventBus().publish(
                EventChannel.CONFIG_EVENTS,
                EventType.SYSTEM_OPTION_CHANGED,
                {'action': 'upsert', 'key': key},
            )
        except Exception as e:
            logger.warning("发布系统选项变更事件失败，降级忽略: %s", e)
