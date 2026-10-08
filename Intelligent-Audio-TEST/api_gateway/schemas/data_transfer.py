# -*- coding: utf-8 -*-
"""任务数据导入导出请求模型（INT-25）"""
from typing import List

from pydantic import Field

from shared.schemas.base import APIModel


class TaskDataExportRequest(APIModel):
    """POST /data-transfer/export 请求体"""
    task_ids: List[int] = Field(default_factory=list)
    include_ref_params: bool = Field(True)
    include_audios: bool = Field(False)
