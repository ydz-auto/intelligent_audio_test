# -*- coding: utf-8 -*-
"""评估策略仓储 — EvaluationStrategyRepository（INT-590）

评估策略实体归 task_service（用例域）：引用/删保护/列表计数全部本地化。
参照 testcase_repository 的事务控制口径（commit/rollback 委托 get_db_session）。
"""
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from shared.models.database import get_db_session
from task_service.domain.repositories.evaluation_strategy_repository import (
    EvaluationStrategyRepositoryABC,
)
from task_service.infrastructure.persistence.models import (
    EvaluationStrategy, TestCase,
)


class EvaluationStrategyRepository(EvaluationStrategyRepositoryABC):
    """评估策略仓储实现（组合查询 Mixin 风格）"""

    # ========== 写操作 ==========

    def create_strategy(self, data: dict) -> EvaluationStrategy:
        """创建评估策略（含 flush，未 commit）。

        data 需含 id/name/config（description/algorithm_type/enabled 可选）。
        created_by_user_id（INT-590）：从 x-user-id 上下文取 JWT 操作人。
        """
        from shared.infrastructure.user_context import get_current_user_id
        session = get_db_session()
        strategy = EvaluationStrategy(
            id=data.get('id'),
            name=data.get('name'),
            description=data.get('description'),
            algorithm_type=data.get('algorithm_type'),
            enabled=bool(data.get('enabled', True)),
            config=data.get('config') or {},
            created_by_user_id=get_current_user_id(),
        )
        session.add(strategy)
        session.flush()
        return strategy

    def update_strategy_attrs(self, strategy: EvaluationStrategy, data: dict) -> None:
        """更新评估策略属性（含 flush，未 commit）。

        字段粒度更新：name/description/algorithm_type/enabled/config 传入才更新；
        name 唯一冲突由应用层先 get_strategy_by_name 校验。
        """
        from shared.infrastructure.user_context import get_current_user_id
        session = get_db_session()
        if data.get('name') is not None:
            strategy.name = data['name']
        if data.get('description') is not None:
            strategy.description = data['description']
        if data.get('algorithm_type') is not None:
            strategy.algorithm_type = data['algorithm_type']
        if data.get('enabled') is not None:
            strategy.enabled = bool(data['enabled'])
        if data.get('config') is not None:
            strategy.config = data['config']
        strategy.updated_by_user_id = get_current_user_id()
        session.flush()

    def soft_delete_strategy(self, strategy_id: str) -> bool:
        """软删除评估策略（未 commit；记录删除人，INT-590）。"""
        from shared.infrastructure.user_context import get_current_user_id
        session = get_db_session()
        strategy = session.query(EvaluationStrategy).filter_by(
            id=strategy_id, deleted=False).first()
        if not strategy:
            return False
        from shared.utils.query_utils import now_cst
        strategy.deleted = True
        strategy.deleted_at = now_cst()
        strategy.deleted_by_user_id = get_current_user_id()
        strategy.updated_at = now_cst()
        session.flush()
        return True

    # ========== 读操作 ==========

    def get_strategy(self, strategy_id: str, include_deleted: bool = False) -> Optional[EvaluationStrategy]:
        """按 ID 查询单个评估策略。"""
        session = get_db_session()
        query = session.query(EvaluationStrategy).filter_by(id=strategy_id)
        if not include_deleted:
            query = query.filter(EvaluationStrategy.deleted == False)  # noqa: E712
        return query.first()

    def get_strategy_by_name(self, name: str) -> Optional[EvaluationStrategy]:
        """按名称查询未删除评估策略（重名校验用）。"""
        session = get_db_session()
        return session.query(EvaluationStrategy).filter_by(
            name=name, deleted=False).first()

    def list_strategies(self, page: int = 1, per_page: int = 10,
                        keyword: Optional[str] = None,
                        algorithm_type: Optional[str] = None,
                        enabled: Optional[bool] = None) -> dict:
        """分页查询未删除评估策略（含 referenced_case_count）。

        引用计数经关联子查询统计 test_cases.strategy_id 引用（未删除用例），
        列表展示与删除保护同源。
        """
        session = get_db_session()
        query = session.query(EvaluationStrategy).filter(
            EvaluationStrategy.deleted == False)  # noqa: E712
        if keyword:
            query = query.filter(EvaluationStrategy.name.ilike(f'%{keyword}%'))
        if algorithm_type:
            query = query.filter(EvaluationStrategy.algorithm_type == algorithm_type)
        if enabled is not None:
            query = query.filter(EvaluationStrategy.enabled == enabled)

        total = query.count()
        query = query.order_by(EvaluationStrategy.updated_at.desc())
        items = query.offset((page - 1) * per_page).limit(per_page).all()

        # 批量引用计数（一次查询，避免 N+1）
        strategy_ids = [s.id for s in items]
        ref_counts: Dict[str, int] = {}
        if strategy_ids:
            rows = (
                session.query(TestCase.strategy_id, func.count())
                .filter(
                    TestCase.strategy_id.in_(strategy_ids),
                    TestCase.deleted == False,  # noqa: E712
                )
                .group_by(TestCase.strategy_id)
                .all()
            )
            ref_counts = {sid: cnt for sid, cnt in rows}

        data = []
        for s in items:
            item = self._serialize(s)
            item['referenced_case_count'] = ref_counts.get(s.id, 0)
            data.append(item)

        pages = (total + per_page - 1) // per_page if per_page > 0 else 0
        return {
            'items': data,
            'total': total,
            'page': page,
            'per_page': per_page,
            'pages': pages,
        }

    def count_referenced_cases(self, strategy_id: str) -> int:
        """统计引用该策略的未删除用例数（删保护 + 列表计数同源）。"""
        session = get_db_session()
        return session.query(TestCase).filter(
            TestCase.strategy_id == strategy_id,
            TestCase.deleted == False,  # noqa: E712
        ).count()

    # ========== 序列化 ==========

    @staticmethod
    def _serialize(strategy: EvaluationStrategy) -> dict:
        """评估策略 PO → API DTO（snake_case）。"""
        return {
            'id': strategy.id,
            'name': strategy.name,
            'description': strategy.description,
            'algorithm_type': strategy.algorithm_type,
            'enabled': bool(strategy.enabled),
            'config': strategy.config or {},
            'created_by_user_id': strategy.created_by_user_id,
            'updated_by_user_id': strategy.updated_by_user_id,
            'created_at': strategy.created_at.isoformat() if strategy.created_at else None,
            'updated_at': strategy.updated_at.isoformat() if strategy.updated_at else None,
        }

    # ========== 事务控制 ==========

    def commit(self):
        """提交事务。"""
        get_db_session().commit()

    def rollback(self):
        """回滚事务。"""
        get_db_session().rollback()

    def flush(self):
        """flush session。"""
        get_db_session().flush()


# 模块级单例，供 application 层导入
evaluation_strategy_repository = EvaluationStrategyRepository()
