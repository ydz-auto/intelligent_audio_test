# -*- coding: utf-8 -*-
"""任务仓储 — 任务创建/合并/编辑 Mixin（从 task_repository.py 拆分，P4-5）。

任务与关联（用例/设备/API）的原子创建、任务合并、名称/描述编辑、
用例动态增删、批量软删除、导出数据、运行中任务计数。
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from shared.models.database import get_db_session
from shared.utils.status_constants import (
    ExecutionStatus,
    EvaluationStatus,
    TaskCaseStatus,
    TaskStatus as SharedTaskStatus,
)
from task_service.infrastructure.persistence.models import Task, TaskCase, TaskAPI, TaskDevice, TaskTag

logger = logging.getLogger(__name__)

# 中国标准时区（UTC+8）
from task_service.infrastructure.persistence._task_converters import _UTC_PLUS_8


class ExecutionAffinityError(ValueError):
    """无法确定执行亲和域（task_case_relations.device_type，INT-1799）。

    建任务派生 / 动态加用例在「取不到被测 API 的 streaming」或「任务内 API
    流式性不一致」时抛出；应用层转 400，不落猜测值。
    """


class MissingDeviceTypeError(ValueError):
    """用例未携带执行路由 device_type（设备/API 分域唯一依据）。

    device_type 不允许空：建任务由 case_devices 显式给出，动态加用例必须
    随请求传入；应用层转 400，不回落到用例配置形态猜测。
    """


def resolve_api_affinity_token(api_ids) -> str:
    """按任务关联 API 的 `streaming` 派生执行亲和域令牌（INT-1799）。

    亲和域令牌语义（B0 裁定 §3.3）：
    - 任一 API streaming=true → `websocket_api`（需要实例亲和的流式会话；
      SSE 也归此域，保守超集只损失一点负载均衡自由度）
    - 全部 streaming=false    → `http_api`（无状态请求）
    - api_ids 为空            → 无 API 可派生（纯 E2E / 历史调用），沿用 http_api
    - ACL 取不到 / 混道       → 抛 ExecutionAffinityError（应用层 400，不猜）
    """
    from shared.models.common_enums import DeviceType
    from task_service.infrastructure.acl.api_acl_repository import api_acl_repository

    ids = [i for i in (api_ids or []) if i]
    if not ids:
        return DeviceType.HTTP_API.value
    flags = api_acl_repository.get_api_streaming_flags(ids)
    if flags is None:
        raise ExecutionAffinityError(
            '无法确定执行亲和域：取不到被测 API 的 streaming 配置')
    # 混选（流式 + 非流式）允许存在于同一任务：执行侧按「每个 API 自身的
    # streaming」逐条归道（流式走 RealtimeSessionExecutor、非流式走
    # APISessionExecutor），任务级令牌只作保守超集（任一流式 → websocket_api），
    # 供音频渲染出口/失败文案兜底，不再据此拒绝建任务。
    return (DeviceType.WEBSOCKET_API.value if any(flags.values())
            else DeviceType.HTTP_API.value)


class TaskCrudMixin:
    """任务创建 / 合并 / 编辑（供 TaskRepository 组合）"""

    def create_task_with_relations(
        self,
        name: str,
        description: str,
        config: Optional[Dict[str, Any]],
        algorithm_type: Optional[str],
        algorithm_params: Optional[Dict[str, Any]],
        case_ids: List[str],
        device_ids: List[int],
        api_ids: List[int],
        created_by: Optional[int],
        now: Optional[datetime] = None,
        case_devices: Optional[List[Dict[str, Any]]] = None,
        lab_ids: Optional[List[int]] = None,
        visibility: Optional[str] = None,
    ) -> int:
        """创建任务记录及其关联关系（用例/设备/API/实验室）。

        Args:
            name: 任务名称
            description: 任务描述
            config: 任务配置
            algorithm_type: 算法类型
            algorithm_params: 算法参数
            case_ids: 关联用例 ID 列表
            device_ids: 关联设备 ID 列表
            api_ids: 关联 API ID 列表
            created_by: 创建人
            now: 创建时间（调用方传入，保证时区一致）
            case_devices: 用例级设备选择（执行域 P0）：
                [{"case_id": str, "device_type": str, "device_id": str, "lab_id": int|None}, ...]
            lab_ids: 关联实验室 ID 列表（实验室扩展 INT-493/INT-540，可选；
                缺省/None = 不限定实验室，兼容现状）。按传入顺序写入
                task_laboratory_relations.priority（1 起），N:M 多实验室。
            visibility: 新建任务可见性（INT-566；shared/private；None 默认 shared）

        Returns:
            新任务 ID。

        说明：此方法在一个 DB session 内原子创建 Task + 关联表记录。
        """
        from task_service.infrastructure.persistence.models import TaskMergeRelation  # noqa: F401
        if now is None:
            now = datetime.now(_UTC_PLUS_8)

        session = get_db_session()
        try:
            task = self._build_new_task(
                name=name, description=description,
                config=config, algorithm_type=algorithm_type,
                algorithm_params=algorithm_params,
                total_cases=len(case_ids), created_by=created_by, now=now,
                visibility=visibility,
            )
            session.add(task)
            session.flush()  # 获取自增 ID
            task_id = task.id

            self._add_task_relations(session, task_id, case_ids, device_ids, api_ids, now, case_devices)
            self._add_task_laboratory_relations(session, task_id, lab_ids, now)

            # 用例级口径：total_cases 按去重用例数（一个用例 × 多 API 只算一条）
            task.total_cases = session.query(TaskCase.test_case_id).filter(
                TaskCase.task_id == task_id).distinct().count()

            session.commit()
            return task_id
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _build_new_task(name: str, description: str,
                        config: Optional[Dict[str, Any]],
                        algorithm_type: Optional[str],
                        algorithm_params: Optional[Dict[str, Any]],
                        total_cases: int, created_by: Optional[int],
                        now: datetime,
                        visibility: Optional[str] = None) -> Task:
        """构造新 Task PO（统一字段初始化，消除重复）。

        created_by_user_id（INT-141）：统一从 x-user-id 上下文取 JWT 操作人，
        不信任客户端自报 user_id（红线：0/None 不充当真实用户，保持 NULL）。
        visibility（INT-566）：新建任务可见性透传（默认 shared，与迁移一致）。
        """
        from shared.infrastructure.user_context import get_current_user_id
        return Task(
            name=name,
            description=description,
            status=SharedTaskStatus.PENDING,
            config=config or None,
            algorithm_type=algorithm_type,
            algorithm_params=algorithm_params or None,
            total_cases=total_cases,
            completed_cases=0,
            failed_cases=0,
            created_by=created_by,
            created_by_user_id=get_current_user_id(),
            visibility=visibility or 'shared',
            created_at=now,
            updated_at=now,
        )

    @staticmethod
    def _add_task_relations(session, task_id: int, case_ids: List[str],
                            device_ids: List[int], api_ids: List[int],
                            now: datetime,
                            case_devices: Optional[List[Dict[str, Any]]] = None) -> None:
        """批量添加任务关联记录（用例/设备/API）。

        Args:
            case_devices: 用例级设备选择（执行域 P0 + INT-604 混选前置）：
                [{"case_id": str, "device_type": str, "device_id": str, "lab_id": int|None}, ...]，
                按 (case_id, device_type, device_id) 归一化后写入 TaskCase——同一用例可落
                多条 TaskCase（设备侧 + API 侧），使「同个用例在设备与 API 间执行」成立。

        说明：device_type 是执行路由唯一依据，不允许为空——建任务由前端按目标
        展开 case_devices 显式传入（INT-1433），不再按用例配置形态派生。
        旧调用未传 case_devices 时按任务目标展开路由：每个 device_id 落一条
        physical 路由；api_ids 非空时追加一条 API 亲和域路由（流式性见
        resolve_api_affinity_token）。

        INT-604 幂等：应用层拒绝同一 (task, case, route) 重复提交——
        路由键按 (case_id, device_type 归一, device_id 归一)，NULL device_type
        归一为 physical、NULL device_id 归一为空串，与 DB 唯一索引
        uq_task_case_route 口径一致（见 202611 迁移）。
        """
        from shared.models.common_enums import DeviceType

        # 归一化用例级设备选择: {case_id: [item, ...]}（INT-604：同一用例可多条路由）
        device_map: Dict[str, List[Dict[str, Any]]] = {}
        for item in case_devices or []:
            case_id = item.get('case_id')
            if case_id is not None:
                device_map.setdefault(str(case_id), []).append(item)

        # 旧调用（无 case_devices）：按任务目标展开路由，不读用例配置
        legacy_entries: List[Dict[str, Any]] = [
            {'device_type': DeviceType.PHYSICAL.value, 'device_id': str(device_id)}
            for device_id in device_ids
        ]
        if api_ids:
            legacy_entries.append({
                'device_type': resolve_api_affinity_token(api_ids),
                'device_id': None,
            })
        if not legacy_entries:
            # 无任何执行目标的历史调用：物理域兜底（device_type 仍非空）
            legacy_entries.append({
                'device_type': DeviceType.PHYSICAL.value,
                'device_id': None,
            })

        def _entries_for(case_id: str) -> List[Dict[str, Any]]:
            entries = device_map.get(str(case_id)) or legacy_entries
            for entry in entries:
                if not entry.get('device_type'):
                    raise MissingDeviceTypeError(
                        f'用例 {case_id} 缺少 device_type 路由（请通过 case_devices 指定）')
            return entries

        # 应用层幂等（INT-604）：任务内已存在的 (case, route) 不再重复提交
        existing_routes = set()
        for tc_case_id, tc_device_type, tc_device_id in session.query(
                TaskCase.test_case_id, TaskCase.device_type, TaskCase.device_id
        ).filter(TaskCase.task_id == task_id).all():
            existing_routes.add((
                str(tc_case_id),
                (tc_device_type or DeviceType.PHYSICAL.value),
                (tc_device_id or ''),
            ))

        def _add_case_row(case_id: str, device_type: str,
                          device_id: Optional[str], lab_id: Optional[int]) -> None:
            route_key = (str(case_id),
                         (device_type or DeviceType.PHYSICAL.value),
                         (device_id or ''))
            if route_key in existing_routes:
                return
            existing_routes.add(route_key)
            session.add(TaskCase(
                task_id=task_id,
                test_case_id=case_id,
                status=TaskCaseStatus.PENDING,
                execution_status=ExecutionStatus.PENDING,
                evaluation_status=EvaluationStatus.PENDING,
                device_type=device_type,
                device_id=str(device_id) if device_id is not None else None,
                lab_id=lab_id or None,
                created_at=now,
            ))

        # 关联用例（INT-604：按 (case_id, device_type, device_id) 多维度落行）
        for case_id in case_ids:
            for dev in _entries_for(str(case_id)):
                _add_case_row(str(case_id), dev['device_type'],
                              dev.get('device_id'), dev.get('lab_id'))

        # 关联设备
        for device_id in device_ids:
            session.add(TaskDevice(task_id=task_id, device_id=device_id))

        # 关联 API
        for api_id in api_ids:
            session.add(TaskAPI(task_id=task_id, api_id=api_id))

    @staticmethod
    def _add_task_laboratory_relations(session, task_id: int,
                                       lab_ids: Optional[List[int]],
                                       now: datetime) -> None:
        """批量添加任务-实验室关联记录（N:M，实验室扩展 INT-493/INT-540）。

        priority 按 lab_ids 传入顺序 1 起，保留用户选择顺序；lab_ids 去重
        （UNIQUE(task_id, lab_id) 兜底）。空/None = 不关联实验室（兼容现状）。
        """
        from task_service.infrastructure.persistence.models import TaskLaboratoryRelation
        if not lab_ids:
            return
        seen = set()
        for priority, lab_id in enumerate(lab_ids, start=1):
            if lab_id is None or lab_id in seen:
                continue
            seen.add(lab_id)
            session.add(TaskLaboratoryRelation(
                task_id=task_id,
                lab_id=int(lab_id),
                priority=priority,
                created_at=now,
            ))

    def merge_tasks(
        self,
        source_task_ids: List[int],
        merged_task_name: str,
        description: str,
        created_by: Optional[int],
        now: Optional[datetime] = None,
    ) -> Tuple[int, int]:
        """创建合并任务并建立源任务-合并任务映射关系。

        Args:
            source_task_ids: 源任务 ID 列表
            merged_task_name: 合并后任务名称
            description: 任务描述
            created_by: 创建人
            now: 创建时间

        Returns:
            (merged_task_id, total_results)

        说明（迁移自 V9.7.10 task_controller.merge 增强）:
        - 允许合并已完成/合并任务/已合并任务（后两者会展开为原始源任务，
          使"合并任务再次被合并"时不会丢失其历史源任务）
        - 合并容器任务由 TaskMergeRelation(merged_task_id) 存在性标识
          （task.type 已废弃，差异#2 收尾）
        - 用例集合以源任务 TaskCase 为准（TestResult 可能包含已删除用例的执行记录，
          否则会导致合并任务 TaskCase 数量与 total_cases 不一致）
        - 新建 TaskCase 继承源任务的执行/评估状态，避免合并任务详情中所有用例显示为待执行
        - 设备/API/标签从源任务关联表继承
        """
        from task_service.infrastructure.persistence.models import (
            TaskMergeRelation, TaskCase, TaskDevice, TaskAPI, TaskTag,
        )
        if now is None:
            now = datetime.now(_UTC_PLUS_8)

        session = get_db_session()
        try:
            tasks = session.query(Task).filter(Task.id.in_(list(source_task_ids))).all()
            if len(tasks) != len(source_task_ids):
                raise ValueError("部分任务未找到")

            for t in tasks:
                # 允许合并已完成任务、合并任务、已合并任务（后两者在下方展开为原始源任务）
                if t.status not in (SharedTaskStatus.COMPLETED, SharedTaskStatus.MERGED):
                    raise ValueError(f"任务 '{t.name}' 未完成，无法合并")

            # 展开合并任务/已合并任务：找到合并之前的原始源任务
            candidate_ids = [t.id for t in tasks]
            merge_container_ids = {
                r.merged_task_id for r in session.query(TaskMergeRelation.merged_task_id)
                .filter(TaskMergeRelation.merged_task_id.in_(candidate_ids)).all()
            }
            final_source_ids = set()
            remerged_task_ids = set()
            for t in tasks:
                if t.id in merge_container_ids:
                    relations = session.query(TaskMergeRelation).filter_by(merged_task_id=t.id).all()
                    if relations:
                        final_source_ids.update(r.source_task_id for r in relations)
                        remerged_task_ids.add(t.id)
                        continue
                    final_source_ids.add(t.id)
                elif t.status == SharedTaskStatus.MERGED:
                    relations = (session.query(TaskMergeRelation)
                                 .filter_by(source_task_id=t.id)
                                 .order_by(TaskMergeRelation.id.desc()).all())
                    if relations:
                        latest_merged_id = relations[0].merged_task_id
                        source_relations = (session.query(TaskMergeRelation)
                                            .filter_by(merged_task_id=latest_merged_id).all())
                        if source_relations:
                            final_source_ids.update(r.source_task_id for r in source_relations)
                            remerged_task_ids.add(latest_merged_id)
                            continue
                    final_source_ids.add(t.id)
                else:
                    final_source_ids.add(t.id)

            if not final_source_ids:
                raise ValueError("合并后没有可用的源任务")

            source_tasks = session.query(Task).filter(Task.id.in_(list(final_source_ids))).all()
            source_task_map = {st.id: st for st in source_tasks}
            ordered_source_ids = [sid for sid in final_source_ids if sid in source_task_map]

            # 源任务贡献结果数、设备/API/用例/标签集合
            source_result_counts = {}
            device_ids_set = set()
            api_ids_set = set()
            case_ids_set = set()
            tag_ids_set = set()

            for task in source_tasks:
                source_result_counts[task.id] = task.completed_cases or 0
                for td in session.query(TaskDevice).filter_by(task_id=task.id).all():
                    device_ids_set.add(td.device_id)
                for ta in session.query(TaskAPI).filter_by(task_id=task.id).all():
                    api_ids_set.add(ta.api_id)
                for tc in session.query(TaskCase).filter_by(task_id=task.id).all():
                    case_ids_set.add(tc.test_case_id)
                for tag in task.tags:
                    tag_ids_set.add(tag.id)

            # total_cases 与合并任务的 TaskCase 集合保持一致（源任务用例重叠时 SUM 会重复计数）
            total_cases = len(case_ids_set)

            merged_task = self._build_new_task(
                name=merged_task_name, description=description,
                config=None, algorithm_type=None, algorithm_params=None,
                total_cases=total_cases, created_by=created_by, now=now,
            )
            merged_task.status = SharedTaskStatus.COMPLETED
            merged_task.completed_cases = 0
            merged_task.failed_cases = 0
            started_list = [t.started_at for t in source_tasks if t.started_at]
            completed_list = [t.completed_at for t in source_tasks if t.completed_at]
            if started_list:
                merged_task.started_at = min(started_list)
            if completed_list:
                merged_task.completed_at = max(completed_list)
            session.add(merged_task)
            session.flush()
            merged_task_id = merged_task.id

            # 关联设备
            for device_id in device_ids_set:
                existing = session.query(TaskDevice).filter_by(
                    task_id=merged_task_id, device_id=device_id).first()
                if not existing:
                    session.add(TaskDevice(task_id=merged_task_id, device_id=device_id))

            # 关联 API
            for api_id in api_ids_set:
                existing = session.query(TaskAPI).filter_by(
                    task_id=merged_task_id, api_id=api_id).first()
                if not existing:
                    session.add(TaskAPI(task_id=merged_task_id, api_id=api_id))

            # 源任务用例状态映射，供合并任务新建 TaskCase 时继承
            source_case_status = {}
            for task in tasks:
                for tc in session.query(TaskCase).filter_by(task_id=task.id).all():
                    if tc.test_case_id not in source_case_status:
                        source_case_status[tc.test_case_id] = tc

            for case_id in case_ids_set:
                existing = session.query(TaskCase).filter_by(
                    task_id=merged_task_id, test_case_id=case_id).first()
                if not existing:
                    src_tc = source_case_status.get(case_id)
                    # 继承源任务的执行/评估状态，避免合并任务详情中所有用例都显示为待执行
                    session.add(TaskCase(
                        task_id=merged_task_id,
                        test_case_id=case_id,
                        status=(src_tc.status if src_tc else TaskCaseStatus.COMPLETED),
                        execution_status=(src_tc.execution_status if src_tc else ExecutionStatus.COMPLETED),
                        evaluation_status=(src_tc.evaluation_status if src_tc else EvaluationStatus.COMPLETED),
                        device_type=(src_tc.device_type if src_tc else None),
                        device_id=(src_tc.device_id if src_tc else None),
                        started_at=getattr(src_tc, 'started_at', None) if src_tc else None,
                        completed_at=getattr(src_tc, 'completed_at', None) if src_tc else None,
                        duration=getattr(src_tc, 'duration', None) if src_tc else None,
                        error_message=getattr(src_tc, 'error_message', None) if src_tc else None,
                        created_at=now,
                    ))

            # 关联标签
            for tag_id in tag_ids_set:
                existing = session.query(TaskTag).filter_by(
                    task_id=merged_task_id, tag_id=tag_id).first()
                if not existing:
                    session.add(TaskTag(task_id=merged_task_id, tag_id=tag_id))

            # 被再次合并的合并任务标记为已合并（其历史源任务由新合并任务接管）
            for mid in remerged_task_ids:
                m_task = session.get(Task, mid)
                if m_task:
                    m_task.status = SharedTaskStatus.MERGED

            # 原始源任务标记为已合并（已是 merged 的保持不动）
            for sid in ordered_source_ids:
                s_task = source_task_map[sid]
                if s_task.status != SharedTaskStatus.MERGED:
                    s_task.status = SharedTaskStatus.MERGED

            # 新合并任务直接关联展开后的原始源任务
            for sid in ordered_source_ids:
                session.add(TaskMergeRelation(
                    merged_task_id=merged_task_id,
                    source_task_id=sid,
                    source_result_count=source_result_counts.get(sid, 0),
                    created_at=now,
                ))

            # 以合并任务自身 TaskCase 统计完成/失败数，保证与总用例数自洽
            session.flush()
            merged_task.total_cases = session.query(TaskCase).filter_by(task_id=merged_task_id).count()
            merged_task.completed_cases = session.query(TaskCase).filter_by(
                task_id=merged_task_id, status=TaskCaseStatus.COMPLETED).count()
            merged_task.failed_cases = session.query(TaskCase).filter_by(
                task_id=merged_task_id, status=TaskCaseStatus.FAILED).count()

            session.commit()
            return merged_task_id, merged_task.total_cases
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    # ========== task_crud_service 兼容方法 ==========

    def update_task(self, task_id: int, name: str = None,
                    description: str = None, visibility: str = None) -> bool:
        """更新任务名称/描述（updated_by_user_id 记录操作人，INT-141）。

        visibility（INT-466）：可见性切换（shared/private；None 不更新）。

        Returns:
            True 如果任务存在且已更新；False 如果任务不存在。
        """
        from shared.infrastructure.user_context import get_current_user_id
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return False
            if name is not None:
                task.name = name
            if description is not None:
                task.description = description
            if visibility is not None:
                task.visibility = visibility
            task.updated_by_user_id = get_current_user_id()
            task.updated_at = datetime.now(_UTC_PLUS_8)
            session.commit()
            return True
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def update_cases(self, task_id: int, action: str,
                     case_ids: List[str],
                     case_devices: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        """动态添加/移除用例。

        Args:
            task_id: 任务 ID
            action: 'add' 或 'remove'
            case_ids: 用例 ID 列表
            case_devices: add 时的执行路由（device_type 必填）：
                [{"case_id": str, "device_type": str, "device_id": str|None, "lab_id": int|None}]

        Returns:
            {'task_id': task_id, 'total_count': N} 或 None（任务不存在）
            或 {'error': str, 'code': int}
        """
        session = get_db_session()
        try:
            task = session.get(Task, task_id)
            if task is None:
                return None

            now = datetime.now(_UTC_PLUS_8)

            err = self._apply_case_action(session, task_id, action, case_ids, now, case_devices)
            if err:
                return err

            session.flush()
            total = session.query(TaskCase).filter(
                TaskCase.task_id == task_id
            ).count()
            task.total_cases = total
            task.updated_at = now
            session.commit()
            return {'task_id': task_id, 'total_count': total}
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _apply_case_action(session, task_id: int, action: str,
                           case_ids: List[str], now: datetime,
                           case_devices: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        """执行用例动态增/删动作。返回错误 dict 或 None。"""
        if action == 'add':
            # device_type 是执行路由唯一依据，add 时必须由调用方显式给出
            device_map: Dict[str, Dict[str, Any]] = {}
            for item in case_devices or []:
                case_id = item.get('case_id')
                if case_id is not None:
                    device_map[str(case_id)] = item

            for case_id in case_ids:
                entry = device_map.get(str(case_id)) or {}
                device_type = entry.get('device_type')
                if not device_type:
                    return {
                        'error': f'用例 {case_id} 缺少 device_type 路由（请通过 case_devices 指定）',
                        'code': 400,
                    }
                existing = session.query(TaskCase).filter(
                    TaskCase.task_id == task_id,
                    TaskCase.test_case_id == case_id,
                ).first()
                if existing is None:
                    device_id = entry.get('device_id')
                    session.add(TaskCase(
                        task_id=task_id,
                        test_case_id=case_id,
                        status=TaskCaseStatus.PENDING,
                        execution_status=ExecutionStatus.PENDING,
                        evaluation_status=EvaluationStatus.PENDING,
                        device_type=device_type,
                        device_id=str(device_id) if device_id is not None else None,
                        lab_id=entry.get('lab_id') or None,
                        created_at=now,
                    ))
        elif action == 'remove':
            session.query(TaskCase).filter(
                TaskCase.task_id == task_id,
                TaskCase.test_case_id.in_(list(case_ids)),
            ).delete(synchronize_session=False)
        else:
            return {'error': f'未知操作: {action}', 'code': 400}
        return None

    def batch_stop_and_soft_delete(self, task_ids: List[int]) -> int:
        """批量停止并软删除任务。

        调用方应先停止运行中的任务（通过执行引擎），
        此方法仅做软删除。统一盖 deleted_at / deleted_by_user_id
        （INT-141：回收站可见性与操作人记录）。

        Returns:
            实际删除的条数

        INT-423：逐行可见性过滤——私有非 owner 任务跳过，不整批放行
        （与应用层 filter_visible_task_ids 双保险）。
        """
        if not task_ids:
            return 0
        from shared.infrastructure.user_context import get_current_user_id, get_current_user_is_admin
        from shared.models.database import utc8now
        session = get_db_session()
        try:
            ids = self.filter_visible_task_ids(
                task_ids, user_id=get_current_user_id(),
                is_admin=get_current_user_is_admin())
            if not ids:
                return 0
            count = session.query(Task).filter(
                Task.id.in_(ids)
            ).update({
                Task.deleted: True,
                Task.deleted_at: utc8now(),
                Task.deleted_by_user_id: get_current_user_id(),
            }, synchronize_session=False)
            session.commit()
            return count
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def filter_visible_task_ids(self, task_ids: List[int], user_id=None,
                                is_admin: bool = False) -> List[int]:
        """批量任务可见性逐行过滤（INT-423）：返回可见 id 子集。

        私有非 owner 行跳过（共享 + owner 放行；admin 全量），
        供 batch delete / batch export 等批量操作逐行收敛。
        """
        if not task_ids:
            return []
        from shared.infrastructure.visibility_filter import filter_visible_owners
        session = get_db_session()
        try:
            ids = [int(i) for i in task_ids]
            rows = session.query(Task.id, Task.created_by_user_id, Task.visibility).filter(
                Task.id.in_(ids)).all()
            visible = filter_visible_owners([(r[0], r[1], r[2]) for r in rows], user_id, is_admin)
            visible_set = set(visible)
            return [i for i in ids if i in visible_set]
        finally:
            session.close()

    def batch_restore(self, task_ids: List[int]) -> int:
        """批量恢复软删除任务（仅已删除行会恢复）。

        TaskCase 关联行在软删除期间未被清理（60 天硬清理按任务整体过期），
        恢复任务行即恢复其用例关联，无需二次处理。

        Returns:
            实际恢复的条数（已删除行数；未删除/不存在的 ID 不计入）

        INT-423：仅恢复当前用户可见的行（共享 + 自己创建的私有行）。
        """
        if not task_ids:
            return 0
        from shared.infrastructure.user_context import get_current_user_id, get_current_user_is_admin
        session = get_db_session()
        try:
            ids = self.filter_visible_task_ids(
                task_ids, user_id=get_current_user_id(),
                is_admin=get_current_user_is_admin())
            if not ids:
                return 0
            count = session.query(Task).filter(
                Task.id.in_(ids),
                Task.deleted == True,  # noqa: E712
            ).update(
                {Task.deleted: False, Task.deleted_at: None},
                synchronize_session=False,
            )
            session.commit()
            return count
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_tasks_for_export(self, task_ids: List[int]) -> List[Dict[str, Any]]:
        """获取任务导出数据（dict 列表）。"""
        session = get_db_session()
        try:
            tasks = session.query(Task).filter(
                Task.id.in_(task_ids),
                Task.deleted == False,  # noqa: E712
            ).all()
            return [{
                'id': t.id,
                'name': t.name,
                'description': t.description,
                'status': t.status,
                'config': t.config,
                'algorithm_type': t.algorithm_type,
                'algorithm_params': t.algorithm_params,
                'total_cases': t.total_cases,
                'completed_cases': t.completed_cases,
                'failed_cases': t.failed_cases,
                'created_at': t.created_at.isoformat() if t.created_at else None,
                'updated_at': t.updated_at.isoformat() if t.updated_at else None,
                'started_at': t.started_at.isoformat() if t.started_at else None,
                'completed_at': t.completed_at.isoformat() if t.completed_at else None,
            } for t in tasks]
        finally:
            session.close()
