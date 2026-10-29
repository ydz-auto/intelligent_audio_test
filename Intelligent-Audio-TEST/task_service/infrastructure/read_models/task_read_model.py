# -*- coding: utf-8 -*-
"""TaskReadModel - 任务读模型。

CQRS 读侧：直接查询 DB，支持过滤、分页、聚合统计。
读模型不返回领域聚合根，返回扁平 DTO 字典。

按职责拆分为 Mixin 组合（对外 API 不变，导入路径保持本模块）：
- task_read_model_detail.TaskDetailReadModelMixin: 任务详情 DTO 组装 + 设备/API 列表查询
- task_read_model_progress_stats.TaskProgressStatsMixin: 进度/统计查询（含标签统计）
- task_read_model_case_results.TaskCaseResultsMixin: 用例列表/详情/结果查询
- 本文件保留任务查询主流程（单查/分页搜索）与扁平 DTO 序列化。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional  # noqa: F401

from shared.models.database import get_db_session
from task_service.infrastructure.persistence.models import Task, TaskCase
from shared.utils.query_utils import now_cst
from shared.utils.status_constants import (
    TaskStatus, ExecutionStatus, EvaluationStatus, TaskCaseStatus, ACTIVE_EXECUTION_STATUSES,
)
from shared.models.common_enums import TestType
from sqlalchemy import and_, or_, String  # String: search_tasks 中 Task.id.cast(String) 需要
from sqlalchemy.orm import selectinload
from shared.infrastructure.visibility_filter import VisibilityDenied, check_visible, visible_condition
from task_service.infrastructure.visibility_context import visibility_identity

from task_service.infrastructure.read_models.task_read_model_detail import TaskDetailReadModelMixin
from task_service.infrastructure.read_models.task_read_model_progress_stats import TaskProgressStatsMixin
from task_service.infrastructure.read_models.task_read_model_case_results import TaskCaseResultsMixin
from task_service.infrastructure.read_models.task_device_type_derivation import fetch_task_device_types

logger = logging.getLogger(__name__)


def _id_key(value: Any) -> str:
    """跨服务 ID 归一化键（关系表整数 ID 与 gRPC 返回 ID 的类型可能不一致）。"""
    return str(value)


def _dedup_ids(id_groups) -> List[Any]:
    """按归一化键去重并保留首次出现的原始 ID 值（保持传给下游 gRPC 的类型）。"""
    seen: Dict[str, Any] = {}
    for ids in id_groups:
        for i in ids:
            seen.setdefault(_id_key(i), i)
    return list(seen.values())


class TaskReadModel(
    TaskDetailReadModelMixin,
    TaskProgressStatsMixin,
    TaskCaseResultsMixin,
):
    """任务读模型。

    提供面向查询优化的读取方法，避免加载完整 ORM 关系。
    所有方法返回 dict/list，不返回 ORM 对象。

    职责拆分为三个 Mixin 组合：
    - TaskDetailReadModelMixin: 任务详情 DTO 组装
    - TaskProgressStatsMixin: 进度/统计查询
    - TaskCaseResultsMixin: 用例列表/结果查询
    """

    def find_by_id(self, task_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 查询单个任务（扁平 DTO）。

        INT-423：私有任务对非 owner 视为不存在（返回 None → 网关 404），
        不抛 VisibilityDenied 以免读路径 500。
        """
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return None
            uid, is_admin = visibility_identity()
            try:
                check_visible(task.created_by_user_id, task.visibility, uid, is_admin)
            except VisibilityDenied:
                return None
            return self._to_dto(task, session)
        finally:
            session.close()

    def get_task_labs(self, task_id: int) -> Optional[Dict[str, Any]]:
        """查询任务关联实验室（GET /api/tasks/{id}/labs，实验室扩展 INT-540）。

        返回 {task_id, labs: [{id, code, name}]}（多实验室 N:M，按 priority
        排序，即创建时 lab_ids 传入顺序）；已软删实验室不计入。任务不存在
        返回 None。
        """
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return None
            labs = self._fetch_labs_map(session, [task_id]).get(task_id, [])
            return {'task_id': task_id, 'labs': labs}
        finally:
            session.close()

    @staticmethod
    def _fetch_labs_map(session, task_ids) -> Dict[int, List[Dict[str, Any]]]:
        """批量获取任务关联实验室映射 {task_id: [{id, code, name}]}（实验室扩展 INT-540）。

        数据源 task_laboratory_relations（task_service 自有表，ORM 查询）join
        laboratories（共享库表，raw SQL 只读——同 INT-537/INT-538 的共享库
        join 先例，避免网关二次 RPC）。按 priority 升序 = 创建时 lab_ids
        传入顺序；已软删实验室不计入（与 laboratory_repository.get 软删过滤
        口径一致）。空 task_ids 返回 {}。

        表缺失（旧测试夹具未建 task_laboratory_relations / laboratories）时
        降级为空映射——失败语句已把 PostgreSQL 事务置为 aborted，必须先
        rollback 恢复，否则后续查询（报告/设备/API 批量）连锁抛
        InFailedSqlTransaction，整个列表接口 400（同 INT-339 挑选容器判定降级）。
        """
        if not task_ids:
            return {}
        from task_service.infrastructure.persistence.models import TaskLaboratoryRelation
        try:
            rel_rows = (
                session.query(TaskLaboratoryRelation)
                .filter(TaskLaboratoryRelation.task_id.in_(list(task_ids)))
                .order_by(TaskLaboratoryRelation.task_id, TaskLaboratoryRelation.priority)
                .all()
            )
            if not rel_rows:
                return {}
            lab_ids = sorted({r.lab_id for r in rel_rows if r.lab_id is not None})
            lab_map: Dict[int, Dict[str, Any]] = {}
            if lab_ids:
                from sqlalchemy import bindparam, text
                lab_rows = session.execute(
                    text(
                        'SELECT id, code, name FROM laboratories '
                        'WHERE id IN :lab_ids AND deleted = FALSE'
                    ).bindparams(bindparam('lab_ids', expanding=True)),
                    {'lab_ids': lab_ids},
                ).fetchall()
                for row in lab_rows:
                    lab_map[int(row[0])] = {'id': int(row[0]), 'code': row[1], 'name': row[2]}
            labs_map: Dict[int, List[Dict[str, Any]]] = {}
            for r in rel_rows:
                lab = lab_map.get(r.lab_id)
                if lab is None:
                    continue
                labs_map.setdefault(r.task_id, []).append(lab)
            return labs_map
        except Exception as e:
            try:
                session.rollback()
            except Exception:
                pass
            logger.debug("任务关联实验室批量查询降级（表可能未建）: %s", e)
            return {}

    def search(self,
               status: Optional[str] = None,
               algorithm_type: Optional[str] = None,
               created_by: Optional[int] = None,
               include_deleted: bool = False,
               page: int = 1,
               page_size: int = 20) -> Dict[str, Any]:
        """多条件过滤分页查询。"""
        session = get_db_session()
        try:
            q = session.query(Task)
            if not include_deleted:
                q = q.filter(Task.deleted == False)  # noqa: E712
            if status:
                q = q.filter(Task.status == status)
            if algorithm_type:
                q = q.filter(Task.algorithm_type == algorithm_type)
            if created_by is not None:
                q = q.filter(Task.created_by == created_by)

            total = q.count()
            offset = (page - 1) * page_size
            items = (q.order_by(Task.created_at.desc())
                     .offset(offset)
                     .limit(page_size)
                     .all())

            # INT-297：分页信封统一为 {items, page, pages, per_page, total}
            # （page_size 保留为兼容别名）
            return {
                'items': [self._to_dto(t, session) for t in items],
                'total': total,
                'page': page,
                'per_page': page_size,
                'pages': (total + page_size - 1) // page_size if page_size else 1,
                'page_size': page_size,
            }
        finally:
            session.close()

    def search_tasks(self, page: int = 1, per_page: int = 10,
                     status: Optional[str] = None,
                     device_type: Optional[str] = None,
                     algorithm_type: Optional[str] = None,
                     search: Optional[str] = None,
                     start_date: Optional[str] = None,
                     end_date: Optional[str] = None,
                     favorite: bool = False,
                     deleted: bool = False,
                     user_id: Optional[int] = None,
                     evaluation_status: Optional[str] = None,
                     merged: bool = False,
                     cherry_pick: bool = False,
                     execution_status: Optional[str] = None,
                     merge_type: Optional[str] = None,
                     stats: bool = False,
                     visibility: Optional[str] = None) -> Dict[str, Any]:
        """网关 get_all 使用的查询逻辑：含 Report 关联。

        device_type（可选）：按用例级被测设备类型过滤（任务下存在该类型用例）。
        favorite（可选，INT-141）：仅当前用户收藏（user_id 来自 x-user-id metadata）。
        deleted（可选，INT-141）：仅回收站软删除项（含删除人/删除时间）。
        evaluation_status（可选，INT-301）：按任务级评估状态过滤（与执行状态
            过滤并列；复用派生表达式，展示与筛选口径一致）。
        merged（可选，INT-298）：仅合并容器任务（存在 TaskMergeRelation 的任务；
            task.type 已废弃，合并容器以关系表存在性判定，对齐 V9.7.10 合并页签）。
        cherry_pick（可选，INT-339）：仅挑选合并容器任务（task_cherry_pick_relations
            存在性判定，§5.4 与 merged 容器判定同构）。
        execution_status（可选，INT-301 F1）：按任务级执行状态过滤（复用派生
            表达式，徽章展示与筛选命中同口径）。
        merge_type（可选，INT-577）：合并方式快捷筛选（whole|picked），网关已
            映射为 merged/cherry_pick 布尔，此处透传（供兼容/审计）。
        stats（可选，INT-577）：恒返回合并容器统计块（merged ∪ cherry_pick 并集，
            供「挑选合并」页签计数/facet）。合并容器计数独立于列表分页。
        visibility（可选，INT-466）：可见性筛选（shared/private；None=全部）。
        """
        from datetime import datetime
        from sqlalchemy import select as sa_select, or_
        from task_service.infrastructure.read_models.task_dual_status_expr import (
            EXECUTION_STATUS_EXPR, EVALUATION_STATUS_EXPR, evaluation_filter_condition,
            execution_filter_condition,
        )

        session = get_db_session()
        try:
            # INT-577：merged 与 cherry_pick 同时为 True 时取并集（OR），
            # 而非历史 AND（交集）——统一「挑选合并」页签双容器并集
            from task_service.infrastructure.persistence.models import TaskMergeRelation
            merge_exists = sa_select(TaskMergeRelation.id).where(
                TaskMergeRelation.merged_task_id == Task.id).correlate(Task).exists()
            from task_service.infrastructure.persistence.models import TaskCherryPickRelation
            cherry_exists = sa_select(TaskCherryPickRelation.id).where(
                TaskCherryPickRelation.cherry_pick_task_id == Task.id).correlate(Task).exists()
            if merge_type == 'whole':
                merged, cherry_pick = True, False
            elif merge_type == 'picked':
                merged, cherry_pick = False, True
            # INT-141：回收站模式查软删除项，正常模式查活跃项（互斥）
            query = session.query(Task, EXECUTION_STATUS_EXPR, EVALUATION_STATUS_EXPR).filter(
                Task.deleted == (True if deleted else False))  # noqa: E712
            # INT-423：行级可见性过滤（共享 + 自己创建的私有行；admin 全量）。
            # user_id 显式传参（收藏/回收站入口）优先，否则取用户上下文。
            _vis_uid, _vis_admin = visibility_identity(user_id)
            query = query.filter(visible_condition(
                Task.created_by_user_id, Task.visibility, _vis_uid, _vis_admin))
            # INT-466：可见性筛选（?visibility=shared|private；None 不追加）
            if visibility:
                query = query.filter(Task.visibility == visibility)
            if status:
                # INT-301 F1 兼容：历史入口的原始 Task.status 过滤保留原文匹配
                # （evaluating 等过渡态值仍按原始态命中，行为不变；执行域筛选
                # 已由 execution_status 参数以派生口径承载）
                query = query.filter(Task.status == status)
            if merged and cherry_pick:
                # INT-577：双容器并集（OR）
                query = query.filter(or_(merge_exists, cherry_exists))
            elif merged:
                # INT-298：合并容器任务（TaskMergeRelation.merged_task_id 命中即容器）
                query = query.filter(merge_exists)
            elif cherry_pick:
                # INT-339：挑选合并容器任务（task_cherry_pick_relations 存在性判定，
                # §5.4 与 merged 容器同构；不使用 task.type）
                query = query.filter(cherry_exists)
            if device_type:
                from task_service.infrastructure.persistence.models import TaskCase
                # SQLAlchemy 2.0：exists() 不再接受 Query，改用 select().exists()
                query = query.filter(sa_select(TaskCase.id)
                                     .where(TaskCase.task_id == Task.id,
                                            TaskCase.device_type == device_type)
                                     .correlate(Task)
                                     .exists())
            if favorite:
                from shared.models.common_enums import EntityType
                from task_service.infrastructure.persistence.models import Favorite
                if not user_id:
                    return {'items': [], 'total': 0, 'page': page,
                            'per_page': per_page, 'pages': 0}
                # per-user 收藏量小，两段查询（先取收藏 ID 再 IN 过滤）跨库兼容
                fav_rows = (session.query(Favorite.entity_id)
                            .filter(Favorite.user_id == user_id,
                                    Favorite.entity_type == EntityType.TASK.value)
                            .all())
                fav_task_ids = [int(r[0]) for r in fav_rows
                                if str(r[0]).isdigit()]
                query = query.filter(Task.id.in_(fav_task_ids))
            if algorithm_type:
                query = query.filter(Task.algorithm_type == algorithm_type)
            if search:
                query = query.filter(
                    or_(
                        Task.name.ilike(f'%{search}%'),
                        Task.id.cast(String).ilike(f'%{search}%')
                    )
                )
            if start_date:
                try:
                    dt_start = datetime.fromisoformat(start_date)
                    query = query.filter(Task.created_at >= dt_start)
                except ValueError:
                    logger.debug("start_date 非法 ISO 格式已忽略: %r", start_date)
            if end_date:
                try:
                    dt_end = datetime.fromisoformat(end_date)
                    query = query.filter(Task.created_at <= dt_end)
                except ValueError:
                    logger.debug("end_date 非法 ISO 格式已忽略: %r", end_date)
            if evaluation_status:
                # INT-301：评估状态过滤（复用派生 CASE 表达式，与徽章展示口径一致）
                query = query.filter(evaluation_filter_condition(evaluation_status))
            if execution_status:
                # INT-301 F1：执行状态过滤（复用派生 CASE 表达式，命中行执行徽章
                # == 筛选值；与原始 status 过滤并存）
                query = query.filter(execution_filter_condition(execution_status))

            query = query.order_by(Task.created_at.desc())
            # INT-1462：tags 一次 selectin 批量取回，消除列表逐任务懒加载 N+1
            query = query.options(selectinload(Task.tags))
            pagination = query.paginate(page=page, per_page=per_page, error_out=False)
            tasks = [row[0] for row in pagination.items]
            dual_status_map = {row[0].id: (row[1], row[2]) for row in pagination.items}

            items = []
            from task_service.infrastructure.persistence.models import TaskDevice, TaskAPI, TaskMergeRelation, TaskCase
            # 批量获取合并任务来源（按 TaskMergeRelation 存在性判定合并容器，
            # task.type 已废弃），避免 N+1
            page_task_ids = [task.id for task in tasks]
            # 实验室扩展（INT-540）：批量获取本页任务关联实验室（N:M，含已软删过滤）
            labs_map = self._fetch_labs_map(session, page_task_ids)
            source_tasks_map = {}
            merge_container_ids = set()
            merge_container_stats: Dict[int, Dict[str, int]] = {}
            if page_task_ids:
                relations = (session.query(TaskMergeRelation)
                             .filter(TaskMergeRelation.merged_task_id.in_(page_task_ids)).all())
                merged_task_ids = sorted({r.merged_task_id for r in relations})
                merge_container_ids = set(merged_task_ids)
                source_ids = sorted({r.source_task_id for r in relations})
                source_map = {t.id: t for t in session.query(Task).filter(Task.id.in_(source_ids)).all()} if source_ids else {}
                for mid in merged_task_ids:
                    briefs = []
                    rels = [r for r in relations if r.merged_task_id == mid]
                    for rel in rels:
                        st = source_map.get(rel.source_task_id)
                        if st:
                            briefs.append({
                                'id': st.id,
                                'name': st.name,
                                'status': st.status,
                                'total_cases': st.total_cases,
                                'completed_cases': st.completed_cases,
                                'failed_cases': st.failed_cases,
                                'created_at': st.created_at.isoformat() if st.created_at else None,
                            })
                    source_tasks_map[mid] = briefs
                    # INT-577：整任务合并容器来源计数（来源任务数 = 去重 source_task_id；
                    # 结果数 = source_result_count 求和——merge_tasks 落库口径）
                    merge_container_stats[mid] = {
                        'source_task_count': len({r.source_task_id for r in rels}),
                        'source_result_count': sum(int(r.source_result_count or 0) for r in rels),
                    }
            # INT-339：挑选合并容器判定（本页批量，避免 N+1；沿用外层 session，
            # with_session 包装的仓储方法会 close 共享 scoped session，不得在
            # 查询中途调用）。表缺失（旧测试夹具未建表）时降级为空集合，
            # 仅影响 is_cherry_pick 输出，不影响主结果集。
            from task_service.infrastructure.persistence.models import TaskCherryPickRelation
            cherry_pick_container_ids = set()
            cherry_pick_container_stats: Dict[int, Dict[str, int]] = {}
            if page_task_ids:
                try:
                    cp_rows = (session.query(TaskCherryPickRelation)
                               .filter(TaskCherryPickRelation.cherry_pick_task_id.in_(page_task_ids)).all())
                    cherry_pick_container_ids = {r.cherry_pick_task_id for r in cp_rows}
                    for cid in cherry_pick_container_ids:
                        rels = [r for r in cp_rows if r.cherry_pick_task_id == cid]
                        cherry_pick_container_stats[cid] = {
                            'source_task_count': len({r.source_task_id for r in rels}),
                            'source_result_count': len(rels),
                        }
                    # INT-774 ⑤：cherry-pick 容器来源任务 briefs（与 merge 容器同构）——
                    # 按 cherry_pick_task_id 分组取去重源任务（relation 行 source_task_id
                    # 指真实源任务，briefs 从 Task 表当前行构建，已删源任务跳过）
                    cp_source_ids = sorted({r.source_task_id for r in cp_rows})
                    cp_source_map = {t.id: t for t in session.query(Task).filter(
                        Task.id.in_(cp_source_ids)).all()} if cp_source_ids else {}
                    for cid in cherry_pick_container_ids:
                        seen_ids: set = set()
                        briefs: List[Dict[str, Any]] = []
                        for rel in [r for r in cp_rows if r.cherry_pick_task_id == cid]:
                            if rel.source_task_id in seen_ids:
                                continue
                            seen_ids.add(rel.source_task_id)
                            st = cp_source_map.get(rel.source_task_id)
                            if st:
                                briefs.append({
                                    'id': st.id,
                                    'name': st.name,
                                    'status': st.status,
                                    'total_cases': st.total_cases,
                                    'completed_cases': st.completed_cases,
                                    'failed_cases': st.failed_cases,
                                    'created_at': st.created_at.isoformat() if st.created_at else None,
                                })
                        # 与 merge 容器同构：填 source_tasks_map（merge 已填的保留）
                        source_tasks_map.setdefault(cid, briefs)
                except Exception as cp_err:
                    logger.debug("挑选合并容器批量判定降级（表可能未建）: %s", cp_err)
            # 批量取页面任务的用例级被测设备类型集合（差异#2 收尾：取代 task.type 输出）。
            # INT-1233：无用例级 device_type 行（含无 task_case_relations 的历史任务）
            # 按任务级设备/API 关系回退派生（与 read model device_types 输出同口径）。
            device_types_map = fetch_task_device_types(session, page_task_ids) if page_task_ids else {}
            # INT-141：当前用户对本页任务的收藏集合（is_favorite 标记）
            favorite_ids = set()
            if user_id and page_task_ids:
                from shared.models.common_enums import EntityType
                from task_service.infrastructure.persistence.models import Favorite
                fav_rows = (session.query(Favorite.entity_id)
                            .filter(Favorite.user_id == user_id,
                                    Favorite.entity_type == EntityType.TASK.value,
                                    Favorite.entity_id.in_([str(i) for i in page_task_ids]))
                            .all())
                favorite_ids = {r[0] for r in fav_rows}
            # INT-1462：报告 / 设备 / API 改为页级批量组装，消除列表 N+1 串行跨服务
            # 调用——报告一次 RPC 取整页；设备/API 各一次 IN 查询 + 各一次批量 gRPC。
            # 回收站模式不输出这些字段，跳过批量取数以省开销。
            reports_by_task: Dict[int, List[Dict[str, Any]]] = {}
            devices_by_task: Dict[int, List[Dict[str, Any]]] = {}
            apis_by_task: Dict[int, List[Dict[str, Any]]] = {}
            if page_task_ids and not deleted:
                reports_by_task = self._fetch_reports_batch(page_task_ids)
                devices_by_task, apis_by_task = self._fetch_relation_briefs_batch(
                    session, page_task_ids)
            for task in tasks:
                # INT-301：SQL 派生的执行/评估双状态（评估推进只落评估侧）
                task_execution_status, task_evaluation_status = dual_status_map.get(
                    task.id, (task.status, None))
                # 回收站模式：仅返回轻量字段（删除人/删除时间），不查报告/设备/API
                if deleted:
                    items.append({
                        'id': task.id,
                        'name': task.name,
                        'description': task.description,
                        'status': task.status,
                        'execution_status': task_execution_status,
                        'evaluation_status': task_evaluation_status,
                        'algorithm_type': task.algorithm_type,
                        'total_cases': task.total_cases,
                        'deleted': True,
                        'deleted_at': task.deleted_at.isoformat() if task.deleted_at else None,
                        'deleted_by_user_id': task.deleted_by_user_id,
                        # INT-423/466：资源可见性与归属人（网关路由层 owner 校验 / 前端徽标）
                        'visibility': task.visibility,
                        'created_by_user_id': task.created_by_user_id,
                        'created_at': task.created_at.isoformat() if task.created_at else None,
                    })
                    continue
                # INT-1462：本页批量取回的报告摘要（组装阶段零跨服务往返）
                reports = reports_by_task.get(task.id, [])
                report_info = {
                    'count': len(reports),
                    'reports': [
                        {
                            'id': r.get('id'),
                            'name': r.get('name'),
                            'status': r.get('status'),
                            'type': r.get('type'),
                            'created_at': r.get('created_at'),
                        }
                        for r in reports
                    ],
                }
                # P3 改造：task.devices / task.apis 关系已移除，
                # 通过 TaskDevice/TaskAPI 关联表 + gRPC 查询设备/API 信息
                # INT-1462：关系与设备/API 摘要均已按本页批量取回
                devices = devices_by_task.get(task.id, [])
                apis = apis_by_task.get(task.id, [])
                items.append({
                    'id': task.id,
                    'name': task.name,
                    'description': task.description,
                    'status': task.status,
                    'execution_status': task_execution_status,
                    'evaluation_status': task_evaluation_status,
                    'device_types': device_types_map.get(task.id, []),
                    'config': task.config or {},
                    'algorithm_type': task.algorithm_type,
                    'algorithm_params': task.algorithm_params,
                    'started_at': task.started_at.isoformat() if task.started_at else None,
                    'completed_at': task.completed_at.isoformat() if task.completed_at else None,
                    'total_cases': task.total_cases,
                    'case_count': task.total_cases,
                    'device_count': len(devices),
                    'completed_cases': task.completed_cases,
                    'failed_cases': task.failed_cases,
                    'tags': [tag.name for tag in task.tags],
                    'created_at': task.created_at.isoformat() if task.created_at else None,
                    'updated_at': task.updated_at.isoformat() if task.updated_at else None,
                    'is_favorite': str(task.id) in favorite_ids,
                    'is_cherry_pick': task.id in cherry_pick_container_ids,
                    # INT-423/466：资源可见性与归属人（网关路由层 owner 校验 / 前端徽标）
                    'visibility': task.visibility,
                    'created_by_user_id': task.created_by_user_id,
                    # INT-577：合并方式（whole=整任务合并 / picked=结果挑选）+ 来源任务·结果计数
                    # （供列表次行「来源 {n} 任务 · 结果 {m} 条」与统计徽章）
                    'merge_type': (
                        'picked' if task.id in cherry_pick_container_ids
                        else 'whole' if task.id in merge_container_ids
                        else None
                    ),
                    'source_task_count': (
                        cherry_pick_container_stats.get(task.id, {}).get('source_task_count')
                        if task.id in cherry_pick_container_ids
                        else merge_container_stats.get(task.id, {}).get('source_task_count')
                    ),
                    'source_result_count': (
                        cherry_pick_container_stats.get(task.id, {}).get('source_result_count')
                        if task.id in cherry_pick_container_ids
                        else merge_container_stats.get(task.id, {}).get('source_result_count')
                    ),
                    'reports': report_info,
                    'devices': devices,
                    'apis': apis,
                    'source_tasks': source_tasks_map.get(task.id, []),
                    # 实验室扩展（INT-540）：任务关联实验室 [{id, code, name}]（多实验室 N:M）
                    'labs': labs_map.get(task.id, []),
                })

            # INT-577：合并容器统计（merged ∪ cherry_pick 并集，供「挑选合并」页签
            # 计数/facet；独立于列表分页，仅统计未删除容器任务）。表缺失降级 None。
            container_stats: Optional[Dict[str, int]] = None
            try:
                from sqlalchemy import func as sa_func, union as sa_union
                _deleted_flag = (True if deleted else False)
                whole_q = (session.query(TaskMergeRelation.merged_task_id)
                           .join(Task, Task.id == TaskMergeRelation.merged_task_id)
                           .filter(Task.deleted == _deleted_flag)  # noqa: E712
                           .distinct())
                picked_q = (session.query(TaskCherryPickRelation.cherry_pick_task_id)
                            .join(Task, Task.id == TaskCherryPickRelation.cherry_pick_task_id)
                            .filter(Task.deleted == _deleted_flag)  # noqa: E712
                            .distinct())
                whole_count = int(whole_q.count() or 0)
                picked_count = int(picked_q.count() or 0)
                union_sub = sa_union(whole_q, picked_q).subquery()
                union_count = int(session.query(sa_func.count()).select_from(union_sub).scalar() or 0)
                container_stats = {
                    'total': union_count,
                    'whole': whole_count,
                    'picked': picked_count,
                }
            except Exception as cp_err:
                # 表缺失（旧测试夹具未建表）时降级 None；失败语句已把事务置为
                # aborted，必须 rollback 恢复，否则 return 后会话清理连锁抛错。
                session.rollback()
                logger.debug("合并容器统计降级（表可能未建）: %s", cp_err)

            return {
                'items': items,
                'total': pagination.total,
                'page': pagination.page,
                'per_page': pagination.per_page,
                'pages': pagination.pages,
                'stats': container_stats,
            }
        finally:
            session.close()

    # ---- 内部序列化 ----

    @staticmethod
    def _fetch_reports_batch(task_ids) -> Dict[int, List[Dict[str, Any]]]:
        """页级批量取整页任务的报告摘要（INT-1462，一次 gRPC）。

        Returns:
            {task_id: [{id,name,status,type,created_at}, ...]}；失败降级为空 dict
            （列表仍可渲染，仅报告徽标缺省）。
        """
        from task_service.infrastructure.acl.report_acl_repository import (
            report_acl_repository,
        )
        try:
            return report_acl_repository.list_reports_by_task_ids(task_ids)
        except Exception:
            logger.debug("批量查询报告摘要失败", exc_info=True)
            return {}

    def _fetch_relation_briefs_batch(self, session, task_ids) -> tuple:
        """页级批量取任务→设备/API 关系并回填设备/API 摘要（INT-1462）。

        TaskDevice / TaskAPI 各一次 IN 查询，设备状态与 API 配置各一次批量
        gRPC 调用，取代原先逐任务 2 次 DB 查询 + 逐任务 gRPC 的 N+1。

        Returns:
            (devices_by_task, apis_by_task)，形如
            {task_id: [{id,name,status,model}, ...]} / {task_id: [{id,name,status}, ...]}
        """
        from task_service.infrastructure.persistence.models import TaskDevice, TaskAPI

        device_ids_by_task: Dict[int, List[Any]] = {}
        api_ids_by_task: Dict[int, List[Any]] = {}
        device_rows = (session.query(TaskDevice.task_id, TaskDevice.device_id)
                       .filter(TaskDevice.task_id.in_(task_ids))
                       .order_by(TaskDevice.task_id, TaskDevice.id).all())
        for task_id, device_id in device_rows:
            device_ids_by_task.setdefault(task_id, []).append(device_id)
        api_rows = (session.query(TaskAPI.task_id, TaskAPI.api_id)
                    .filter(TaskAPI.task_id.in_(task_ids))
                    .order_by(TaskAPI.task_id, TaskAPI.id).all())
        for task_id, api_id in api_rows:
            api_ids_by_task.setdefault(task_id, []).append(api_id)

        all_device_ids = _dedup_ids(device_ids_by_task.values())
        all_api_ids = _dedup_ids(api_ids_by_task.values())
        device_briefs = {_id_key(d.get('id')): d
                         for d in self._fetch_device_list(all_device_ids)} if all_device_ids else {}
        api_briefs = {_id_key(a.get('id')): a
                      for a in self._fetch_api_list(all_api_ids)} if all_api_ids else {}

        def _group(ids_by_task, briefs):
            grouped: Dict[int, List[Dict[str, Any]]] = {}
            for task_id, ids in ids_by_task.items():
                rows = [briefs[_id_key(i)] for i in ids if _id_key(i) in briefs]
                if rows:
                    grouped[task_id] = rows
            return grouped

        return _group(device_ids_by_task, device_briefs), _group(api_ids_by_task, api_briefs)

    @staticmethod
    def _to_dto(task: Task, session=None) -> Dict[str, Any]:
        total = task.total_cases or 0
        completed = task.completed_cases or 0
        failed = task.failed_cases or 0
        processed = completed + failed
        percent = round(processed / total * 100, 2) if total > 0 else 0.0
        # 用例级被测设备类型集合（差异#2 收尾：取代 task.type 输出）
        # INT-1233：无用例级 device_type 行（含无 task_case_relations 的历史任务）
        # 按任务级设备/API 关系回退派生（与 search_tasks / stats 同口径）。
        device_types = fetch_task_device_types(session, [task.id]).get(task.id, []) if session is not None else []
        return {
            'task_id': task.id,
            'name': task.name,
            'description': task.description,
            'device_types': device_types,
            'status': task.status,
            'config': task.config,
            'algorithm_type': task.algorithm_type,
            'algorithm_params': task.algorithm_params,
            'total_cases': total,
            'completed_cases': completed,
            'failed_cases': failed,
            'processed_cases': processed,
            'progress_percent': percent,
            'created_by': task.created_by,
            # INT-423/466：资源可见性与归属人
            'visibility': task.visibility,
            'created_by_user_id': task.created_by_user_id,
            'created_at': task.created_at.isoformat() if task.created_at else None,
            'updated_at': task.updated_at.isoformat() if task.updated_at else None,
            'started_at': task.started_at.isoformat() if task.started_at else None,
            'completed_at': task.completed_at.isoformat() if task.completed_at else None,
            'estimated_time': task.estimated_time,
            'actual_duration': task.actual_duration,
            'deleted': task.deleted or False,
            'reevaluated_at': task.reevaluated_at.isoformat() if task.reevaluated_at else None,
            'reevaluation_count': task.reevaluation_count or 0,
        }


# 模块级单例
task_read_model = TaskReadModel()
