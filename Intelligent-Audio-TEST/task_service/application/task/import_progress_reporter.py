# -*- coding: utf-8 -*-
"""导入进度推送（M5）

task_service 经 EventBus TASK_EVENTS / import_progress 发布（网关订阅五通道后
转 SocketIO emit），同步写 Redis HASH 快照供 GET /import/progress 兜底。
payload 契约见 shared/schemas/socket_payloads.ImportProgressPayload。
"""
from typing import Optional

from shared.constants.data_transfer import (
    PROGRESS_TTL_SECONDS,
    REDIS_PROGRESS_KEY,
    ImportProgressStep,
)
from shared.schemas.socket_payloads import ImportProgressPayload
from shared.utils.redis_pubsub import EventBus, EventChannel, EventType, RedisStore

# 各阶段完成时的基础百分比（writing_db 阶段内部按行数推进）
_STEP_BASE_PERCENT = {
    ImportProgressStep.PARSING.value: 0,
    ImportProgressStep.WRITING_DB.value: 5,
    ImportProgressStep.EXTRACTING_FILES.value: 70,
    ImportProgressStep.UPDATING_PATHS.value: 90,
    ImportProgressStep.DONE.value: 100,
}


class ImportProgressReporter:
    """导入进度报告器：发布 + 快照双通道"""

    def __init__(self, batch_id: str):
        self._batch_id = batch_id
        self._store = RedisStore()
        self._total_rows = 0
        self._processed_rows = 0
        self._current_table = ''
        self._last_payload: Optional[dict] = None

    def set_total_rows(self, total_rows: int) -> None:
        self._total_rows = max(int(total_rows), 0)

    def advance_rows(self, processed: int) -> None:
        self._processed_rows = processed

    def report(self, step: ImportProgressStep,
               message: str = '',
               current_table: str = '') -> dict:
        payload = ImportProgressPayload(
            step=step.value,
            current_table=current_table or self._current_table,
            processed_rows=self._processed_rows,
            total_rows=self._total_rows,
            percentage=self._percentage(step),
            message=message,
        ).model_dump()
        self._current_table = payload['current_table']
        self._last_payload = payload
        try:
            EventBus().publish(EventChannel.TASK_EVENTS, EventType.IMPORT_PROGRESS,
                               {'event': 'import_progress', 'data': payload})
        except Exception:
            pass  # 进度推送失败不阻塞导入主流程
        self._save_snapshot()
        return payload

    def table_progress(self, table: str, processed_rows: int,
                       message: str = '') -> dict:
        """writing_db 阶段内按表推进"""
        self._current_table = table
        self._processed_rows = processed_rows
        return self.report(ImportProgressStep.WRITING_DB,
                           message=message or f'正在写入 {table}',
                           current_table=table)

    def _percentage(self, step: ImportProgressStep) -> float:
        base = _STEP_BASE_PERCENT.get(step.value, 0)
        if step is ImportProgressStep.DONE:
            return 100.0
        if step is ImportProgressStep.WRITING_DB and self._total_rows > 0:
            span = (_STEP_BASE_PERCENT[ImportProgressStep.EXTRACTING_FILES.value]
                    - _STEP_BASE_PERCENT[ImportProgressStep.WRITING_DB.value])
            return round(base + span * (self._processed_rows / self._total_rows), 1)
        return float(base)

    def _save_snapshot(self) -> None:
        if not self._last_payload:
            return
        try:
            self._store.save_task(REDIS_PROGRESS_KEY,
                                  dict(self._last_payload, batch_id=self._batch_id),
                                  ttl_seconds=PROGRESS_TTL_SECONDS)
        except Exception:
            pass  # 快照失败不阻塞导入主流程


def load_progress_snapshot() -> dict:
    """读取最近一次导入进度快照（网关 GET /import/progress 兜底）"""
    store = RedisStore()
    return store.load_task(REDIS_PROGRESS_KEY)
