# -*- coding: utf-8 -*-
"""离线搬运 source_map 登记计划（INT-1760，纯函数层）

把「导入包内的原始行」+「导入实际产生的 old→new 主键映射」翻译成待登记的
source_map 条目。纯函数、不连库，供编排层在导入成功后一次 upsert。

登记口径（D0 A4 / 卡片范围）：
- 只登记**真正发生重映射**的条目（`source_id == local_id` 是等价映射，不登记）；
- 四类实体：tasks / test_results / test_result_dimensions / test_reports；
- 关联表自增主键不登记（无可翻译语义）；
- `source_task_id` 一律取包内行的**源任务 id**（A 原始 task_id），它是增量回导
  按任务取映射的查询键——不是本地 id，也不是逐级反查出来的本地任务。
"""
from typing import Dict, Iterable, List, Optional, Tuple

from shared.constants.data_transfer import SourceMapEntity, TransferTable


def _entry(source_server: str, source_task_id: int, entity_type: SourceMapEntity,
           source_id: int, local_id: int) -> dict:
    return {
        'source_server': source_server,
        'source_task_id': int(source_task_id),
        'entity_type': entity_type.value,
        'source_id': int(source_id),
        'local_id': int(local_id),
    }


def _int_or_none(value) -> Optional[int]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _result_task_index(rows_by_table: Dict[str, List[dict]]) -> Dict[int, int]:
    """包内 test_results 行：源结果 id → 源任务 id（维度行反查 source_task_id 用）"""
    index: Dict[int, int] = {}
    for row in rows_by_table.get(TransferTable.TEST_RESULTS.value) or []:
        source_id = _int_or_none(row.get('id'))
        task_id = _int_or_none(row.get('task_id'))
        if source_id is not None and task_id is not None:
            index[source_id] = task_id
    return index


def plan_source_map_entries(source_server: str,
                            rows_by_table: Dict[str, List[dict]],
                            mappings: Dict[str, Dict[int, int]],
                            ) -> Tuple[List[dict], List[str]]:
    """生成待登记条目。

    Args:
        source_server: 源服务稳定标识（manifest.serverInfo.source）
        rows_by_table: 导入包内的原始行（键为表名，值保留 A 原始 id）
        mappings: 导入产生的 old→new 映射（键为 FkMappingKey 值：
            tasks / test_results / test_result_dimensions / test_reports；
            值允许含映射到自身的条目，本函数自行过滤）

    Returns:
        (entries, warnings)：entries 按 (entity_type, local_id) 去重；
        warnings 记录无法确定 source_task_id 而跳过的行（不得静默丢弃）。
    """
    entries: List[dict] = []
    warnings: List[str] = []
    if not source_server:
        return entries, ['source_server 为空，source_map 不登记（所有映射都会失联）']

    def _map_of(key: SourceMapEntity) -> Dict[int, int]:
        return {int(k): int(v) for k, v in (mappings.get(key.value) or {}).items()}

    # 1) tasks：source_task_id == source_id == 源任务 id
    task_mapping = _map_of(SourceMapEntity.TASKS)
    for row in rows_by_table.get(TransferTable.TEST_TASKS.value) or []:
        source_id = _int_or_none(row.get('id'))
        if source_id is None:
            continue
        local_id = task_mapping.get(source_id, source_id)
        if local_id != source_id:
            entries.append(_entry(source_server, source_id,
                                  SourceMapEntity.TASKS, source_id, local_id))

    # 2) test_results：source_task_id 取包内结果行的 task_id
    result_mapping = _map_of(SourceMapEntity.TEST_RESULTS)
    result_task = _result_task_index(rows_by_table)
    for row in rows_by_table.get(TransferTable.TEST_RESULTS.value) or []:
        source_id = _int_or_none(row.get('id'))
        if source_id is None:
            continue
        local_id = result_mapping.get(source_id, source_id)
        if local_id == source_id:
            continue
        source_task_id = _int_or_none(row.get('task_id'))
        if source_task_id is None:
            warnings.append(f'test_results id={source_id} 缺 task_id，映射未登记')
            continue
        entries.append(_entry(source_server, source_task_id,
                              SourceMapEntity.TEST_RESULTS, source_id, local_id))

    # 3) test_result_dimensions：source_task_id 经源结果 id 反查
    dim_mapping = _map_of(SourceMapEntity.TEST_RESULT_DIMENSIONS)
    for row in rows_by_table.get(TransferTable.TEST_RESULT_DIMENSIONS.value) or []:
        source_id = _int_or_none(row.get('id'))
        if source_id is None:
            continue
        local_id = dim_mapping.get(source_id, source_id)
        if local_id == source_id:
            continue
        source_result_id = _int_or_none(row.get('test_result_id'))
        source_task_id = result_task.get(source_result_id) if source_result_id else None
        if source_task_id is None:
            warnings.append(
                f'test_result_dimensions id={source_id} 的源结果 '
                f'{source_result_id} 不在包内，映射未登记')
            continue
        entries.append(_entry(source_server, source_task_id,
                              SourceMapEntity.TEST_RESULT_DIMENSIONS, source_id, local_id))

    # 4) test_reports：source_task_id 取包内报告行的 task_id
    report_mapping = _map_of(SourceMapEntity.TEST_REPORTS)
    for row in rows_by_table.get(TransferTable.TEST_REPORTS.value) or []:
        source_id = _int_or_none(row.get('id'))
        if source_id is None:
            continue
        local_id = report_mapping.get(source_id, source_id)
        if local_id == source_id:
            continue
        source_task_id = _int_or_none(row.get('task_id'))
        if source_task_id is None:
            warnings.append(f'test_reports id={source_id} 缺 task_id，映射未登记')
            continue
        entries.append(_entry(source_server, source_task_id,
                              SourceMapEntity.TEST_REPORTS, source_id, local_id))

    return dedupe_entries(entries), warnings


def dedupe_entries(entries: Iterable[dict]) -> List[dict]:
    """按唯一键 (source_server, entity_type, local_id) 去重，后者覆盖前者。"""
    seen: Dict[Tuple[str, str, int], dict] = {}
    order: List[Tuple[str, str, int]] = []
    for entry in entries:
        key = (entry['source_server'], entry['entity_type'], int(entry['local_id']))
        if key not in seen:
            order.append(key)
        seen[key] = entry
    return [seen[key] for key in order]
