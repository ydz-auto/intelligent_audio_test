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
    # 结果类型缺值哨兵（INT-1510 §8.2.2）：与写路径落库口径（NULL）配对的过滤值
    RESULT_TYPE_PENDING,
)

from task_service.core.time_utils import local_naive_to_utc_naive, utcnow
from task_service.infrastructure.persistence.cherry_pick_repository import cherry_pick_repository
from task_service.infrastructure.persistence.task_repository import task_repository

logger = logging.getLogger(__name__)

# 展示/命名用本地时区（写库口径一律 UTC naive，见 task_service.core.time_utils）
_UTC_PLUS_8 = timezone(timedelta(hours=8))

# 可挑选任务清单（INT-1496 §8.1）：入参取值显式枚举，拒绝魔法字符串
_PICKABLE_TASK_STATUSES = tuple(s.value for s in PickableTaskStatus)
_PICKABLE_TASK_SORT_KEYS = ('status', 'name', 'created_at')
_PICKABLE_TASK_SORT_ORDERS = ('asc', 'desc')

# 同用例多条所选结果 → 容器 TaskCase 执行状态的聚合优先级（INT-1715 ②）：
# 越靠前越「异常」，同一用例被多条结果命中时取最差，避免把失败藏成 completed。
_CASE_EXEC_PRECEDENCE = (
    ExecutionStatus.FAILED,
    ExecutionStatus.STOPPED,
    ExecutionStatus.RUNNING,
    ExecutionStatus.QUEUED,
    ExecutionStatus.SKIPPED,
    ExecutionStatus.PENDING,
)

# 所选结果维度行 → 容器 TaskCase 评估状态的聚合优先级（INT-1715 ②）：
# 与 evaluation_service 收尾口径（_check_all_results_completed）同构——任一维度
# 失败即失败；仍在评估中的过渡态取最靠后者；全部完成才 completed。
_CASE_EVAL_PRECEDENCE = (
    EvaluationStatus.FAILED,
    EvaluationStatus.STOPPED,
    EvaluationStatus.CALCULATING,
    EvaluationStatus.RUNNING,
    EvaluationStatus.QUEUED,
    EvaluationStatus.PENDING,
)

# 溯源/非容器同口径字面量（前端按「非 200 即非容器、静默」判定，改口径须同步前端）
_NOT_CHERRY_PICK_MESSAGE = '该任务不是挑选合并容器任务'

# 候选树 evaluation_status 取值（§8.2.2：evaluated/pending，与 candidates 同口径）
_TREE_EVALUATION_STATUSES = ('evaluated', 'pending')


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
            # INT-1693 §11-7：购物车用例视图按 分组/标签 组织，行级补 tags/group_id/
            # group_name（与候选行同源同口径，按响应内全部 source_case_id 一次批量回填）；
            # with_duration=False——购物车不用时长，不触发 audio gRPC 慢路径。
            case_meta = self._case_meta_map(case_ids, with_duration=False) if case_ids else {}
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
                # INT-1693 §11-7：行级用例分组/标签（缺省 []/null/null，用例已软删或
                # 查不到同落缺省；容器来源行按 source_case_id 取，天然覆盖）
                meta = case_meta.get(str(it.get('source_case_id'))) if it.get('source_case_id') else None
                it['tags'] = (meta or {}).get('tags', [])
                it['group_id'] = (meta or {}).get('group_id')
                it['group_name'] = (meta or {}).get('group_name')
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
        - case_keyword: 用例关键字模糊搜索（命中用例名/用例ID；INT-401 修复——
          与 case_ids 精确语义区分，前端「按用例搜索」改走此参数）
        - execution_status / evaluation_status: 结果执行/评估状态
        - start_date / end_date: 结果执行时间范围（TestResult.created_at）
        - api_ids: 结果级 API 维度过滤（INT-1510 §8.2.4；叶明细分页按展开的
          API 节点过滤，服务端出 total，不靠客户端过滤）
        - result_type: 结果类型等值过滤（INT-1510 §8.2.4）；取值 `default`
          命中缺值桶（落库 NULL/空串，与写路径口径一致）
        - excluded=True 时返回被删用例排除行（缺省剔除，对齐 INT-305 口径）
        - select_all=True（INT-577）：不翻页，返回当前筛选命中全部 result_id 集合
          （跨页全选语义 §11-4；与候选行查询同一条件口径）
        """
        try:
            task_ids = [int(t) for t in (data.get('task_ids') or [])]
            device_ids = [int(d) for d in (data.get('device_ids') or [])]
            api_ids = [int(a) for a in (data.get('api_ids') or [])]
            case_ids = [str(c) for c in (data.get('case_ids') or [])]
            case_keyword = (data.get('case_keyword') or '').strip() or None
            result_type = (data.get('result_type') or '').strip() or None
            execution_status = data.get('execution_status') or None
            evaluation_status = data.get('evaluation_status') or None
            start_date = data.get('start_date') or None
            end_date = data.get('end_date') or None
            page = max(1, int(data.get('page') or 1))
            per_page = min(200, max(1, int(data.get('per_page') or 50)))

            select_all = bool(data.get('select_all'))
            if select_all:
                # INT-577 §11-4：跨页全选——不翻页，命中全部 result_id 集合
                rows = self._query_candidate_results(
                    task_ids=task_ids, device_ids=device_ids, api_ids=api_ids,
                    case_ids=case_ids, case_keyword=case_keyword,
                    result_type=result_type,
                    execution_status=execution_status,
                    evaluation_status=evaluation_status,
                    start_date=start_date, end_date=end_date,
                    page=1, per_page=2 ** 31 - 1,  # 一次拉全（有界 by 命中量）
                )[0]
                return {'success': True, 'message': 'ok', 'data': {
                    'result_ids': [r['result_id'] for r in rows],
                }}

            rows, total = self._query_candidate_results(
                task_ids=task_ids, device_ids=device_ids, api_ids=api_ids,
                case_ids=case_ids, case_keyword=case_keyword,
                result_type=result_type,
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

    def pickable_tasks(self, data: dict) -> dict:
        """挑选向导阶段 1 可挑选任务清单（设计文档 §8.1，INT-1496）。

        取代「candidates 首页 200 行客户端聚合」的旧数据源：聚合与分页由仓储
        单条 SQL 完成，返回体只含任务级字段，不取评估状态 / 用例元信息 /
        音频时长等结果级装饰（性能硬性 1/3）。

        参数：keyword（任务名模糊）/ status（PickableTaskStatus 枚举值）/
        sort_by（status|name|created_at）/ sort_order（asc|desc）/ page / per_page。
        """
        try:
            keyword = (data.get('keyword') or '').strip() or None
            status = data.get('status') or None
            if status is not None and status not in _PICKABLE_TASK_STATUSES:
                return {'success': False, 'message': f'不支持的任务状态: {status}',
                        'data': {'code': 400}, 'code': 400}
            sort_by = data.get('sort_by') or 'status'
            if sort_by not in _PICKABLE_TASK_SORT_KEYS:
                return {'success': False, 'message': f'不支持的排序键: {sort_by}',
                        'data': {'code': 400}, 'code': 400}
            sort_order = (data.get('sort_order') or 'asc').lower()
            if sort_order not in _PICKABLE_TASK_SORT_ORDERS:
                return {'success': False, 'message': f'不支持的排序方向: {sort_order}',
                        'data': {'code': 400}, 'code': 400}
            page = max(1, int(data.get('page') or 1))
            per_page = min(200, max(1, int(data.get('per_page') or 50)))

            from task_service.infrastructure.visibility_context import visibility_identity
            user_id, is_admin = visibility_identity()
            result = self._repo.pickable_tasks(
                keyword=keyword, status=status, sort_by=sort_by,
                sort_order=sort_order, page=page, per_page=per_page,
                user_id=user_id, is_admin=is_admin,
            )
            return {'success': True, 'message': 'ok', 'data': {
                'items': result['items'], 'total': result['total'],
                'page': page, 'per_page': per_page,
            }}
        except (ValueError, TypeError) as e:
            return {'success': False, 'message': f'查询参数非法: {e}',
                    'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"可挑选任务清单查询失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    # ==================== 阶段 2 候选树聚合（INT-1510 §8.2） ====================

    def candidate_tree(self, data: dict) -> dict:
        """阶段 2 候选树聚合（设计文档 §8.2.2，INT-1510）。

        一次请求返回「任务 → 用例 → 设备/API → result_type」的分组计数与每个
        `result_type` 节点的 `result_id` 集，取代「candidates 首页 200 行由客户端
        重建树」的降级路径（§8.2.1 缺陷根因）。

        性能硬性（§8.2.3）：
        - 分组计数与 result_id 集在仓储单条聚合 SQL 内完成（不拉结果行进内存）；
        - `result_type` 取落库列，请求路径零 OSS 往返；
        - 跨服务调用只剩设备名 / API 名各 1 次批量（去重集合），与行数无关；
        - body 体量随命中结果行数增长（真实库 3614 行实测约 1.0MB），本卡不做缓存。

        容器任务（INT-657）经 `task_cherry_pick_relations` 展开，命中行归属容器
        任务（直查命中优先），与 candidates 同口径。
        """
        try:
            task_ids = [int(t) for t in (data.get('task_ids') or [])]
            if not task_ids or len(task_ids) > 200:
                return {'success': False, 'message': 'task_ids 必填且为 1–200 个',
                        'data': {'code': 400}, 'code': 400}
            device_ids = [int(d) for d in (data.get('device_ids') or [])]
            api_ids = [int(a) for a in (data.get('api_ids') or [])]
            case_ids = [str(c) for c in (data.get('case_ids') or [])]
            case_keyword = (data.get('case_keyword') or '').strip() or None
            execution_status = data.get('execution_status') or None
            evaluation_status = data.get('evaluation_status') or None
            if evaluation_status is not None and evaluation_status not in _TREE_EVALUATION_STATUSES:
                return {'success': False, 'message': f'不支持的评估状态: {evaluation_status}',
                        'data': {'code': 400}, 'code': 400}
            start_date = self._parse_iso_dt(data.get('start_date'))
            end_date = self._parse_iso_dt(data.get('end_date'))

            # INT-657：容器任务经引用关系解析（容器自身无 test_results 行）
            direct_task_ids, container_result_map = self._resolve_container_task_ids(task_ids)
            if not direct_task_ids and not container_result_map:
                return {'success': True, 'message': 'ok', 'data': {
                    'total': 0, 'task_count': 0,
                    'meta': {'tasks': [], 'cases': [], 'devices': [], 'apis': []},
                    'tree': [],
                }}

            from task_service.infrastructure.visibility_context import visibility_identity
            user_id, is_admin = visibility_identity()

            result = self._repo.candidate_tree(
                direct_task_ids, container_result_map,
                device_ids=device_ids, api_ids=api_ids, case_ids=case_ids,
                case_keyword=case_keyword, execution_status=execution_status,
                evaluation_status=evaluation_status,
                start_date=start_date, end_date=end_date,
                user_id=user_id, is_admin=is_admin,
            )
            groups = result['groups']

            tree, total, case_ids_hit, device_ids_hit, api_ids_hit = self._assemble_tree(groups)
            meta = {
                'tasks': sorted(result['tasks'], key=lambda t: t['task_id']),
                'cases': self._tree_case_meta(case_ids_hit),
                'devices': self._tree_device_meta(device_ids_hit),
                'apis': self._tree_api_meta(api_ids_hit),
            }
            return {'success': True, 'message': 'ok', 'data': {
                'total': total,
                'task_count': len(tree),
                'meta': meta,
                'tree': tree,
            }}
        except (ValueError, TypeError) as e:
            return {'success': False, 'message': f'查询参数非法: {e}',
                    'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"候选树聚合查询失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    @staticmethod
    def _parse_iso_dt(value) -> Optional[datetime]:
        """ISO 8601 时间串 → 库内 UTC naive（非法值按未传处理，与 candidates 同口径）。

        入参是用户选的本地墙钟，列里存 UTC naive（INT-2283），进 SQL 前归一。
        """
        if not value:
            return None
        try:
            return local_naive_to_utc_naive(datetime.fromisoformat(str(value)))
        except ValueError:
            return None

    _STATUS_KEYS = ('completed', 'failed', 'stopped', 'skipped')

    @classmethod
    def _blank_node_summary(cls) -> Dict[str, Any]:
        """节点状态汇总初值（执行状态分布 + 已评估数 + 末条结果时间）。"""
        return {
            'execution_status_counts': {k: 0 for k in cls._STATUS_KEYS},
            'evaluated_count': 0,
            'last_result_at': None,
        }

    @classmethod
    def _merge_node_summary(cls, node: Dict[str, Any], group: Dict[str, Any]) -> None:
        """把分组行的状态汇总滚加到树节点（任务/用例/设备/result_type 逐层）。"""
        counts = group.get('execution_status_counts') or {}
        target = node['execution_status_counts']
        for key in cls._STATUS_KEYS:
            target[key] += int(counts.get(key) or 0)
        node['evaluated_count'] += int(group.get('evaluated_count') or 0)
        last = group.get('last_result_at')
        if last and (node['last_result_at'] is None or last > node['last_result_at']):
            node['last_result_at'] = last

    @classmethod
    def _assemble_tree(cls, groups: List[Dict[str, Any]]) -> tuple:
        """把仓储的分组行装配为四层树（只在分组行上做字典归并，与行数无关）。

        每个节点都带状态汇总（`execution_status_counts` / `evaluated_count` /
        `last_result_at`，叶子→任务逐层滚加），前端按 count 直接渲染父行状态，
        不再逐节点探测叶明细。

        Returns:
            (tree, total, case_ids, device_ids, api_ids)——
            后三者是去重集合（meta 去重表的入参）。
        """
        task_map: Dict[int, Dict[str, Any]] = {}
        case_ids, device_ids, api_ids = set(), set(), set()
        total = 0
        for group in groups:
            count = int(group.get('count') or 0)
            total += count
            task_id = group['task_id']
            case_id = group.get('case_id')
            if case_id:
                case_ids.add(case_id)
            if group.get('device_id') is not None:
                device_ids.add(group['device_id'])
            if group.get('api_id') is not None:
                api_ids.add(group['api_id'])

            task_node = task_map.setdefault(
                task_id,
                {'task_id': task_id, 'count': 0, 'cases': {},
                 **cls._blank_node_summary()})
            task_node['count'] += count
            cls._merge_node_summary(task_node, group)
            case_node = task_node['cases'].setdefault(
                case_id,
                {'case_id': case_id, 'count': 0, 'devices': {},
                 **cls._blank_node_summary()})
            case_node['count'] += count
            cls._merge_node_summary(case_node, group)
            device_key = (group.get('device_id'), group.get('api_id'))
            device_node = case_node['devices'].setdefault(device_key, {
                'device_id': group.get('device_id'),
                'api_id': group.get('api_id'),
                'count': 0,
                'result_types': [],
                **cls._blank_node_summary(),
            })
            device_node['count'] += count
            cls._merge_node_summary(device_node, group)
            rt_node = {
                'result_type': group.get('result_type'),
                'count': count,
                'result_ids': list(group.get('result_ids') or []),
                **cls._blank_node_summary(),
            }
            cls._merge_node_summary(rt_node, group)
            device_node['result_types'].append(rt_node)

        tree = []
        for task_id in sorted(task_map):
            task_node = task_map[task_id]
            cases = []
            for case_id in sorted(task_node['cases'],
                                  key=lambda c: (c is None, c or '')):
                case_node = task_node['cases'][case_id]
                devices = []
                for key in sorted(case_node['devices'],
                                  key=lambda k: (k[0] is None, k[0] or 0,
                                                 k[1] is None, k[1] or 0)):
                    device_node = case_node['devices'][key]
                    device_node['result_types'].sort(
                        key=lambda rt: (rt['result_type'] or ''))
                    devices.append(device_node)
                cases.append({'case_id': case_id, 'count': case_node['count'],
                              'devices': devices,
                              'execution_status_counts': case_node['execution_status_counts'],
                              'evaluated_count': case_node['evaluated_count'],
                              'last_result_at': case_node['last_result_at']})
            tree.append({'task_id': task_id, 'count': task_node['count'],
                         'cases': cases,
                         'execution_status_counts': task_node['execution_status_counts'],
                         'evaluated_count': task_node['evaluated_count'],
                         'last_result_at': task_node['last_result_at']})
        return tree, total, case_ids, device_ids, api_ids

    def _tree_case_meta(self, case_ids) -> List[Dict[str, Any]]:
        """meta.cases 去重表（字段口径同 §8.1 用例元信息；查不到的用例落缺省）。"""
        if not case_ids:
            return []
        meta_map = self._case_meta_map(case_ids)
        out = []
        for case_id in sorted(case_ids):
            meta = meta_map.get(str(case_id)) or {}
            out.append({
                'case_id': case_id,
                'case_name': meta.get('case_name') or case_id,
                'algorithm_type': meta.get('algorithm_type'),
                'tags': meta.get('tags', []),
                'group_id': meta.get('group_id'),
                'group_name': meta.get('group_name'),
                'duration': meta.get('duration'),
                'rounds': meta.get('rounds'),
            })
        return out

    def _tree_device_meta(self, device_ids) -> List[Dict[str, Any]]:
        """meta.devices 去重表（设备名 1 次批量 gRPC，失败落 None）。"""
        if not device_ids:
            return []
        names = self._fetch_device_names(sorted(device_ids))
        return [{'device_id': d, 'device_name': names.get(d)}
                for d in sorted(device_ids)]

    def _tree_api_meta(self, api_ids) -> List[Dict[str, Any]]:
        """meta.apis 去重表（API 名 1 次批量 gRPC，失败落 None）。"""
        if not api_ids:
            return []
        names = self._fetch_api_names(sorted(api_ids))
        return [{'api_id': a, 'api_name': names.get(a)}
                for a in sorted(api_ids)]

    def _query_candidate_results(self, task_ids, device_ids, case_ids, case_keyword,
                                 execution_status, evaluation_status,
                                 start_date, end_date, page, per_page,
                                 api_ids=None, result_type=None) -> tuple:
        """挑选候选结果查询核心（只读，CQRS 查询侧无副作用）。

        - 默认仅终态任务（§10 显式终态集合 completed/failed/stopped）
        - 默认剔除 excluded=1 行（被删用例排除，INT-305 聚合口径）
        - 评估状态取自 evaluation_service（TestResultDimension 存在性），
          INT-1625 起走 ACL 共享库只读投影（只取存在性集合，不再回传全部维度行）
        - INT-1510：api_ids / result_type 服务端过滤（叶明细分页口径；
          result_type=default 命中落库 NULL/空串的缺值桶）
        - INT-657：task_ids 命中容器任务时经 task_cherry_pick_relations
          解析其引用的源结果参与候选命中（容器自身无 test_results 行，
          引用方案 A §5.1），命中项标注为容器任务（与源任务口径一致）
        """
        from task_service.infrastructure.persistence.models import Task, TestResult
        from shared.models.database import get_db_session
        from shared.infrastructure.visibility_filter import visible_condition
        from task_service.infrastructure.visibility_context import visibility_identity
        from sqlalchemy import func as sa_func, or_

        direct_task_ids = list(task_ids)
        container_result_map = {}
        if task_ids:
            direct_task_ids, container_result_map = self._resolve_container_task_ids(task_ids)
            if not direct_task_ids and not container_result_map:
                # 所选来源任务全部为不可再挑容器任务（§10）：无候选命中（INT-657）
                return [], 0

        _vis_uid, _vis_admin = visibility_identity()
        session = get_db_session()
        try:
            q = session.query(TestResult, Task).join(
                Task, TestResult.task_id == Task.id)
            # §10：仅终态任务可挑选（显式集合，拒绝魔法字符串）
            q = q.filter(Task.status.in_([s.value for s in PickableTaskStatus]),
                         Task.deleted == False,  # noqa: E712
                         # INT-423：私有任务对非 owner 不可挑选（列表不可见）
                         visible_condition(
                             Task.created_by_user_id, Task.visibility, _vis_uid, _vis_admin))
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
            if api_ids:
                # INT-1510 §8.2.4：结果级 API 维度过滤（与 device_ids 同层 AND）
                q = q.filter(TestResult.api_id.in_(api_ids))
            if result_type:
                # INT-1510 §8.2.4：result_type 等值过滤；default = 缺值桶
                # （落库口径 NULL/空串，§8.2.2「结果类型待补充」）
                if result_type == RESULT_TYPE_PENDING:
                    q = q.filter(or_(TestResult.result_type.is_(None),
                                     TestResult.result_type == ''))
                else:
                    q = q.filter(TestResult.result_type == result_type)
            if case_ids:
                q = q.filter(TestResult.test_case_id.in_(case_ids))
            if case_keyword:
                # INT-401：用例关键字模糊搜索——命中用例名/用例ID（与 case_ids 精确 IN 语义区分）
                from task_service.infrastructure.persistence.models import TestCase
                from sqlalchemy import select
                kw = f'%{case_keyword}%'
                matched_case_ids = select(TestCase.id).where(
                    or_(TestCase.name.like(kw), TestCase.id.like(kw)))
                q = q.filter(TestResult.test_case_id.in_(matched_case_ids))
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
                        Task.deleted == False,  # noqa: E712
                        visible_condition(
                            Task.created_by_user_id, Task.visibility, _vis_uid, _vis_admin),
                    ).all()]  # noqa: E712
                    result_ids_in_scope = [r[0] for r in session.query(TestResult.id).filter(
                        TestResult.task_id.in_(scope_ids),
                        TestResult.excluded == 0).all()] if scope_ids else []
                evaluated = self._evaluated_result_ids(result_ids_in_scope, session=session)
                if evaluation_status == EvaluationStatus.PENDING:
                    # 未评估：不在已评估集合（含维度行缺失场景）
                    q = q.filter(~TestResult.id.in_(evaluated))
                else:
                    q = q.filter(TestResult.id.in_(evaluated))
            # INT-305：默认剔除被删用例的排除行
            q = q.filter(TestResult.excluded == 0)
            if start_date:
                try:
                    # 用户输入是本地墙钟，列里是 UTC naive（INT-2283）
                    q = q.filter(TestResult.created_at >= local_naive_to_utc_naive(
                        datetime.fromisoformat(start_date)))
                except ValueError:
                    pass
            if end_date:
                try:
                    q = q.filter(TestResult.created_at <= local_naive_to_utc_naive(
                        datetime.fromisoformat(end_date)))
                except ValueError:
                    pass

            total = q.with_entities(sa_func.count(sa_func.distinct(TestResult.id))).scalar() or 0
            rows = (q.order_by(TestResult.task_id.desc(), TestResult.id)
                    .offset((page - 1) * per_page).limit(per_page).all())

            # 批量取评估状态标注（结果级已评估/未评估，存在性投影一次 IN 取回）
            row_result_ids = [r.id for r, _t in rows]
            evaluated_map = (self._evaluated_result_ids(row_result_ids, session=session)
                             if row_result_ids else {})

            # INT-577 §11-2：候选行补展示字段——case_name / device_name / api_name /
            # result_type（多级挑选树节点命名与 result_type 分组/筛选数据源）
            case_names = self._case_name_map({r.test_case_id for r, _t in rows if r.test_case_id})
            # INT-1130 §11-7：候选行补用例级元信息——tags/group_id/group_name/duration/rounds
            # （三视图与购物车分组·标签组织数据源，同源用例管理列表口径；无新表无多余请求）
            case_meta = self._case_meta_map({r.test_case_id for r, _t in rows if r.test_case_id})
            device_ids_in_page = {r.device_id for r, _t in rows if r.device_id is not None}
            api_ids_in_page = {r.api_id for r, _t in rows if r.api_id is not None}
            device_names = self._fetch_device_names(list(device_ids_in_page)) if device_ids_in_page else {}
            api_names = self._fetch_api_names(list(api_ids_in_page)) if api_ids_in_page else {}

            # INT-1510 §8.2.3 第 1 条：result_type 直接取落库列（读侧 DB-first，
            # 请求路径零对象存储往返；原 INT-1625 的文件并发预取已删除，不留开关）
            # 缺值（落库 NULL）按「结果类型待补充」桶对外输出 default。

            # INT-657：容器引用命中的结果标注为容器任务（与源任务口径一致）；
            # 同结果同时被源任务直查命中的保留源任务标注（直查优先，不混淆归属）
            direct_task_ids_set = set(direct_task_ids)
            items = []
            for result, task in rows:
                label = container_result_map.get(result.id) if container_result_map else None
                use_container = label is not None and (
                    not direct_task_ids_set or result.task_id not in direct_task_ids_set)
                meta = case_meta.get(result.test_case_id) or {}
                items.append({
                    'result_id': result.id,
                    'task_id': label['task_id'] if use_container else task.id,
                    'task_name': label['task_name'] if use_container else task.name,
                    'task_status': label['task_status'] if use_container else task.status,
                    'case_id': result.test_case_id,
                    # INT-577 §11-2：用例名（缺省显示 ID，容错口径）
                    'case_name': case_names.get(result.test_case_id) or result.test_case_id,
                    # INT-1130 §11-7：用例卡元信息（tags/分组/时长/轮次，缺省 []/null）
                    'tags': meta.get('tags', []),
                    'group_id': meta.get('group_id'),
                    'group_name': meta.get('group_name'),
                    'duration': meta.get('duration'),
                    'rounds': meta.get('rounds'),
                    'device_id': result.device_id,
                    'api_id': result.api_id,
                    # INT-577 §11-2：设备/API 名（TestResult 归属二选一，缺省 None）
                    'device_name': device_names.get(result.device_id),
                    'api_name': api_names.get(result.api_id),
                    # INT-1510 §8.2.3：result_type 取落库列，缺值输出 default
                    'result_type': result.result_type or RESULT_TYPE_PENDING,
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

    def _evaluated_result_ids(self, result_ids: Optional[List[int]], session=None) -> set:
        """批量查询已评估结果 ID 集合（P1.7 先例口径）。

        INT-1625：改 ACL 的共享库只读投影（只取「有无维度行」的存在性集合，
        不再经 gRPC 回传全部维度行——候选首页 200 个结果 ID 对应 5592 行维度，
        宿主实测 5~22s，是 60s 超时的主要来源）。
        """
        from task_service.infrastructure.acl.evaluation_config_acl_repository import (
            evaluation_config_acl_repository,
        )
        try:
            return evaluation_config_acl_repository.get_evaluated_result_ids(
                list(result_ids) if result_ids else [], session=session)
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
            # INT-774 ④：跨任务配置差异检测（§5.2 拍板：不一致强制确认提示，
            # 比「默认取首源」严）——algorithm_type / algorithm_params / config
            # 逐项比较；source_configs 供创建弹窗确认提示数据源（先例 agent/2/int-280）
            source_tasks = list({t.id: t for _r, t in rows.values()}.values())
            config_inconsistent = False
            config_fields: List[str] = []
            if len(source_tasks) > 1:
                first = source_tasks[0]
                if any(t.algorithm_type != first.algorithm_type for t in source_tasks[1:]):
                    config_inconsistent = True
                    config_fields.append('algorithm_type')
                if any(t.algorithm_params != first.algorithm_params for t in source_tasks[1:]):
                    config_inconsistent = True
                    config_fields.append('algorithm_params')
                if any(t.config != first.config for t in source_tasks[1:]):
                    config_inconsistent = True
                    config_fields.append('config')
            source_configs = [{
                'task_id': t.id,
                'task_name': t.name,
                'algorithm_type': t.algorithm_type,
                'algorithm_params': t.algorithm_params,
                'config': t.config,
            } for t in source_tasks]
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
                'config_inconsistent': config_inconsistent,
                'config_fields': config_fields,
                'source_configs': source_configs,
            }}
        except ValueError as e:
            return {'success': False, 'message': str(e), 'data': {'code': 400}, 'code': 400}
        except Exception as e:
            logger.error(f"合并预览失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def checkout_merge(self, data: dict) -> dict:
        """下单 merge：生成 cherry-pick 容器任务 + 结果引用关系（方案 A）。

        - 容器任务创建即 completed（§5.3，对齐现有合并容器口径）+ TaskCase
          执行状态按所选结果派生（INT-1715 ②，双状态派生表达式自动生效）
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
        """批量加载 (result_id → (TestResult, Task))，源任务被删视为失效。

        INT-423：源任务私有对非 owner 视为失效（越权读取源数据不可下单）。
        """
        from task_service.infrastructure.persistence.models import Task, TestResult
        from shared.models.database import get_db_session
        from shared.infrastructure.visibility_filter import visible_condition
        from task_service.infrastructure.visibility_context import visibility_identity
        ids = [int(r) for r in result_ids]
        if not ids:
            return {}
        _vis_uid, _vis_admin = visibility_identity()
        session = get_db_session()
        try:
            results = session.query(TestResult).filter(TestResult.id.in_(ids)).all()
            task_ids = {r.task_id for r in results if r.task_id}
            if task_ids:
                tasks = {t.id: t for t in session.query(Task).filter(
                    Task.id.in_(list(task_ids)),
                    Task.deleted == False,  # noqa: E712
                    visible_condition(
                        Task.created_by_user_id, Task.visibility, _vis_uid, _vis_admin),
                ).all()}
            else:
                tasks = {}
            out: Dict[int, tuple] = {}
            for result in results:
                task = tasks.get(result.task_id)
                if task is None:
                    continue
                out[result.id] = (result, task)
            return out
        finally:
            session.close()

    @staticmethod
    def _aggregate_case_exec_status(statuses) -> str:
        """所选结果执行状态 → 容器 TaskCase 执行状态（单条即原值，多条取最差）。

        容器 TaskCase 必须跟随**所选结果**（INT-1715 ②）：源 TaskCase 可能因人工
        复核只改判结果、未回写用例行而陈旧，继承源行会让容器关联用例区与所选
        结果状态相反。
        """
        present = {s for s in statuses if s}
        for candidate in _CASE_EXEC_PRECEDENCE:
            if candidate in present:
                return candidate
        return ExecutionStatus.COMPLETED

    @staticmethod
    def _aggregate_case_eval_status(statuses) -> Optional[str]:
        """所选结果维度行的评估过程状态 → 容器 TaskCase 评估状态（多条取最差）。

        INT-1715 ② 返工：评估侧同样按**所选结果**派生，不再继承可能陈旧的源
        TaskCase 评估态（实测任务 417/用例 4c42c1d5：结果 5480 维度行全 completed，
        源用例行却是 failed → 容器用例行被推导成 failed，与所选结果相反）。

        口径与 evaluation_service 收尾（`_check_all_results_completed`）同构：
        任一维度 evaluation_status=failed 即用例评估失败；仍处评估过渡态
        （pending/queued/running/calculating）取最靠后者（推导为 evaluating）；
        全部 completed → completed。

        无维度行（结果从未评估、或投影降级）返回 None，由调用方退回源用例行口径
        ——此时没有可派生的依据。
        """
        present = {s for s in statuses if s}
        if not present:
            return None
        for candidate in _CASE_EVAL_PRECEDENCE:
            if candidate in present:
                return candidate
        return EvaluationStatus.COMPLETED

    def _create_container_task(self, name: str, data: dict,
                               rows: Dict[int, tuple],
                               valid_items: List[Dict[str, Any]],
                               user_id: int) -> int:
        """创建 cherry-pick 容器任务（原子：Task + TaskCase + 关系表同事务）。

        - 创建即 completed（§5.3，对齐现有合并容器任务口径）
        - TaskCase 用例集 = 所选结果的用例集合，执行状态按所选结果派生、
          评估状态按所选结果维度行派生（INT-1715 ②；避免容器详情全部显示
          待执行，也避免与所选结果相反）
        - 任务级配置取首个来源任务（§5.2 默认口径），data 覆盖优先
        """
        from task_service.infrastructure.persistence.models import (
            Task, TaskCase, TaskDevice, TaskAPI, TaskTag,
        )
        from shared.models.database import get_db_session
        from shared.utils.status_utils import derive_task_case_status

        # INT-2209：容器任务的 created_at/started_at/completed_at 一律 UTC naive；
        # 来源结果行的 created_at 也是库内 UTC naive，两侧同口径直接取极值。
        now = utcnow()
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

            # TaskCase：用例集 = 所选结果用例集合，执行状态按所选结果派生（INT-1715 ②）
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

            # 参与状态派生的所选结果（按用例分组）。INT-1715 P3：已被「从任务移除
            # 用例」排除的结果（excluded=1）不参与派生——购物车若混入源任务已移除
            # 的结果，不应把容器用例行状态带偏（候选查询本就剔除这类行）。
            case_rows: Dict[str, List[Any]] = {}
            for result, _task in rows.values():
                if (getattr(result, 'excluded', 0) or 0) == 1:
                    continue
                if result.test_case_id:
                    case_rows.setdefault(result.test_case_id, []).append(result)

            # 评估过程状态投影（一次 IN 取回，失败降级为空 dict → 退回源用例行口径）
            dim_eval_map: Dict[int, List[str]] = {}
            selected_result_ids = [r.id for rs in case_rows.values() for r in rs]
            try:
                from task_service.infrastructure.acl.evaluation_config_acl_repository import (
                    evaluation_config_acl_repository,
                )
                dim_eval_map = evaluation_config_acl_repository.get_dimension_evaluation_statuses(
                    selected_result_ids, session=session)
            except Exception as e:
                logger.warning(f"容器用例评估状态投影失败（退回源用例行口径）: {e}")

            for case_id in case_ids:
                src_tc = case_device_map.get(case_id)
                selected = case_rows.get(case_id) or []
                # 执行侧按「所选结果」聚合（INT-1715 ②）：源 TaskCase 可能在人工
                # 复核只改判结果、未回写用例行时陈旧（实测结果 5715 completed /
                # 源用例行 failed），继续继承源行会让容器关联用例区与结果相反。
                case_exec = self._aggregate_case_exec_status(
                    [r.execution_status for r in selected])
                # 评估侧同样按所选结果派生（INT-1715 ② 返工）：结果行无评估列，
                # 取该用例所选结果在 test_result_dimensions 的评估过程状态聚合；
                # 无维度行（源结果从未评估/投影降级）才退回源用例行评估态。
                case_eval = self._aggregate_case_eval_status(
                    [s for r in selected for s in dim_eval_map.get(r.id) or []])
                if case_eval is None:
                    case_eval = (src_tc.evaluation_status if src_tc
                                 else EvaluationStatus.COMPLETED)
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

        INT-1706 §8.2：「不是容器」是正常查询结果（200 + `groups: []` +
        `is_cherry_pick: false`），不再用 4xx 表达——任务详情页对每个任务都会
        探一次本接口，普通任务恒 400 只会制造接口噪音。对齐同域的读探针
        `review_count` / `review_history`：无数据即空结果，不做任务存在性判定
        （存在性由任务详情接口负责）。

        INT-1714 §11-8：在既有返回结构上**追加**结果级字段（老字段不改名、
        不改语义、不删）——叶行状态徽章/result_type 分层/信息头来源任务状态位
        的数据源。批量实现（一次结果多列投影 + 各自一次 IN），无逐行查询：
        - `result_type` 取落库列（与候选行同源，INT-1510/INT-1669 口径），
          缺值输出 `default`；缺失行取不到结果，输出 null
        - `execution_status`/`result_created_at` 缺失行为 null；
          `evaluated` 缺失行恒 false
        - `case_name` 缺名返回 null（「未知用例」是前端文案，不裸显 UUID）
        - `groups[].source_task_status` 取 `Task.status`（一次 IN）
        """
        try:
            # INT-1715 ①：容器 Task 已软删（或不存在）→ 与「非容器」同口径返回
            # （success=false、非 200、不返回容器数据）。关系行不随软删级联
            # （回收站可恢复，级联删会丢溯源），存活判定放在读侧；否则软删容器
            # 仍会被前端按「200 即容器」渲染，与 GET /tasks?cherry_pick=true 口径矛盾。
            if not self._repo.container_task_alive(task_id):
                return {'success': False, 'message': _NOT_CHERRY_PICK_MESSAGE,
                        'data': {'code': 404}, 'code': 404}
            relations = self._repo.relations_by_container(task_id)
            if not relations:
                return {'success': True, 'message': 'ok', 'data': {
                    'task_id': task_id,
                    'is_cherry_pick': False,
                    'total': 0,
                    'groups': [],
                }}
            result_ids = [r['result_id'] for r in relations]
            snapshots = self._source_result_snapshots(result_ids)
            existing_ids = [rid for rid in result_ids if rid in snapshots]

            evaluated_ids = (self._evaluated_result_ids(existing_ids)
                             if existing_ids else set())
            case_ids = sorted({s['test_case_id'] for s in snapshots.values()
                               if s.get('test_case_id')})
            case_names = self._case_name_map(case_ids) if case_ids else {}
            device_ids = sorted({s['device_id'] for s in snapshots.values()
                                 if s.get('device_id') is not None})
            api_ids = sorted({s['api_id'] for s in snapshots.values()
                              if s.get('api_id') is not None})
            device_names = self._fetch_device_names(device_ids) if device_ids else {}
            api_names = self._fetch_api_names(api_ids) if api_ids else {}
            source_task_status = self._repo.source_task_status_map(
                sorted({r['source_task_id'] for r in relations}))

            grouped: Dict[int, List[Dict[str, Any]]] = {}
            for r in relations:
                snap = snapshots.get(r['result_id'])
                r['missing'] = snap is None
                # 结果级追加字段（缺失行取不到结果 → null / false）
                r['result_type'] = snap['result_type'] if snap else None
                r['execution_status'] = snap['execution_status'] if snap else None
                r['evaluated'] = bool(snap) and r['result_id'] in evaluated_ids
                r['case_name'] = (case_names.get(snap['test_case_id'])
                                  if snap and snap.get('test_case_id') else None)
                r['device_name'] = device_names.get(snap['device_id']) if snap else None
                r['api_name'] = api_names.get(snap['api_id']) if snap else None
                r['result_created_at'] = snap['result_created_at'] if snap else None
                grouped.setdefault(r['source_task_id'], []).append(r)
            return {'success': True, 'message': 'ok', 'data': {
                'task_id': task_id,
                'is_cherry_pick': True,
                'total': len(relations),
                'groups': [{
                    'source_task_id': src_id,
                    'source_task_name': (rows[0].get('source_task_name') if rows else None) or f'任务 {src_id}',
                    # INT-1714：来源任务状态（列表 DTO TaskSourceBriefDto 同口径）
                    'source_task_status': source_task_status.get(src_id),
                    'results': rows,
                } for src_id, rows in grouped.items()],
            }}
        except Exception as e:
            logger.error(f"挑选溯源查询失败 task_id={task_id}: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    @staticmethod
    def _source_result_snapshots(result_ids: List[int]) -> Dict[int, Dict[str, Any]]:
        """批量取源结果级字段（INT-1714 §11-8 溯源补字段）。

        一次 IN 多列投影：同时得出 missing 判定与 result_type/execution_status/
        result_created_at/用例·设备·API 归属，不逐行查、不走对象存储。
        `result_type` 与候选行同源取落库列，缺值输出 `default`（待补充桶）。
        结果行缺失（已删）不出现在返回 dict 中，调用侧按 missing 处理。
        """
        ids = sorted({int(r) for r in (result_ids or [])})
        if not ids:
            return {}
        from task_service.infrastructure.persistence.models import TestResult
        from shared.models.database import get_db_session
        session = get_db_session()
        try:
            rows = session.query(
                TestResult.id, TestResult.result_type, TestResult.execution_status,
                TestResult.created_at, TestResult.test_case_id,
                TestResult.device_id, TestResult.api_id,
            ).filter(TestResult.id.in_(ids)).all()
            return {int(r[0]): {
                'result_type': r[1] or RESULT_TYPE_PENDING,
                'execution_status': r[2],
                'result_created_at': r[3].isoformat() if r[3] else None,
                'test_case_id': r[4],
                'device_id': r[5],
                'api_id': r[6],
            } for r in rows}
        finally:
            session.close()

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

            # 任务名嵌本地墙钟（用户可见的本地日历语义）；created_at 走 UTC naive
            name = (data.get('name') or '').strip() or \
                f'挑选重执行_{datetime.now(_UTC_PLUS_8).strftime("%Y%m%d%H%M%S")}'
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
                now=utcnow(),
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

    # ==================== INT-577 §11-2 候选补字段辅助 ====================

    @staticmethod
    def _case_name_map(case_ids) -> Dict[str, Optional[str]]:
        """批量查询用例名称（test_cases 为用例目录，id 主键）。"""
        ids = [str(c) for c in (case_ids or []) if c]
        if not ids:
            return {}
        from task_service.infrastructure.persistence.models import TestCase
        from shared.models.database import get_db_session
        session = get_db_session()
        try:
            rows = session.query(TestCase.id, TestCase.name).filter(
                TestCase.id.in_(ids)).all()
            return {str(r[0]): r[1] for r in rows}
        except Exception as e:
            logger.warning(f"批量查询用例名称失败: {e}")
            return {}
        finally:
            session.close()

    @staticmethod
    def _case_meta_map(case_ids, with_duration: bool = True) -> Dict[str, Dict[str, Any]]:
        """批量查询用例级元信息（INT-1130 §11-7）：tags/group_id/group_name/duration/rounds。

        与用例管理列表（TestCaseListItem tags/groupId/groupName/totalDuration）同源口径：
        - tags：test_cases → test_case_tags → tags.name（去重保序，§11-7）
        - group_id/group_name：test_cases.group_id → test_case_groups（缺分组 None）
        - duration：collect_audios(config) 逐音频时长累加（同 total_duration 路径，
          audio_service gRPC 批量查询），无音频/无时长返回 None
        - rounds：len(config.get('rounds') or [])（轮次数，不返回 rounds 数组本身）

        INT-1693：with_duration=False 时跳过音频收集与 audio gRPC（购物车只要分组/
        标签），此时 duration 恒 None，分组/标签口径与候选行完全一致。

        INT-1693 返工：用例软删（deleted=true）与查不到同口径——一律不进 map，
        调用方落缺省（tags / group_id / group_name = []/null/null），与用例管理页
        已看不到的用例保持一致；候选侧结果本就由 TestResult.excluded 挡掉，不受影响。

        失败（如表异常 / gRPC 失败）返回空 dict，仅日志告警，不阻断候选查询。
        """
        ids = [str(c) for c in (case_ids or []) if c]
        if not ids:
            return {}
        from task_service.infrastructure.persistence.models import TestCase
        from shared.models.database import get_db_session
        from sqlalchemy.orm import joinedload
        from shared.utils import testcase_helpers as common
        session = get_db_session()
        try:
            rows = (session.query(TestCase)
                    .options(joinedload(TestCase.group), joinedload(TestCase.tags))
                    .filter(TestCase.id.in_(ids),
                            TestCase.deleted == False)  # noqa: E712
                    .all())
            # duration 同源 total_duration：批量收集引用音频，经 gRPC 一次性查时长
            audio_ids = set()
            if with_duration:
                for tc in rows:
                    for audio_item in common.collect_audios(tc.config or {}):
                        aid = audio_item.get('audio_id')
                        if aid is not None:
                            audio_ids.add(aid)
            audio_map = {}
            if audio_ids:
                # INT-1625：只取时长窄字段（原 GetAudiosByIds 逐音频查标签+标注，
                # 真实库 337 个音频实测 22.8s；口径同 RPC 的 audios.deleted 过滤）
                from task_service.infrastructure.acl.audio_acl_repository import audio_acl_repository
                durations = audio_acl_repository.get_audio_durations(audio_ids, session=session)
                audio_map = {aid: {'duration': dur} for aid, dur in durations.items()}
            out: Dict[str, Dict[str, Any]] = {}
            for tc in rows:
                config = tc.config or {}
                duration = 0.0
                # INT-1693 返工：with_duration=False 不做音频收集（原来仍逐用例跑
                # collect_audios 只为算恒为 None 的 duration，纯浪费）
                if with_duration:
                    for audio_item in common.collect_audios(config):
                        audio_id = audio_item.get('audio_id')
                        if audio_id:
                            audio = audio_map.get(audio_id)
                            if audio and audio.get('duration'):
                                duration += float(audio.get('duration'))
                out[str(tc.id)] = {
                    # INT-1510 §8.2.2：候选树 meta.cases 需要用例名与算法类型
                    # （candidates 只取 tags/group/duration/rounds 四个键，不暴露）
                    'case_name': tc.name,
                    'algorithm_type': tc.algorithm_type,
                    'tags': list(dict.fromkeys(t.name for t in tc.tags)),
                    'group_id': tc.group_id,
                    'group_name': tc.group.name if tc.group else None,
                    'duration': round(duration, 2) if duration > 0 else None,
                    'rounds': len(config.get('rounds') or []),
                }
            return out
        except Exception as e:
            logger.warning(f"批量查询用例元信息失败: {e}")
            return {}
        finally:
            session.close()

    def _fetch_api_names(self, api_ids: List[int]) -> Dict[int, Optional[str]]:
        """通过 gRPC 批量获取 API 名称（失败返回空 dict，仅日志告警）。"""
        if not api_ids:
            return {}
        try:
            from task_service.infrastructure.acl.report_acl_repository import api_test_acl_repository
            return {int(k): v for k, v in (api_test_acl_repository.fetch_api_names(api_ids) or {}).items()}
        except Exception as e:
            logger.warning(f"批量查询 API 名称失败: {e}")
            return {}


def task_lifecycle_start(task_id: int) -> dict:
    """启动任务（S4 重执行下单用，走正常执行链路）。"""
    from task_service.application.task.task_lifecycle_service import task_lifecycle_service
    return task_lifecycle_service.start(task_id)


# 模块级单例
cherry_pick_service = CherryPickService()
