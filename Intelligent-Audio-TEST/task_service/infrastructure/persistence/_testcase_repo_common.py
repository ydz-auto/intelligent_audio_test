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

    INT-2240：id 值须整值匹配，不得命中前缀相同的维度（维度 3 不得命中
    30/31/300）。数字 id 在序列化产物里没有右边界标记，旧模式以裸 `%` 收尾，
    于是 `"id": 3%` 命中 `"id": 30` / `"id": 31` / `"id": 300`；列表 / 分组
    计数 / stats / fetch_case_ids（批量与导出圈定）因此成为超集。数字 id 右侧
    只会出现 `,`（非末项）或 `}`（末项），据此补两种右界；字符串 id 形态带
    闭合引号（`"id": "3"`），本就整值，保持原模式。

    跨方言约束：PG 侧 config 为 JSON 列（非 JSONB，没有 `@>` 包含算子），
    单测库是 SQLite，故保持文本 LIKE 口径；已对真实库比对确认整值
    边界匹配与 jsonb_path_exists 的维度语义判定结果完全一致。
    """
    escaped = dim_str.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    cast_text = TestCase.config.cast(Text)
    clauses = [
        # 字符串 id：闭合引号即右界
        cast_text.like(f'%"id": "{escaped}"%', escape='\\'),
        cast_text.like(f'%"id":"{escaped}"%', escape='\\'),
    ]
    for head in (f'%"id": {escaped}', f'%"id":{escaped}'):
        # 数字 id：值后紧跟 `,` 或 `}`
        clauses.append(cast_text.like(f'{head},%', escape='\\'))
        clauses.append(cast_text.like(f'{head}}}%', escape='\\'))
    return or_(*clauses)


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
