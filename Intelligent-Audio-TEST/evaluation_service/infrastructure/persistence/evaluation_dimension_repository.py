# -*- coding: utf-8 -*-
"""评估维度领域仓储 — 返回领域实体（Entity），做 PO ↔ Entity 转换

与 evaluation_repository.py 的区别：
- evaluation_repository.py: 旧式仓储，返回 PO（Category/Dimension ORM 对象），供 CRUD handler 用
- evaluation_dimension_repository.py（本文件）: 新式 DDD 仓储，返回领域实体（EvaluationDimension），
  供领域服务用，隔离领域层与 ORM

PO ↔ Entity 转换规则：
- Dimension PO → EvaluationDimension 聚合根（含 DimensionSnapshot + ScoringRule）
- TestResultDimension PO → DimensionScore 实体
"""
from typing import List, Optional

from shared.infrastructure.raw_payload_store import (
    KIND_REQUEST,
    KIND_RESPONSE,
    raw_payload_store,
)
from shared.models.database import end_read_transaction, get_db_session
from shared.utils.status_constants import EvaluationStatus

from evaluation_service.infrastructure.persistence.orm_models import (
    Category as CategoryPO,
    Dimension as DimensionPO,
    TestResultDimension as TestResultDimensionPO,
)
from evaluation_service.domain.repositories.evaluation_dimension_repository import (
    EvaluationDimensionRepository as EvaluationDimensionRepositoryABC,
)
from evaluation_service.domain.entities import (
    EvaluationDimension,
    DimensionScore,
    DimensionSnapshot,
    ScoringRule,
    RoundResult,
)


def _dimension_po_to_snapshot(po: DimensionPO) -> DimensionSnapshot:
    """Dimension PO → DimensionSnapshot 值对象"""
    return DimensionSnapshot(
        id=po.id,
        name=po.name,
        algorithm_type=po.task_type_code or '',  # task_type_code 是 API 调用时的算法类型
        task_type_code=po.task_type_code,
        dimension_type=po.dimension_type or 'main',
        parent_dimension_id=po.parent_dimension_id,
        category_id=po.category_id,
        result_type=po.result_type,
        result_min=po.result_min,
        result_max=po.result_max,
        decimal_places=po.decimal_places,
        weight=po.weight or 1,
        score_unit=po.score_unit or '',
        statistic_method=po.statistic_method or 'average',
        rule=ScoringRule.from_dict(po.rule if isinstance(po.rule, dict) else {}),
        api_endpoints=po.api_endpoints or [],
        api_settings=po.api_settings,
        api_url=po.api_url,
        api_status=po.api_status or 'online',
    )


def _dimension_po_to_entity(po: DimensionPO) -> EvaluationDimension:
    """Dimension PO → EvaluationDimension 聚合根"""
    return EvaluationDimension(
        id=po.id,
        name=po.name,
        algorithm_type=po.task_type_code or '',
        snapshot=_dimension_po_to_snapshot(po),
        scores=[],
    )


def _trd_po_to_entity(po: TestResultDimensionPO) -> DimensionScore:
    """TestResultDimension PO → DimensionScore 实体（含持久化主键 id）"""
    return DimensionScore(
        id=po.id,
        test_result_id=po.test_result_id,
        dimension_id=po.dimension_id,
        algorithm_type=po.algorithm_type or '',
        round_number=po.round_number,
        dimension_value=po.dimension_value,
        score=po.score,
        status=po.status,
        evaluation_status=po.evaluation_status or EvaluationStatus.PENDING,
        error_message=po.error_message,
    )


def _score_entity_to_po_fields(score: DimensionScore) -> dict:
    """DimensionScore 实体 → TestResultDimension PO 字段 dict（用于 update）"""
    return {
        'dimension_value': score.dimension_value,
        'score': score.score,
        'status': score.status,
        'evaluation_status': score.evaluation_status,
        'error_message': score.error_message,
    }


class EvaluationDimensionRepository(EvaluationDimensionRepositoryABC):
    """评估维度领域仓储

    提供 PO ↔ Entity 转换，向上层（domain/services）返回领域实体。
    领域服务通过本仓储访问数据，不直接接触 ORM。
    """

    # ========== Dimension 读 ==========

    def get_dimension_by_id(self, dim_id: int) -> Optional[EvaluationDimension]:
        """按 ID 加载维度聚合根（INT-1691：返回前结束只读事务）"""
        session = get_db_session()
        try:
            po = session.get(DimensionPO, dim_id)
            if po is None or po.deleted:
                return None
            return _dimension_po_to_entity(po)
        finally:
            end_read_transaction()

    def list_dimensions_by_ids(self, dim_ids: List[int]) -> List[EvaluationDimension]:
        """批量加载维度聚合根（仅未删除；INT-1691：返回前结束只读事务）"""
        session = get_db_session()
        try:
            if not dim_ids:
                return []
            pos = session.query(DimensionPO).filter(
                DimensionPO.id.in_(dim_ids),
                DimensionPO.deleted == False,  # noqa: E712
            ).all()
            return [_dimension_po_to_entity(po) for po in pos]
        finally:
            end_read_transaction()

    def list_active_dimensions_by_algorithm(
        self, algorithm_type: str
    ) -> List[EvaluationDimension]:
        """按算法类型列出可用维度（未删除 + 已启用 + API 在线）"""
        session = get_db_session()
        try:
            pos = session.query(DimensionPO).filter(
                DimensionPO.task_type_code == algorithm_type,
                DimensionPO.deleted == False,  # noqa: E712
                DimensionPO.status == True,  # noqa: E712
                DimensionPO.api_status == 'online',
            ).all()
            return [_dimension_po_to_entity(po) for po in pos]
        finally:
            end_read_transaction()

    def list_active_dimensions_by_ids(
        self, dim_ids: List[int]
    ) -> List[EvaluationDimension]:
        """按 ID 列表批量加载可用维度（未删除 + 已启用）。

        供 dimension_loader 在评估时按 unique_dimension_ids 加载维度用。
        INT-1691：评估链路跑在 EndpointWorker / 线程池等长驻线程上，这些线程
        没有请求级 scope，多轮评估共用同一线程级 session —— 读完必须结束事务，
        否则整段评估期间一直挂着 dimensions 的 ACCESS SHARE。
        """
        session = get_db_session()
        try:
            if not dim_ids:
                return []
            pos = session.query(DimensionPO).filter(
                DimensionPO.id.in_(dim_ids),
                DimensionPO.deleted == False,  # noqa: E712
                DimensionPO.status == True,  # noqa: E712
            ).all()
            return [_dimension_po_to_entity(po) for po in pos]
        finally:
            end_read_transaction()

    def list_all_endpoint_dimensions(self) -> List[EvaluationDimension]:
        """加载全部维度（含已禁用，不含已删除），用于端点 Worker 初始化预加载。

        供 worker_management._load_all_endpoint_configs 使用——它需要扫描全部
        维度的 api_endpoints/api_url 配置以预创建端点 Worker。
        INT-1691：本方法在 lifespan 与配置热更新订阅线程（DimensionConfigSub）
        上调用，订阅线程长驻且每次维度变更都会再读一次 —— 不结束事务会形成
        「同一事务里反复 SELECT dimensions」的空事务（事故采样形态）。
        """
        session = get_db_session()
        try:
            pos = session.query(DimensionPO).filter(
                DimensionPO.deleted == False,  # noqa: E712
            ).all()
            return [_dimension_po_to_entity(po) for po in pos]
        finally:
            end_read_transaction()

    def get_dimension_basics_by_ids(
        self, dim_ids: List[int]
    ) -> List[dict]:
        """按 dim_id 列表批量查询维度信息（id/name/type/description + 报告指标口径字段）。

        返回 dict 列表，供 gRPC servicer 直接序列化。

        INT-1571：除基础信息外一并返回 statistic_method / score_unit / agg_denominator /
        sort_order / dimension_type / parent_dimension_id 等口径字段——报告侧需要按
        ID 还原“评估时使用的维度”列头与聚合口径，而这些维度可能已停用/软删。
        本查询按 ID 解析引用，**不过滤 status/deleted**（与 GetDimension 的 404 语义不同），
        否则历史任务的报告会丢掉全部指标。
        """
        session = get_db_session()
        try:
            dims = session.query(DimensionPO).filter(DimensionPO.id.in_(dim_ids)).all()
            return [
                {
                    'id': d.id,
                    'name': d.name,
                    'type': d.type,
                    'description': d.description,
                    'dimension_type': d.dimension_type,
                    'parent_dimension_id': d.parent_dimension_id,
                    'category_id': d.category_id,
                    'task_type_code': d.task_type_code,
                    'statistic_method': d.statistic_method,
                    'score_unit': d.score_unit,
                    'decimal_places': d.decimal_places,
                    'agg_denominator': d.agg_denominator,
                    'sort_order': d.sort_order,
                    'weight': d.weight,
                    'exclude_rounds': d.exclude_rounds,
                    'status': d.status,
                    'deleted': d.deleted,
                }
                for d in dims
            ]
        finally:
            end_read_transaction()

    # ========== DimensionScore 读 ==========

    def list_scores_by_result_id(
        self, result_id: int
    ) -> List[DimensionScore]:
        """读取某 TestResult 的所有维度评分（INT-1691：返回前结束只读事务）"""
        session = get_db_session()
        try:
            pos = session.query(TestResultDimensionPO).filter(
                TestResultDimensionPO.test_result_id == result_id,
            ).all()
            return [_trd_po_to_entity(po) for po in pos]
        finally:
            end_read_transaction()

    def list_pending_scores(self, result_id: int) -> List[DimensionScore]:
        """读取待评估的维度评分（INT-1691：返回前结束只读事务）"""
        session = get_db_session()
        try:
            pos = session.query(TestResultDimensionPO).filter(
                TestResultDimensionPO.test_result_id == result_id,
                TestResultDimensionPO.evaluation_status == EvaluationStatus.PENDING,
            ).all()
            return [_trd_po_to_entity(po) for po in pos]
        finally:
            end_read_transaction()

    def find_score(
        self, result_id: int, dimension_id: int, round_number: Optional[int] = None
    ) -> Optional[DimensionScore]:
        """按 result_id + dimension_id + round_number 查找已存在的维度评分记录。

        round_number 为 None 时匹配 round_number IS NULL。
        INT-1691：返回实体（值已复制），返回前结束只读事务。
        """
        session = get_db_session()
        try:
            q = session.query(TestResultDimensionPO).filter(
                TestResultDimensionPO.test_result_id == result_id,
                TestResultDimensionPO.dimension_id == dimension_id,
            )
            if round_number is not None:
                q = q.filter(TestResultDimensionPO.round_number == round_number)
            else:
                q = q.filter(TestResultDimensionPO.round_number.is_(None))
            po = q.first()
            return _trd_po_to_entity(po) if po else None
        finally:
            end_read_transaction()

    # ========== DimensionScore 写 ==========

    def create_score(self, score: DimensionScore) -> int:
        """创建维度评分记录（含 flush，未 commit）。返回新 ID。"""
        session = get_db_session()
        po = TestResultDimensionPO(
            test_result_id=score.test_result_id,
            dimension_id=score.dimension_id,
            algorithm_type=score.algorithm_type,
            round_number=score.round_number,
            dimension_value=score.dimension_value,
            score=score.score,
            status=score.status,
            evaluation_status=score.evaluation_status,
            error_message=score.error_message,
        )
        session.add(po)
        session.flush()
        return po.id

    def create_score_with_commit(self, score: DimensionScore) -> Optional[int]:
        """创建维度评分记录并提交事务。

        含 flush + commit + 提交后验证。失败时 rollback 并返回 None。
        供 domain/services/dimension_result_recorder 在无需自管 session 的情况下使用。
        """
        session = get_db_session()
        try:
            po = TestResultDimensionPO(
                test_result_id=score.test_result_id,
                dimension_id=score.dimension_id,
                algorithm_type=score.algorithm_type,
                round_number=score.round_number,
                dimension_value=score.dimension_value,
                score=score.score,
                status=score.status,
                evaluation_status=score.evaluation_status,
                error_message=score.error_message,
            )
            session.add(po)
            session.flush()
            new_id = po.id
            session.commit()
            # 提交后验证
            verify = session.get(TestResultDimensionPO, new_id)
            if verify is None:
                return None
            return new_id
        except Exception:
            session.rollback()
            return None

    def update_score(self, score_id: int, score: DimensionScore) -> None:
        """更新维度评分（含 flush，未 commit）。"""
        session = get_db_session()
        session.query(TestResultDimensionPO).filter(
            TestResultDimensionPO.id == score_id,
        ).update(_score_entity_to_po_fields(score), synchronize_session=False)
        session.flush()

    def mark_score_status(
        self, score_id: int, evaluation_status: str, error_message: Optional[str] = None
    ) -> None:
        """快速更新评估状态（含 flush，未 commit）。"""
        session = get_db_session()
        update_fields = {'evaluation_status': evaluation_status}
        if error_message is not None:
            update_fields['error_message'] = error_message
        session.query(TestResultDimensionPO).filter(
            TestResultDimensionPO.id == score_id,
        ).update(update_fields, synchronize_session=False)
        session.flush()

    def reset_score_to_pending(self, score_id: int) -> None:
        """重置维度评分记录为 pending（含 commit）。

        清空 score/error_message 与原始报文的对象指针五列（两组），evaluation_status
        置为 pending，供重新评估复用。M1（INT-1813）起 JSON 两列已在库中删除，报文
        只存在于对象里，重置只需清指针。
        """
        session = get_db_session()
        # INT-1809（C2）：重评前把旧报文指针一并清掉——否则重评失败时行上会留着
        # 指向上一轮报文的陈旧指针（评分已是新的 / 报文还是旧的）。
        reset_fields = {
            'evaluation_status': EvaluationStatus.PENDING,
            'score': None,
            'error_message': None,
            'api_request_body_uri': None,
            'api_request_body_sha256': None,
            'api_request_body_bytes': None,
            'api_request_body_content_type': None,
            'api_request_body_created_at': None,
            'api_raw_response_uri': None,
            'api_raw_response_sha256': None,
            'api_raw_response_bytes': None,
            'api_raw_response_content_type': None,
            'api_raw_response_created_at': None,
        }
        # 仅重置 PO 上存在的列，避免列名不存在报错
        existing_cols = {c.name for c in TestResultDimensionPO.__table__.columns}
        safe_fields = {k: v for k, v in reset_fields.items() if k in existing_cols}
        session.query(TestResultDimensionPO).filter(
            TestResultDimensionPO.id == score_id,
        ).update(safe_fields, synchronize_session=False)
        session.commit()

    def mark_result_dimensions_completed(self, result_id: int) -> int:
        """将某 TestResult 的所有维度评分标记为 completed（用于无维度的兜底）。
        返回受影响行数。"""
        session = get_db_session()
        count = session.query(TestResultDimensionPO).filter(
            TestResultDimensionPO.test_result_id == result_id,
            TestResultDimensionPO.evaluation_status != EvaluationStatus.COMPLETED,
        ).update({'evaluation_status': EvaluationStatus.COMPLETED}, synchronize_session=False)
        session.flush()
        return count

    def delete_scores_by_result_id(self, result_id: int) -> int:
        """删除某 TestResult 的所有维度评分记录（重新评估前清理）。返回删除行数。"""
        session = get_db_session()
        count = session.query(TestResultDimensionPO).filter_by(
            test_result_id=result_id,
        ).delete()
        session.commit()
        return count

    def delete_failed_round_scores(self, result_id: int, dimension_ids, error_message: str = '') -> int:
        """删除某 TestResult 中指定维度的历史失败逐轮行（幽灵行，INT-364 对齐 V9.7.10 f02ba75e）。

        只删 round_number 非空且 evaluation_status='failed' 的行：
        - 整体行（round_number IS NULL）不删——由评估入口按
          (result, dim, round) 复用重置 pending；
        - 已通过的逐轮投影行（completed）不删——保留有效投影结果；
        - 仅限本次待重评维度（dimension_ids），其他维度的失败行不动。
        返回删除行数。
        """
        session = get_db_session()
        try:
            count = session.query(TestResultDimensionPO).filter(
                TestResultDimensionPO.test_result_id == result_id,
                TestResultDimensionPO.dimension_id.in_(set(dimension_ids)),
                TestResultDimensionPO.round_number.isnot(None),
                TestResultDimensionPO.evaluation_status == EvaluationStatus.FAILED,
            ).delete(synchronize_session=False)
            session.commit()
            return count
        except Exception:
            session.rollback()
            raise

    def mark_active_scores_failed_excluding_rounds(
        self, result_id: int, keep_round_numbers, error_message: str
    ) -> int:
        """将某 TestResult 中「不在本次重评提交范围」的非终态维度评分收口为 failed。

        INT-174：failed 型重评只重评失败/未完成 TRD，但被配置排除的轮次
        （evaluation.enabled=false、无整体口径维度）或过滤后无可评估维度的轮次，
        其遗留的非终态 TRD（重启崩溃残留等）永远不会被任何评估触达——统一收尾
        的全维终态门控因此拒绝收敛，用例/任务永久卡死。提交阶段收尾时把这些
        维度收口为 failed 终态（失败 TRD 本就是终态，不受影响）。

        Args:
            result_id: TestResult 主键
            keep_round_numbers: 保持不动的轮次集合（int 轮次 / None=整体口径）；
                None 表示不排除任何轮次（全部收口）
            error_message: 收口原因
        Returns:
            受影响行数
        """
        session = get_db_session()
        try:
            from sqlalchemy import or_
            from shared.utils.status_constants import ACTIVE_EVALUATION_STATUSES

            q = session.query(TestResultDimensionPO).filter(
                TestResultDimensionPO.test_result_id == result_id,
                TestResultDimensionPO.evaluation_status.in_(ACTIVE_EVALUATION_STATUSES),
            )
            if keep_round_numbers is not None:
                keep = set(keep_round_numbers)
                int_rounds = [r for r in keep if r is not None]
                in_scope_conds = []
                if int_rounds:
                    in_scope_conds.append(
                        TestResultDimensionPO.round_number.in_(int_rounds))
                if None in keep:
                    in_scope_conds.append(
                        TestResultDimensionPO.round_number.is_(None))
                if in_scope_conds:
                    q = q.filter(~or_(*in_scope_conds))
            count = q.update({
                'evaluation_status': EvaluationStatus.FAILED,
                'error_message': error_message,
            }, synchronize_session=False)
            session.commit()
            return count
        except Exception:
            session.rollback()
            raise

    def mark_round_active_scores_failed(
        self, result_id: int, round_number, dimension_ids=None, error_message: str = ''
    ) -> int:
        """将某 TestResult 指定轮次（可限定维度）的非终态评分收口为 failed。

        INT-174：评估入口请求的维度中被配置/启用状态排除（如维度已软删）或
        过滤后无可评估维度时，其遗留的非终态 TRD 不会被本次评估触达——统一
        收尾的全维终态门控因此拒绝收敛。提交/准备阶段就地收口。

        Args:
            result_id: TestResult 主键
            round_number: 轮次（None=整体口径，匹配 round_number IS NULL）
            dimension_ids: 限定维度 id 集合；None=该轮全部非终态 TRD
            error_message: 收口原因
        Returns:
            受影响行数
        """
        session = get_db_session()
        try:
            from shared.utils.status_constants import ACTIVE_EVALUATION_STATUSES

            q = session.query(TestResultDimensionPO).filter(
                TestResultDimensionPO.test_result_id == result_id,
                TestResultDimensionPO.evaluation_status.in_(ACTIVE_EVALUATION_STATUSES),
            )
            if round_number is None:
                q = q.filter(TestResultDimensionPO.round_number.is_(None))
            else:
                q = q.filter(TestResultDimensionPO.round_number == round_number)
            if dimension_ids is not None:
                q = q.filter(TestResultDimensionPO.dimension_id.in_(set(dimension_ids)))
            count = q.update({
                'evaluation_status': EvaluationStatus.FAILED,
                'error_message': error_message,
            }, synchronize_session=False)
            session.commit()
            return count
        except Exception:
            session.rollback()
            raise

    def get_dimension_results_with_names_by_result_ids(
        self, result_ids: List[int], include_body: bool = False
    ) -> List[dict]:
        """按 result_id 列表批量查询维度评估结果（含 dimension_name）。
        返回 dict 列表，供 gRPC servicer 直接序列化。

        Args:
            include_body: 是否携带 api_request_body / api_raw_response（LLM 复检
                INT-823 上下文聚合用；默认 False 保持既有 read model 调用载荷不变，
                避免对报告/导出等大批量消费方回传大 JSON 字段）。

        INT-1809（C2）：``include_body`` 的报文改**按指针读对象**（sha256 校验），
        不再读 JSON 列——M1 删列后这里也不会退化成「读已删列报错」。载荷形状不变
        （仍是解析后的 dict）。对象缺失 / 损坏 / 存储不可用 → 抛
        ``RawPayloadError``（调用方据此显式报错，绝不返回空上下文）。
        """
        session = get_db_session()
        # 只取需要的列：绝不 SELECT 两个 JSON 大字段（C2 起它们不该再有读者），
        # 报文按指针在会话外读对象（不在持连接期间做 OSS IO）。
        try:
            rows = session.query(
                TestResultDimensionPO.id,
                TestResultDimensionPO.test_result_id,
                TestResultDimensionPO.dimension_id,
                DimensionPO.name,
                TestResultDimensionPO.dimension_value,
                TestResultDimensionPO.score,
                TestResultDimensionPO.status,
                TestResultDimensionPO.evaluation_status,
                TestResultDimensionPO.error_message,
                TestResultDimensionPO.round_number,
                TestResultDimensionPO.api_request_body_uri,
                TestResultDimensionPO.api_request_body_sha256,
                TestResultDimensionPO.api_raw_response_uri,
                TestResultDimensionPO.api_raw_response_sha256,
            ).outerjoin(
                DimensionPO, TestResultDimensionPO.dimension_id == DimensionPO.id
            ).filter(
                TestResultDimensionPO.test_result_id.in_(result_ids)
            ).all()
        finally:
            end_read_transaction()

        items = []
        payload_refs = []
        for (dim_id, result_id, dimension_id, dim_name, dimension_value, score,
             status, evaluation_status, error_message, round_number,
             req_uri, req_sha, resp_uri, resp_sha) in rows:
            item = {
                'id': dim_id,
                'test_result_id': result_id,
                'dimension_id': dimension_id,
                'dimension_name': dim_name,
                'dimension_value': dimension_value,
                'score': score,
                'status': status,
                'evaluation_status': evaluation_status,
                'error_message': error_message,
                'round_number': round_number,
            }
            items.append(item)
            payload_refs.append((req_uri, req_sha, resp_uri, resp_sha))

        if include_body:
            for item, (req_uri, req_sha, resp_uri, resp_sha) in zip(items, payload_refs):
                item['api_request_body'] = self._load_raw_payload(
                    KIND_REQUEST, req_uri, req_sha)
                item['api_raw_response'] = self._load_raw_payload(
                    KIND_RESPONSE, resp_uri, resp_sha)
        return items

    @staticmethod
    def _load_raw_payload(kind: str, uri: Optional[str], sha256: Optional[str]):
        """按指针读原始报文对象；无指针（历史无报文行）→ None。

        sha256 不符 / 解压失败 / 对象不存在 / 存储不可用一律抛
        ``RawPayloadError``，由调用方显式报错（不返回空上下文）。
        """
        if not uri and not sha256:
            return None
        return raw_payload_store.load(kind, uri, sha256)

    def delete_scores_by_result_ids(self, result_ids: List[int]) -> int:
        """按 result_id 列表批量删除维度评估记录。返回删除行数。"""
        session = get_db_session()
        try:
            count = session.query(TestResultDimensionPO).filter(
                TestResultDimensionPO.test_result_id.in_(result_ids)
            ).delete(synchronize_session=False)
            session.commit()
            return count
        except Exception:
            session.rollback()
            raise

    def set_review_status_by_result_ids(
        self, result_ids: List[int], evaluation_status: str, status: str
    ) -> int:
        """人工复核评估状态改判（INT-340）：按 result_id 列表批量更新 TRD。

        evaluation_status 取 completed/failed（双状态口径）；
        status（维度评估结论）取 passed/failed（completed→passed，failed→failed）。
        仅更新已有维度行；无维度行（未评估结果）不创建。
        返回更新行数。
        """
        session = get_db_session()
        try:
            count = session.query(TestResultDimensionPO).filter(
                TestResultDimensionPO.test_result_id.in_(result_ids)
            ).update({
                'evaluation_status': evaluation_status,
                'status': status,
            }, synchronize_session=False)
            session.commit()
            return count
        except Exception:
            session.rollback()
            raise


# 模块级单例（与 evaluation_repository.py 风格一致）
evaluation_dimension_repository = EvaluationDimensionRepository()
