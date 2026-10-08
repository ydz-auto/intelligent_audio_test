# -*- coding: utf-8 -*-
"""已发布任务应用服务（Published Task Service）

对齐 V9.7.10 published_task_controller 的完整业务逻辑：
- publish：日常任务 → 已发布任务（配置快照 + 版本 v1 + 报告冻结）
- get_list / get_detail：当前版本列表（分页+筛选）/ 详情（版本历史 + 来源摘要 + 执行历史）
- execute：读取快照创建新的日常任务（带追溯字段）
- create_version：不可变版本 vN → vN+1（旧版本 is_current=False）
- archive：幂等归档
- update_name：重命名作用于整个版本链

约定：所有方法返回 dict: {success, message, data, code}（与 task_service 应用服务一致）。
数据经 gRPC 序列化为 JSON，网关层负责转换 snake_case 契约。
"""
import logging
from datetime import datetime

from task_service.infrastructure.persistence._task_converters import _UTC_PLUS_8
from task_service.infrastructure.persistence.published_task_repository import (
    published_task_repository as repo,
    PUBLISHABLE_STATUSES,
)

logger = logging.getLogger(__name__)


class PublishedTaskService:
    """已发布任务应用服务（静态方法 + 模块级单例）。"""

    # ---------- 快照与校验 ----------

    @staticmethod
    def _build_snapshot(task):
        """从日常任务生成不可变配置快照（camelCase 字段名契约）。

        Args:
            task: Task PO（必须已加载 config/algorithm_type/algorithm_params）
        """
        case_ids = repo.get_task_case_ids(task.id)
        if not case_ids:
            # 历史数据兜底：task_case_relations 缺失时，从该任务的报告用例取
            case_ids = repo.get_task_report_case_ids(task.id)
        device_ids = repo.get_task_device_ids(task.id)
        api_ids = repo.get_task_api_ids(task.id)
        tag_names = repo.get_task_tag_names(task.id)
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
    def _get_publishable_task(source_task_id):
        """校验并返回可发布的源日常任务（设计文档 §5.1/§5.2）。"""
        if not source_task_id:
            return None, 'sourceTaskId 不能为空', 100, 400
        task = repo.get_task(source_task_id)
        if not task or task.deleted:
            return None, '源任务不存在或已删除', 201, 404
        if task.status not in PUBLISHABLE_STATUSES:
            return None, (
                f'任务当前状态为 {task.status}，仅 completed/failed/stopped/pending 可发布'
            ), 203, 400
        return task, None, 0, 0

    @staticmethod
    def _validate_snapshot(snapshot):
        """快照完整性校验：至少一个存在用例；已删除的用例 ID 自动过滤。"""
        case_ids = snapshot.get('caseIds') or []
        if not case_ids:
            return None, '已发布任务至少需要包含一个测试用例', 100, 400
        existing = repo.get_existing_case_ids(case_ids)
        valid = [cid for cid in dict.fromkeys(case_ids) if cid in existing]
        if not valid:
            return None, '用例不存在（已删除），无法发布', 100, 400
        return valid, None, 0, 0

    # ---------- 发布 ----------

    @staticmethod
    def publish(data: dict) -> dict:
        """发布：日常任务 → 已发布任务 v1（冻结快照 + 报告快照）。"""
        try:
            source_task_id = data.get('source_task_id') or data.get('sourceTaskId')
            name = (data.get('name') or '').strip()
            if not source_task_id:
                return {'success': False, 'message': 'sourceTaskId 不能为空', 'data': None, 'code': 100}
            if not name:
                return {'success': False, 'message': '任务名称不能为空', 'data': None, 'code': 101}

            task, err, code, http = PublishedTaskService._get_publishable_task(source_task_id)
            if err:
                return {'success': False, 'message': err, 'data': None, 'code': code}

            snapshot = PublishedTaskService._build_snapshot(task)
            _, err, code, _ = PublishedTaskService._validate_snapshot(snapshot)
            if err:
                return {'success': False, 'message': err, 'data': None, 'code': code}
            report_snapshot = repo.freeze_report_snapshot(source_task_id)

            pt = repo.create(
                name=name,
                description=data.get('description'),
                source_task_id=source_task_id,
                task_type=task.type,
                status='published',
                version=1,
                is_current=True,
                snapshot_config=snapshot,
                report_snapshot=report_snapshot,
                publish_reason=data.get('publish_reason') or data.get('publishReason'),
                published_by=None,  # G 域落地后从请求上下文回填
            )
            return {'success': True, 'message': '已发布任务创建成功', 'data': {'id': pt.id}, 'code': 201}
        except Exception as e:
            logger.exception('发布已发布任务失败')
            return {'success': False, 'message': str(e), 'data': None, 'code': 301}

    # ---------- 查询 ----------

    @staticmethod
    def _item_dict(pt, version_count=None) -> dict:
        """PublishedTask PO → 列表项 dict（snake_case 契约）。"""
        return {
            'id': pt.id,
            'source_task_id': pt.source_task_id,
            'name': pt.name,
            'description': pt.description,
            'type': pt.type,
            'status': pt.status,
            'version': pt.version,
            'is_current': pt.is_current,
            'version_count': version_count,
            'published_by': pt.published_by,
            'published_at': pt.published_at.isoformat() if pt.published_at else None,
            'archived_at': pt.archived_at.isoformat() if pt.archived_at else None,
            'created_at': pt.created_at.isoformat() if pt.created_at else None,
        }

    @staticmethod
    def get_list(page: int = 1, per_page: int = 10, status: str = '',
                 keyword: str = '', task_type: str = '',
                 start_date: str = '', end_date: str = '') -> dict:
        """当前版本列表（分页 + status/keyword/type/时间筛选 + 版本数统计）。"""
        try:
            rows, total = repo.get_list(
                page=page, per_page=per_page, status=status, keyword=keyword,
                task_type=task_type, start_date=start_date, end_date=end_date,
            )
            group_ids = [r.task_group_id or r.id for r in rows]
            version_counts = repo.get_version_counts(group_ids)
            items = [
                PublishedTaskService._item_dict(
                    r, version_counts.get(r.task_group_id or r.id, 1)
                )
                for r in rows
            ]
            pages = (total + per_page - 1) // per_page if total else 0
            return {
                'success': True,
                'message': 'ok',
                'data': {
                    'items': items,
                    'total': total,
                    'page': page,
                    'per_page': per_page,
                    'pages': pages,
                },
                'code': 0,
            }
        except Exception as e:
            logger.exception('查询已发布任务列表失败')
            return {'success': False, 'message': str(e), 'data': None, 'code': 301}

    @staticmethod
    def get_detail(published_task_id: int) -> dict:
        """详情（元数据 + 快照 + 来源任务摘要 + 版本历史 + 执行历史）。"""
        try:
            pt = repo.get_by_id(published_task_id)
            if not pt:
                return {'success': False, 'message': '已发布任务不存在', 'data': None, 'code': 201}

            source_summary = repo.get_source_task_summary(pt.source_task_id)

            group_id = pt.task_group_id or pt.id
            group_versions = repo.get_group_versions(group_id)
            versions = [
                PublishedTaskService._item_dict(v) for v in group_versions
            ]

            version_ids = [v.id for v in group_versions]
            execution_history = repo.get_execution_history(version_ids)
            for item in execution_history:
                if not item.get('version'):
                    item['version'] = pt.version

            return {
                'success': True,
                'message': 'ok',
                'data': {
                    'id': pt.id,
                    'task_group_id': group_id,
                    'source_task_id': pt.source_task_id,
                    'name': pt.name,
                    'description': pt.description,
                    'type': pt.type,
                    'status': pt.status,
                    'version': pt.version,
                    'is_current': pt.is_current,
                    'snapshot_config': pt.snapshot_config or {},
                    'publish_reason': pt.publish_reason,
                    'published_by': pt.published_by,
                    'published_at': pt.published_at.isoformat() if pt.published_at else None,
                    'archived_by': pt.archived_by,
                    'archived_at': pt.archived_at.isoformat() if pt.archived_at else None,
                    'source_task_name': source_summary['name'] if source_summary else None,
                    'source_task_status': source_summary['status'] if source_summary else None,
                    'source_task_total_cases': source_summary['total_cases'] if source_summary else None,
                    'source_task_completed_cases': source_summary['completed_cases'] if source_summary else None,
                    'report_snapshot': pt.report_snapshot or None,
                    'has_report_snapshot': bool(pt.report_snapshot),
                    'versions': versions,
                    'execution_history': execution_history,
                },
                'code': 0,
            }
        except Exception as e:
            logger.exception('查询已发布任务详情失败')
            return {'success': False, 'message': str(e), 'data': None, 'code': 301}

    # ---------- 执行 ----------

    @staticmethod
    def execute(published_task_id: int) -> dict:
        """执行：按快照创建新的日常任务（带追溯字段）。"""
        try:
            pt = repo.get_by_id(published_task_id)
            if not pt:
                return {'success': False, 'message': '已发布任务不存在', 'data': None, 'code': 201}
            if pt.status == 'archived':
                return {'success': False, 'message': '已归档任务禁止执行，请选择可用版本', 'data': None, 'code': 203}

            snapshot = pt.snapshot_config or {}
            case_ids, err, code, _ = PublishedTaskService._validate_snapshot(snapshot)
            if err:
                return {'success': False, 'message': err, 'data': None, 'code': code}

            new_task_id = repo.create_daily_task(
                name=f"{pt.name} (v{pt.version})",
                description=pt.description,
                task_type=pt.type,
                snapshot_config=snapshot,
                case_ids=case_ids,
            )
            repo.update_task_trace(
                new_task_id,
                execution_source='published_task',
                published_task_id=pt.id,
                published_task_version=pt.version,
            )
            return {
                'success': True,
                'message': '日常任务创建成功，可前往任务列表执行',
                'data': {
                    'task_id': new_task_id,
                    'task_name': f"{pt.name} (v{pt.version})",
                    'published_task_id': pt.id,
                    'published_task_version': pt.version,
                },
                'code': 0,
            }
        except Exception as e:
            logger.exception('执行已发布任务失败')
            return {'success': False, 'message': str(e), 'data': None, 'code': 301}

    # ---------- 新版本 ----------

    @staticmethod
    def create_version(published_task_id: int, data: dict) -> dict:
        """创建新版本：不可变版本 vN → vN+1（旧版本 is_current=False）。"""
        try:
            pt = repo.get_by_id(published_task_id)
            if not pt:
                return {'success': False, 'message': '已发布任务不存在', 'data': None, 'code': 201}

            group_id = pt.task_group_id or pt.id
            current = repo.get_current_version(group_id) or pt

            source_task_id = data.get('source_task_id') or data.get('sourceTaskId')
            if source_task_id:
                task, err, code, _ = PublishedTaskService._get_publishable_task(source_task_id)
                if err:
                    return {'success': False, 'message': err, 'data': None, 'code': code}
                snapshot = PublishedTaskService._build_snapshot(task)
                new_source_task_id = task.id
            else:
                snapshot = dict(current.snapshot_config or {})
                new_source_task_id = current.source_task_id
            _, err, code, _ = PublishedTaskService._validate_snapshot(snapshot)
            if err:
                return {'success': False, 'message': err, 'data': None, 'code': code}

            new_version = repo.create_version(
                task_group_id=group_id,
                source_task_id=new_source_task_id,
                name=(data.get('name') or '').strip() or current.name,
                description=data.get('description')
                if data.get('description') is not None else current.description,
                task_type=current.type,
                version=current.version + 1,
                snapshot_config=snapshot,
                publish_reason=data.get('publish_reason') or data.get('publishReason'),
                demote_id=current.id,  # 同事务：旧版本 is_current=False
            )
            return {
                'success': True,
                'message': f'已发布任务 v{new_version.version} 创建成功',
                'data': {'id': new_version.id},
                'code': 201,
            }
        except Exception as e:
            logger.exception('创建已发布任务新版本失败')
            return {'success': False, 'message': str(e), 'data': None, 'code': 301}

    # ---------- 归档 ----------

    @staticmethod
    def archive(published_task_id: int) -> dict:
        """归档（幂等：已归档直接返回成功）。"""
        try:
            pt = repo.get_by_id(published_task_id)
            if not pt:
                return {'success': False, 'message': '已发布任务不存在', 'data': None, 'code': 201}
            if pt.status == 'archived':
                return {
                    'success': True, 'message': '任务已归档',
                    'data': {'id': pt.id, 'status': pt.status}, 'code': 0,
                }
            pt = repo.archive(published_task_id, archived_by=None)
            return {
                'success': True, 'message': '任务已归档',
                'data': {'id': pt.id, 'status': pt.status}, 'code': 0,
            }
        except Exception as e:
            logger.exception('归档已发布任务失败')
            return {'success': False, 'message': str(e), 'data': None, 'code': 301}

    # ---------- 重命名 ----------

    @staticmethod
    def update_name(published_task_id: int, data: dict) -> dict:
        """重命名（作用于整个版本链，task_group_id 锚点）。"""
        try:
            name = (data.get('name') or '').strip()
            if not name:
                return {'success': False, 'message': '任务名称不能为空', 'data': None, 'code': 101}
            pt = repo.get_by_id(published_task_id)
            if not pt:
                return {'success': False, 'message': '已发布任务不存在', 'data': None, 'code': 201}
            repo.update_name(published_task_id, name)
            return {
                'success': True, 'message': '任务名称已更新',
                'data': {'id': pt.id, 'name': name}, 'code': 0,
            }
        except Exception as e:
            logger.exception('重命名已发布任务失败')
            return {'success': False, 'message': str(e), 'data': None, 'code': 301}


# 模块级单例
published_task_service = PublishedTaskService()
