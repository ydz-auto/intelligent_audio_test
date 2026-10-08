# -*- coding: utf-8 -*-
"""已发布任务仓储（Published Task Repository）

职责：
- PublishedTask PO 的持久化 CRUD（create/get_by_id/get_list/get_group_versions/
  get_current_version/update_name/archive/create_version）
- 新增 test_tasks 追溯字段写入（execution_source / published_task_id / published_task_version）
- 快照数据读取（供应用服务组装快照/冻结报告/校验/执行建新任务）

DDD 分层：本仓储只操作 task_service 自有表（published_tasks / test_tasks 及其关联表）。
报告冻结所需的报告数据（test_reports / report_summaries / report_summary_meta /
report_metric_stats / report_cases）归属 report_service，为保持冻结快照契约与
V9.7.10 完全等价，本仓储直接读取 report_service 的 PO（同一 DB），
后续如需严格跨服务隔离可改为 gRPC 调用 ReportConfigService。
"""
import json
import logging
from datetime import datetime

from shared.models.database import get_db_session
from shared.utils.status_constants import (
    ExecutionStatus,
    EvaluationStatus,
    TaskCaseStatus,
    TaskStatus,
)

from task_service.infrastructure.persistence._task_converters import _UTC_PLUS_8
from task_service.infrastructure.persistence.models import (
    Task, TaskCase, TaskDevice, TaskAPI, TaskTag, Tag, PublishedTask,
)
from task_service.infrastructure.persistence.models.testcase_models import TestCase
from report_service.infrastructure.persistence.models import (
    Report, ReportSummary, ReportSummaryMeta, ReportMetricStats, ReportCase,
)

logger = logging.getLogger(__name__)

# 可发布状态（与设计文档 §5.1 一致）
PUBLISHABLE_STATUSES = (
    TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.STOPPED, TaskStatus.PENDING,
)


def parse_benchmark_filter(value) -> bool | None:
    """benchmark 筛选参数解析（三态）：'true'/'True'/'1' → True，
    'false'/'False'/'0' → False，其余（空/None）→ None 表示不过滤。

    网关与 gRPC 层以字符串承载该布尔筛选（proto string 字段），
    仅在仓储入口归一化为 bool，下游查询不再做字符串判断。
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ('true', '1'):
        return True
    if text in ('false', '0'):
        return False
    return None


class PublishedTaskRepository:
    """已发布任务仓储（单例使用，方法级 session 管理）。"""

    # ==================== PublishedTask 持久化 ====================

    def create(
        self,
        *,
        task_group_id=None,
        source_task_id=None,
        name: str,
        description=None,
        task_type: str,
        status: str = 'published',
        version: int = 1,
        is_current: bool = True,
        benchmark: bool = False,
        snapshot_config=None,
        report_snapshot=None,
        publish_reason=None,
        published_by=None,
    ) -> PublishedTask:
        """创建已发布任务 PO。

        首个版本（task_group_id 为空）以自身 ID 作为版本链锚点，
        与 V9.7.10 publish 语义一致（published.task_group_id = published.id）。
        """
        session = get_db_session()
        try:
            now = datetime.now(_UTC_PLUS_8)
            pt = PublishedTask(
                task_group_id=task_group_id,
                source_task_id=source_task_id,
                name=name,
                description=description,
                type=task_type,
                status=status,
                version=version,
                is_current=is_current,
                benchmark=bool(benchmark),
                snapshot_config=snapshot_config,
                report_snapshot=report_snapshot,
                publish_reason=publish_reason,
                published_by=published_by,
                published_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(pt)
            session.flush()
            if pt.task_group_id is None:
                pt.task_group_id = pt.id
            session.commit()
            # commit 后属性已过期，close 后实例脱离 session；
            # refresh 重载属性，保证调用方在方法返回后仍可读取（如审计/响应组装）
            session.refresh(pt)
            return pt
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_by_id(self, published_task_id: int):
        """按 ID 查询已发布任务（含已归档）。"""
        session = get_db_session()
        try:
            return session.get(PublishedTask, published_task_id)
        finally:
            session.close()

    def get_task(self, task_id: int):
        """按 ID 查询来源日常任务（Task PO，含已软删除判断字段）。"""
        session = get_db_session()
        try:
            return session.get(Task, task_id)
        finally:
            session.close()

    def get_list(
        self,
        *,
        page: int = 1,
        per_page: int = 10,
        status: str = '',
        keyword: str = '',
        task_type: str = '',
        benchmark=None,
        start_date: str = '',
        end_date: str = '',
    ):
        """分页查询当前版本列表（含筛选），返回 (rows, total)。

        benchmark: True/False 精确过滤（供 Benchmark 排行实测轨消费），
        None/'' 表示不过滤。
        """
        session = get_db_session()
        try:
            query = session.query(PublishedTask).filter(
                PublishedTask.is_current.is_(True)
            )
            if status:
                query = query.filter(PublishedTask.status == status)
            if task_type:
                query = query.filter(PublishedTask.type == task_type)
            benchmark_flag = parse_benchmark_filter(benchmark)
            if benchmark_flag is not None:
                query = query.filter(PublishedTask.benchmark.is_(benchmark_flag))
            if keyword:
                like = f'%{keyword}%'
                query = query.filter(
                    (PublishedTask.name.ilike(like)) | (PublishedTask.description.ilike(like))
                )
            if start_date or end_date:
                try:
                    if start_date:
                        query = query.filter(
                            PublishedTask.published_at >= datetime.fromisoformat(start_date)
                        )
                    if end_date:
                        query = query.filter(
                            PublishedTask.published_at <= datetime.fromisoformat(end_date)
                        )
                except ValueError:
                    pass

            total = query.count()
            rows = (
                query.order_by(PublishedTask.published_at.desc(), PublishedTask.id.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all()
            )
            return rows, total
        finally:
            session.close()

    def get_version_counts(self, group_ids):
        """按 task_group_id 分组统计版本数，返回 {group_id: count}。"""
        if not group_ids:
            return {}
        session = get_db_session()
        try:
            from sqlalchemy import func
            counts = (
                session.query(PublishedTask.task_group_id, func.count(PublishedTask.id))
                .filter(PublishedTask.task_group_id.in_(list(group_ids)))
                .group_by(PublishedTask.task_group_id)
                .all()
            )
            return {gid: cnt for gid, cnt in counts}
        finally:
            session.close()

    def get_group_versions(self, group_id: int):
        """查询版本链全部版本（按版本号倒序）。"""
        session = get_db_session()
        try:
            return (
                session.query(PublishedTask)
                .filter(PublishedTask.task_group_id == group_id)
                .order_by(PublishedTask.version.desc())
                .all()
            )
        finally:
            session.close()

    def get_current_version(self, group_id: int):
        """查询版本链当前版本。"""
        session = get_db_session()
        try:
            return (
                session.query(PublishedTask)
                .filter(
                    PublishedTask.task_group_id == group_id,
                    PublishedTask.is_current.is_(True),
                )
                .first()
            )
        finally:
            session.close()

    def update_name(self, published_task_id: int, name: str) -> bool:
        """重命名（作用于整个版本链，task_group_id 锚点）。"""
        session = get_db_session()
        try:
            pt = session.get(PublishedTask, published_task_id)
            if pt is None:
                return False
            group_id = pt.task_group_id or pt.id
            versions = (
                session.query(PublishedTask)
                .filter(
                    (PublishedTask.task_group_id == group_id)
                    | (PublishedTask.id == group_id)
                )
                .all()
            )
            for v in versions:
                v.name = name
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def archive(self, published_task_id: int, archived_by=None) -> PublishedTask:
        """归档已发布任务（调用方先判断幂等，本方法直接置为 archived）。"""
        session = get_db_session()
        try:
            pt = session.get(PublishedTask, published_task_id)
            if pt is None:
                return None
            pt.status = 'archived'
            pt.archived_by = archived_by
            pt.archived_at = datetime.now(_UTC_PLUS_8)
            pt.updated_at = datetime.now(_UTC_PLUS_8)
            session.commit()
            session.refresh(pt)
            return pt
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def create_version(
        self,
        *,
        task_group_id: int,
        source_task_id=None,
        name: str,
        description=None,
        task_type: str,
        version: int,
        benchmark: bool = False,
        snapshot_config=None,
        publish_reason=None,
        demote_id: int = None,
    ) -> PublishedTask:
        """创建新版本 PO。

        Args:
            benchmark: 新版本 Benchmark 标记（默认 False，由应用服务继承当前版本）
            demote_id: 旧当前版本 ID；同事务内置为 is_current=False
                （与 V9.7.10 create_version 原子语义一致：旧版本 vN 置 False + 新版本 vN+1）。
        """
        session = get_db_session()
        try:
            now = datetime.now(_UTC_PLUS_8)
            if demote_id is not None:
                current = session.get(PublishedTask, demote_id)
                if current is not None:
                    current.is_current = False
                    current.updated_at = now
            new_version = PublishedTask(
                task_group_id=task_group_id,
                source_task_id=source_task_id,
                name=name,
                description=description,
                type=task_type,
                status='published',
                version=version,
                is_current=True,
                benchmark=bool(benchmark),
                snapshot_config=snapshot_config,
                publish_reason=publish_reason,
                published_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(new_version)
            session.commit()
            session.refresh(new_version)
            return new_version
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def mark_not_current(self, published_task_id: int) -> None:
        """将指定版本标记为非当前版本（旧调用兼容；create_version 已内置 demote）。"""
        session = get_db_session()
        try:
            pt = session.get(PublishedTask, published_task_id)
            if pt is not None:
                pt.is_current = False
                pt.updated_at = datetime.now(_UTC_PLUS_8)
                session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ==================== test_tasks 追溯字段写入 ====================

    def update_task_trace(
        self,
        task_id: int,
        *,
        execution_source: str,
        published_task_id: int,
        published_task_version: int,
    ) -> bool:
        """为已发布任务执行生成的日常任务回填追溯字段。"""
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return False
            task.execution_source = execution_source
            task.published_task_id = published_task_id
            task.published_task_version = published_task_version
            task.updated_at = datetime.now(_UTC_PLUS_8)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ==================== 快照构建数据读取 ====================

    def get_task_case_ids(self, task_id: int):
        """读取任务关联用例 ID（按 TaskCase.id 升序保序）。"""
        session = get_db_session()
        try:
            rows = (
                session.query(TaskCase.test_case_id)
                .filter(TaskCase.task_id == task_id)
                .order_by(TaskCase.id.asc())
                .all()
            )
            return [row[0] for row in rows if row[0]]
        finally:
            session.close()

    def get_task_report_case_ids(self, task_id: int):
        """历史数据兜底：从该任务的报告用例取用例 ID（有报告的任务必可发布）。"""
        session = get_db_session()
        try:
            report = (
                session.query(Report)
                .filter(Report.task_id == task_id, Report.type == 'task')
                .order_by(Report.id.desc())
                .first()
            )
            if not report:
                return []
            rows = (
                session.query(ReportCase.test_case_id)
                .filter(ReportCase.report_id == report.id)
                .all()
            )
            return [row[0] for row in rows if row[0]]
        finally:
            session.close()

    def get_task_device_ids(self, task_id: int):
        """读取任务关联设备 ID。"""
        session = get_db_session()
        try:
            rows = (
                session.query(TaskDevice.device_id)
                .filter(TaskDevice.task_id == task_id)
                .all()
            )
            return [row[0] for row in rows if row[0] is not None]
        finally:
            session.close()

    def get_task_api_ids(self, task_id: int):
        """读取任务关联 API ID。"""
        session = get_db_session()
        try:
            rows = (
                session.query(TaskAPI.api_id)
                .filter(TaskAPI.task_id == task_id)
                .all()
            )
            return [row[0] for row in rows if row[0] is not None]
        finally:
            session.close()

    def get_task_tag_names(self, task_id: int):
        """读取任务标签名列表（task_tags → tags）。"""
        session = get_db_session()
        try:
            rows = (
                session.query(Tag.name)
                .join(TaskTag, TaskTag.tag_id == Tag.id)
                .filter(TaskTag.task_id == task_id)
                .all()
            )
            return [row[0] for row in rows if row[0]]
        finally:
            session.close()

    # ==================== 快照校验 ====================

    def get_existing_case_ids(self, case_ids):
        """返回传入用例 ID 中仍存在的子集（已删除的自动过滤）。"""
        if not case_ids:
            return set()
        session = get_db_session()
        try:
            rows = (
                session.query(TestCase.id)
                .filter(TestCase.id.in_(list(case_ids)))
                .all()
            )
            return {row[0] for row in rows}
        finally:
            session.close()

    # ==================== 报告冻结 ====================

    @staticmethod
    def _to_json(val):
        """JSON 列 → list（None/非法串兜底为 []）。"""
        if val is None:
            return []
        if isinstance(val, (list, dict)):
            return val
        if isinstance(val, str):
            try:
                return json.loads(val)
            except Exception:
                return []
        return []

    @staticmethod
    def _to_json_obj(val):
        """JSON 列 → dict（None/非法串兜底为 {}）。"""
        if val is None:
            return {}
        if isinstance(val, dict):
            return val
        if isinstance(val, str):
            try:
                return json.loads(val)
            except Exception:
                return {}
        return {}

    def freeze_report_snapshot(self, source_task_id):
        """冻结来源任务当时的执行产物（报告/用例结果/评估数据/用例日志）为不可变快照。

        无报告时返回 None；发布后即使源任务被改/删/重生成报告，冻结快照保持不变。
        """
        if not source_task_id:
            return None
        session = get_db_session()
        try:
            report = (
                session.query(Report)
                .filter(Report.task_id == source_task_id, Report.type == 'task')
                .order_by(Report.id.desc())
                .first()
            )
            if not report:
                return None

            summary_info = (
                session.query(ReportSummary).filter_by(report_id=report.id).first()
            )
            summary_meta = (
                session.query(ReportSummaryMeta).filter_by(report_id=report.id).first()
            )
            metric_stats = (
                session.query(ReportMetricStats).filter_by(report_id=report.id).first()
            )
            cases = (
                session.query(ReportCase)
                .filter(ReportCase.report_id == report.id)
                .order_by(ReportCase.id.asc())
                .all()
            )

            return {
                'reportId': report.id,
                'name': report.name,
                'type': report.type,
                'status': report.status,
                'description': report.description,
                'analysis': report.analysis,
                'createdAt': report.created_at.isoformat() if report.created_at else None,
                'updatedAt': report.updated_at.isoformat() if report.updated_at else None,
                'summary': {
                    'totalCases': summary_info.total_cases if summary_info else 0,
                    'completedCases': summary_info.completed_cases if summary_info else 0,
                    'failedCases': summary_info.failed_cases if summary_info else 0,
                    'passRate': summary_info.pass_rate if summary_info else 0,
                    'duration': summary_info.duration if summary_info else 0,
                    'startedAt': summary_info.started_at.isoformat() if summary_info and summary_info.started_at else None,
                    'completedAt': summary_info.completed_at.isoformat() if summary_info and summary_info.completed_at else None,
                    'caseCategories': self._to_json(summary_meta.case_categories) if summary_meta else [],
                    'allMetrics': self._to_json(summary_meta.all_metrics) if summary_meta else [],
                    'dimensionValues': self._to_json(summary_meta.dimension_values) if summary_meta else [],
                    'devices': self._to_json(summary_meta.devices) if summary_meta else [],
                    'apis': self._to_json(summary_meta.apis) if summary_meta else [],
                    'deviceStats': self._to_json(metric_stats.device_stats) if metric_stats else [],
                    'apiStats': self._to_json(metric_stats.api_stats) if metric_stats else [],
                    'metricData': self._to_json_obj(metric_stats.metric_data) if metric_stats else {},
                    'tagMetricData': self._to_json_obj(metric_stats.tag_metric_data) if metric_stats else {},
                },
                'cases': [
                    {
                        'testCaseId': c.test_case_id,
                        'name': c.name,
                        'description': c.description,
                        'category': c.category,
                        'tags': self._to_json(c.tags),
                        'metrics': self._to_json_obj(c.metrics),
                        'results': self._to_json(c.results),
                        'audios': self._to_json(c.audios),
                        'referenceParams': self._to_json_obj(c.reference_params),
                        'algorithmResults': self._to_json_obj(c.algorithm_results),
                        'algorithmType': c.algorithm_type,
                        'logs': c.logs,
                    }
                    for c in cases
                ],
            }
        finally:
            session.close()

    # ==================== 执行建新任务 ====================

    def create_daily_task(
        self,
        *,
        name: str,
        description=None,
        task_type: str,
        snapshot_config: dict,
        case_ids,
    ) -> int:
        """按快照创建新的日常任务（执行已发布任务的复用链路）。

        Returns:
            新任务 ID。
        """
        now = datetime.now(_UTC_PLUS_8)
        session = get_db_session()
        try:
            new_task = Task(
                name=name,
                description=description,
                type=task_type,
                status=TaskStatus.PENDING,
                config=snapshot_config.get('config') or None,
                algorithm_type=snapshot_config.get('algorithmType'),
                algorithm_params=snapshot_config.get('algorithmParams') or None,
                total_cases=len(case_ids),
                completed_cases=0,
                failed_cases=0,
                created_at=now,
                updated_at=now,
            )
            session.add(new_task)
            session.flush()
            task_id = new_task.id

            for case_id in case_ids:
                session.add(TaskCase(
                    task_id=task_id,
                    test_case_id=case_id,
                    status=TaskCaseStatus.PENDING,
                    execution_status=ExecutionStatus.PENDING,
                    evaluation_status=EvaluationStatus.PENDING,
                    created_at=now,
                ))
            for device_id in (snapshot_config.get('deviceIds') or []):
                session.add(TaskDevice(task_id=task_id, device_id=device_id))
            for api_id in (snapshot_config.get('apiIds') or []):
                session.add(TaskAPI(task_id=task_id, api_id=api_id))
            for tag_name in (snapshot_config.get('tags') or []):
                tag = session.query(Tag).filter_by(name=tag_name).first()
                if not tag:
                    tag = Tag(name=tag_name, created_at=now, updated_at=now)
                    session.add(tag)
                    session.flush()
                session.add(TaskTag(task_id=task_id, tag_id=tag.id, created_at=now))

            session.commit()
            return task_id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ==================== 详情组装数据 ====================

    def get_source_task_summary(self, task_id: int):
        """来源日常任务摘要（详情页）。"""
        if not task_id:
            return None
        session = get_db_session()
        try:
            source = session.get(Task, task_id)
            if not source:
                return None
            return {
                'name': source.name,
                'status': source.status,
                'total_cases': source.total_cases,
                'completed_cases': source.completed_cases,
            }
        finally:
            session.close()

    def get_execution_history(self, version_ids):
        """该版本链创建并执行的日常任务（冻结快照 → 执行 → 数据可追溯）。"""
        if not version_ids:
            return []
        session = get_db_session()
        try:
            exec_tasks = (
                session.query(Task)
                .filter(
                    Task.execution_source == 'published_task',
                    Task.published_task_id.in_(list(version_ids)),
                    Task.deleted.is_(False),
                )
                .order_by(Task.created_at.desc())
                .limit(50)
                .all()
            )
            return [
                {
                    'task_id': t.id,
                    'task_name': t.name,
                    'version': t.published_task_version,
                    'status': t.status,
                    'total_cases': t.total_cases or 0,
                    'completed_cases': t.completed_cases or 0,
                    'created_at': t.created_at.isoformat() if t.created_at else None,
                    'completed_at': t.completed_at.isoformat() if t.completed_at else None,
                }
                for t in exec_tasks
            ]
        finally:
            session.close()


# 模块级单例
published_task_repository = PublishedTaskRepository()
