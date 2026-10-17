# -*- coding: utf-8 -*-
"""CherryPickService — 挑选合并应用服务（INT-339，task_service 域）。

职责（设计文档 §3/§4/§8，前向可行性评审裁定 1-5）：
- S1 购物车/挑选集：加购（溯源快照仓储提取，防伪造）、移除、清空、
  另存挑选集、恢复进购物车（per-user，Favorite 模式）
- S2 跨任务挑选查询：多条件 AND 组合筛选（来源任务/设备/用例/标签/
  执行·评估状态/时间范围，设备+用例为负责人点名必支持项）
- S3 下单 merge：cherry-pick 容器任务（创建即 completed）+ 专有关系表
  引用源结果（方案 A，禁止搬家语义）+ 合并预览 + 下单校验
- S4 下单 reexecute：按所选结果的用例×设备集合创建重执行任务并启动
- S5 下单 reevaluate：逐源任务发起（多次 Reevaluate(mode=selected)，
  零评估域改动，裁定 4）

约定：所有方法返回 dict: {success, message, data, code?}；
通过 cherry_pick_repository / task_repository 访问 DB，不直接持有 session。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

from shared.models.common_enums import (
    CherryPickCheckoutAction, DeviceType, PickableTaskStatus,
)
from shared.utils.status_constants import (
    ExecutionStatus, EvaluationStatus, TaskCaseStatus, TaskStatus,
    FINISHED_TASK_STATUSES,
)

from task_service.infrastructure.persistence.cherry_pick_repository import cherry_pick_repository
from task_service.infrastructure.persistence.task_repository import task_repository

logger = logging.getLogger(__name__)

_UTC_PLUS_8 = timezone(timedelta(hours=8))


class CherryPickService:
    """挑选合并应用服务（S1-S5 命令与查询）。"""

    def __init__(self):
        self._repo = cherry_pick_repository

    # ==================== 用户上下文 ====================

    @staticmethod
    def _current_user_id() -> Optional[int]:
        from shared.infrastructure.user_context import get_current_user_id
        return get_current_user_id()

    def _require_user(self) -> tuple:
        """写侧 per-user 操作入口的用户校验（未认证拒绝，红线：0/None 不充当真实用户）。

        INT-660：读侧方法（cart_get/sets_list/set_detail/preview）不调本方法，
        直接取 _current_user_id() 且 None 容忍（AUTH_MODE=off 空态，对齐收藏）。
        """
        user_id = self._current_user_id()
        if not user_id:
            return None, ({'success': False, 'message': '未认证用户，禁止使用挑选购物车',
                           'data': {'code': 401}, 'code': 401})
        return user_id, None

    # ==================== S1 购物车 ====================

    def cart_add(self, data: dict) -> dict:
        """加入购物车（来源结果勾选集；溯源快照由仓储从源行提取）。"""
        try:
            user_id, err = self._require_user()
            if err:
                return err
            result_ids = [int(r) for r in (data.get('result_ids') or [])]
            if not result_ids:
                return {'success': False, 'message': 'result_ids 不能为空',
                        'data': {'code': 400}, 'code': 400}
            outcome = self._repo.cart_add(user_id, [{'result_id': r} for r in result_ids])
            missing = outcome.get('missing') or []
            if missing and not outcome.get('added'):
                return {'success': False, 'message': f'所选执行结果不存在或源任务已删除: {missing[:5]}',
                        'data': {'code': 404}, 'code': 404}
            message = f'已加入购物车 {len(outcome.get("added") or [])} 条'
            if outcome.get('duplicated'):
                message += f'（重复 {len(outcome["duplicated"])} 条已跳过）'
            if missing:
                message += f'（失效 {len(missing)} 条未加入）'
            return {'success': True, 'message': message, 'data': outcome}
        except ValueError as e:
            return {'success': False, 'message': str(e), 'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"购物车加购失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def cart_remove(self, item_ids: List[int]) -> dict:
        """从购物车移除条目。"""
        try:
            user_id, err = self._require_user()
            if err:
                return err
            outcome = self._repo.cart_remove(user_id, item_ids or [])
            return {'success': True, 'message': f'已移除 {outcome.get("removed", 0)} 条', 'data': outcome}
        except ValueError as e:
            return {'success': False, 'message': str(e), 'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"购物车移除失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def cart_clear(self) -> dict:
        """清空购物车。"""
        try:
            user_id, err = self._require_user()
            if err:
                return err
            outcome = self._repo.cart_clear(user_id)
            return {'success': True, 'message': f'已清空 {outcome.get("removed", 0)} 条', 'data': outcome}
        except ValueError as e:
            return {'success': False, 'message': str(e), 'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"购物车清空失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def cart_get(self) -> dict:
        """当前用户购物车内容（按来源任务分组 + 失效标注，设计文档 §3/§10）。

        INT-660：读侧 None 用户（AUTH_MODE=off）不再 401，走仓储
        cart_list(None)→[] 空态（对齐收藏「未收藏语义」）。
        """
        try:
            user_id = self._current_user_id()
            items = self._repo.cart_list(user_id)
            # INT-577 §11-5：购物车树形分组到 result_type 级需补齐来源用例/设备名
            # （候选行 §11-2 同源；缺名容错显示 ID，可用性优先于严格契约）
            case_ids = {str(it.get('source_case_id')) for it in items if it.get('source_case_id')}
            device_ids = {int(it['source_device_id']) for it in items if it.get('source_device_id') is not None}
            case_names = self._case_name_map(case_ids) if case_ids else {}
            device_names = self._fetch_device_names(list(device_ids)) if device_ids else {}
            grouped: Dict[int, List[Dict[str, Any]]] = {}
            invalid_item_ids: List[int] = []
            result_ids = [it['result_id'] for it in items]
            existing_results = self._results_exist(result_ids)
            for it in items:
                it['invalid'] = it['result_id'] not in existing_results
                if it['invalid']:
                    invalid_item_ids.append(it['item_id'])
                if it.get('source_case_id'):
                    it['source_case_name'] = case_names.get(it['source_case_id'])
                if it.get('source_device_id') is not None:
                    it['source_device_name'] = device_names.get(it['source_device_id'])
                grouped.setdefault(it['source_task_id'], []).append(it)
            groups = [{
                'source_task_id': task_id,
                'source_task_name': (rows[0].get('source_task_name') if rows else None) or f'任务 {task_id}',
                'items': rows,
            } for task_id, rows in grouped.items()]
            return {'success': True, 'message': 'ok', 'data': {
                'groups': groups,
                'total': len(items),
                'invalid_item_ids': invalid_item_ids,
            }}
        except ValueError as e:
            return {'success': False, 'message': str(e), 'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"购物车查询失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def _results_exist(self, result_ids: List[int]) -> set:
        """批量校验结果行仍存在（购物车失效标注，§10）。"""
        if not result_ids:
            return set()
        from task_service.infrastructure.persistence.models import TestResult
        from shared.models.database import get_db_session
        session = get_db_session()
        try:
            rows = session.query(TestResult.id).filter(
                TestResult.id.in_([int(r) for r in result_ids])).all()
            return {r[0] for r in rows}
        finally:
            session.close()

    def cart_save_as_set(self, data: dict) -> dict:
        """购物车另存为挑选集。"""
        try:
            user_id, err = self._require_user()
            if err:
                return err
            items = self._repo.cart_list(user_id)
            if not items:
                return {'success': False, 'message': '购物车为空，无法另存',
                        'data': {'code': 400}, 'code': 400}
            outcome = self._repo.set_save(
                user_id, data.get('name') or '', data.get('description'),
                [{'result_id': it['result_id']} for it in items])
            return {'success': True, 'message': f'挑选集「{outcome["name"]}」已保存'
                    f'（{outcome["item_count"]} 条）', 'data': outcome, 'code': 201}
        except ValueError as e:
            return {'success': False, 'message': str(e), 'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"挑选集另存失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def sets_list(self) -> dict:
        """挑选集列表（当前用户）。

        INT-660：读侧 None 用户（AUTH_MODE=off）不再 401，走仓储
        set_list(None)→[] 空态。
        """
        try:
            user_id = self._current_user_id()
            sets = self._repo.set_list(user_id)
            return {'success': True, 'message': 'ok', 'data': {'items': sets}}
        except ValueError as e:
            return {'success': False, 'message': str(e), 'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"挑选集列表查询失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def set_detail(self, set_id: int) -> dict:
        """挑选集详情。

        INT-660：读侧 None 用户（AUTH_MODE=off）不再 401，走仓储
        set_detail(None,id)→None → 404 未找到挑选集。
        """
        try:
            user_id = self._current_user_id()
            detail = self._repo.set_detail(user_id, set_id)
            if detail is None:
                return {'success': False, 'message': '未找到挑选集',
                        'data': {'code': 404}, 'code': 404}
            return {'success': True, 'message': 'ok', 'data': detail}
        except ValueError as e:
            return {'success': False, 'message': str(e), 'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"挑选集详情查询失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def set_delete(self, set_id: int) -> dict:
        """删除挑选集。"""
        try:
            user_id, err = self._require_user()
            if err:
                return err
            outcome = self._repo.set_delete(user_id, set_id)
            if not outcome.get('deleted'):
                return {'success': False, 'message': '未找到挑选集',
                        'data': {'code': 404}, 'code': 404}
            return {'success': True, 'message': '挑选集已删除', 'data': outcome}
        except ValueError as e:
            return {'success': False, 'message': str(e), 'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"挑选集删除失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def set_to_cart(self, set_id: int) -> dict:
        """挑选集恢复进购物车（另存/恢复两向，设计文档 §3）。"""
        try:
            user_id, err = self._require_user()
            if err:
                return err
            detail = self._repo.set_detail(user_id, set_id)
            if detail is None:
                return {'success': False, 'message': '未找到挑选集',
                        'data': {'code': 404}, 'code': 404}
            outcome = self._repo.cart_add(
                user_id, [{'result_id': it['result_id']} for it in detail['items']])
            return {'success': True,
                    'message': f'已恢复 {len(outcome.get("added") or [])} 条进购物车',
                    'data': outcome}
        except ValueError as e:
            return {'success': False, 'message': str(e), 'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"挑选集恢复失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    # ==================== S2 跨任务挑选查询 ====================

    def list_candidates(self, data: dict) -> dict:
        """跨任务结果挑选查询（多条件 AND，设计文档 §4；设备+用例为点名必支持项）。

        条件（全部可选，组合 AND）：
        - task_ids: 来源任务（多选，仅终态任务可挑选 §10）
        - device_ids: 设备（TestResult.device_id，点名维度）
        - case_ids: 用例（点名维度）
        - execution_status / evaluation_status: 结果执行/评估状态
        - start_date / end_date: 结果执行时间范围（TestResult.created_at）
        - excluded=True 时返回被删用例排除行（缺省剔除，对齐 INT-305 口径）
        """
        try:
            task_ids = [int(t) for t in (data.get('task_ids') or [])]
            device_ids = [int(d) for d in (data.get('device_ids') or [])]
            case_ids = [str(c) for c in (data.get('case_ids') or [])]
            execution_status = data.get('execution_status') or None
            evaluation_status = data.get('evaluation_status') or None
            start_date = data.get('start_date') or None
            end_date = data.get('end_date') or None
            page = max(1, int(data.get('page') or 1))
            per_page = min(200, max(1, int(data.get('per_page') or 50)))

            rows, total = self._query_candidate_results(
                task_ids=task_ids, device_ids=device_ids, case_ids=case_ids,
                execution_status=execution_status,
                evaluation_status=evaluation_status,
                start_date=start_date, end_date=end_date,
                page=page, per_page=per_page,
            )
            return {'success': True, 'message': 'ok', 'data': {
                'items': rows, 'total': total, 'page': page, 'per_page': per_page,
            }}
        except (ValueError, TypeError) as e:
            return {'success': False, 'message': f'查询参数非法: {e}',
                    'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"挑选候选结果查询失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def _query_candidate_results(self, task_ids, device_ids, case_ids,
                                 execution_status, evaluation_status,
                                 start_date, end_date, page, per_page) -> tuple:
        """挑选候选结果查询核心（只读，CQRS 查询侧无副作用）。

        - 默认仅终态任务（§10 显式终态集合 completed/failed/stopped）
        - 默认剔除 excluded=1 行（被删用例排除，INT-305 聚合口径）
        - 评估状态取自 evaluation_service（TestResultDimension 存在性），
          经 gRPC 批量查询（P1.7 先例），跨服务不直连
        - INT-657：task_ids 命中容器任务时经 task_cherry_pick_relations
          解析其引用的源结果参与候选命中（容器自身无 test_results 行，
          引用方案 A §5.1），命中项标注为容器任务（与源任务口径一致）
        """
        from task_service.infrastructure.persistence.models import Task, TestResult
        from shared.models.database import get_db_session
        from sqlalchemy import func as sa_func, or_

        direct_task_ids = list(task_ids)
        container_result_map = {}
        if task_ids:
            direct_task_ids, container_result_map = self._resolve_container_task_ids(task_ids)
            if not direct_task_ids and not container_result_map:
                # 所选来源任务全部为不可再挑容器任务（§10）：无候选命中（INT-657）
                return [], 0

        session = get_db_session()
        try:
            q = session.query(TestResult, Task).join(
                Task, TestResult.task_id == Task.id)
            # §10：仅终态任务可挑选（显式集合，拒绝魔法字符串）
            q = q.filter(Task.status.in_([s.value for s in PickableTaskStatus]),
                         Task.deleted == False)  # noqa: E712
            if task_ids:
                # INT-657：容器任务经引用关系解析命中（源任务直查 ∪ 容器引用结果）
                conds = []
                if direct_task_ids:
                    conds.append(TestResult.task_id.in_(direct_task_ids))
                if container_result_map:
                    conds.append(TestResult.id.in_(list(container_result_map.keys())))
                q = q.filter(conds[0] if len(conds) == 1 else or_(*conds))
            if device_ids:
                q = q.filter(TestResult.device_id.in_(device_ids))
            if case_ids:
                q = q.filter(TestResult.test_case_id.in_(case_ids))
            if execution_status:
                q = q.filter(TestResult.execution_status == execution_status)
            if evaluation_status:
                # 评估状态过滤（已评估/未评估）：评估维度行归属 evaluation_service，
                # 经 gRPC 批量解析命中范围内的已评估结果 ID 集（限定范围控制批量化成本；
                # 未指定 task_ids 时以全部可挑选终态任务为范围）
                result_ids_in_scope = []
                if task_ids:
                    # INT-657：容器命中范围含引用结果（源任务直查结果 ∪ 容器引用结果）
                    if direct_task_ids:
                        result_ids_in_scope += [r[0] for r in session.query(TestResult.id).filter(
                            TestResult.task_id.in_(direct_task_ids),
                            TestResult.excluded == 0).all()]
                    if container_result_map:
                        result_ids_in_scope += [r[0] for r in session.query(TestResult.id).filter(
                            TestResult.id.in_(list(container_result_map.keys())),
                            TestResult.excluded == 0).all()]
                else:
                    scope_ids = [t.id for t in session.query(Task.id).filter(
                        Task.status.in_([s.value for s in PickableTaskStatus]),
                        Task.deleted == False).all()]  # noqa: E712
                    result_ids_in_scope = [r[0] for r in session.query(TestResult.id).filter(
                        TestResult.task_id.in_(scope_ids),
                        TestResult.excluded == 0).all()] if scope_ids else []
                evaluated = self._evaluated_result_ids(result_ids_in_scope)
                if evaluation_status == EvaluationStatus.PENDING:
                    # 未评估：不在已评估集合（含维度行缺失场景）
                    q = q.filter(~TestResult.id.in_(evaluated))
                else:
                    q = q.filter(TestResult.id.in_(evaluated))
            # INT-305：默认剔除被删用例的排除行
            q = q.filter(TestResult.excluded == 0)
            if start_date:
                try:
                    q = q.filter(TestResult.created_at >= datetime.fromisoformat(start_date))
                except ValueError:
                    pass
            if end_date:
                try:
                    q = q.filter(TestResult.created_at <= datetime.fromisoformat(end_date))
                except ValueError:
                    pass

            total = q.with_entities(sa_func.count(sa_func.distinct(TestResult.id))).scalar() or 0
            rows = (q.order_by(TestResult.task_id.desc(), TestResult.id)
                    .offset((page - 1) * per_page).limit(per_page).all())

            # 批量取评估状态标注（结果级已评估/未评估，gRPC 范围批量化）
            row_result_ids = [r.id for r, _t in rows]
            evaluated_map = self._evaluated_result_ids(row_result_ids) if row_result_ids else {}

            # INT-657：容器引用命中的结果标注为容器任务（与源任务口径一致）；
            # 同结果同时被源任务直查命中的保留源任务标注（直查优先，不混淆归属）
            direct_task_ids_set = set(direct_task_ids)
            items = []
            for result, task in rows:
                label = container_result_map.get(result.id) if container_result_map else None
                use_container = label is not None and (
                    not direct_task_ids_set or result.task_id not in direct_task_ids_set)
                items.append({
                    'result_id': result.id,
                    'task_id': label['task_id'] if use_container else task.id,
                    'task_name': label['task_name'] if use_container else task.name,
                    'task_status': label['task_status'] if use_container else task.status,
                    'case_id': result.test_case_id,
                    'device_id': result.device_id,
                    'api_id': result.api_id,
                    'algorithm_type': result.algorithm_type,
                    'execution_status': result.execution_status,
                    'evaluated': result.id in evaluated_map,
                    'created_at': result.created_at.isoformat() if result.created_at else None,
                })
            return items, int(total)
        finally:
            session.close()

    def _resolve_container_task_ids(self, task_ids: List[int]) -> tuple:
        """候选查询容器命中解析（INT-657）。

        容器任务自身无 test_results 行（引用方案 A，§5.1），须经
        task_cherry_pick_relations 把容器任务解析为其引用的源结果 ID，
        使容器任务在「来源任务」候选下拉中可命中再挑（与源任务口径一致）。

        返回 (direct_task_ids, container_result_map)：
        - direct_task_ids：非容器任务（原 TestResult.task_id 直查）+ 不可
          再挑选的容器任务（merged/已删除容器 §10 口径，退回直查恒无命中）
        - container_result_map：{result_id: 容器任务标注 dict}（容器命中时
          task_id/task_name/task_status 标注为容器任务）
        """
        ids = [int(t) for t in (task_ids or [])]
        if not ids:
            return [], {}
        container_ids = self._repo.container_ids_in(ids)
        direct_ids = [t for t in ids if t not in set(container_ids)]
        result_map: Dict[int, Dict[str, Any]] = {}
        if container_ids:
            # §10：容器任务自身也须为可挑选终态（merged/已删除容器不可再挑选，
            # 退回 direct 直查——容器自身无结果行，不命中）
            from task_service.infrastructure.persistence.models import Task
            from shared.models.database import get_db_session
            session = get_db_session()
            try:
                pickable = {t[0] for t in session.query(Task.id).filter(
                    Task.id.in_(container_ids),
                    Task.status.in_([s.value for s in PickableTaskStatus]),
                    Task.deleted == False).all()}  # noqa: E712
            finally:
                session.close()
            direct_ids += [t for t in container_ids if t not in pickable]
            if pickable:
                for rel in self._repo.relations_by_containers(sorted(pickable)):
                    result_map.setdefault(rel['result_id'], {
                        'task_id': rel['cherry_pick_task_id'],
                        'task_name': rel['container_task_name'],
                        'task_status': rel['container_task_status'],
                    })
        return direct_ids, result_map

    def _evaluated_result_ids(self, result_ids: Optional[List[int]]) -> set:
        """经 evaluation_service gRPC 批量查询已评估结果 ID 集合（P1.7 先例口径）。"""
        from task_service.infrastructure.acl.evaluation_config_acl_repository import (
            evaluation_config_acl_repository,
        )
        try:
            grouped = evaluation_config_acl_repository.get_dimension_results_by_result_ids(
                list(result_ids) if result_ids else [])
            return {int(rid) for rid, items in (grouped or {}).items() if items}
        except Exception as e:
            logger.warning(f"批量查询评估结果失败（按未评估降级）: {e}")
            return set()

    # ==================== S3 合并预览 / 下单 merge ====================

    def preview(self) -> dict:
        """合并预览（下单前统计/失效校验，设计文档 §3/§10）。

        预览只读购物车 + 引用结果行，不产生任何副作用（CQRS 查询侧）。
        INT-660：读侧 None 用户（AUTH_MODE=off）不再 401，走仓储
        cart_list(None)→[] → 空购物车分支。
        """
        try:
            user_id = self._current_user_id()
            items = self._repo.cart_list(user_id)
            if not items:
                return {'success': False, 'message': '购物车为空',
                        'data': {'code': 400}, 'code': 400}
            result_ids = [it['result_id'] for it in items]
            rows = self._load_results_with_tasks(result_ids)
            invalid_result_ids = [rid for rid in result_ids if rid not in rows]

            device_ids: List[int] = []
            device_names: Dict[int, Optional[str]] = {}
            case_ids: List[str] = []
            source_task_ids: List[int] = []
            execution_status_counts: Dict[str, int] = {}
            for result, task in rows.values():
                if result.device_id is not None and result.device_id not in device_ids:
                    device_ids.append(result.device_id)
                if result.test_case_id and result.test_case_id not in case_ids:
                    case_ids.append(result.test_case_id)
                if task.id not in source_task_ids:
                    source_task_ids.append(task.id)
                execution_status_counts[result.execution_status] = (
                    execution_status_counts.get(result.execution_status, 0) + 1)

            device_names = self._fetch_device_names(device_ids)
            # 重复与冲突提示（同设备同用例多来源默认全保留并标注来源，对齐任务合并方案 A）
            combo_counts: Dict[tuple, int] = {}
            for result, _task in rows.values():
                combo = (result.device_id, result.test_case_id)
                combo_counts[combo] = combo_counts.get(combo, 0) + 1
            duplicates = [
                {'device_id': dev_id, 'case_id': case_id, 'count': count}
                for (dev_id, case_id), count in combo_counts.items() if count > 1
            ]
            return {'success': True, 'message': 'ok', 'data': {
                'total_results': len(rows),
                'invalid_result_ids': invalid_result_ids,
                'source_task_count': len(source_task_ids),
                'source_task_ids': source_task_ids,
                'device_ids': device_ids,
                'device_names': [device_names.get(d) or f'设备 {d}' for d in device_ids],
                'case_count': len(case_ids),
                'execution_status_counts': execution_status_counts,
                'duplicates': duplicates,
            }}
        except ValueError as e:
            return {'success': False, 'message': str(e), 'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"合并预览失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def checkout_merge(self, data: dict) -> dict:
        """下单 merge：生成 cherry-pick 容器任务 + 结果引用关系（方案 A）。

        - 容器任务创建即 completed（§5.3，对齐现有合并容器口径）+ TaskCase
          状态继承源结果（双状态派生表达式自动生效）
        - 关系行（result_id + 溯源快照）与容器任务同事务原子创建
        - 任务级配置：算法参数/标签取首个来源任务，创建时允许编辑（§5.2 默认口径）
        - 下单成功已下单条目出清，未下单条目保留（§3 购物车口径）
        """
        try:
            user_id, err = self._require_user()
            if err:
                return err
            name = (data.get('name') or '').strip()
            if not name:
                return {'success': False, 'message': '新任务名称不能为空',
                        'data': {'code': 400}, 'code': 400}
            items = self._repo.cart_list(user_id)
            if not items:
                return {'success': False, 'message': '购物车为空，无法下单',
                        'data': {'code': 400}, 'code': 400}
            result_ids = [it['result_id'] for it in items]
            rows = self._load_results_with_tasks(result_ids)
            valid_items = [it for it in items if it['result_id'] in rows]
            if not valid_items:
                return {'success': False, 'message': '购物车条目全部失效（源结果已删除），无法下单',
                        'data': {'code': 400}, 'code': 400}

            new_task_id = self._create_container_task(name, data, rows, valid_items, user_id)
            try:
                from api_gateway.application.services.stats_cache import refresh_stats_cache
                refresh_stats_cache()
            except Exception:
                logger.debug("挑选合并下单后刷新统计缓存失败", exc_info=True)

            # 出清已下单条目，未下单（失效/重复）条目保留（§3）
            self._repo.cart_clear(user_id, keep_result_ids=[r for r in result_ids if r not in rows])
            return {'success': True, 'message': f'挑选合并任务「{name}」已创建',
                    'data': {'task_id': new_task_id, 'result_count': len(rows)},
                    'code': 201}
        except ValueError as e:
            return {'success': False, 'message': str(e), 'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"挑选合并下单失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def _load_results_with_tasks(self, result_ids: List[int]) -> Dict[int, tuple]:
        """批量加载 (result_id → (TestResult, Task))，源任务被删视为失效。"""
        from task_service.infrastructure.persistence.models import Task, TestResult
        from shared.models.database import get_db_session
        ids = [int(r) for r in result_ids]
        if not ids:
            return {}
        session = get_db_session()
        try:
            results = session.query(TestResult).filter(TestResult.id.in_(ids)).all()
            task_ids = {r.task_id for r in results if r.task_id}
            tasks = {t.id: t for t in session.query(Task).filter(
                Task.id.in_(list(task_ids)), Task.deleted == False).all()} if task_ids else {}  # noqa: E712
            out: Dict[int, tuple] = {}
            for result in results:
                task = tasks.get(result.task_id)
                if task is None:
                    continue
                out[result.id] = (result, task)
            return out
        finally:
            session.close()

    def _create_container_task(self, name: str, data: dict,
                               rows: Dict[int, tuple],
                               valid_items: List[Dict[str, Any]],
                               user_id: int) -> int:
        """创建 cherry-pick 容器任务（原子：Task + TaskCase + 关系表同事务）。

        - 创建即 completed（§5.3，对齐现有合并容器任务口径）
        - TaskCase 用例集 = 所选结果的用例集合，状态继承对应源结果
          （避免容器任务详情全部显示待执行，对齐 merge_tasks 先例）
        - 任务级配置取首个来源任务（§5.2 默认口径），data 覆盖优先
        """
        from task_service.infrastructure.persistence.models import (
            Task, TaskCase, TaskDevice, TaskAPI, TaskTag,
        )
        from task_service.infrastructure.persistence._task_converters import _UTC_PLUS_8
        from shared.models.database import get_db_session
        from shared.utils.status_utils import derive_task_case_status

        now = datetime.now(_UTC_PLUS_8)
        ordered = list(rows.values())  # dict 保序（插入序）
        first_result, first_task = ordered[0]

        session = get_db_session()
        try:
            # 任务级配置：请求显式携带 > 首个来源任务值（§5.2）
            algorithm_type = data.get('algorithm_type') or first_task.algorithm_type
            algorithm_params = data.get('algorithm_params') or first_task.algorithm_params
            description = data.get('description')
            if description is None:
                description = f'挑选合并自 {len({t.id for _r, t in rows.values()})} 个来源任务'

            container = Task(
                name=name, description=description,
                status=TaskStatus.COMPLETED,  # §5.3 创建即 completed
                config=data.get('config') or first_task.config,
                algorithm_type=algorithm_type,
                algorithm_params=algorithm_params,
                total_cases=0, completed_cases=0, failed_cases=0,
                created_by_user_id=user_id,
                created_at=now, updated_at=now,
                started_at=min((r.created_at for r, _t in rows.values() if r.created_at), default=now),
                completed_at=max((r.created_at for r, _t in rows.values() if r.created_at), default=now),
            )
            session.add(container)
            session.flush()
            task_id = container.id

            # TaskCase：用例集 = 所选结果用例集合，状态继承对应源结果的 TaskCase
            case_ids = sorted({r.test_case_id for r, _t in rows.values() if r.test_case_id})
            # 设备/API/标签继承（详情/统计/报告侧设备列表展示依赖）
            device_ids = {r.device_id for r, _t in rows.values() if r.device_id is not None}
            api_ids = {r.api_id for r, _t in rows.values() if r.api_id is not None}

            # 源 TaskCase 状态映射（首个命中为准，跨任务重复用例取最新结果对应行）
            source_task_ids = {t.id for _r, t in rows.values()}
            source_case_map: Dict[str, Any] = {}
            for tc in (session.query(TaskCase)
                       .filter(TaskCase.task_id.in_(list(source_task_ids)),
                               TaskCase.test_case_id.in_(case_ids)).all()):
                # 同用例多来源：保留与所选结果最新任务对齐的行（简单口径：首个）
                if tc.test_case_id not in source_case_map:
                    source_case_map[tc.test_case_id] = tc

            # 用例级被测设备路由（执行域 P0）：从源 TaskCase 继承 device_type/device_id/lab_id
            case_device_map: Dict[str, Any] = {}
            for tc in source_case_map.values():
                case_device_map[tc.test_case_id] = tc

            for case_id in case_ids:
                src_tc = case_device_map.get(case_id)
                # 结果继承：源结果行 execution_status 决定 TaskCase 执行侧状态
                # （容器任务无执行过程，结果即终态快照）
                result_rows = [r for r, _t in rows.values() if r.test_case_id == case_id]
                result_exec = result_rows[0].execution_status if result_rows else ExecutionStatus.COMPLETED
                case_exec = (src_tc.execution_status if src_tc else result_exec)
                case_eval = (src_tc.evaluation_status if src_tc else EvaluationStatus.COMPLETED)
                session.add(TaskCase(
                    task_id=task_id,
                    test_case_id=case_id,
                    status=derive_task_case_status(case_exec, case_eval),
                    execution_status=case_exec,
                    evaluation_status=case_eval,
                    device_type=(src_tc.device_type if src_tc else None),
                    device_id=(src_tc.device_id if src_tc else None),
                    lab_id=(getattr(src_tc, 'lab_id', None) if src_tc else None),
                    started_at=getattr(src_tc, 'started_at', None) if src_tc else None,
                    completed_at=getattr(src_tc, 'completed_at', None) if src_tc else None,
                    duration=getattr(src_tc, 'duration', None) if src_tc else None,
                    error_message=getattr(src_tc, 'error_message', None) if src_tc else None,
                    created_at=now,
                ))

            for device_id in device_ids:
                session.add(TaskDevice(task_id=task_id, device_id=device_id))
            for api_id in api_ids:
                session.add(TaskAPI(task_id=task_id, api_id=api_id))
            # 标签继承首个来源任务（§5.2 任务级口径；会话内重读避免 detached 懒加载）
            first_task_row = session.get(Task, first_task.id)
            for tag in (first_task_row.tags if first_task_row else []):
                session.add(TaskTag(task_id=task_id, tag_id=tag.id, created_at=now))

            # 关系表（引用方案 A）：与容器任务同事务原子创建
            snapshot_items = []
            for it in valid_items:
                result, task = rows[it['result_id']]
                snapshot_items.append({
                    'result_id': result.id,
                    'source_task_id': task.id,
                    'source_task_name': task.name,
                    'source_case_id': result.test_case_id,
                    'source_device_id': result.device_id,
                    'source_api_id': result.api_id,
                })
            for item in snapshot_items:
                from task_service.infrastructure.persistence.models import TaskCherryPickRelation
                session.add(TaskCherryPickRelation(
                    cherry_pick_task_id=task_id,
                    result_id=item['result_id'],
                    source_task_id=item['source_task_id'],
                    source_task_name=item['source_task_name'],
                    source_case_id=item['source_case_id'],
                    source_device_id=item['source_device_id'],
                    source_api_id=item['source_api_id'],
                    created_by_user_id=user_id,
                    created_at=now,
                ))

            # 计数自洽：以容器任务自身 TaskCase 统计（对齐 merge_tasks 口径）
            session.flush()
            container.total_cases = session.query(TaskCase).filter_by(task_id=task_id).count()
            container.completed_cases = session.query(TaskCase).filter_by(
                task_id=task_id, status=TaskCaseStatus.COMPLETED).count()
            container.failed_cases = session.query(TaskCase).filter_by(
                task_id=task_id, status=TaskCaseStatus.FAILED).count()

            session.commit()
            return task_id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ==================== S3 溯源查询 ====================

    def source_trace(self, task_id: int) -> dict:
        """新任务溯源查询（GET /tasks/{taskId}/cherry-pick-source，§8）。

        返回容器任务每条引用结果的来源任务/用例/设备；源结果已删的行
        标注 missing（引用方案 A 的缺失场景，§10）。
        """
        try:
            relations = self._repo.relations_by_container(task_id)
            if not relations:
                return {'success': False, 'message': '该任务不是挑选合并容器任务',
                        'data': {'code': 404}, 'code': 404}
            result_ids = [r['result_id'] for r in relations]
            existing = self._results_exist(result_ids)
            grouped: Dict[int, List[Dict[str, Any]]] = {}
            for r in relations:
                r['missing'] = r['result_id'] not in existing
                grouped.setdefault(r['source_task_id'], []).append(r)
            return {'success': True, 'message': 'ok', 'data': {
                'task_id': task_id,
                'is_cherry_pick': True,
                'total': len(relations),
                'groups': [{
                    'source_task_id': src_id,
                    'source_task_name': (rows[0].get('source_task_name') if rows else None) or f'任务 {src_id}',
                    'results': rows,
                } for src_id, rows in grouped.items()],
            }}
        except Exception as e:
            logger.error(f"挑选溯源查询失败 task_id={task_id}: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    # ==================== S4 下单 reexecute ====================

    def checkout_reexecute(self, data: dict) -> dict:
        """下单 reexecute：按所选结果的用例×设备集合创建重执行任务并启动。

        覆盖集合 = 所选结果去重后的 (用例, 用例级被测设备路由)（验收 §5/§12.7）；
        复用任务创建先例（create_task_with_relations + case_devices 用例级路由），
        走正常 start 链路（执行引擎接管）。
        """
        try:
            user_id, err = self._require_user()
            if err:
                return err
            items = self._repo.cart_list(user_id)
            if not items:
                return {'success': False, 'message': '购物车为空',
                        'data': {'code': 400}, 'code': 400}
            rows = self._load_results_with_tasks([it['result_id'] for it in items])
            if not rows:
                return {'success': False, 'message': '购物车条目全部失效，无法下单',
                        'data': {'code': 400}, 'code': 400}

            # 用例×设备集合（去重，设备路由从源 TaskCase 继承）
            case_ids = sorted({r.test_case_id for r, _t in rows.values() if r.test_case_id})
            case_devices = self._inherit_case_devices(rows)
            device_ids = sorted({r.device_id for r, _t in rows.values() if r.device_id is not None})

            now = datetime.now(_UTC_PLUS_8)
            name = (data.get('name') or '').strip() or f'挑选重执行_{now.strftime("%Y%m%d%H%M%S")}'
            new_task_id = task_repository.create_task_with_relations(
                name=name,
                description=data.get('description') or '挑选结果重新执行任务',
                config=data.get('config'),
                algorithm_type=data.get('algorithm_type'),
                algorithm_params=data.get('algorithm_params'),
                case_ids=case_ids,
                device_ids=device_ids,
                api_ids=sorted({r.api_id for r, _t in rows.values() if r.api_id is not None}),
                created_by=None,
                case_devices=case_devices,
            )
            if not new_task_id:
                return {'success': False, 'message': '创建重执行任务失败',
                        'data': {'code': 500}, 'code': 500}

            # 启动（走正常执行链路；启动失败不回滚任务创建——任务可手动再启动）
            start_result = task_lifecycle_start(new_task_id)
            self._repo.cart_clear(user_id)
            return {'success': True,
                    'message': f'重执行任务「{name}」已创建' + (
                        '' if start_result.get('success') else f'（自动启动失败：{start_result.get("message")}，可手动启动）'),
                    'data': {'task_id': new_task_id,
                             'case_count': len(case_ids),
                             'started': bool(start_result.get('success'))},
                    'code': 201}
        except ValueError as e:
            return {'success': False, 'message': str(e), 'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"挑选重执行下单失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def _inherit_case_devices(self, rows: Dict[int, tuple]) -> List[Dict[str, Any]]:
        """从源 TaskCase 继承用例级被测设备路由（执行域 P0：device_type 是
        执行路由唯一依据，NULL 会兜底 physical 误路由）。"""
        from task_service.infrastructure.persistence.models import TaskCase
        from shared.models.database import get_db_session

        case_ids = sorted({r.test_case_id for r, _t in rows.values() if r.test_case_id})
        source_task_ids = sorted({t.id for _r, t in rows.values()})
        if not case_ids or not source_task_ids:
            return []
        session = get_db_session()
        try:
            tc_rows = (session.query(TaskCase)
                       .filter(TaskCase.task_id.in_(source_task_ids),
                               TaskCase.test_case_id.in_(case_ids)).all())
            seen: Dict[str, Dict[str, Any]] = {}
            for tc in tc_rows:
                # 同用例多来源取首个完整路由行
                if tc.test_case_id in seen:
                    continue
                if not tc.device_type:
                    continue
                seen[tc.test_case_id] = {
                    'case_id': tc.test_case_id,
                    'device_type': tc.device_type,
                    'device_id': tc.device_id,
                    'lab_id': getattr(tc, 'lab_id', None),
                }
            return list(seen.values())
        finally:
            session.close()

    # ==================== S5 下单 reevaluate ====================

    def checkout_reevaluate(self, data: dict) -> dict:
        """下单 reevaluate：逐源任务发起（裁定 4，零评估域改动）。

        对购物车条目按来源任务分组，逐任务发起 Reevaluate(mode=selected,
        case_ids=该任务下所选用例)；Reevaluate RPC 为任务粒度，不动评估域契约。
        """
        try:
            user_id, err = self._require_user()
            if err:
                return err
            items = self._repo.cart_list(user_id)
            if not items:
                return {'success': False, 'message': '购物车为空',
                        'data': {'code': 400}, 'code': 400}
            rows = self._load_results_with_tasks([it['result_id'] for it in items])
            valid_items = [it for it in items if it['result_id'] in rows]
            if not valid_items:
                return {'success': False, 'message': '购物车条目全部失效，无法下单',
                        'data': {'code': 400}, 'code': 400}

            # 按来源任务分组 → {task_id: set(case_ids)}
            task_cases: Dict[int, set] = {}
            for it in valid_items:
                result, _task = rows[it['result_id']]
                if result.test_case_id:
                    task_cases.setdefault(result.task_id, set()).add(result.test_case_id)

            from task_service.infrastructure.acl.evaluation_acl_repository import evaluation_acl_repository
            submitted: List[int] = []
            failed: List[Dict[str, Any]] = []
            for source_task_id, case_set in task_cases.items():
                try:
                    resp = evaluation_acl_repository.submit_reevaluate(
                        task_id=source_task_id,
                        reextract_device_output=False,
                        reevaluate_type='all',
                        options={'mode': 'selected',
                                 'case_ids': sorted(case_set)},
                    )
                    if resp.get('success'):
                        submitted.append(source_task_id)
                    else:
                        failed.append({'task_id': source_task_id,
                                       'message': resp.get('message') or '提交失败'})
                except Exception as submit_err:
                    failed.append({'task_id': source_task_id, 'message': str(submit_err)})

            # 全部提交成功才出清（部分失败保留条目便于重试，§3 口径延伸）
            if submitted and not failed:
                self._repo.cart_clear(user_id)
            message = f'已对 {len(submitted)} 个来源任务发起重新评估'
            if failed:
                message += f'（失败 {len(failed)} 个任务，条目已保留）'
            return {'success': bool(submitted), 'message': message, 'data': {
                'submitted_task_ids': submitted,
                'failed': failed,
                'cleared': bool(submitted and not failed),
            }}
        except ValueError as e:
            return {'success': False, 'message': str(e), 'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"挑选重评估下单失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    # ==================== 下单统一入口 ====================

    def checkout(self, data: dict) -> dict:
        """下单统一入口（action=merge/reexecute/reevaluate，设计文档 §8）。

        merge 为默认出口（对齐 §8 checkout 契约）。
        """
        action = data.get('action') or CherryPickCheckoutAction.MERGE.value
        try:
            action = CherryPickCheckoutAction(action)
        except ValueError:
            return {'success': False, 'message': f'非法下单出口: {action}',
                    'data': {'code': 400}, 'code': 400}
        if action is CherryPickCheckoutAction.MERGE:
            return self.checkout_merge(data)
        if action is CherryPickCheckoutAction.REEXECUTE:
            return self.checkout_reexecute(data)
        return self.checkout_reevaluate(data)

    # ==================== 设备名批量查询（gRPC，P3 先例） ====================

    def _fetch_device_names(self, device_ids: List[int]) -> Dict[int, Optional[str]]:
        """通过 gRPC 批量获取设备名称（失败返回空 dict，仅日志告警）。"""
        if not device_ids:
            return {}
        try:
            from task_service.infrastructure.acl.device_acl_repository import device_acl_repository
            items = device_acl_repository.get_device_statuses(device_ids)
            return {item.get('id'): item.get('name') for item in items
                    if item.get('id') is not None}
        except Exception as e:
            logger.warning(f"批量查询设备名称失败: {e}")
            return {}


def task_lifecycle_start(task_id: int) -> dict:
    """启动任务（S4 重执行下单用，走正常执行链路）。"""
    from task_service.application.task.task_lifecycle_service import task_lifecycle_service
    return task_lifecycle_service.start(task_id)


# 模块级单例
cherry_pick_service = CherryPickService()
