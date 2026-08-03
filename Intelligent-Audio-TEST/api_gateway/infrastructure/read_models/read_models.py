"""api_gateway 基础设施层 —— 读模型

CQRS 读模型：优化复杂查询，避免走 ORM 关系加载。

对于简单 CRUD 查询直接用 application/queries/handlers.py 中的 ORM 查询。
对于复杂列表、统计、聚合查询，使用 read_models 直接 SQL 查询优化。
"""
from sqlalchemy import text, func
from shared.models.database import db
from shared.models.models import (
    TestCase, Task, TestResult, Report, Audio, Device, API,
    Dimension, TestCaseGroup, Tag, TaskStatus
)
from typing import Optional, List, Dict, Any


class TestCaseReadModel:
    """测试用例读模型 —— 优化列表查询"""

    @staticmethod
    def list_with_stats(page: int = 1, page_size: int = 20,
                        group_id: Optional[str] = None,
                        keyword: Optional[str] = None) -> dict:
        """列表 + 统计信息"""
        sql = text("""
            SELECT
                tc.id, tc.name, tc.description, tc.algorithm_type,
                tc.group_id, tc.created_at,
                g.name as group_name,
                (SELECT COUNT(*) FROM test_results tr
                 WHERE tr.test_case_id = tc.id) as result_count,
                (SELECT COUNT(*) FROM task_cases tcm
                 WHERE tcm.test_case_id = tc.id) as task_count
            FROM test_cases tc
            LEFT JOIN test_case_groups g ON tc.group_id = g.id
            WHERE tc.deleted = false
            ORDER BY tc.created_at DESC
            LIMIT :limit OFFSET :offset
        """)

        params = {'limit': page_size, 'offset': (page - 1) * page_size}
        result = db.session.execute(sql, params).fetchall()

        items = [{
            'id': row.id,
            'name': row.name,
            'description': row.description or '',
            'algorithm_type': row.algorithm_type,
            'group': {'id': row.group_id, 'name': row.group_name} if row.group_id else None,
            'result_count': row.result_count,
            'task_count': row.task_count,
            'created_at': row.created_at.isoformat() if row.created_at else None,
        } for row in result]

        count_sql = text("SELECT COUNT(*) FROM test_cases WHERE deleted = false")
        total = db.session.execute(count_sql).scalar() or 0

        return {'total': total, 'page': page, 'page_size': page_size, 'items': items}


class TaskReadModel:
    """任务读模型 —— 优化任务列表 + 进度查询"""

    @staticmethod
    def list_with_progress(page: int = 1, page_size: int = 20,
                           status: Optional[str] = None,
                           task_type: Optional[str] = None) -> dict:
        """任务列表 + 进度"""
        q = Task.query.filter_by(deleted=False)

        if status:
            q = q.filter_by(status=status)
        if task_type:
            q = q.filter_by(type=task_type)

        total = q.count()
        tasks = q.order_by(Task.created_at.desc()) \
                  .offset((page - 1) * page_size) \
                  .limit(page_size).all()

        items = []
        for t in tasks:
            progress = 0
            if t.total_cases and t.total_cases > 0:
                progress = round(
                    (t.completed_cases or 0) / t.total_cases * 100, 2
                )
            items.append({
                'id': t.id,
                'name': t.name,
                'status': t.status,
                'type': t.type,
                'total_cases': t.total_cases or 0,
                'completed_cases': t.completed_cases or 0,
                'failed_cases': t.failed_cases or 0,
                'progress': progress,
                'created_at': t.created_at.isoformat() if t.created_at else None,
            })

        return {'total': total, 'page': page, 'page_size': page_size, 'items': items}


class ReportReadModel:
    """报告读模型 —— 优化报告列表 + 详情"""

    @staticmethod
    def list_with_task_info(page: int = 1, page_size: int = 20,
                            task_id: Optional[str] = None) -> dict:
        """报告列表 + 关联任务信息"""
        q = Report.query
        if task_id:
            q = q.filter_by(task_id=task_id)

        total = q.count()
        reports = q.order_by(Report.created_at.desc()) \
                   .offset((page - 1) * page_size) \
                   .limit(page_size).all()

        items = []
        for r in reports:
            task = db.session.get(Task, r.task_id) if r.task_id else None
            items.append({
                'id': r.id,
                'task_id': r.task_id,
                'task_name': task.name if task else None,
                'name': r.name,
                'type': r.type,
                'status': r.status,
                'created_at': r.created_at.isoformat() if r.created_at else None,
            })

        return {'total': total, 'page': page, 'page_size': page_size, 'items': items}


class HomeStatsReadModel:
    """首页统计读模型 —— 聚合统计"""

    @staticmethod
    def get_dashboard_stats() -> dict:
        """获取首页仪表盘统计"""
        case_count = TestCase.query.filter_by(deleted=False).count()
        task_count = Task.query.filter_by(deleted=False).count()
        report_count = Report.query.count()
        audio_count = Audio.query.count()
        device_count = Device.query.filter_by(deleted=False).count()
        api_count = API.query.filter_by(deleted=False).count()
        group_count = TestCaseGroup.query.count()
        dimension_count = Dimension.query.filter_by(status=True, deleted=False).count()

        running_tasks = Task.query.filter(
            Task.status.in_([TaskStatus.PENDING.value, TaskStatus.RUNNING.value])
        ).count()

        completed_tasks = Task.query.filter_by(
            status=TaskStatus.COMPLETED.value, deleted=False
        ).count()

        failed_tasks = Task.query.filter_by(
            status=TaskStatus.FAILED.value, deleted=False
        ).count()

        return {
            'cases': case_count,
            'tasks': task_count,
            'running_tasks': running_tasks,
            'completed_tasks': completed_tasks,
            'failed_tasks': failed_tasks,
            'reports': report_count,
            'audios': audio_count,
            'devices': device_count,
            'apis': api_count,
            'groups': group_count,
            'dimensions': dimension_count,
        }
