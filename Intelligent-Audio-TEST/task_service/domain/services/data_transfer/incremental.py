# -*- coding: utf-8 -*-
"""增量包（链路 2）领域服务：id 翻译 / 指纹 / 维度定义匹配（纯函数，不连库）

设计依据：《任务数据离线搬运与增量回导功能设计文档》§5.2/§5.4 + D0 裁定 A1/A2/A7。

口径（与整包链路的关键差异）：
- 增量包内 id 已是 **A 原始 id**（导出侧经 source_map 翻译），导入侧不重映射；
- 唯一例外是 `test_result_dimensions.dimension_id`：它保留 **B 侧维度 id**，
  A 侧按 `(name, 父维度链, task_type_code)` 匹配到 A 的 `dimensions.id`；
  匹配不到的行跳过并计入 warnings，绝不直写 B 的 dimension_id（A2-4）；
- 指纹 `caseSetHash = sha256(','.join(sorted(test_case_ids)))`（A7）。
"""
import hashlib
from typing import Dict, Iterable, List, Optional, Tuple

from shared.constants.data_transfer import (
    INCREMENTAL_REPORT_TABLES,
    TransferTable,
)

# 报告 7 表的表名集合（子表 6 张）
_REPORT_TABLE_NAMES = tuple(table.value for table in INCREMENTAL_REPORT_TABLES)
_CHILD_REPORT_TABLES = _REPORT_TABLE_NAMES[1:]


def _int_or_none(value) -> Optional[int]:
    if value is None or isinstance(value, bool) or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def case_set_hash(case_ids: Iterable) -> str:
    """任务用例集指纹（A7）：sha256(','.join(sorted(test_case_ids)))

    空集合也有确定的哈希（sha256('')），不会与「无指纹」混淆。
    """
    normalized = sorted({str(cid) for cid in (case_ids or []) if cid is not None and cid != ''})
    return hashlib.sha256(','.join(normalized).encode('utf-8')).hexdigest()


# ---------- 导出侧翻译（B 本地 id → A 原始 id）----------

def translate_dimension_rows(rows: List[dict],
                             result_local_to_source: Dict[int, int],
                             ) -> Tuple[List[dict], List[int]]:
    """把维度行 `test_result_id` 从 B 本地 id 翻译回 A 原始 id。

    `dimension_id` 原样保留 B 侧值（由 A 侧按维度定义链翻译，A2-4）。

    Returns:
        (translated_rows, unmapped_result_ids)：存在未映射结果行时调用方必须
        整包拒绝（409 + data.unmappedResultIds，A2-2 导出侧硬闸）。
    """
    translated: List[dict] = []
    unmapped: set = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        local_result_id = _int_or_none(row.get('test_result_id'))
        if local_result_id is None:
            continue
        source_result_id = result_local_to_source.get(local_result_id)
        if source_result_id is None:
            unmapped.add(local_result_id)
            continue
        rewritten = dict(row)
        rewritten['test_result_id'] = int(source_result_id)
        translated.append(rewritten)
    return translated, sorted(unmapped)


def translate_report_tables(tables: Dict[str, List[dict]],
                            task_local_to_source: Dict[int, int],
                            report_local_to_source: Dict[int, int],
                            ) -> Tuple[Dict[str, List[dict]], List[int]]:
    """把报告 7 表的 task_id / report_id 翻译回 A 原始 id。

    - `test_reports.task_id` 必须能翻译，否则整包拒绝（返回未映射任务 id）；
    - `test_reports.id` 有映射时改写为 A 原报告 id；**无映射时清除该行 id**
      （B 侧 `regenerate_report` 删旧建新后的新报告，A 侧按「任务下最新报告」
      或新建定位，A5-2），同时子表行的 `report_id` 也一并清除，由 A 侧替换时
      统一改写到目标报告 id——不留 B 的 id 去撞 A 的 id 空间。
    """
    result: Dict[str, List[dict]] = {name: [] for name in _REPORT_TABLE_NAMES}
    unmapped_task_ids: set = set()

    report_rows = tables.get(TransferTable.TEST_REPORTS.value) or []
    kept_report_ids: set = set()
    for row in report_rows:
        if not isinstance(row, dict):
            continue
        local_task_id = _int_or_none(row.get('task_id'))
        source_task_id = task_local_to_source.get(local_task_id) if local_task_id else None
        if source_task_id is None:
            if local_task_id is not None:
                unmapped_task_ids.add(local_task_id)
            continue
        rewritten = dict(row)
        rewritten['task_id'] = int(source_task_id)
        local_report_id = _int_or_none(row.get('id'))
        source_report_id = report_local_to_source.get(local_report_id) if local_report_id else None
        if source_report_id is not None:
            rewritten['id'] = int(source_report_id)
        else:
            rewritten.pop('id', None)  # B 新建报告：不带 id 进包（A 侧重新定位目标）
        kept_report_ids.add(local_report_id)
        result[TransferTable.TEST_REPORTS.value].append(rewritten)

    for table in _CHILD_REPORT_TABLES:
        for row in tables.get(table) or []:
            if not isinstance(row, dict):
                continue
            local_report_id = _int_or_none(row.get('report_id'))
            if local_report_id is None:
                continue
            # 只带被保留父行的子表行（防包内孤儿子行）
            if local_report_id not in kept_report_ids:
                continue
            rewritten = dict(row)
            source_report_id = report_local_to_source.get(local_report_id)
            if source_report_id is not None:
                rewritten['report_id'] = int(source_report_id)
            else:
                rewritten.pop('report_id', None)  # 无 id 父行 → 子行同样不带 id
            result[table].append(rewritten)

    return result, sorted(unmapped_task_ids)


# ---------- A 侧结构校验 ----------

def validate_incremental_package(manifest: dict,
                                 rows_by_table: Dict[str, List[dict]]) -> List[str]:
    """包结构 / 任务一致性校验（A7 失败码表 400 的三种场景）。

    Returns: 错误文案列表（非空即 400 拒绝，不写任何数据）。
    """
    errors: List[str] = []
    source_task = manifest.get('sourceTask')
    if not isinstance(source_task, dict):
        return ['增量包缺少 manifest.sourceTask']
    source_task_id = _int_or_none(source_task.get('id'))
    if source_task_id is None:
        return ['manifest.sourceTask.id 缺失或非法']

    tasks = manifest.get('tasks') or []
    task_ids = {_int_or_none(row.get('id')) for row in tasks if isinstance(row, dict)}
    task_ids.discard(None)
    if len(task_ids) > 1:
        errors.append(f'增量包只支持单任务（包内任务: {sorted(task_ids)}）')
    foreign = sorted(task_ids - {source_task_id})
    if foreign:
        errors.append(f'manifest.tasks 与 sourceTask.id={source_task_id} 不一致: {foreign}')

    report_task_ids = {_int_or_none(row.get('task_id'))
                       for row in rows_by_table.get(TransferTable.TEST_REPORTS.value) or []
                       if isinstance(row, dict)}
    report_task_ids.discard(None)
    foreign_reports = sorted(report_task_ids - {source_task_id})
    if foreign_reports:
        errors.append(
            f'包内报告任务的 task_id 与源任务 {source_task_id} 不一致: {foreign_reports}')

    for row in rows_by_table.get(TransferTable.TEST_RESULT_DIMENSIONS.value) or []:
        if not isinstance(row, dict):
            continue
        if _int_or_none(row.get('test_result_id')) is None:
            errors.append('维度评分行缺少 test_result_id')
            break
    return errors


# ---------- A 侧维度定义翻译（B dimension_id → A dimension_id）----------

def _def_index(defs: List[dict]) -> Dict[int, dict]:
    index: Dict[int, dict] = {}
    for item in defs or []:
        if not isinstance(item, dict):
            continue
        dim_id = _int_or_none(item.get('id'))
        if dim_id is not None:
            index[dim_id] = item
    return index


def _normalize_code(value) -> str:
    return str(value or '').strip().lower()


def build_dimension_id_mapping(package_defs: List[dict],
                               target_defs: List[dict],
                               ) -> Tuple[Dict[int, int], List[int], List[str]]:
    """按 `(name, 父维度链, task_type_code)` 把包内维度 id 映射到 A 的维度 id。

    匹配规则（A2-4 / §5.2）：
    1. 同名 + `task_type_code` 归一后相同（两侧都非空时参与比较，缺省不参与）；
    2. 父维度先递归匹配，父链一致（都无父，或父映射到同一个 A id）；
    3. 多个候选时取 id 最小者并给出歧义 warning（同名不同义无法自动识别，
       见 §10.2 遗留风险 2）。

    Returns:
        (mapping {B dim id: A dim id}, unmatched_ids, warnings)
    """
    package_index = _def_index(package_defs)
    target_index = _def_index(target_defs)
    by_name: Dict[str, List[dict]] = {}
    for item in target_index.values():
        by_name.setdefault(str(item.get('name') or '').strip(), []).append(item)

    mapping: Dict[int, int] = {}
    warnings: List[str] = []
    resolving: set = set()

    def resolve(dim_id: int) -> Optional[int]:
        if dim_id in mapping:
            return mapping[dim_id]
        if dim_id in resolving:
            # 包内维度定义成环（坏数据）：不猜，按未匹配处理
            return None
        source = package_index.get(dim_id)
        if source is None:
            return None
        resolving.add(dim_id)
        try:
            parent_pkg_id = _int_or_none(source.get('parent_dimension_id'))
            parent_target_id: Optional[int] = None
            if parent_pkg_id is not None:
                parent_target_id = resolve(parent_pkg_id)
                if parent_target_id is None:
                    return None  # 父维度匹配不到 → 子维度也不匹配（父链口径）
            name = str(source.get('name') or '').strip()
            code = _normalize_code(source.get('task_type_code'))
            candidates = []
            for item in by_name.get(name, []):
                item_parent = _int_or_none(item.get('parent_dimension_id'))
                if parent_pkg_id is None:
                    if item_parent is not None:
                        continue
                elif item_parent != parent_target_id:
                    continue
                item_code = _normalize_code(item.get('task_type_code'))
                if code and item_code and code != item_code:
                    continue
                candidates.append(item)
            if not candidates:
                return None
            candidates.sort(key=lambda item: _int_or_none(item.get('id')) or 0)
            chosen = candidates[0]
            chosen_id = _int_or_none(chosen.get('id'))
            if chosen_id is None:
                return None
            if len(candidates) > 1:
                warnings.append(
                    f'维度 {name!r} 在目标库有 {len(candidates)} 个同名候选，'
                    f'已取 id 最小者 {chosen_id}')
            mapping[dim_id] = chosen_id
            return chosen_id
        finally:
            resolving.discard(dim_id)

    for dim_id in sorted(package_index):
        resolve(dim_id)

    unmatched = sorted(set(package_index) - set(mapping))
    return mapping, unmatched, warnings


def package_report_ids(rows_by_table: Dict[str, List[dict]]) -> List[int]:
    """包内 test_reports 的 id 列表（无 id 的 B 新建报告不出现）"""
    ids: List[int] = []
    for row in rows_by_table.get(TransferTable.TEST_REPORTS.value) or []:
        if not isinstance(row, dict):
            continue
        report_id = _int_or_none(row.get('id'))
        if report_id is not None:
            ids.append(report_id)
    return ids
