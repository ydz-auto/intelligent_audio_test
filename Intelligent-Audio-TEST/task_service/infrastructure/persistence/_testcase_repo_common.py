# -*- coding: utf-8 -*-
"""测试用例仓储公共小工具（从 testcase_repository.py 拆分，P4-5）。

被各 *_mixin.py 与主仓储文件共享，避免循环导入。
"""
from typing import List

from sqlalchemy import BigInteger, or_, Text

from shared.utils.query_utils import now_cst
from task_service.infrastructure.persistence.models import TestCase


def _now():
    return now_cst()


def build_dim_id_filter(dim_str: str):
    """构建按维度 ID 过滤的 OR 条件（匹配 config JSON 中的 dimension id）。

    兼容 JSON 序列化时 id 与引号/空格的多种排列组合。
    INT-146 修正：LIKE 需 % 通配符才是"包含"语义（无通配符为全串等值，
    恒不命中——与旧库同源缺陷，旧库注释意图即包含匹配）。
    """
    cast_text = TestCase.config.cast(Text)
    return (
        cast_text.like(f'%"id": {dim_str}%') |
        cast_text.like(f'%"id":{dim_str}%') |
        cast_text.like(f'%"id": "{dim_str}"%') |
        cast_text.like(f'%"id":"{dim_str}"%')
    )


def build_lab_id_filter(lab_ids: List[int]):
    """构建按实验室过滤的 OR 条件（含通用用例口径，INT-539）。

    通用用例语义：config JSONB 顶层无 lab_id（空/缺失）不受实验室约束，
    任意实验室下可选；有值则须属于已选实验室集合。
    SQL（Postgres）口径：(config->>'lab_id' IS NULL) OR
    ((config->>'lab_id')::bigint = ANY(:lab_ids))。

    注意：`config ->> 'lab_id'` 仅取顶层键，不会误命中嵌套字段
    （如 rounds 音频项），与 LIKE 方案的关键差异。调用方保证
    lab_ids 非空时才进入本过滤（空集合 = 不过滤）。
    """
    expr = TestCase.config.op('->>')('lab_id')
    generic = expr.is_(None)
    if not lab_ids:
        return generic
    return or_(generic, expr.cast(BigInteger).in_(list(lab_ids)))


def apply_keyword_like(query, column, keyword: str):
    """对列应用转义后的模糊匹配（统一 %/_ 转义，消除重复代码）。"""
    escaped = keyword.replace('%', '\\%').replace('_', '\\_')
    return query.filter(column.like(f'%{escaped}%', escape='\\'))
