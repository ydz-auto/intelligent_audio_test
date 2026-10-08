# -*- coding: utf-8 -*-
"""任务数据导入导出 —— ID 重映射规划（纯函数，无 DB / 网络 / 存储依赖）

设计规格（INT-25）：导入时系统逐条自动判断 ID 策略——
原 ID 在目标库不存在则保持原值；已存在则去 id 交由 DB 自增分配新 ID 并记录映射。
全自动无用户选项。15 条外键转换规则来自 shared/constants/data_transfer.FK_RULES。

跨服务职责边界：
- 本模块负责 task_service 段（7 表）的规划；evaluation/report 段在各自服务的
  导入器内用 shared/utils/data_transfer 的原语做同构处理（服务边界禁止反向导入）。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Sequence, Set

from shared.constants.data_transfer import (
    FkMappingKey,
    FkRule,
    TransferTable,
    fk_rules_of,
)
from shared.utils.data_transfer import (
    apply_fk_mapping,
    build_id_mapping,
    conflicted_ids,
    strip_conflicting_ids,
)

# 四类映射键 → 对应主表（映射对象 = 这四张表的行；关联表不映射）
REMAP_TABLE_OF = {
    FkMappingKey.TASKS: TransferTable.TEST_TASKS,
    FkMappingKey.TEST_RESULTS: TransferTable.TEST_RESULTS,
    FkMappingKey.TEST_RESULT_DIMENSIONS: TransferTable.TEST_RESULT_DIMENSIONS,
    FkMappingKey.TEST_REPORTS: TransferTable.TEST_REPORTS,
}


@dataclass
class TablePlan:
    """单表导入规划结果"""
    table: TransferTable
    rows: List[dict] = field(default_factory=list)            # 冲突行已去 id 的待插入行
    conflicted_old_ids: List[int] = field(default_factory=list)  # 被去 id 的原主键（按行序，flush 后对应新 id）

    @property
    def row_count(self) -> int:
        return len(self.rows)


@dataclass
class ImportPlan:
    """一次导入的 15 表规划（task_service 段 + 转交远端服务的段）"""
    tables: Dict[str, TablePlan] = field(default_factory=dict)

    def get(self, table: TransferTable) -> TablePlan:
        return self.tables[table.value]

    def total_rows(self) -> int:
        return sum(plan.row_count for plan in self.tables.values())


def plan_task_segment(rows_by_table: Dict[str, List[dict]],
                      existing_ids_by_table: Dict[str, Set[int]]) -> ImportPlan:
    """对导出包内 task_service 段 7 表做冲突检测与 id 剥离（纯函数）。

    Args:
        rows_by_table: 表名 → 行列表（来自 ZIP db/*.json）
        existing_ids_by_table: 表名 → 目标库已存在主键集合
    """
    plan = ImportPlan()
    for table in TransferTable:
        rows = rows_by_table.get(table.value) or []
        if not rows:
            plan.tables[table.value] = TablePlan(table=table)
            continue
        existing = existing_ids_by_table.get(table.value) or set()
        stripped_rows = strip_conflicting_ids(rows, existing)
        conflicts = conflicted_ids(rows, existing)
        plan.tables[table.value] = TablePlan(
            table=table, rows=stripped_rows, conflicted_old_ids=conflicts)
    return plan


def build_table_mapping(all_old_ids: Sequence[int],
                        conflicted_old_ids: Sequence[int],
                        new_ids_of_conflicted: Sequence[int]) -> Dict[int, int]:
    """由 flush 结果构建一张表的完整 old→new 映射（无冲突记录映射到自身）。"""
    mapping = {old_id: old_id for old_id in all_old_ids}
    mapping.update(build_id_mapping(conflicted_old_ids, new_ids_of_conflicted))
    return mapping


def rewrite_fk_rows(rows: List[dict], rules: Sequence[FkRule],
                    mappings: Dict[FkMappingKey, Dict[int, int]]) -> List[dict]:
    """按规则表重写行外键（每条规则表达式统一为 mapping.get(old, old)）。"""
    current = rows
    for rule in rules:
        mapping = mappings.get(rule.mapping)
        if mapping:
            current = apply_fk_mapping(current, rule.column, mapping)
    return current


def filter_merge_relations(merge_rows: List[dict],
                           exported_task_ids: Set[int]) -> List[dict]:
    """TaskMergeRelation 仅保留 merged_task_id 与 source_task_id 都在导出集内的记录（防悬空外键）。"""
    return [
        row for row in merge_rows
        if row.get('merged_task_id') in exported_task_ids
        and row.get('source_task_id') in exported_task_ids
    ]


def collect_external_references(rows_by_table: Dict[str, List[dict]]) -> dict:
    """收集导出包内引用的外部配置实体 ID（不迁移不重映射，预检 warning 用）。

    返回 {test_case_ids, device_ids, api_ids}（元素统一转 str 便于比对）。
    """
    test_case_ids: Set[str] = set()
    device_ids: Set[str] = set()
    api_ids: Set[str] = set()
    for row in rows_by_table.get(TransferTable.TASK_CASE_RELATIONS.value, []):
        if row.get('test_case_id') is not None:
            test_case_ids.add(str(row['test_case_id']))
    for row in rows_by_table.get(TransferTable.TASK_DEVICE_RELATIONS.value, []):
        if row.get('device_id') is not None:
            device_ids.add(str(row['device_id']))
    for row in rows_by_table.get(TransferTable.TASK_API_RELATIONS.value, []):
        if row.get('api_id') is not None:
            api_ids.add(str(row['api_id']))
    for row in rows_by_table.get(TransferTable.TEST_RESULTS.value, []):
        if row.get('device_id') is not None:
            device_ids.add(str(row['device_id']))
    return {'test_case_ids': sorted(test_case_ids),
            'device_ids': sorted(device_ids),
            'api_ids': sorted(api_ids)}


def apply_result_file_key_remapping(rows: List[dict],
                                    tasks_mapping: Dict[int, int]) -> List[dict]:
    """计算导入后 test_results.result_data_path 的新存储 key（task_id 段重映射）。

    返回 [(old_path, new_key)]（仅 task_id 被重映射、且原路径可解析的行）；
    任务 ID 未变的行路径不变，不出现在结果里。
    """
    from shared.utils.data_transfer import parse_storage_path, remap_task_id_in_key
    changes: List[tuple] = []
    for row in rows:
        old_path = row.get('result_data_path')
        old_task_id = row.get('task_id')
        if not old_path or old_task_id is None:
            continue
        new_task_id = tasks_mapping.get(old_task_id, old_task_id)
        if new_task_id == old_task_id:
            continue
        _category, key = parse_storage_path(old_path)
        if not key:
            continue
        changes.append((old_path, remap_task_id_in_key(key, new_task_id)))
    return changes
