# -*- coding: utf-8 -*-
"""评估维度仓储 — 持久化访问 Category / Dimension 自有 PO，
algorithm_service 归属的 AlgorithmDimensionRelation / EvaluationDimensionParam /
ParamMapping 通过 gRPC 访问。

涉及模型：
- Category                       评估分类（本服务自有 PO）
- Dimension                      评估维度（本服务自有 PO）
- AlgorithmDimensionRelation     算法-维度关联（algorithm_service PO，走 gRPC）
- EvaluationDimensionParam       评估维度参数（algorithm_service PO，走 gRPC）
- ParamMapping                   参数映射（algorithm_service PO，走 gRPC）
"""
from typing import Any, Dict, List, Optional

from shared.models.database import get_db_session
from evaluation_service.infrastructure.persistence.orm_models import Category, Dimension
from evaluation_service.infrastructure.acl.algorithm_acl_repository import (
    algorithm_acl_repository,
)
from evaluation_service.domain.repositories.evaluation_repository_abc import (
    EvaluationRepositoryABC,
)
from shared.utils.query_utils import now_cst


def _now():
    return now_cst()


class EvaluationRepository(EvaluationRepositoryABC):
    """评估维度仓储

    自有 PO（Category/Dimension）通过本地 session 访问；
    algorithm_service PO 通过 algorithm_acl_repository gRPC 访问。
    """

    def __init__(self):
        self._algo = algorithm_acl_repository

    # ========== Category CRUD ==========

    def get_category_by_name(self, name: str) -> Optional[Category]:
        """按名称查询未删除的分类。"""
        session = get_db_session()
        return session.query(Category).filter_by(name=name, deleted=False).first()

    def get_category_by_id(self, cat_id: int) -> Optional[Category]:
        """按 ID 查询分类（含已删除）。"""
        session = get_db_session()
        return session.get(Category, cat_id)

    def create_category(self, data: Dict[str, Any]) -> Category:
        """创建分类（含 flush，未 commit）。"""
        session = get_db_session()
        cat = Category(
            name=data.get('name'),
            description=data.get('description'),
            icon=data.get('icon'),
        )
        session.add(cat)
        session.flush()
        return cat

    def list_categories(self) -> List[Category]:
        """查询所有未删除分类。"""
        session = get_db_session()
        return session.query(Category).filter(
            Category.deleted == False  # noqa: E712
        ).all()

    # ========== Dimension CRUD ==========

    def get_dimension(self, dim_id: int) -> Optional[Dimension]:
        """按 ID 查询单个维度（含已删除）。"""
        session = get_db_session()
        return session.get(Dimension, dim_id)

    def create_dimension(self, create_data: Dict[str, Any]) -> Dimension:
        """创建维度记录（含 flush，未 commit）。"""
        session = get_db_session()
        dim = Dimension(**create_data)
        session.add(dim)
        session.flush()
        return dim

    def soft_delete_dimension(self, dim: Dimension) -> None:
        """软删除维度（含 flush，未 commit）。"""
        now = _now()
        dim.deleted = True
        dim.updated_at = now
        get_db_session().flush()

    def batch_update_dimensions(self, ids: List[int], update_data: Dict[str, Any]) -> int:
        """按 ID 列表批量更新维度（含 flush，未 commit）。返回受影响行数。"""
        session = get_db_session()
        if not ids:
            return 0
        count = session.query(Dimension).filter(
            Dimension.id.in_(ids)
        ).update(update_data, synchronize_session=False)
        session.flush()
        return count

    def list_dimensions_by_ids(self, ids: List[int]) -> List[Dimension]:
        """按 ID 列表查询维度。"""
        session = get_db_session()
        if not ids:
            return []
        return session.query(Dimension).filter(Dimension.id.in_(ids)).all()

    def list_sub_dimensions(self, parent_id: int) -> List[Dimension]:
        """查询某主维度下未删除的子维度。"""
        session = get_db_session()
        return session.query(Dimension).filter(
            Dimension.parent_dimension_id == parent_id,
            Dimension.dimension_type == 'sub',
            Dimension.deleted == False,  # noqa: E712
        ).all()

    def query_dimensions_paginated(
        self,
        category_id: Optional[int] = None,
        page: int = 1,
        per_page: int = 10,
        search: str = '',
    ):
        """分页查询维度（带搜索）。"""
        session = get_db_session()
        query = session.query(Dimension).filter_by(deleted=False)

        if category_id:
            query = query.filter_by(category_id=category_id)

        if search:
            query = query.filter(
                (Dimension.name.ilike(f'%{search}%'))
                | (Dimension.description.ilike(f'%{search}%'))
                | (Dimension.keywords.ilike(f'%{search}%'))
            )

        return query.paginate(page=page, per_page=per_page, error_out=False)

    def list_dimension_options(self, algorithm_type: str = '') -> List[Dimension]:
        """查询维度选项列表（可按 algorithm_type 过滤）。

        当指定 algorithm_type 但无关联维度时，返回空列表由调用方短路处理。
        通过 gRPC 调用 algorithm_service.GetAlgorithmDimensions 获取关联 dimension_ids。
        """
        session = get_db_session()
        query = session.query(Dimension).filter_by(deleted=False)
        if algorithm_type:
            associated_dim_ids: List[int] = []
            try:
                from shared.clients.grpc_clients import (
                    get_algorithm_definition_service_stub,
                )
                from shared.proto import algorithm_service_pb2 as _algo_pb
                stub = get_algorithm_definition_service_stub()
                req = _algo_pb.GetAlgorithmDimensionsRequest(
                    algorithm_type=algorithm_type
                )
                resp = stub.GetAlgorithmDimensions(req)
                if resp.success:
                    from shared.utils.grpc_json import loads as _grpc_loads
                    data = _grpc_loads(resp.data, {}) or {}
                    associated_dim_ids = [
                        int(d) for d in data.get('dimension_ids', [])
                    ]
            except Exception:
                pass
            if associated_dim_ids:
                query = query.filter(Dimension.id.in_(associated_dim_ids))
            else:
                return []
        return query.order_by(Dimension.id).all()

    def update_dimension_attrs(self, dim: Dimension, data: Dict[str, Any]) -> None:
        """更新维度可赋值字段（含 flush，未 commit）。"""
        session = get_db_session()
        for field, value in data.items():
            setattr(dim, field, value)
        session.flush()

    # ========== AlgorithmDimensionRelation 管理（gRPC） ==========

    def delete_relations_by_dimension(self, dim_id: int) -> bool:
        """按维度 ID 删除所有算法-维度关联（gRPC）。

        与原逻辑一致：更新关联时先清空旧关联再插入新关联。
        """
        return self._algo.sync_dimension_relations(dim_id, [])

    def add_relation(self, data: Dict[str, Any]) -> bool:
        """创建单条算法-维度关联（gRPC）。

        注意：gRPC 的 SyncDimensionRelations 是"先清空再插入"模式，
        单条创建改为直接调用 CreateDimensionRelation。
        """
        try:
            from shared.clients.grpc_clients import get_algorithm_definition_service_stub
            from shared.proto import algorithm_service_pb2 as _algo_pb
            from shared.utils.grpc_json import dumps as _dumps
            stub = get_algorithm_definition_service_stub()
            resp = stub.CreateDimensionRelation(_algo_pb.CreateDimensionRelationRequest(
                data=_dumps(data),
            ))
            return resp.success
        except Exception:
            return False

    def sync_relations(self, dim_id: int, relations: List[Dict[str, Any]]) -> bool:
        """同步算法-维度关联（先清空旧关联再插入新关联，gRPC）。"""
        return self._algo.sync_dimension_relations(dim_id, relations)

    def list_relations_by_dimension(self, dim_id: int) -> List[Dict[str, Any]]:
        """查询维度关联的未删除算法-维度关联列表（gRPC，返回 dict 列表）。"""
        return self._algo.get_relations_by_dimension(dim_id)

    # ========== EvaluationDimensionParam 管理（gRPC） ==========

    def delete_input_params_by_dimension(self, dim_id: int) -> bool:
        """按维度 ID 删除所有 input 方向参数（gRPC）。"""
        return self._algo.delete_dimension_params_by_direction(dim_id, 'input')

    def delete_output_params_by_dimension(self, dim_id: int) -> bool:
        """按维度 ID 删除所有 output 方向参数（gRPC）。"""
        return self._algo.delete_dimension_params_by_direction(dim_id, 'output')

    def add_dimension_param(self, data: Dict[str, Any]) -> Optional[int]:
        """创建单条评估维度参数（gRPC）。返回新 param_id 或 None。"""
        return self._algo.create_dimension_param(data)

    def list_dimension_params(self, dim_id: int) -> List[Dict[str, Any]]:
        """查询评估维度的参数列表（gRPC，返回 dict 列表）。"""
        return self._algo.get_dimension_params(dim_id)

    def find_audio_dimension_ids(self, dim_ids: List[int]) -> set:
        """查询需要音频文件参数的维度 ID 集合（gRPC）。"""
        return self._algo.find_audio_dimension_ids(dim_ids)

    # ========== ParamMapping 同步（gRPC） ==========

    def list_param_mappings_for_dimension(
        self, dimension_id: int
    ) -> List[Dict[str, Any]]:
        """查询某维度所有 ParamMapping（含软删除项，用于同步逻辑，gRPC）。

        注意：与 list_mappings 不同，此处不过滤 deleted，因为同步逻辑需要
        复活软删除的记录以避免唯一约束冲突。
        """
        return self._algo.list_param_mappings_for_dimension(dimension_id)

    def sync_param_mappings(
        self,
        dimension_id: int,
        params: Any,
        direction: str = 'output',
        algorithm_type: str = 'voice_llm',
    ) -> bool:
        """同步 ParamMapping（gRPC 委托）。

        当评估维度的输入/输出字段变更时，自动为该维度创建/更新/删除
        对应的 ParamMapping 记录。
        """
        return self._algo.sync_param_mappings(
            dimension_id, params, direction, algorithm_type
        )

    # ========== 事务控制（仅限本服务自有 PO） ==========

    def commit(self):
        """提交事务。"""
        get_db_session().commit()

    def rollback(self):
        """回滚事务。"""
        get_db_session().rollback()

    def flush(self):
        """flush session。"""
        get_db_session().flush()


# 模块级单例（与 evaluation_dimension_repository.py 风格一致）
evaluation_repository = EvaluationRepository()
