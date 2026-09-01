# -*- coding: utf-8 -*-
"""测试用例仓储公共小工具（从 testcase_repository.py 拆分，P4-5）。

被各 *_mixin.py 与主仓储文件共享，避免循环导入。
"""
from typing import List

from sqlalchemy import Text

from shared.utils.query_utils import now_cst
from task_service.infrastructure.persistence.models import TestCase


def _now():
    return now_cst()


def build_dim_id_filter(dim_str: str):
    """构建按维度 ID 过滤的 OR 条件（匹配 config JSON 中的 dimension id）。

    兼容 JSON 序列化时 id 与引号/空格的多种排列组合。
    """
    cast_text = TestCase.config.cast(Text)
    return (
        cast_text.like(f'"id": {dim_str}') |
        cast_text.like(f'"id":{dim_str}') |
        cast_text.like(f'"id": "{dim_str}"') |
        cast_text.like(f'"id":"{dim_str}"')
    )


def apply_keyword_like(query, column, keyword: str):
    """对列应用转义后的模糊匹配（统一 %/_ 转义，消除重复代码）。"""
    escaped = keyword.replace('%', '\\%').replace('_', '\\_')
    return query.filter(column.like(f'%{escaped}%', escape='\\'))
