"""
已发布任务控制器 (Published Task Controller)

职责（对齐《任务发布功能设计文档》）：
- publish：日常任务 → 已发布任务（配置快照 + 版本 v1）
- get_all / get_one：已发布任务列表 / 详情（含版本历史）
- execute：读取快照创建新的日常任务（带追溯字段）
- create_version：不可变版本 vN → vN+1（旧版本 is_current=False）
- archive：幂等归档

权限：所有接口挂 require_permission；AUTH_ENABLED=false（V9.7.10 过渡）时默认放行。
"""
import logging
from flask import request
from sqlalchemy import or_, func

from backend.models.database import db
from backend.models.models import (
    Task, TaskCase, TaskDevice, TaskAPI, TestCase, Tag, PublishedTask, utc8now,
    Report, ReportSummary, ReportSummaryMeta, ReportRawData, ReportMetricStats, ReportCase,
)
from backend.utils.web.response import success_response, error_response
from backend.utils.web.error_codes import ErrorCode
from backend.utils.web.permissions import require_permission, PermissionPoints
from backend.schemas.common import IdData, StatusData
from backend.schemas.published_task import (
    PublishedTaskCreateRequest,
    PublishedTaskVersionCreateRequest,
    PublishedTaskUpdateRequest,
    PublishedTaskDetailData,
    PublishedTaskExecuteData,
    PublishedTaskItem,
    PublishedTaskListData,
)

logger = logging.getLogger(__name__)

# 可发布状态（与设计文档 §5.1 一致）
PUBLISHABLE_STATUSES = ('completed', 'failed', 'stopped', 'pending')


class PublishedTaskController:
    # ---------- 快照与校验 ----------

    @staticmethod
    def _build_snapshot(task):
        """从日常任务生成不可变配置快照（Domain 层约定 camelCase 字段名）"""
        case_ids = [
            tc.test_case_id
            for tc in TaskCase.query.filter_by(task_id=task.id, deleted=False).order_by(TaskCase.id).all()
        ]
        if not case_ids:
            # 历史数据兜底：task_case_relations 缺失时，从该任务的报告用例取（有报告的任务必可发布）
            report = (
                Report.query.filter_by(task_id=task.id, type='task', deleted=False)
                .order_by(Report.id.desc()).first()
            )
            if report:
                case_ids = [
                    c.test_case_id
                    for c in ReportCase.query.filter_by(report_id=report.id).all()
                    if c.test_case_id
                ]
        device_ids = [d.id for d in task.devices]
        api_ids = [a.id for a in task.apis]
        tag_names = [t.name for t in task.tags]
        return {
            'caseIds': list(dict.fromkeys(case_ids)),  # 去重保序
            'deviceIds': list(dict.fromkeys(device_ids)),
            'apiIds': list(dict.fromkeys(api_ids)),
            'config': task.config or {},
            'algorithmType': task.algorithm_type,
            'algorithmParams': task.algorithm_params or {},
            'tags': tag_names,
            'sourceTaskId': task.id,
        }

    @staticmethod
    def _freeze_report_snapshot(source_task_id):
        """冻结来源任务当时的执行产物（报告/用例结果/评估数据/用例日志）为不可变快照。

        无报告时返回 None；发布后即使源任务被改/删/重生成报告，冻结快照保持不变。
        """
        if not source_task_id:
            return None
        report = (
            Report.query.filter_by(task_id=source_task_id, type='task', deleted=False)
            .order_by(Report.id.desc()).first()
        )
        if not report:
            return None

        summary_info = ReportSummary.query.filter_by(report_id=report.id).first()
        summary_meta = ReportSummaryMeta.query.filter_by(report_id=report.id).first()
        metric_stats = ReportMetricStats.query.filter_by(report_id=report.id).first()
        cases = (
            ReportCase.query.filter_by(report_id=report.id)
            .order_by(ReportCase.id.asc()).all()
        )

        def _to_json(val):
            if val is None:
                return []
            if isinstance(val, (list, dict)):
                return val
            if isinstance(val, str):
                import json
                try:
                    return json.loads(val)
                except Exception:
                    return []
            return []

        def _to_json_obj(val):
            if val is None:
                return {}
            if isinstance(val, dict):
                return val
            if isinstance(val, str):
                import json
                try:
                    return json.loads(val)
                except Exception:
                    return {}
            return {}

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
                'caseCategories': _to_json(summary_meta.case_categories) if summary_meta else [],
                'allMetrics': _to_json(summary_meta.all_metrics) if summary_meta else [],
                'dimensionValues': _to_json(summary_meta.dimension_values) if summary_meta else [],
                'devices': _to_json(summary_meta.devices) if summary_meta else [],
                'apis': _to_json(summary_meta.apis) if summary_meta else [],
                'deviceStats': _to_json(metric_stats.device_stats) if metric_stats else [],
                'apiStats': _to_json(metric_stats.api_stats) if metric_stats else [],
                'metricData': _to_json_obj(metric_stats.metric_data) if metric_stats else {},
                'tagMetricData': _to_json_obj(metric_stats.tag_metric_data) if metric_stats else {},
            },
            'cases': [
                {
                    'testCaseId': c.test_case_id,
                    'name': c.name,
                    'description': c.description,
                    'category': c.category,
                    'tags': _to_json(c.tags),
                    'metrics': _to_json_obj(c.metrics),
                    'results': _to_json(c.results),
                    'audios': _to_json(c.audios),
                    'referenceParams': _to_json_obj(c.reference_params),
                    'algorithmResults': _to_json_obj(c.algorithm_results),
                    'algorithmType': c.algorithm_type,
                    'logs': c.logs,
                }
                for c in cases
            ],
        }

    @staticmethod
    def _get_publishable_task(source_task_id):
        """校验并返回可发布的源日常任务（设计文档 §5.1/§5.2）"""
        if not source_task_id:
            return None, error_response('sourceTaskId 不能为空', code=ErrorCode.INVALID_PARAMS, http_code=400)
        task = db.session.get(Task, source_task_id)
        if not task or task.deleted:
            return None, error_response('源任务不存在或已删除', code=ErrorCode.NOT_FOUND, http_code=404)
        if task.status not in PUBLISHABLE_STATUSES:
            return None, error_response(
                f'任务当前状态为 {task.status}，仅 completed/failed/stopped/pending 可发布',
                code=ErrorCode.OPERATION_FAILED, http_code=400,
            )
        return task, None

    @staticmethod
    def _validate_snapshot(snapshot):
        """快照完整性校验：至少一个存在用例；已删除的用例 ID 自动过滤（历史报告兜底场景）"""
        case_ids = snapshot.get('caseIds') or []
        if not case_ids:
            return None, error_response('已发布任务至少需要包含一个测试用例', code=ErrorCode.INVALID_PARAMS, http_code=400)
        existing = {
            cid for (cid,) in db.session.query(TestCase.id).filter(TestCase.id.in_(case_ids)).all()
        }
        valid = [cid for cid in dict.fromkeys(case_ids) if cid in existing]
        if not valid:
            return None, error_response('用例不存在（已删除），无法发布', code=ErrorCode.INVALID_PARAMS, http_code=400)
        return valid, None

    @staticmethod
    def _build_new_task(published_task):
        """按快照创建新的日常任务（执行已发布任务的复用链路）"""
        snapshot = published_task.snapshot_config or {}
        case_ids, err = PublishedTaskController._validate_snapshot(snapshot)
        if err:
            return None, err

        new_task = Task(
            name=f"{published_task.name} (v{published_task.version})",
            description=published_task.description,
            type=published_task.type,
            status='pending',
            config=snapshot.get('config') or {},
            algorithm_type=snapshot.get('algorithmType'),
            algorithm_params=snapshot.get('algorithmParams') or {},
            total_cases=len(case_ids),
            execution_source='published_task',
            published_task_id=published_task.id,
            published_task_version=published_task.version,
        )
        db.session.add(new_task)
        db.session.flush()

        for case_id in case_ids:
            db.session.add(TaskCase(
                task_id=new_task.id,
                test_case_id=case_id,
                status='pending',
                execution_status='pending',
                evaluation_status='pending',
            ))
        for device_id in (snapshot.get('deviceIds') or []):
            db.session.add(TaskDevice(task_id=new_task.id, device_id=device_id))
        for api_id in (snapshot.get('apiIds') or []):
            db.session.add(TaskAPI(task_id=new_task.id, api_id=api_id))
        for tag_name in (snapshot.get('tags') or []):
            tag = Tag.query.filter_by(name=tag_name).first()
            if not tag:
                tag = Tag(name=tag_name)
                db.session.add(tag)
            new_task.tags.append(tag)
        return new_task, None

    # ---------- 发布 ----------

    @staticmethod
    def publish():
        perm_err = require_permission(PermissionPoints.TASK_PUBLISH)
        if perm_err:
            return perm_err

        req = PublishedTaskCreateRequest.model_validate(request.get_json())
        task, err = PublishedTaskController._get_publishable_task(req.source_task_id)
        if err:
            return err

        snapshot = PublishedTaskController._build_snapshot(task)
        _, err = PublishedTaskController._validate_snapshot(snapshot)
        if err:
            return err
        report_snapshot = PublishedTaskController._freeze_report_snapshot(req.source_task_id)

        try:
            published = PublishedTask(
                name=req.name,
                description=req.description,
                source_task_id=req.source_task_id,
                type=task.type,
                # 冗余算法类型：发布时冻结自源任务，列表按算法筛选直接查本列
                algorithm_type=snapshot.get('algorithmType'),
                status='published',
                version=1,
                is_current=True,
                snapshot_config=snapshot,
                report_snapshot=report_snapshot,
                publish_reason=req.publish_reason,
                published_by=None,  # G 域落地后从 request.state.username 回填
            )
            db.session.add(published)
            db.session.flush()
            published.task_group_id = published.id  # 首个版本 ID 作为版本链锚点
            db.session.commit()
            return success_response(IdData(id=published.id), '已发布任务创建成功', http_code=201)
        except Exception as e:
            db.session.rollback()
            logger.exception('发布已发布任务失败')
            return error_response(str(e), code=ErrorCode.DATABASE_ERROR)

    # ---------- 查询 ----------

    @staticmethod
    def get_all():
        perm_err = require_permission(PermissionPoints.PUBLISHED_TASK_READ)
        if perm_err:
            return perm_err

        page = max(int(request.args.get('page', 1)), 1)
        per_page = min(max(int(request.args.get('perPage', 10)), 1), 100)
        status = request.args.get('status', '')
        keyword = request.args.get('keyword', '').strip()
        task_type = request.args.get('type', '')
        algorithm_type = request.args.get('algorithm_type', '')
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')

        query = PublishedTask.query.filter(PublishedTask.is_current.is_(True))
        if status:
            query = query.filter(PublishedTask.status == status)
        if task_type:
            query = query.filter(PublishedTask.type == task_type)
        if algorithm_type and algorithm_type != 'all':
            # 直接查发布时冻结的冗余列
            query = query.filter(PublishedTask.algorithm_type == algorithm_type)
        if keyword:
            like = f'%{keyword}%'
            query = query.filter(or_(PublishedTask.name.ilike(like), PublishedTask.description.ilike(like)))
        if start_date or end_date:
            from datetime import datetime
            if start_date:
                try:
                    query = query.filter(PublishedTask.published_at >= datetime.fromisoformat(start_date))
                except ValueError:
                    pass
            if end_date:
                try:
                    query = query.filter(PublishedTask.published_at <= datetime.fromisoformat(end_date))
                except ValueError:
                    pass

        total = query.count()
        rows = (
            query.order_by(PublishedTask.published_at.desc(), PublishedTask.id.desc())
            .offset((page - 1) * per_page).limit(per_page).all()
        )

        # 版本数统计（按 task_group_id 分组）
        group_ids = [r.task_group_id or r.id for r in rows]
        version_counts = {}
        if group_ids:
            counts = (
                db.session.query(PublishedTask.task_group_id, func.count(PublishedTask.id))
                .filter(PublishedTask.task_group_id.in_(group_ids))
                .group_by(PublishedTask.task_group_id).all()
            )
            version_counts = {gid: cnt for gid, cnt in counts}

        items = [
            PublishedTaskItem(
                id=r.id,
                source_task_id=r.source_task_id,
                name=r.name,
                description=r.description,
                type=r.type,
                algorithm_type=r.algorithm_type,
                status=r.status,
                version=r.version,
                is_current=r.is_current,
                version_count=version_counts.get(r.task_group_id or r.id, 1),
                published_by=r.published_by,
                published_at=r.published_at.isoformat() if r.published_at else None,
                archived_at=r.archived_at.isoformat() if r.archived_at else None,
                created_at=r.created_at.isoformat() if r.created_at else None,
            )
            for r in rows
        ]
        pages = (total + per_page - 1) // per_page if total else 0
        return success_response(PublishedTaskListData(
            items=items, total=total, page=page, per_page=per_page, pages=pages,
        ))

    @staticmethod
    def get_one(published_task_id):
        perm_err = require_permission(PermissionPoints.PUBLISHED_TASK_READ)
        if perm_err:
            return perm_err

        pt = db.session.get(PublishedTask, published_task_id)
        if not pt:
            return error_response('已发布任务不存在', code=ErrorCode.NOT_FOUND, http_code=404)

        source_summary = None
        if pt.source_task_id:
            source = db.session.get(Task, pt.source_task_id)
            if source:
                source_summary = {
                    'name': source.name,
                    'status': source.status,
                    'total_cases': source.total_cases,
                    'completed_cases': source.completed_cases,
                }

        versions = []
        group_id = pt.task_group_id or pt.id
        group_versions = (
            PublishedTask.query.filter(PublishedTask.task_group_id == group_id)
            .order_by(PublishedTask.version.desc()).all()
        )
        for v in group_versions:
            versions.append(PublishedTaskItem(
                id=v.id,
                source_task_id=v.source_task_id,
                name=v.name,
                description=v.description,
                type=v.type,
                status=v.status,
                version=v.version,
                is_current=v.is_current,
                published_by=v.published_by,
                published_at=v.published_at.isoformat() if v.published_at else None,
                archived_at=v.archived_at.isoformat() if v.archived_at else None,
                created_at=v.created_at.isoformat() if v.created_at else None,
            ))

        # 执行历史：该版本链创建并执行的日常任务（冻结快照 → 执行 → 数据可追溯）
        version_ids = [v.id for v in group_versions]
        execution_history = []
        if version_ids:
            from backend.models.models import Task as DailyTask
            exec_tasks = (
                DailyTask.query.filter(
                    DailyTask.execution_source == 'published_task',
                    DailyTask.published_task_id.in_(version_ids),
                    DailyTask.deleted.is_(False),
                )
                .order_by(DailyTask.created_at.desc())
                .limit(50)
                .all()
            )
            from backend.schemas.published_task import PublishedTaskExecutionItem
            for t in exec_tasks:
                execution_history.append(PublishedTaskExecutionItem(
                    task_id=t.id,
                    task_name=t.name,
                    version=t.published_task_version or pt.version,
                    status=t.status,
                    total_cases=t.total_cases or 0,
                    completed_cases=t.completed_cases or 0,
                    created_at=t.created_at.isoformat() if t.created_at else None,
                    completed_at=t.completed_at.isoformat() if t.completed_at else None,
                ))

        return success_response(PublishedTaskDetailData(
            id=pt.id,
            task_group_id=group_id,
            source_task_id=pt.source_task_id,
            name=pt.name,
            description=pt.description,
            type=pt.type,
            status=pt.status,
            version=pt.version,
            is_current=pt.is_current,
            snapshot_config=pt.snapshot_config or {},
            publish_reason=pt.publish_reason,
            published_by=pt.published_by,
            published_at=pt.published_at.isoformat() if pt.published_at else None,
            archived_by=pt.archived_by,
            archived_at=pt.archived_at.isoformat() if pt.archived_at else None,
            source_task_name=source_summary['name'] if source_summary else None,
            source_task_status=source_summary['status'] if source_summary else None,
            source_task_total_cases=source_summary['total_cases'] if source_summary else None,
            source_task_completed_cases=source_summary['completed_cases'] if source_summary else None,
            report_snapshot=pt.report_snapshot or None,
            has_report_snapshot=bool(pt.report_snapshot),
            versions=versions,
            execution_history=execution_history,
        ))

    # ---------- 执行 ----------

    @staticmethod
    def execute(published_task_id):
        perm_err = require_permission(PermissionPoints.PUBLISHED_TASK_EXECUTE)
        if perm_err:
            return perm_err

        pt = db.session.get(PublishedTask, published_task_id)
        if not pt:
            return error_response('已发布任务不存在', code=ErrorCode.NOT_FOUND, http_code=404)
        if pt.status == 'archived':
            return error_response('已归档任务禁止执行，请选择可用版本', code=ErrorCode.OPERATION_FAILED, http_code=400)

        try:
            new_task, err = PublishedTaskController._build_new_task(pt)
            if err:
                return err
            db.session.commit()
            return success_response(PublishedTaskExecuteData(
                task_id=new_task.id,
                task_name=new_task.name,
                published_task_id=pt.id,
                published_task_version=pt.version,
            ), '日常任务创建成功，可前往任务列表执行')
        except Exception as e:
            db.session.rollback()
            logger.exception('执行已发布任务失败')
            return error_response(str(e), code=ErrorCode.DATABASE_ERROR)

    # ---------- 新版本 ----------

    @staticmethod
    def create_version(published_task_id):
        perm_err = require_permission(PermissionPoints.PUBLISHED_TASK_VERSION)
        if perm_err:
            return perm_err

        req = PublishedTaskVersionCreateRequest.model_validate(request.get_json() or {})
        pt = db.session.get(PublishedTask, published_task_id)
        if not pt:
            return error_response('已发布任务不存在', code=ErrorCode.NOT_FOUND, http_code=404)

        group_id = pt.task_group_id or pt.id
        current = (
            PublishedTask.query.filter(
                PublishedTask.task_group_id == group_id,
                PublishedTask.is_current.is_(True),
            ).first()
        ) or pt

        try:
            # 新版本数据源：指定新来源任务则重新生成快照，否则沿用当前版本快照
            if req.source_task_id:
                task, err = PublishedTaskController._get_publishable_task(req.source_task_id)
                if err:
                    return err
                snapshot = PublishedTaskController._build_snapshot(task)
                source_task_id = task.id
            else:
                snapshot = dict(current.snapshot_config or {})
                source_task_id = current.source_task_id
            _, err = PublishedTaskController._validate_snapshot(snapshot)
            if err:
                return err

            new_version = PublishedTask(
                task_group_id=group_id,
                source_task_id=source_task_id,
                name=req.name or current.name,
                description=req.description if req.description is not None else current.description,
                type=current.type,
                # 冗余算法类型：沿用快照冻结值
                algorithm_type=snapshot.get('algorithmType'),
                status='published',
                version=current.version + 1,
                is_current=True,
                snapshot_config=snapshot,
                publish_reason=req.publish_reason,
                published_by=None,
            )
            current.is_current = False
            db.session.add(new_version)
            db.session.commit()
            return success_response(IdData(id=new_version.id), f'已发布任务 v{new_version.version} 创建成功', http_code=201)
        except Exception as e:
            db.session.rollback()
            logger.exception('创建已发布任务新版本失败')
            return error_response(str(e), code=ErrorCode.DATABASE_ERROR)

    # ---------- 归档 ----------

    @staticmethod
    def archive(published_task_id):
        perm_err = require_permission(PermissionPoints.PUBLISHED_TASK_ARCHIVE)
        if perm_err:
            return perm_err

        pt = db.session.get(PublishedTask, published_task_id)
        if not pt:
            return error_response('已发布任务不存在', code=ErrorCode.NOT_FOUND, http_code=404)
        if pt.status == 'archived':  # 幂等
            return success_response(StatusData(id=pt.id, status=pt.status), '任务已归档')

        try:
            pt.status = 'archived'
            pt.archived_by = None  # G 域落地后从 request.state.username 回填
            pt.archived_at = utc8now()
            db.session.commit()
            return success_response(StatusData(id=pt.id, status=pt.status), '任务已归档')
        except Exception as e:
            db.session.rollback()
            logger.exception('归档已发布任务失败')
            return error_response(str(e), code=ErrorCode.DATABASE_ERROR)

    # ---------- 重命名 ----------

    @staticmethod
    def update(published_task_id):
        perm_err = require_permission(PermissionPoints.PUBLISHED_TASK_READ)
        if perm_err:
            return perm_err

        req = PublishedTaskUpdateRequest.model_validate(request.get_json())
        name = req.name.strip()
        if not name:
            return error_response('任务名称不能为空', code=ErrorCode.MISSING_PARAMS)

        pt = db.session.get(PublishedTask, published_task_id)
        if not pt:
            return error_response('已发布任务不存在', code=ErrorCode.NOT_FOUND, http_code=404)

        try:
            # 重命名作用于整个版本链（task_group_id 锚点），保持版本间名称一致
            group_id = pt.task_group_id or pt.id
            versions = PublishedTask.query.filter(
                or_(PublishedTask.task_group_id == group_id, PublishedTask.id == group_id)
            ).all()
            for v in versions:
                v.name = name
            db.session.commit()
            return success_response(IdData(id=pt.id, name=name), '任务名称已更新')
        except Exception as e:
            db.session.rollback()
            logger.exception('重命名已发布任务失败')
            return error_response(str(e), code=ErrorCode.DATABASE_ERROR)

