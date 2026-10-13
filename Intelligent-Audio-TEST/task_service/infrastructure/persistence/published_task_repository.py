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
import copy
import json
import logging
import uuid
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
from task_service.infrastructure.persistence.models.testcase_models import (
    Tag, TestCase, TestCaseGroup, TestCaseTag,
)
from report_service.infrastructure.persistence.models import (
    Report, ReportSummary, ReportSummaryMeta, ReportMetricStats, ReportCase, ReportRawData,
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
        task_type: str = None,
        algorithm_type: str = None,
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
                algorithm_type=algorithm_type,
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
        algorithm_type: str = '',
        benchmark=None,
        start_date: str = '',
        end_date: str = '',
    ):
        """分页查询当前版本列表（含筛选），返回 (rows, total)。

        benchmark: True/False 精确过滤（供 Benchmark 排行实测轨消费），
        None/'' 表示不过滤。
        task_type / algorithm_type: 精确过滤发布时冻结的冗余列
        （type/algorithm_type，对齐 V9.7.10；'' 或 'all' 表示不过滤）。
        """
        session = get_db_session()
        try:
            query = session.query(PublishedTask).filter(
                PublishedTask.is_current.is_(True)
            )
            if status:
                query = query.filter(PublishedTask.status == status)
            if task_type and task_type != 'all':
                query = query.filter(PublishedTask.type == task_type)
            if algorithm_type and algorithm_type != 'all':
                query = query.filter(PublishedTask.algorithm_type == algorithm_type)
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
        version: int,
        task_type: str = None,
        algorithm_type: str = None,
        benchmark: bool = False,
        snapshot_config=None,
        report_snapshot=None,
        publish_reason=None,
        published_by=None,
        demote_id: int = None,
    ) -> PublishedTask:
        """创建新版本 PO。

        Args:
            benchmark: 新版本 Benchmark 标记（默认 False，由应用服务继承当前版本）
            task_type / algorithm_type: 发布时冻结的冗余列（应用服务派生/继承）
            report_snapshot: 冻结报告快照（应用服务冻结/继承，INT-258 快照语义）
            published_by: 新版本发布操作人（应用服务从请求上下文回填）
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
                algorithm_type=algorithm_type,
                status='published',
                version=version,
                is_current=True,
                benchmark=bool(benchmark),
                snapshot_config=snapshot_config,
                report_snapshot=report_snapshot,
                publish_reason=publish_reason,
                published_by=published_by,
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

    def get_task_case_devices(self, task_id: int):
        """读取用例级被测设备选择（快照 caseDevices 数据源，执行路由还原依据）。"""
        session = get_db_session()
        try:
            rows = (
                session.query(
                    TaskCase.test_case_id, TaskCase.device_type,
                    TaskCase.device_id, TaskCase.lab_id,
                )
                .filter(TaskCase.task_id == task_id)
                .order_by(TaskCase.id.asc())
                .all()
            )
            return [
                {
                    'case_id': test_case_id,
                    'device_type': device_type,
                    'device_id': device_id,
                    'lab_id': lab_id,
                }
                for test_case_id, device_type, device_id, lab_id in rows
                if test_case_id
            ]
        finally:
            session.close()

    def get_task_report_case_ids(self, task_id: int):
        """历史数据兜底：从该任务的报告用例取用例 ID（有报告的任务必可发布）。"""
        session = get_db_session()
        try:
            report = (
                session.query(Report)
                .filter(
                    Report.task_id == task_id,
                    Report.type == 'task',
                    Report.deleted.is_(False),
                )
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

    # ==================== 任务详情冻结（INT-303）====================

    def freeze_task_snapshot(self, task) -> dict:
        """冻结来源日常任务的任务详情全量数据（INT-303 快照语义）。

        与 report_snapshot（INT-258 冻结真实报告）同一语义：任务详情也要真冻结。
        发布/新版本（指定新来源任务）时把任务详情内联冻结进快照，源任务/源用例
        后续被编辑/删除不再影响已发布版本的详情展示与执行。

        camelCase 契约（schemaVersion=2）：
        - task 基本信息冻结（name/description/config/algorithmType/algorithmParams/tags）
        - cases[]：每个用例完整配置深拷贝——rounds/音频引用/播放设备/标签/分组/
          评价维度/算法参数/参考参数内容内联（对齐 B1 导入导出"可独立还原"口径，
          参考参数从存储读出内容内联而非存路径）
        - devices/apis/playbackDevices/splMappings：关联引用快照（含名称，渲染不再 join 现库）
        """
        session = get_db_session()
        try:
            # ---- 任务基本信息 ----
            # task 由 repo.get_task 返回（session 已 close，列属性可用但
            # relationship 惰性加载不可用）——任务标签经 task_tags 联表读取
            task_tag_names = [row[0] for row in (
                session.query(Tag.name)
                .join(TaskTag, TaskTag.tag_id == Tag.id)
                .filter(TaskTag.task_id == task.id)
                .all()
            ) if row[0]]
            task_body = {
                'name': task.name,
                'description': task.description,
                'config': copy.deepcopy(task.config) if task.config else {},
                'algorithmType': task.algorithm_type,
                'algorithmParams': copy.deepcopy(task.algorithm_params) if task.algorithm_params else {},
                'tags': task_tag_names,
            }

            # ---- 用例完整配置深拷贝 ----
            task_cases = (
                session.query(TaskCase)
                .filter(TaskCase.task_id == task.id)
                .order_by(TaskCase.id.asc())
                .all()
            )
            case_ids = [tc.test_case_id for tc in task_cases if tc.test_case_id]
            case_rows = (
                session.query(TestCase)
                .filter(TestCase.id.in_(case_ids))
                .all()
                if case_ids else []
            )
            case_map = {c.id: c for c in case_rows}

            # 用例关联标签批量预取（test_case_tags → tags）
            tag_map = {}
            if case_ids:
                tag_rows = (
                    session.query(TestCaseTag.test_case_id, Tag.name)
                    .join(Tag, Tag.id == TestCaseTag.tag_id)
                    .filter(TestCaseTag.test_case_id.in_(case_ids))
                    .all()
                )
                for cid, name in tag_rows:
                    tag_map.setdefault(cid, []).append(name)

            # 分组批量预取
            group_ids = {c.group_id for c in case_rows if c.group_id}
            group_map = {}
            if group_ids:
                for g in session.query(TestCaseGroup).filter(TestCaseGroup.id.in_(list(group_ids))).all():
                    group_map[g.id] = {
                        'id': g.id,
                        'name': g.name,
                        'description': g.description,
                        'algorithmType': g.algorithm_type,
                    }

            # 播放设备名称解析（音频 playback_device_id → playback_devices.name）
            playback_ids = set()
            for c in case_rows:
                for audio_item in self._collect_case_audios(c.config):
                    pdid = audio_item.get('playback_device_id')
                    if pdid is not None:
                        pdid = self._normalize_int(pdid)
                        if pdid is not None:
                            playback_ids.add(pdid)
            playback_name_map = self._fetch_playback_names(list(playback_ids))

            frozen_cases = []
            for tc in task_cases:
                case = case_map.get(tc.test_case_id)
                if case is None:
                    continue
                # 参考参数内容内联（发布时从存储读出；路径仅留档 tracedFrom）
                reference_params_inline = self._inline_reference_params(case.reference_params)
                frozen_cases.append({
                    'caseId': case.id,
                    'name': case.name,
                    'description': case.description,
                    'config': copy.deepcopy(case.config) if case.config else {},
                    'algorithmType': case.algorithm_type,
                    'algorithmParams': copy.deepcopy(case.algorithm_params) if case.algorithm_params else None,
                    'referenceParams': reference_params_inline,
                    'referenceParamsSource': self._reference_params_paths(case.reference_params),
                    'tags': tag_map.get(case.id, []),
                    'group': group_map.get(case.group_id),
                    # 用例级执行路由快照（差异#2 收尾：device_type/device_id/lab_id）
                    'deviceType': tc.device_type,
                    'deviceId': tc.device_id,
                    'labId': tc.lab_id,
                })

            # ---- 设备/API 引用快照（含名称，详情渲染不再 join 现库） ----
            device_ids = [row[0] for row in (
                session.query(TaskDevice.device_id)
                .filter(TaskDevice.task_id == task.id)
                .all()
            ) if row[0] is not None]
            api_ids = [row[0] for row in (
                session.query(TaskAPI.api_id)
                .filter(TaskAPI.task_id == task.id)
                .all()
            ) if row[0] is not None]
            devices_snapshot = self._fetch_device_snapshots(list(dict.fromkeys(device_ids)))
            apis_snapshot = self._fetch_api_snapshots(list(dict.fromkeys(api_ids)))

            return {
                'schemaVersion': 2,
                'task': task_body,
                'cases': frozen_cases,
                'devices': devices_snapshot,
                'apis': apis_snapshot,
                'playbackDevices': [
                    {'id': pid, 'name': playback_name_map.get(pid)}
                    for pid in sorted(playback_ids)
                ],
            }
        finally:
            session.close()

    # ---- freeze_task_snapshot 辅助 ----

    @staticmethod
    def _normalize_int(value):
        """宽松 int 归一（None/''/非数值 → None）。"""
        if value in (None, ''):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _collect_case_audios(config):
        """从用例 config 提取音频项（rounds[].audios，对齐 shared.utils.testcase_helpers.collect_audios）。"""
        if not config:
            return []
        all_audios = []
        for round_item in config.get('rounds', []) or []:
            if isinstance(round_item, dict):
                round_audios = round_item.get('audios', [])
                if isinstance(round_audios, list):
                    all_audios.extend(a for a in round_audios if isinstance(a, dict))
        return all_audios

    @staticmethod
    def _case_matches_frozen(existing: TestCase, frozen: dict) -> bool:
        """源用例是否与冻结数据一致（可复用判定：任一字段被编辑 → 走影子还原）。"""
        # 冻结留档 [{roundNumber, path}]（camelCase）→ 列口径 [{round_number, reference_params_path}]
        frozen_ref_col = [
            {'round_number': entry.get('roundNumber'), 'reference_params_path': entry.get('path')}
            for entry in (frozen.get('referenceParamsSource') or [])
            if isinstance(entry, dict)
        ] or None
        return (
            existing.config == frozen.get('config')
            and (existing.algorithm_params or None) == (frozen.get('algorithmParams') or None)
            and existing.algorithm_type == frozen.get('algorithmType')
            and (existing.reference_params or None) == frozen_ref_col
        )

    @staticmethod
    def _reference_params_paths(reference_params_col):
        """reference_params 列 → 逐轮存储路径留档 [{roundNumber, path}]。"""
        if not isinstance(reference_params_col, list):
            return []
        traced = []
        for entry in reference_params_col:
            if isinstance(entry, dict) and entry.get('reference_params_path'):
                traced.append({
                    'roundNumber': entry.get('round_number'),
                    'path': entry.get('reference_params_path'),
                })
        return traced

    def _inline_reference_params(self, reference_params_col):
        """参考参数内容内联：按轮从存储读出（B1 导入导出口径：可独立还原）。

        读取失败的轮次保留路径（content 为空列表），不中断冻结——
        详情/执行回退路径留档仍在。
        """
        if not isinstance(reference_params_col, list):
            return []
        from shared.infrastructure.storage import storage_load_bytes
        from shared.utils.data_transfer import parse_storage_path

        inlined = []
        for entry in reference_params_col or []:
            if not isinstance(entry, dict):
                continue
            path = entry.get('reference_params_path')
            round_number = entry.get('round_number')
            content = []
            if path:
                try:
                    raw = storage_load_bytes(path)
                    loaded = json.loads(raw.decode('utf-8'))
                    if isinstance(loaded, list):
                        content = loaded
                except Exception:
                    logger.warning('参考参数文件读取失败（冻结保留路径）: %s', path, exc_info=True)
            inlined.append({
                'roundNumber': round_number,
                'referenceParams': content,
                'path': path,
            })
        return inlined

    @staticmethod
    def _fetch_playback_names(playback_ids):
        """播放设备名称映射（gRPC PlaybackConfigService；失败返回空映射仅告警）。"""
        if not playback_ids:
            return {}
        name_map = {}
        try:
            from shared.clients.grpc_clients import get_playback_config_service_stub
            from shared.proto import device_service_pb2 as e2e_pb
            from shared.utils.grpc_json import loads as _loads
            stub = get_playback_config_service_stub()
            for pid in playback_ids:
                try:
                    resp = stub.GetPlaybackDevice(e2e_pb.GetPlaybackDeviceRequest(device_id=pid))
                    if resp.success and resp.data:
                        item = _loads(resp.data, {}) or {}
                        name_map[pid] = item.get('name')
                except Exception:
                    logger.warning('GetPlaybackDevice 查询失败 (id=%s)', pid, exc_info=True)
        except Exception:
            logger.warning('播放设备名称批量查询失败', exc_info=True)
        return name_map

    @staticmethod
    def _fetch_device_snapshots(device_ids):
        """被测设备引用快照（gRPC DeviceConfigService.GetDeviceStatuses；失败降级仅 ID）。"""
        items = [{'id': did, 'name': None} for did in device_ids]
        if not device_ids:
            return items
        try:
            from task_service.infrastructure.acl.device_acl_repository import device_acl_repository
            fetched = device_acl_repository.get_device_statuses(device_ids)
            name_by_id = {item.get('id'): item.get('name') for item in fetched or []}
            return [{'id': did, 'name': name_by_id.get(did)} for did in device_ids]
        except Exception:
            logger.warning('设备名称批量查询失败（快照降级仅 ID）', exc_info=True)
            return items

    @staticmethod
    def _fetch_api_snapshots(api_ids):
        """API 引用快照（gRPC APITestService.GetAPIConfig；失败降级仅 ID）。"""
        items = [{'id': aid, 'name': None} for aid in api_ids]
        if not api_ids:
            return items
        try:
            from task_service.infrastructure.acl.report_acl_repository import api_test_acl_repository
            name_map = api_test_acl_repository.fetch_api_names(api_ids)
            return [{'id': aid, 'name': name_map.get(aid)} for aid in api_ids]
        except Exception:
            logger.warning('API 名称批量查询失败（快照降级仅 ID）', exc_info=True)
            return items

    # ==================== 冻结用例还原（执行链路，INT-303）====================

    def restore_frozen_cases(self, frozen_cases, case_devices) -> list:
        """按冻结数据还原真实 TestCase 行（执行入口用）。

        已存在同 ID 行且（config/algorithm_params/algorithm_type/reference_params
        路径）与冻结数据一致时直接复用；源用例缺失或任一不一致时以新 UUID
        重建只读影子用例（不回写源用例，配置内容以冻结数据为准）。
        设备路由按快照 caseDevices 重映射到新用例 ID。

        Returns:
            [(new_case_id, device_type, device_id, lab_id)]，顺序与 frozen_cases 一致。
        """
        session = get_db_session()
        restored = []
        try:
            device_map = {
                str(item.get('case_id')): item
                for item in (case_devices or [])
                if item.get('case_id') is not None
            }
            for frozen in frozen_cases or []:
                old_id = frozen.get('caseId')
                if old_id is None:
                    continue
                existing = session.get(TestCase, old_id)
                if existing is not None and not existing.deleted and self._case_matches_frozen(existing, frozen):
                    new_id = old_id
                else:
                    new_id = str(uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f'int303-published-task-frozen-case:{old_id}:'
                        f'{json.dumps(frozen.get("config") or {}, ensure_ascii=False, sort_keys=True, default=str)}'
                        f':{frozen.get("name") or ""}',
                    ))
                    probe = session.get(TestCase, new_id)
                    if probe is None:
                        session.add(TestCase(
                            id=new_id,
                            name=frozen.get('name') or str(old_id),
                            description=frozen.get('description'),
                            config=copy.deepcopy(frozen.get('config') or {}),
                            algorithm_params=copy.deepcopy(frozen.get('algorithmParams') or None),
                            reference_params=self._frozen_reference_params_column(frozen),
                            algorithm_type=frozen.get('algorithmType'),
                        ))
                        session.flush()
                        for tag_name in frozen.get('tags') or []:
                            tag = session.query(Tag).filter_by(name=tag_name).first()
                            if not tag:
                                tag = Tag(name=tag_name, created_at=datetime.now(_UTC_PLUS_8),
                                          updated_at=datetime.now(_UTC_PLUS_8))
                                session.add(tag)
                                session.flush()
                            session.add(TestCaseTag(
                                test_case_id=new_id, tag_id=tag.id,
                                created_at=datetime.now(_UTC_PLUS_8),
                            ))
                        session.flush()
                dev = device_map.get(str(old_id), {})
                restored.append((
                    new_id,
                    dev.get('device_type'),
                    str(dev['device_id']) if dev.get('device_id') is not None else None,
                    dev.get('lab_id'),
                ))
            session.commit()
            return restored
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _frozen_reference_params_column(frozen):
        """冻结参考参数 → TestCase.reference_params 列形态（路径优先，内联内容兜底落文件）。

        还原策略：优先沿用留档路径（源文件通常仍在）；路径不可用时把内联内容
        写入新存储 key（影子用例自持），保证参考文本不因源用例删除而丢失。
        """
        from shared.infrastructure.storage import storage_save_bytes, storage_load_bytes
        from shared.utils.data_transfer import parse_storage_path

        col = []
        for entry in frozen.get('referenceParams') or []:
            if not isinstance(entry, dict):
                continue
            round_number = entry.get('roundNumber')
            path = entry.get('path')
            content = entry.get('referenceParams') or []
            usable_path = None
            if path:
                try:
                    storage_load_bytes(path)
                    usable_path = path
                except Exception:
                    usable_path = None
            if usable_path is None and content:
                try:
                    old_category, old_key = parse_storage_path(path or '')
                    key = f"{frozen.get('caseId')}/int303_frozen_round_{round_number}.json"
                    usable_path = storage_save_bytes(
                        json.dumps(content, ensure_ascii=False, indent=2).encode('utf-8'),
                        'ref_params', key, content_type='application/json')
                except Exception:
                    logger.warning('冻结参考参数内容落盘失败（round=%s）', round_number, exc_info=True)
            if usable_path:
                col.append({'round_number': round_number, 'reference_params_path': usable_path})
        return col or None

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
        """冻结来源任务关联的真实报告（报告管理/历史页面产物）为不可变快照。

        INT-258 快照语义：引用 + 冻结双轨——
        - sourceReportId 引用 test_reports（提供跳转报告页入口）；
        - 冻结体覆盖报告 7 表（test_reports / report_summaries / report_summary_meta /
          report_raw_data / report_cases / report_metric_stats / report_comparison_matrix）
          中报告页渲染所需字段，发布后不受源报告修改/删除影响。

        无报告（含已软删除报告）时返回 None；快照结构为 camelCase 契约（schemaVersion=2）。
        """
        if not source_task_id:
            return None
        session = get_db_session()
        try:
            report = (
                session.query(Report)
                .filter(
                    Report.task_id == source_task_id,
                    Report.type == 'task',
                    Report.deleted.is_(False),
                )
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
            raw_data = (
                session.query(ReportRawData).filter_by(report_id=report.id).first()
            )
            cases = (
                session.query(ReportCase)
                .filter(ReportCase.report_id == report.id)
                .order_by(ReportCase.id.asc())
                .all()
            )

            # Report.analysis 兼容双形态：纯文本结论 或 JSON config 序列化串
            # （name/description/conclusion 存于 config，报告页 _aggregate_to_dict
            # 按此解析；冻结口径与报告页展示口径对齐，INT-258）
            config = {}
            if isinstance(report.analysis, dict):
                config = report.analysis
            elif isinstance(report.analysis, str):
                try:
                    loaded = json.loads(report.analysis)
                    config = loaded if isinstance(loaded, dict) else {}
                except Exception:
                    config = {}
            conclusion_text = ''
            if config:
                conclusion_text = str(config.get('conclusion') or config.get('analysis') or '')
            else:
                conclusion_text = report.analysis or ''
            config_name = config.get('name') if isinstance(config, dict) else None
            config_description = config.get('description') if isinstance(config, dict) else None

            return {
                'schemaVersion': 2,
                # 引用轨：关联 test_reports（版本详情提供跳转报告页入口）
                'sourceReportId': report.id,
                # 兼容字段（V9.7.10 冻结契约遗留，语义同 sourceReportId）
                'reportId': report.id,
                'name': report.name or config_name or '',
                'type': report.type,
                'status': report.status,
                'description': config_description or report.description or '',
                'analysis': conclusion_text,
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
                    'allCaseTags': self._to_json(summary_meta.all_case_tags) if summary_meta else [],
                    'allMetrics': self._to_json(summary_meta.all_metrics) if summary_meta else [],
                    'dimensionValues': self._to_json(summary_meta.dimension_values) if summary_meta else [],
                    'devices': self._to_json(summary_meta.devices) if summary_meta else [],
                    'apis': self._to_json(summary_meta.apis) if summary_meta else [],
                    'resources': self._to_json(summary_meta.resources) if summary_meta else [],
                    'resourceHeaders': self._to_json(summary_meta.resource_headers) if summary_meta else [],
                    'fieldMappings': self._to_json_obj(summary_meta.field_mappings) if summary_meta else {},
                    'deviceStats': self._to_json(metric_stats.device_stats) if metric_stats else [],
                    'apiStats': self._to_json(metric_stats.api_stats) if metric_stats else [],
                    # _to_json 保留原类型（历史版本为 dict / 新版本为 JSON 数组）
                    'metricData': self._to_json(metric_stats.metric_data) if metric_stats else [],
                    'tagMetricData': self._to_json(metric_stats.tag_metric_data) if metric_stats else [],
                    'tagCategoryMetricData': self._to_json(metric_stats.tag_category_metric_data) if metric_stats else [],
                    'caseTypeStats': self._to_json(metric_stats.case_type_stats) if metric_stats else [],
                    'rawData': self._to_json(raw_data.raw_data) if raw_data else [],
                },
                'cases': [
                    {
                        'id': c.id,
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
        snapshot_config: dict,
        case_ids,
        restored_cases=None,
    ) -> int:
        """按快照创建新的日常任务（执行已发布任务的复用链路）。

        用例级 device_type/device_id 从快照 caseDevices 还原
        （差异#2 收尾：执行路由唯一依据，task.type 已废弃）。

        INT-303：restored_cases 非空时（冻结用例还原模式），用例路由按还原
        结果 [(case_id, device_type, device_id, lab_id)] 写入——保证源用例
        被删/改名后仍按冻结配置执行；case_ids 参数此时仅用于 total_cases 计数。

        Returns:
            新任务 ID。
        """
        now = datetime.now(_UTC_PLUS_8)
        session = get_db_session()
        try:
            new_task = Task(
                name=name,
                description=description,
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

            if restored_cases:
                for case_id, device_type, device_id, lab_id in restored_cases:
                    session.add(TaskCase(
                        task_id=task_id,
                        test_case_id=case_id,
                        status=TaskCaseStatus.PENDING,
                        execution_status=ExecutionStatus.PENDING,
                        evaluation_status=EvaluationStatus.PENDING,
                        device_type=device_type,
                        device_id=device_id,
                        lab_id=lab_id,
                        created_at=now,
                    ))
            else:
                device_map = {
                    str(item.get('case_id')): item
                    for item in (snapshot_config.get('caseDevices') or [])
                    if item.get('case_id') is not None
                }
                for case_id in case_ids:
                    dev = device_map.get(str(case_id), {})
                    session.add(TaskCase(
                        task_id=task_id,
                        test_case_id=case_id,
                        status=TaskCaseStatus.PENDING,
                        execution_status=ExecutionStatus.PENDING,
                        evaluation_status=EvaluationStatus.PENDING,
                        device_type=dev.get('device_type') or None,
                        device_id=str(dev['device_id']) if dev.get('device_id') is not None else None,
                        lab_id=dev.get('lab_id') or None,
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
