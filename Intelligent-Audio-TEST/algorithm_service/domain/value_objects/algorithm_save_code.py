# -*- coding: utf-8 -*-
"""算法定义全量保存结果码（INT-589）。

归属：algorithm_service.domain.value_objects

AlgorithmResponse.code 字段的机器可读取值（拒绝魔法字符串，前端据此分支提示）：
- SAVED：新建成功（定义此前不存在，本次插入）
- OK：更新成功（定义已存在，本次整体落库）
- CONFLICT：乐观锁冲突（并发双写，expected_updated_at 已过期，
  前端提示「有他人改动，请刷新」）
- VALIDATION_FAILED：校验失败（必填缺失 / associated_dimensions 维度
  不存在 / algorithm_type 已存在等），不落任何数据

成功（SAVED/OK）时 success=True；CONFLICT/VALIDATION_FAILED 时
success=False 且 message 携带可读原因。
"""
from __future__ import annotations

from enum import Enum


class AlgorithmSaveCode(str, Enum):
    """算法定义全量保存结果码。"""

    SAVED = "SAVED"
    OK = "OK"
    CONFLICT = "CONFLICT"
    VALIDATION_FAILED = "VALIDATION_FAILED"
