# -*- coding: utf-8 -*-
"""导入批次登记（Redis HASH，供分段补偿回滚按主键删除）

每个服务的导入段共用一个 batch_id（编排方生成），各服务把本段插入的主键
登记到 data_transfer:batch:{batch_id} 的独立 field 下（field=服务名，
value=JSON {表名: [主键]}）。回滚 RPC 按本服务 field 取主键删除，互不干扰。

补偿自身失败必须显式报错要求人工介入，不得静默——登记数据保留 TTL 7 天。
"""
import json
from typing import Dict, List

from shared.constants.data_transfer import (
    BATCH_TTL_SECONDS,
    REDIS_BATCH_KEY_PREFIX,
)
from shared.utils.redis_pubsub import RedisStore


class TransferBatchRegistry:
    """导入批次主键登记（RedisStore 之上，无 DB 依赖）"""

    def __init__(self, store: RedisStore = None):
        self._store = store or RedisStore()

    @staticmethod
    def _key(batch_id: str) -> str:
        return f'{REDIS_BATCH_KEY_PREFIX}{batch_id}'

    def record(self, batch_id: str, service: str, tables_pks: Dict[str, List[int]]) -> None:
        """登记一个服务段插入的主键集合（覆盖同服务旧登记）。"""
        if not batch_id:
            raise ValueError('batch_id 不能为空')
        existing = self._store.load_task(self._key(batch_id))
        existing[service] = {'tables': tables_pks}
        self._store.save_task(self._key(batch_id), existing, ttl_seconds=BATCH_TTL_SECONDS)

    def load_service(self, batch_id: str, service: str) -> Dict[str, List[int]]:
        """读取某服务段登记的 {表名: [主键]}；批次或服务段不存在返回空 dict。"""
        data = self._store.load_task(self._key(batch_id))
        return data.get(service, {}).get('tables', {}) or {}

    def remove_service(self, batch_id: str, service: str) -> None:
        data = self._store.load_task(self._key(batch_id))
        data.pop(service, None)
        if data:
            self._store.save_task(self._key(batch_id), data, ttl_seconds=BATCH_TTL_SECONDS)
        else:
            self._store.delete_task(self._key(batch_id))

    def delete(self, batch_id: str) -> None:
        self._store.delete_task(self._key(batch_id))


transfer_batch_registry = TransferBatchRegistry()
