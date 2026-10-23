# -*- coding: utf-8 -*-
"""任务仓储 — TaskCase 状态 / dict 序列化 / 统计 Mixin（从 task_repository.py 拆分，P4-5）。

供 gRPC servicer 使用的 dict 序列化读取、TaskCase 状态更新、聚合统计、
TaskCaseRepositoryABC 接口适配。
"""
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from shared.models.common_enums import DeviceOccupancyStatus, DeviceType
from shared.models.database import get_db_session, utc8now
from shared.utils.status_utils import derive_task_case_status, task_case_not_removed
from shared.utils.status_constants import (
    DEVICE_OCCUPANCY_EXECUTION_STATUSES,
    ExecutionStatus,
    TaskStatus as SharedTaskStatus,
)
from task_service.infrastructure.persistence.models import Task, TaskCase, TaskAPI, TaskDevice


class TaskCaseStatsMixin:
    """TaskCase 状态维护与 dict 序列化（供 TaskRepository 组合）"""

    # ========== TaskDataService servicer 用 — dict 序列化方法 ==========

    def get_task_dict_by_id(self, task_id: int) -> Optional[dict]:
        """按 ID 读取 Task 详情（返回 dict 序列化格式，供 gRPC servicer 用）。"""
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return None
            return {
                'id': task.id,
                'name': task.name,
                'description': task.description,
                'status': task.status,
                'config': task.config,
                'algorithm_type': task.algorithm_type,
                'algorithm_params': task.algorithm_params,
                'total_cases': task.total_cases,
                'completed_cases': task.completed_cases,
                'failed_cases': task.failed_cases,
                'created_by_user_id': task.created_by_user_id,
                'created_at': task.created_at.isoformat() if task.created_at else None,
                'updated_at': task.updated_at.isoformat() if task.updated_at else None,
                'started_at': task.started_at.isoformat() if task.started_at else None,
                'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                'estimated_time': task.estimated_time,
                'actual_duration': task.actual_duration,
            }
        finally:
            session.close()

    def update_status(self, task_id: int, status: str) -> Optional[dict]:
        """更新 Task 的 status，返回 {task_id, old_status, new_status} 或 None。"""
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return None
            old_status = task.status
            task.status = status
            # 重新评估完成时自动更新计数和时间戳
            if old_status == SharedTaskStatus.REEVALUATING and status in (SharedTaskStatus.COMPLETED, SharedTaskStatus.FAILED):
                task.reevaluation_count = (task.reevaluation_count or 0) + 1
                task.reevaluated_at = utc8now()
            session.commit()
            return {
                'task_id': task.id,
                'old_status': old_status,
                'new_status': task.status,
            }
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_task_device_dicts(self, task_id: int) -> List[dict]:
        """获取任务关联设备列表（返回 dict 列表）。"""
        session = get_db_session()
        try:
            rows = session.query(TaskDevice).filter(
                TaskDevice.task_id == task_id
            ).all()
            return [{'id': td.id, 'task_id': td.task_id, 'device_id': td.device_id} for td in rows]
        finally:
            session.close()

    def get_task_api_dicts(self, task_id: int) -> List[dict]:
        """获取任务关联 API 列表（返回 dict 列表）。"""
        session = get_db_session()
        try:
            rows = session.query(TaskAPI).filter(
                TaskAPI.task_id == task_id
            ).all()
            return [{'id': ta.id, 'task_id': ta.task_id, 'api_id': ta.api_id} for ta in rows]
        finally:
            session.close()

    def get_task_case_dicts(self, task_id: int, case_ids: List[str] = None) -> List[dict]:
        """按 task_id + case_ids 批量读取 TaskCase（返回 dict 列表）。

        case_ids 为空时返回该 task 下所有 TaskCase。
        INT-305：移除留痕行（error_message = '用例已被移除'）剔除——报告/评估
        等下游按本接口拉取现存用例，被删用例自动不再计入。
        """
        session = get_db_session()
        try:
            q = session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                task_case_not_removed(TaskCase),
            )
            if case_ids:
                q = q.filter(TaskCase.test_case_id.in_(list(case_ids)))
            tcs = q.all()
            return [{
                'id': tc.id,
                'task_id': tc.task_id,
                'test_case_id': tc.test_case_id,
                'status': tc.status,
                'execution_status': tc.execution_status,
                'evaluation_status': tc.evaluation_status,
                # INT-61：api_test_service 按 device_type 运行时分发执行器
                # （websocket_api → RealtimeSessionExecutor），缺省回退 http_api 旧行为
                'device_type': tc.device_type,
                # INT-71：device_id 随执行数据下发（API 类=api.id / physical=设备ID）
                'device_id': tc.device_id,
                'started_at': tc.started_at.isoformat() if tc.started_at else None,
                'completed_at': tc.completed_at.isoformat() if tc.completed_at else None,
                'duration': tc.duration,
                'error_message': tc.error_message,
            } for tc in tcs]
        finally:
            session.close()

    def update_task_case_status(self, task_id: int, case_id: str,
                                status: str = '', execution_status: str = '',
                                evaluation_status: str = '',
                                error_message: str = '',
                                started_at=None, completed_at=None,
                                tc_rel_id: Optional[int] = None) -> bool:
        """更新 TaskCase 状态，返回是否有更新。

        started_at / completed_at 为 datetime 或 ISO8601 字符串，非 None 才写入。
        与 V9.7.10 行为对齐：开始执行时写 started_at，结束时写 completed_at。

        INT-604：多路由下同一用例存在设备/API 多行 TaskCase，写回必须按路由行
        精确命中——tc_rel_id 优先（执行器/评估已知 task_case_relations.id 时
        传入，避免 (task_id, test_case_id) 全量更新把兄弟路由打成同一终态）；
        tc_rel_id 为空时维持旧口径（单行场景零回归）。
        """
        session = get_db_session()
        try:
            status = self._derive_case_status(
                session, task_id, case_id, status, execution_status, evaluation_status,
                tc_rel_id=tc_rel_id)
            started_at = self._coerce_cst_datetime(started_at)
            completed_at = self._coerce_cst_datetime(completed_at)

            update_fields = {}
            if status:
                update_fields['status'] = status
            if execution_status:
                update_fields['execution_status'] = execution_status
            if evaluation_status:
                update_fields['evaluation_status'] = evaluation_status
            if error_message:
                update_fields['error_message'] = error_message
            if started_at is not None:
                update_fields['started_at'] = started_at
            if completed_at is not None:
                update_fields['completed_at'] = completed_at

            if update_fields:
                q = session.query(TaskCase).filter(TaskCase.task_id == task_id)
                if tc_rel_id is not None:
                    q = q.filter(TaskCase.id == tc_rel_id)
                else:
                    q = q.filter(TaskCase.test_case_id == case_id)
                q.update(update_fields, synchronize_session=False)
                session.commit()
            return bool(update_fields)
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _coerce_cst_datetime(value):
        """datetime 或 ISO8601 字符串 → naive +08:00 datetime；None/空串 → None。"""
        if value is None or value == '':
            return None
        if isinstance(value, datetime):
            dt = value
        else:
            dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None)
        return dt

    @staticmethod
    def _derive_case_status(session, task_id: int, case_id: str, status: str,
                            execution_status: str, evaluation_status: str,
                            tc_rel_id: Optional[int] = None) -> str:
        """未显式传 status 时，由 execution/evaluation 状态推导复合状态。

        INT-604：tc_rel_id 优先精确取路由行（多行时避免 .first() 取错行）。
        """
        if status or not (execution_status or evaluation_status):
            return status
        q = session.query(TaskCase).filter(TaskCase.task_id == task_id)
        if tc_rel_id is not None:
            q = q.filter(TaskCase.id == tc_rel_id)
        else:
            q = q.filter(TaskCase.test_case_id == case_id)
        tc = q.first()
        if not tc:
            return status
        cur_exec = execution_status or tc.execution_status or 'pending'
        cur_eval = evaluation_status or tc.evaluation_status or 'pending'
        return derive_task_case_status(cur_exec, cur_eval)

    def get_task_stats(self, status: str = '', algorithm_type: str = '',
                       group_by: str = '', deleted: bool = False,
                       granularity: str = '') -> dict:
        """聚合统计 Task — count / group_by。

        deleted 指定统计范围（False=未删除，True=回收站软删除，INT-200）。
        """
        from sqlalchemy import func as _func
        session = get_db_session()
        try:
            query = session.query(Task).filter(Task.deleted == bool(deleted))
            if status:
                query = query.filter(Task.status == status)
            if algorithm_type:
                query = query.filter(Task.algorithm_type == algorithm_type)

            if group_by:
                return self._get_task_stats_grouped(
                    session, _func, status, algorithm_type, group_by,
                    deleted=deleted, granularity=granularity)

            total = query.count()
            return {'total': int(total)}
        finally:
            session.close()

    @staticmethod
    def _get_task_stats_grouped(session, _func, status: str,
                                algorithm_type: str, group_by: str,
                                deleted: bool = False,
                                granularity: str = '') -> dict:
        """按字段分组统计分支。

        差异#2 收尾：task.type 列已废弃删除，group_by='type' 改为按用例级
        device_type 派生分布（physical→e2e；http_api/websocket_api→api；兼有
        →mixed，INT-200）。group_by='trend' 返回已完成任务按 created_at 的
        时间分桶计数（granularity=day/week/month/year，INT-200）。
        """
        if group_by == 'type':
            return TaskCaseStatsMixin._get_task_type_distribution(
                session, status, algorithm_type, deleted)
        if group_by == 'trend':
            return TaskCaseStatsMixin._get_task_trend_buckets(
                session, status, algorithm_type, granularity)

        allowed = {'status': Task.status, 'algorithm_type': Task.algorithm_type}
        col = allowed.get(group_by)
        if col is None:
            return {'error': f'unsupported group_by field: {group_by}'}
        rows = session.query(col, _func.count(Task.id)).filter(
            Task.deleted == bool(deleted)
        )
        if status:
            rows = rows.filter(Task.status == status)
        if algorithm_type:
            rows = rows.filter(Task.algorithm_type == algorithm_type)
        rows = rows.group_by(col).all()
        items = [{'key': str(k) if k is not None else '', 'count': int(c)} for k, c in rows]
        return {'items': items}

    # 派生类型桶（与前端 chartUtils 口径一致：无 device_type 行回退 api）
    _TYPE_API_DEVICE_TYPES = frozenset({
        DeviceType.HTTP_API.value, DeviceType.WEBSOCKET_API.value,
    })
    _TREND_GRANULARITIES = frozenset({'day', 'week', 'month', 'year'})

    @staticmethod
    def _get_task_type_distribution(session, status: str,
                                    algorithm_type: str, deleted: bool) -> dict:
        """任务类型分布（派生）：按任务的去重 device_type 集合分桶 api/e2e/mixed。

        无任何 device_type 的任务与前端既有派生口径一致计入 api（INT-200）。
        """
        task_q = session.query(Task.id).filter(Task.deleted == bool(deleted))
        if status:
            task_q = task_q.filter(Task.status == status)
        if algorithm_type:
            task_q = task_q.filter(Task.algorithm_type == algorithm_type)
        rows = (session.query(TaskCase.task_id, TaskCase.device_type)
                .filter(TaskCase.task_id.in_(task_q.statement))
                .filter(TaskCase.device_type.isnot(None),
                        TaskCase.device_type != '')
                .distinct().all())
        per_task: dict = {}
        for tid, dt in rows:
            per_task.setdefault(tid, set()).add(dt)
        # INT-1233：无用例级 device_type 行的任务按任务级设备/API 关系回退派生
        # （历史任务无 task_case_relations，仅剩 task_device_relations/
        # task_api_relations——与列表 device_types、task_type 筛选同口径）
        covered_ids = set(per_task)
        all_ids = {t[0] for t in task_q.all()}
        missing_ids = all_ids - covered_ids
        if missing_ids:
            from task_service.infrastructure.read_models.task_device_type_derivation import (
                fetch_task_device_types,
            )
            rel_map = fetch_task_device_types(session, list(missing_ids))
            for tid, dts in rel_map.items():
                per_task.setdefault(tid, set()).update(dts)
        counts = {'api': 0, 'e2e': 0, 'mixed': 0}
        for dts in per_task.values():
            has_physical = DeviceType.PHYSICAL.value in dts
            has_api = bool(dts & TaskCaseStatsMixin._TYPE_API_DEVICE_TYPES)
            if has_physical and has_api:
                counts['mixed'] += 1
            elif has_physical:
                counts['e2e'] += 1
            else:
                counts['api'] += 1
        # 无用例级 device_type 且无关系的任务按前端口径计入 api
        no_case = len(all_ids) - len(per_task)
        counts['api'] += int(no_case) if no_case > 0 else 0
        return {'items': [{'key': k, 'count': int(v)} for k, v in counts.items()]}

    @staticmethod
    def _get_task_trend_buckets(session, status: str,
                                algorithm_type: str, granularity: str) -> dict:
        """完成任务按 created_at 的时间分桶（key 与前端 chartUtils 键格式一致）。"""
        granularity = granularity or 'day'
        if granularity not in TaskCaseStatsMixin._TREND_GRANULARITIES:
            return {'error': f'unsupported granularity: {granularity}'}
        q = session.query(Task.created_at).filter(
            Task.deleted == False,  # noqa: E712
            Task.status == SharedTaskStatus.COMPLETED,
        )
        # status 过滤与固定 completed 条件取交集（不同值时自然空集）
        if status and status != SharedTaskStatus.COMPLETED:
            q = q.filter(Task.status == status)
        if algorithm_type:
            q = q.filter(Task.algorithm_type == algorithm_type)
        buckets: dict = {}
        for (created_at,) in q.all():
            if created_at is None:
                continue
            key = TaskCaseStatsMixin._trend_bucket_key(created_at, granularity)
            buckets[key] = buckets.get(key, 0) + 1
        items = sorted(
            ({'key': k, 'count': int(c)} for k, c in buckets.items()),
            key=lambda item: TaskCaseStatsMixin._trend_sort_key(item['key']),
        )
        return {'items': items}

    @staticmethod
    def _trend_bucket_key(dt: datetime, granularity: str) -> str:
        if granularity == 'day':
            return dt.strftime('%Y-%m-%d')
        if granularity == 'week':
            # 前端键为「日历年-W ISO 周数」，不补零（chartUtils.getWeekNumber 口径）
            return f'{dt.year}-W{dt.isocalendar().week}'
        if granularity == 'month':
            return f'{dt.year}-{dt.month:02d}'
        return str(dt.year)

    @staticmethod
    def _trend_sort_key(key: str):
        if '-W' in key:
            year, week = key.split('-W', 1)
            return (int(year), int(week))
        return (key,)

    # ========== ABC 接口适配（TaskCaseRepositoryABC） ==========

    def get_task_device_ids(self, task_id: int) -> List[dict]:
        """ABC 接口 — 委托到 get_task_device_dicts。"""
        return self.get_task_device_dicts(task_id)

    def get_task_api_ids(self, task_id: int) -> List[dict]:
        """ABC 接口 — 委托到 get_task_api_dicts。"""
        return self.get_task_api_dicts(task_id)

    def get_by_task_and_case_ids(self, task_id: int,
                                 case_ids: List[str] = None) -> List[dict]:
        """ABC 接口 — 委托到 get_task_case_dicts。"""
        return self.get_task_case_dicts(task_id, case_ids)

    def get_stats(self, algorithm_type: str = '', group_id: str = '',
                  group_by: str = '') -> dict:
        """ABC 接口 — TestCase 维度聚合统计。

        签名与 TaskCaseRepositoryABC.get_stats 对齐（group_id 用于按分组过滤）。
        """
        from sqlalchemy import func as _func
        session = get_db_session()
        try:
            query = session.query(TaskCase).join(
                Task, TaskCase.task_id == Task.id
            ).filter(Task.deleted == False)  # noqa: E712
            if algorithm_type:
                query = query.filter(Task.algorithm_type == algorithm_type)
            if group_id:
                query = query.filter(Task.group_id == group_id)
            total = query.count()
            return {'total': int(total)}
        finally:
            session.close()

    def get_device_occupancy(self, device_ids: List[str] = None,
                             lab_id: int = None) -> dict:
        """按物理设备聚合设备占用状态（实验室扩展 INT-493 §4.3）。

        数据源 task_case_relations 活动行（execution_status IN
        ('pending','queued','running')），只统计 device_type='physical' 的行
        （http_api/websocket_api 排除）。

        状态判定（同一物理设备同一时刻仅一个用例执行，DistributedLock 保证 1:1）：
        - 存在 execution_status='running' 活动行 → testing（测试中）
        - 否则存在 pending/queued 活动行 → occupied（已占用/排队中）
        - 均无 → 该设备不在返回字典中（DTO 层 occupied_status=null）

        返回 {device_id(str): {occupied_status, task_id, case_id}}。
        device_ids/lab_id 均可选过滤，空 device_ids = 全物理设备。
        """
        session = get_db_session()
        try:
            query = session.query(
                TaskCase.device_id,
                TaskCase.execution_status,
                TaskCase.task_id,
                TaskCase.test_case_id,
            ).filter(
                TaskCase.device_type == DeviceType.PHYSICAL.value,
                TaskCase.execution_status.in_(DEVICE_OCCUPANCY_EXECUTION_STATUSES),
            )
            if device_ids:
                # device_id 列为 String(50)，入参为 int（网关设备 ID）时统一转字符串匹配
                query = query.filter(TaskCase.device_id.in_([str(d) for d in device_ids]))
            if lab_id:
                query = query.filter(TaskCase.lab_id == lab_id)
            rows = query.all()

            result: dict = {}
            running = ExecutionStatus.RUNNING
            for device_id, execution_status, task_id, case_id in rows:
                if not device_id:
                    continue
                prev = result.get(device_id)
                if prev is None:
                    result[device_id] = {
                        'occupied_status': (
                            DeviceOccupancyStatus.TESTING.value
                            if execution_status == running
                            else DeviceOccupancyStatus.OCCUPIED.value
                        ),
                        'task_id': task_id,
                        'case_id': case_id,
                    }
                elif execution_status == running:
                    # running 优先：pending/queued 与 running 并存时取 testing
                    result[device_id]['occupied_status'] = DeviceOccupancyStatus.TESTING.value
                    result[device_id]['task_id'] = task_id
                    result[device_id]['case_id'] = case_id
            return result
        finally:
            session.close()

    def get_testcase_lab_ids(self, case_ids: List[str]) -> dict:
        """按用例 ID 批量解析 config 中的 lab_id（实验室扩展 INT-493/INT-540）。

        用例 lab 归属存 test_cases.config JSONB：`config->>'lab_id'` 缺失/空 =
        通用用例（lab_id=None，任意实验室可选）；有值 = 专属用例。
        返回 {case_id(str): lab_id(int|None)}。不存在的用例 ID 返回 None
        （调用方校验语义：查不到视为不满足归属）。
        """
        from task_service.infrastructure.persistence.models import TestCase
        if not case_ids:
            return {}
        session = get_db_session()
        try:
            rows = (session.query(TestCase.id, TestCase.config)
                    .filter(TestCase.id.in_(list(case_ids))).all())
            result: Dict[str, Optional[int]] = {}
            for cid, config in rows:
                lab_id = None
                if config and isinstance(config, dict):
                    raw = config.get('lab_id')
                    if raw is not None and raw != '':
                        try:
                            lab_id = int(raw)
                        except (TypeError, ValueError):
                            lab_id = None
                result[str(cid)] = lab_id
            return result
        finally:
            session.close()
