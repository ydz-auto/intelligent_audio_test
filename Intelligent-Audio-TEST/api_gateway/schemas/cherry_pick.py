# -*- coding: utf-8 -*-
"""挑选合并 Schema（INT-339）——网关入参校验契约。

页面文案一律中文（站内不出现 Cherry-Pick 字样，接口路径除外——§1.2 口径）；
接口路径 /tasks/cherry-picks/** 为设计文档 §8 约定的技术标识，不受文案红线约束。
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# 业务码 → HTTP 状态码映射（后端 data.code 透传语义，对齐 INT-141 F2 口径）
_CODE_HTTP_MAP = {400: 400, 401: 401, 404: 404, 500: 500}


class CherryPickCartAddRequest(BaseModel):
    """加入购物车请求（POST /tasks/cherry-picks/cart/items）"""
    result_ids: List[int] = Field(..., description='源执行结果 ID 集合（溯源快照由后端提取）')


class CherryPickCartRemoveRequest(BaseModel):
    """从购物车移除请求（POST /tasks/cherry-picks/cart/items/remove）"""
    item_ids: List[int] = Field(..., description='购物车条目 ID 集合')


class CherryPickSaveSetRequest(BaseModel):
    """购物车另存为挑选集请求（POST /tasks/cherry-picks/cart/save-as-set）"""
    name: str = Field(..., min_length=1, max_length=255, description='挑选集名称（同名允许重复保存）')
    description: Optional[str] = Field(None, description='挑选集描述')


class CherryPickCandidatesQuery(BaseModel):
    """挑选候选查询参数（GET /tasks/cherry-picks/candidates，多条件 AND）

    多值字段为逗号分隔 ID 串（GET 查询串契约，BFF 层拆分）。
    """
    task_ids: str = Field('', description='来源任务 ID（逗号分隔）')
    device_ids: str = Field('', description='被测设备 ID（逗号分隔，点名维度）')
    case_ids: str = Field('', description='用例 ID（逗号分隔，点名维度）')
    case_keyword: Optional[str] = Field(None, description='用例关键字模糊搜索（INT-401：命中用例名/用例ID，与 case_ids 精确 IN 语义区分）')
    execution_status: Optional[str] = Field(None, description='结果执行状态过滤')
    evaluation_status: Optional[str] = Field(None, description='评估状态（evaluated/pending）')
    start_date: Optional[str] = Field(None, description='结果执行时间起（ISO）')
    end_date: Optional[str] = Field(None, description='结果执行时间止（ISO）')
    page: int = Field(1, ge=1)
    per_page: int = Field(50, ge=1, le=200)


class CherryPickCheckoutRequest(BaseModel):
    """下单请求（POST /tasks/cherry-picks/cart/checkout，三出口）"""
    action: str = Field('merge', description='下单出口：merge/reexecute/reevaluate')
    name: Optional[str] = Field(None, description='新任务名称（merge/reexecute 出口）')
    description: Optional[str] = Field(None, description='新任务描述')
    algorithm_type: Optional[str] = Field(None, description='任务级算法类型覆盖（§5.2）')
    algorithm_params: Optional[Dict[str, Any]] = Field(None, description='任务级算法参数覆盖（§5.2）')
    config: Optional[Dict[str, Any]] = Field(None, description='任务级配置覆盖（§5.2）')
