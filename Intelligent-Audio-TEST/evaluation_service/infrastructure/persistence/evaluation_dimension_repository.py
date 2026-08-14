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

from shared.models.database import get_db_session
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
    """TestResultDimension PO → DimensionScore 实体"""
    return DimensionScore(
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
        """按 ID 加载维度聚合根"""
        session = get_db_session()
        po = session.get(DimensionPO, dim_id)
        if po is None or po.deleted:
            return None
        return _dimension_po_to_entity(po)

    def list_dimensions_by_ids(self, dim_ids: List[int]) -> List[EvaluationDimension]:
        """批量加载维度聚合根（仅未删除）"""
        session = get_db_session()
        if not dim_ids:
            return []
        pos = session.query(DimensionPO).filter(
            DimensionPO.id.in_(dim_ids),
            DimensionPO.deleted == False,  # noqa: E712
        ).all()
        return [_dimension_po_to_entity(po) for po in pos]

    def list_active_dimensions_by_algorithm(
        self, algorithm_type: str
    ) -> List[EvaluationDimension]:
        """按算法类型列出可用维度（未删除 + 已启用 + API 在线）"""
        session = get_db_session()
        pos = session.query(DimensionPO).filter(
            DimensionPO.task_type_code == algorithm_type,
            DimensionPO.deleted == False,  # noqa: E712
            DimensionPO.status == True,  # noqa: E712
            DimensionPO.api_status == 'online',
        ).all()
        return [_dimension_po_to_entity(po) for po in pos]

    def list_active_dimensions_by_ids(
        self, dim_ids: List[int]
    ) -> List[EvaluationDimension]:
        """按 ID 列表批量加载可用维度（未删除 + 已启用）。

        供 dimension_loader 在评估时按 unique_dimension_ids 加载维度用。
        """
        session = get_db_session()
        if not dim_ids:
            return []
        pos = session.query(DimensionPO).filter(
            DimensionPO.id.in_(dim_ids),
            DimensionPO.deleted == False,  # noqa: E712
            DimensionPO.status == True,  # noqa: E712
        ).all()
        return [_dimension_po_to_entity(po) for po in pos]

    def list_all_endpoint_dimensions(self) -> List[EvaluationDimension]:
        """加载全部维度（含已禁用，不含已删除），用于端点 Worker 初始化预加载。

        供 worker_management._load_all_endpoint_configs 使用——它需要扫描全部
        维度的 api_endpoints/api_url 配置以预创建端点 Worker。
        """
        session = get_db_session()
        pos = session.query(DimensionPO).filter(
            DimensionPO.deleted == False,  # noqa: E712
        ).all()
        return [_dimension_po_to_entity(po) for po in pos]

    def get_dimension_basics_by_ids(
        self, dim_ids: List[int]
    ) -> List[dict]:
        """按 dim_id 列表批量查询维度基础信息（id/name/type/description）。
        返回 dict 列表，供 gRPC servicer 直接序列化。"""
        session = get_db_session()
        dims = session.query(DimensionPO).filter(DimensionPO.id.in_(dim_ids)).all()
        return [
            {
                'id': d.id,
                'name': d.name,
                'type': d.type,
                'description': d.description,
            }
            for d in dims
        ]

    # ========== DimensionScore 读 ==========

    def list_scores_by_result_id(
        self, result_id: int
    ) -> List[DimensionScore]:
        """读取某 TestResult 的所有维度评分"""
        session = get_db_session()
        pos = session.query(TestResultDimensionPO).filter(
            TestResultDimensionPO.test_result_id == result_id,
        ).all()
        return [_trd_po_to_entity(po) for po in pos]

    def list_pending_scores(self, result_id: int) -> List[DimensionScore]:
        """读取待评估的维度评分"""
        session = get_db_session()
        pos = session.query(TestResultDimensionPO).filter(
            TestResultDimensionPO.test_result_id == result_id,
            TestResultDimensionPO.evaluation_status == EvaluationStatus.PENDING,
        ).all()
        return [_trd_po_to_entity(po) for po in pos]

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

    def get_dimension_results_with_names_by_result_ids(
        self, result_ids: List[int]
    ) -> List[dict]:
        """按 result_id 列表批量查询维度评估结果（含 dimension_name）。
        返回 dict 列表，供 gRPC servicer 直接序列化。"""
        session = get_db_session()
        rows = session.query(
            TestResultDimensionPO, DimensionPO.name
        ).outerjoin(
            DimensionPO, TestResultDimensionPO.dimension_id == DimensionPO.id
        ).filter(
            TestResultDimensionPO.test_result_id.in_(result_ids)
        ).all()

        items = []
        for dim, dim_name in rows:
            items.append({
                'id': dim.id,
                'test_result_id': dim.test_result_id,
                'dimension_id': dim.dimension_id,
                'dimension_name': dim_name,
                'dimension_value': dim.dimension_value,
                'score': dim.score,
                'status': dim.status,
                'evaluation_status': dim.evaluation_status,
                'error_message': dim.error_message,
                'round_number': getattr(dim, 'round_number', None),
            })
        return items

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


# 模块级单例（与 evaluation_repository.py 风格一致）
evaluation_dimension_repository = EvaluationDimensionRepository()
