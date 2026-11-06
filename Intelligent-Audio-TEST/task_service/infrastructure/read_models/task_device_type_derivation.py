# -*- coding: utf-8 -*-
"""任务级 device_types 派生辅助（INT-1233）。

历史任务在 V9.7.10 以 `task.type` 直存 e2e/api；V9.7.31 移除该列（INT-263）后
改为由 `task_case_relations.device_type` 派生。真实库（INT-1158 导入的生产数据
副本）存在大量**无 task_case_relations 行**的历史任务——仅剩
`task_device_relations` / `task_api_relations`（如任务 187/191/198 等 E2E 任务，
名字含 E2E、关联物理设备、有 test_results），导致任务级 `device_types` 恒为空。

本模块提供「用例级优先、任务级关系回退」的统一派生口径，供 read_model /
stats 分布共用：
- 用例级 device_type 非空 → 以用例级为准（INT-789 回填后即权威来源）；
- 用例级全空（无用例行或行全 NULL）→ 回退任务级关系：
  - 存在 task_device_relations → 'physical'（e2e）
  - 存在 task_api_relations   → 'http_api'（api，websocket 细分见 INT-789 step ③，
    任务级回退不跨服务查 apis 表，真实库 api 关系为 0）
  - 两者兼有 → 'physical' + 'http_api'（mixed）
"""
from typing import Dict, List

from shared.models.common_enums import DeviceType
from task_service.infrastructure.persistence.models import TaskAPI, TaskCase, TaskDevice

# 非空 device_type 的过滤片段（用例级权威来源判定用）
_CASE_TYPE_NOT_BLANK = (
    TaskCase.device_type.isnot(None),
    TaskCase.device_type != '',
)


def fetch_task_device_types(session, task_ids) -> Dict[int, List[str]]:
    """批量派生任务级 device_types（INT-1233 统一口径）。

    :param session: 当前 DB session
    :param task_ids: 任务 ID 集合（可空）
    :return: {task_id: [device_type,...]}；无用例级且无关系的任务不进入结果
    """
    if not task_ids:
        return {}
    ids = [int(t) for t in task_ids]
    result: Dict[int, List[str]] = {}

    # ① 用例级 device_type（权威来源）
    case_rows = (
        session.query(TaskCase.task_id, TaskCase.device_type)
        .filter(TaskCase.task_id.in_(ids), *_CASE_TYPE_NOT_BLANK)
        .distinct()
        .all()
    )
    for tid, dt in case_rows:
        result.setdefault(tid, []).append(dt)

    # ② 无用例级 device_type 的任务 → 任务级关系回退
    # 表缺失（旧测试夹具未建 task_device_relations / task_api_relations）时
    # 降级为空——失败语句已把事务置为 aborted，必须先 rollback 恢复，否则后续
    # 查询连锁抛 InFailedSqlTransaction（同 INT-339 挑选容器判定降级）。
    missing = [tid for tid in ids if tid not in result]
    if missing:
        try:
            dev_ids = {
                r[0] for r in session.query(TaskDevice.task_id)
                .filter(TaskDevice.task_id.in_(missing)).distinct().all()
            }
            api_ids = {
                r[0] for r in session.query(TaskAPI.task_id)
                .filter(TaskAPI.task_id.in_(missing)).distinct().all()
            }
        except Exception:
            try:
                session.rollback()
            except Exception:
                pass
            return result
        for tid in missing:
            dts: List[str] = []
            if tid in dev_ids:
                dts.append(DeviceType.PHYSICAL.value)
            if tid in api_ids:
                dts.append(DeviceType.HTTP_API.value)
            if dts:
                result[tid] = dts
    return result
