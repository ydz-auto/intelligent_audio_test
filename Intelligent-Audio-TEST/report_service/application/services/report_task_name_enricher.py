# -*- coding: utf-8 -*-
"""报告 task_name 实时补名（INT-1776）。

V9.7.10 的报告接口返回任务名，V9.7.31 重构后丢失：生成时 config 只写
name/description，``_aggregate_to_dict`` 也未输出该字段，导致报告详情、
报告中心列表、统计报表与 HTML 导出四处任务名恒空。

口径（卡内裁定）：单一事实源 = task_service，不落库、不做数据迁移、不写主库。
读路径在 application 层按「一页一次」批量补名：

- 收集 ``task_id > 0`` 并去重，整页只调一次 ``_grpc_get_tasks_by_ids``（禁止逐条 RPC）；
- 查不到 → ``''``；对比 / 二次对比报告 ``task_id`` 为空 → ``''``；
- RPC 异常 / 超时 → 记 warning 并降级为 ``''``，读路径不得因此失败（列表仍 200）。
"""
from __future__ import annotations

import logging
import threading

from report_service.config.config import Config

logger = logging.getLogger(__name__)


def _task_id_of(item) -> int:
    """从报告 dict 读取 task_id 并归一为 int（缺失 / 非法 → 0）。"""
    try:
        return int(item.get('task_id') or 0)
    except (TypeError, ValueError):
        return 0


def _task_record_id(task) -> int:
    """从任务记录（gRPC 返回的 dict）读取 id（缺失 / 非法 → 0）。"""
    raw = task.get('id') if isinstance(task, dict) else getattr(task, 'id', None)
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _task_name_of(task) -> str:
    """从任务记录读取名称（缺失 → ''）。"""
    name = task.get('name') if isinstance(task, dict) else getattr(task, 'name', None)
    return name or ''


def _fetch_task_names(task_ids, timeout_seconds) -> dict:
    """整批取任务名，返回 ``{task_id: name}``；失败或超时返回空映射。

    超时用工作线程兜底：task_service 不可达/握手卡住时，报告读路径不能跟着
    一起阻塞（报告列表已有慢的历史，补名不得成为新的阻塞点）。
    """
    from report_service.infrastructure.clients.grpc_clients import _grpc_get_tasks_by_ids

    box = {}

    def _worker():
        try:
            box['tasks'] = _grpc_get_tasks_by_ids(list(task_ids))
        except Exception:
            logger.warning(
                "task_name 补名查询失败，降级为空 task_ids=%s", task_ids, exc_info=True)

    worker = threading.Thread(
        target=_worker, name='report-task-name-enricher', daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    if worker.is_alive():
        logger.warning(
            "task_name 补名查询超时(%.1fs)，降级为空 task_ids=%s",
            timeout_seconds, task_ids)
        return {}

    names = {}
    for task in box.get('tasks') or []:
        task_id = _task_record_id(task)
        if task_id > 0:
            names[task_id] = _task_name_of(task)
    return names


def enrich_task_names(items, timeout_seconds=None):
    """为报告 dict 列表批量补齐 ``task_name``（原地回填并返回同一列表）。

    Args:
        items: 报告 dict 列表（``_aggregate_to_dict`` 的输出 / HTML 导出数据）；
            非 dict 元素忽略
        timeout_seconds: 补名查询等待上限，缺省读
            ``Config.REPORT_TASK_NAME_TIMEOUT_SECONDS``

    Returns:
        传入的 ``items``（就地回填，便于调用方链式使用）
    """
    rows = [item for item in (items or []) if isinstance(item, dict)]
    if not rows:
        return items

    task_ids = sorted({task_id for task_id in map(_task_id_of, rows) if task_id > 0})
    names = {}
    if task_ids:
        if timeout_seconds is None:
            timeout_seconds = Config.REPORT_TASK_NAME_TIMEOUT_SECONDS
        names = _fetch_task_names(task_ids, timeout_seconds)

    for item in rows:
        # task_service 为准；查不到时保留已有值（如 HTML 导出链路的 config 兜底）
        item['task_name'] = names.get(_task_id_of(item)) or item.get('task_name') or ''
    return items
