# -*- coding: utf-8 -*-
"""人工复核 Schema（INT-340）——网关入参校验契约。

可改判状态全集（负责人 2026-10-15 拍板）：
- 执行状态：completed/failed/stopped/skipped（禁 pending/queued/running）
- 评估状态：completed/failed（双状态口径 status_fields_relationship.md §8.3）
"""
from typing import List, Optional

from pydantic import BaseModel, Field

# 业务码 → HTTP 状态码映射（后端 data.code 透传语义，对齐 INT-141 F2 口径）
_CODE_HTTP_MAP = {400: 400, 401: 401, 404: 404, 500: 500}

# 可改判状态全集（与 shared/utils/status_constants.py REVIEWABLE_* 同口径）
_REVIEWABLE_EXECUTION_STATUSES = frozenset({'completed', 'failed', 'stopped', 'skipped'})
_REVIEWABLE_EVALUATION_STATUSES = frozenset({'completed', 'failed'})


class ReviewSubmitRequest(BaseModel):
    """复核提交请求（POST /tasks/results/review，单条/批量逐条留痕）"""
    result_ids: List[int] = Field(..., min_length=1, description='执行结果 ID 集合（批量复核逐条留痕）')
    execution_status: Optional[str] = Field(None, description='执行状态改判（completed/failed/stopped/skipped）')
    evaluation_status: Optional[str] = Field(None, description='评估状态改判（completed/failed）')
    comment: str = Field(..., min_length=1, description='复核备注（必填）')

    def validate_statuses(self) -> Optional[str]:
        """校验改判状态枚举（返回错误消息或 None）。"""
        if self.execution_status and self.execution_status not in _REVIEWABLE_EXECUTION_STATUSES:
            return f'执行状态不可改判: {self.execution_status}（仅限 completed/failed/stopped/skipped）'
        if self.evaluation_status and self.evaluation_status not in _REVIEWABLE_EVALUATION_STATUSES:
            return f'评估状态不可改判: {self.evaluation_status}（仅限 completed/failed）'
        if not self.execution_status and not self.evaluation_status:
            return '执行状态/评估状态至少设置一项'
        return None
