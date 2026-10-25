# -*- coding: utf-8 -*-
"""任务数据导入导出请求模型（INT-25）"""
from typing import List

from pydantic import Field

from shared.constants.data_transfer import DEFAULT_INCREMENTAL_INCLUDE
from shared.schemas.base import APIModel


class TaskDataExportRequest(APIModel):
    """POST /data-transfer/export 请求体"""
    task_ids: List[int] = Field(default_factory=list)
    include_ref_params: bool = Field(True)
    include_audios: bool = Field(False)


class TaskDataIncrementalExportRequest(APIModel):
    """POST /data-transfer/export-incremental 请求体（链路 2，INT-1761）

    契约字段为 camelCase（`taskIds` / `include`），APIModel 的 alias_generator
    同时接受 snake_case 拼写。
    """
    task_ids: List[int] = Field(default_factory=list)
    include: List[str] = Field(default_factory=lambda: list(DEFAULT_INCREMENTAL_INCLUDE))
