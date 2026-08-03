"""api_gateway 应用层 —— 查询处理器

CQRS Query Handler：所有读操作直接查本地 DB，返回 DTO 字典。

不经过 controllers，routes 层直接调用这些 handler。
"""
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta

from shared.models.database import db
from shared.models.models import (
    TestCase, TestCaseGroup, Tag, Task, Report, ReportStatus,
    Audio, Device, API, TestResult, Dimension,
    TaskStatus
)
from shared.utils.response import success_response, error_response

from api_gateway.application.queries.case_queries import (
    GetTestCaseQuery, ListTestCasesQuery, GetTestCaseStatsQuery,
    GetTaskQuery, ListTasksQuery,
    GetReportQuery, ListReportsQuery,
    GetAudioQuery, ListAudiosQuery,
    GetHomeStatsQuery,
)


class GetTestCaseHandler:
    """获取单个测试用例"""

    def handle(self, query: GetTestCaseQuery) -> tuple:
        case = db.session.get(TestCase, query.tc_id)
        if not case or case.deleted:
            return error_response('未找到指定测试用例')

        return success_response({
            'id': case.id,
            'name': case.name,
            'description': case.description or '',
            'group': {
                'id': case.group.id,
                'name': case.group.name,
            } if case.group else None,
            'algorithm_type': case.algorithm_type,
            'config': case.config or {},
            'tags': [{'id': t.id, 'name': t.name} for t in (case.tags or [])],
            'created_at': case.created_at.isoformat() if case.created_at else None,
        })


class ListTestCasesHandler:
    """测试用例列表"""

    def handle(self, query: ListTestCasesQuery) -> tuple:
        q = TestCase.query.filter_by(deleted=False)

        if query.group_id:
            q = q.filter_by(group_id=query.group_id)

        if query.keyword:
            q = q.filter(TestCase.name.ilike(f'%{query.keyword}%'))

        if query.tag_ids:
            q = q.join(TestCase.tags).filter(Tag.id.in_(query.tag_ids))

        total = q.count()
        cases = q.order_by(TestCase.created_at.desc()) \
                 .offset((query.page - 1) * query.page_size) \
                 .limit(query.page_size).all()

        return success_response({
            'total': total,
            'page': query.page,
            'page_size': query.page_size,
            'items': [{
                'id': c.id,
                'name': c.name,
                'description': c.description or '',
                'group': {'id': c.group.id, 'name': c.group.name} if c.group else None,
                'algorithm_type': c.algorithm_type,
                'tags': [{'id': t.id, 'name': t.name} for t in (c.tags or [])],
            } for c in cases],
        })


class GetTestCaseStatsHandler:
    """测试用例统计"""

    def handle(self, query: GetTestCaseStatsQuery) -> tuple:
        q = TestCase.query.filter_by(deleted=False)
        if query.group_id:
            q = q.filter_by(group_id=query.group_id)

        total = q.count()
        by_algorithm = db.session.query(
            TestCase.algorithm_type,
            db.func.count(TestCase.id)
        ).filter_by(deleted=False).group_by(TestCase.algorithm_type).all()

        return success_response({
            'total': total,
            'by_algorithm': {algo: count for algo, count in by_algorithm},
        })


class GetTaskHandler:
    """获取任务详情"""

    def handle(self, query: GetTaskQuery) -> tuple:
        task = db.session.get(Task, query.task_id)
        if not task:
            return error_response('未找到指定任务')

        return success_response({
            'id': task.id,
            'name': task.name,
            'status': task.status,
            'type': task.type,
            'total_cases': task.total_cases,
            'completed_cases': task.completed_cases,
            'failed_cases': task.failed_cases,
            'created_at': task.created_at.isoformat() if task.created_at else None,
        })


class ListTasksHandler:
    """任务列表"""

    def handle(self, query: ListTasksQuery) -> tuple:
        q = Task.query.filter_by(deleted=False)

        if query.status:
            q = q.filter_by(status=query.status)
        if query.task_type:
            q = q.filter_by(type=query.task_type)

        total = q.count()
        tasks = q.order_by(Task.created_at.desc()) \
                  .offset((query.page - 1) * query.page_size) \
                  .limit(query.page_size).all()

        return success_response({
            'total': total,
            'page': query.page,
            'page_size': query.page_size,
            'items': [{
                'id': t.id,
                'name': t.name,
                'status': t.status,
                'type': t.type,
                'total_cases': t.total_cases,
                'completed_cases': t.completed_cases,
                'failed_cases': t.failed_cases,
            } for t in tasks],
        })


class GetReportHandler:
    """获取报告"""

    def handle(self, query: GetReportQuery) -> tuple:
        report = db.session.get(Report, query.report_id)
        if not report:
            return error_response('未找到指定报告')

        return success_response({
            'id': report.id,
            'task_id': report.task_id,
            'name': report.name,
            'type': report.type,
            'status': report.status,
            'created_at': report.created_at.isoformat() if report.created_at else None,
        })


class ListReportsHandler:
    """报告列表"""

    def handle(self, query: ListReportsQuery) -> tuple:
        q = Report.query

        if query.task_id:
            q = q.filter_by(task_id=query.task_id)

        total = q.count()
        reports = q.order_by(Report.created_at.desc()) \
                   .offset((query.page - 1) * query.page_size) \
                   .limit(query.page_size).all()

        return success_response({
            'total': total,
            'page': query.page,
            'page_size': query.page_size,
            'items': [{
                'id': r.id,
                'task_id': r.task_id,
                'name': r.name,
                'type': r.type,
                'status': r.status,
            } for r in reports],
        })


class GetAudioHandler:
    """获取音频"""

    def handle(self, query: GetAudioQuery) -> tuple:
        audio = db.session.get(Audio, query.audio_id)
        if not audio:
            return error_response('未找到指定音频')

        return success_response({
            'id': audio.id,
            'file_name': audio.file_name,
            'file_path': audio.file_path,
            'md5': audio.md5,
            'storage_type': getattr(audio, 'storage_type', 'local'),
        })


class ListAudiosHandler:
    """音频列表"""

    def handle(self, query: ListAudiosQuery) -> tuple:
        q = Audio.query

        if query.keyword:
            q = q.filter(Audio.file_name.ilike(f'%{query.keyword}%'))

        total = q.count()
        audios = q.order_by(Audio.created_at.desc()) \
                  .offset((query.page - 1) * query.page_size) \
                  .limit(query.page_size).all()

        return success_response({
            'total': total,
            'page': query.page,
            'page_size': query.page_size,
            'items': [{
                'id': a.id,
                'file_name': a.file_name,
                'file_path': a.file_path,
                'md5': a.md5,
            } for a in audios],
        })


class GetHomeStatsHandler:
    """首页统计"""

    def handle(self, query: GetHomeStatsQuery) -> tuple:
        case_count = TestCase.query.filter_by(deleted=False).count()
        task_count = Task.query.filter_by(deleted=False).count()
        report_count = Report.query.count()
        audio_count = Audio.query.count()
        device_count = Device.query.filter_by(deleted=False).count()
        api_count = API.query.filter_by(deleted=False).count()

        running_tasks = Task.query.filter(
            Task.status.in_([TaskStatus.PENDING.value, TaskStatus.RUNNING.value])
        ).count()

        return success_response({
            'cases': case_count,
            'tasks': task_count,
            'reports': report_count,
            'audios': audio_count,
            'devices': device_count,
            'apis': api_count,
            'running_tasks': running_tasks,
        })
