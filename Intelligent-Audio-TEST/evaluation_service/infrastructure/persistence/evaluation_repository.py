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

from sqlalchemy import func

from shared.infrastructure.user_context import (
    get_current_user_id,
    get_current_user_is_admin,
)
from shared.infrastructure.visibility_filter import visible_condition
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


# 主/子维度分段排序步长（对齐旧库 SORT_STEP）：主维度 sort_order 占独立段
# （SORT_STEP 的整数倍：0, 1000, 2000...），子维度 sort_order = 父主维度段值 +
# 组内序号（1 起：1001, 1002...）。order_by(sort_order, id) 天然得到
# 「主维度在前、组内子维度紧随」的层级顺序。
DIMENSION_SORT_STEP = 1000


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
        """创建分类（含 flush，未 commit）。

        created_by_user_id（INT-841）：从 x-user-id 上下文取 JWT 操作人，
        未认证（AUTH_MODE=off）为 None → NULL。
        """
        from shared.infrastructure.user_context import get_current_user_id
        session = get_db_session()
        cat = Category(
            name=data.get('name'),
            description=data.get('description'),
            icon=data.get('icon'),
            created_by_user_id=get_current_user_id(),
            visibility=data.get('visibility', 'shared'),
        )
        session.add(cat)
        session.flush()
        return cat

    def list_categories(self) -> List[Category]:
        """查询所有未删除分类（INT-423 行级过滤：私有仅 owner/admin 可见）。"""
        session = get_db_session()
        return session.query(Category).filter(
            Category.deleted == False,  # noqa: E712
            visible_condition(
                Category.created_by_user_id, Category.visibility,
                get_current_user_id(), get_current_user_is_admin(),
            ),
        ).all()

    # ========== Dimension CRUD ==========

    def get_dimension(self, dim_id: int) -> Optional[Dimension]:
        """按 ID 查询单个维度（含已删除）。"""
        session = get_db_session()
        return session.get(Dimension, dim_id)

    def create_dimension(self, create_data: Dict[str, Any]) -> Dimension:
        """创建维度记录（含 flush，未 commit）。

        created_by_user_id（INT-841）：从 x-user-id 上下文取 JWT 操作人，
        未认证（AUTH_MODE=off）为 None → NULL。create_data 来自应用层
        字段白名单（DIMENSION_MODEL_FIELDS），不含操作人列。
        """
        from shared.infrastructure.user_context import get_current_user_id
        session = get_db_session()
        dim = Dimension(**create_data, created_by_user_id=get_current_user_id())
        session.add(dim)
        session.flush()
        return dim

    def soft_delete_dimension(self, dim: Dimension) -> None:
        """软删除维度（含 flush，未 commit）。

        补盖 deleted_by_user_id（INT-841）：软删操作人从 x-user-id 上下文取，
        未认证为 None → NULL。deleted_at/updated_at 语义保持原状不动。
        """
        from shared.infrastructure.user_context import get_current_user_id
        now = _now()
        dim.deleted = True
        dim.deleted_by_user_id = get_current_user_id()
        dim.updated_at = now
        get_db_session().flush()

    def batch_update_dimensions(self, ids: List[int], update_data: Dict[str, Any]) -> int:
        """按 ID 列表批量更新维度（含 flush，未 commit）。返回受影响行数。

        更新操作人（updated_by_user_id）从 x-user-id 上下文统一盖（INT-841）。
        """
        from shared.infrastructure.user_context import get_current_user_id
        session = get_db_session()
        if not ids:
            return 0
        count = session.query(Dimension).filter(
            Dimension.id.in_(ids)
        ).update(
            {**update_data, 'updated_by_user_id': get_current_user_id()},
            synchronize_session=False,
        )
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
        """分页查询维度（带搜索；INT-423 行级过滤：私有仅 owner/admin 可见）。"""
        session = get_db_session()
        query = session.query(Dimension).filter_by(deleted=False)

        # INT-423 行级过滤：user_id 取 x-user-id context，禁止从业务表反查
        query = query.filter(visible_condition(
            Dimension.created_by_user_id, Dimension.visibility,
            get_current_user_id(), get_current_user_is_admin(),
        ))

        if category_id:
            query = query.filter_by(category_id=category_id)

        if search:
            query = query.filter(
                (Dimension.name.ilike(f'%{search}%'))
                | (Dimension.description.ilike(f'%{search}%'))
                | (Dimension.keywords.ilike(f'%{search}%'))
            )

        return query.order_by(Dimension.sort_order, Dimension.id).paginate(page=page, per_page=per_page, error_out=False)

    def list_dimension_options(self, algorithm_type: str = '') -> List[Dimension]:
        """查询维度选项列表（可按 algorithm_type 过滤；INT-423 行级过滤）。

        当指定 algorithm_type 但无关联维度时，返回空列表由调用方短路处理。
        通过 gRPC 调用 algorithm_service.GetAlgorithmDimensions 获取关联 dimension_ids。
        """
        session = get_db_session()
        query = session.query(Dimension).filter_by(deleted=False)
        # INT-423 行级过滤：私有维度不作为非 owner 的可用选项
        query = query.filter(visible_condition(
            Dimension.created_by_user_id, Dimension.visibility,
            get_current_user_id(), get_current_user_is_admin(),
        ))
        if algorithm_type:
            associated_dim_ids = self._algo.get_algorithm_dimensions(algorithm_type)
            if associated_dim_ids:
                query = query.filter(Dimension.id.in_(associated_dim_ids))
            else:
                return []
        return query.order_by(Dimension.sort_order, Dimension.id).all()

    def update_dimension_attrs(self, dim: Dimension, data: Dict[str, Any]) -> None:
        """更新维度可赋值字段（含 flush，未 commit）。"""
        session = get_db_session()
        for field, value in data.items():
            setattr(dim, field, value)
        session.flush()

    def list_dimension_visibility_rows(self, ids: List[int]) -> List[tuple]:
        """批量查询维度可见性三元组 [(id, created_by_user_id, visibility), ...]。

        供 batch_action / export 逐行过滤（filter_visible_owners），私有非 owner 行跳过。
        """
        session = get_db_session()
        if not ids:
            return []
        rows = (
            session.query(Dimension.id, Dimension.created_by_user_id,
                          Dimension.visibility)
            .filter(Dimension.id.in_(ids),
                    Dimension.deleted == False)  # noqa: E712
            .all()
        )
        return [tuple(r) for r in rows]

    def list_category_visibility_rows(self, ids: List[int]) -> List[tuple]:
        """批量查询分类可见性三元组 [(id, created_by_user_id, visibility), ...]。"""
        session = get_db_session()
        if not ids:
            return []
        rows = (
            session.query(Category.id, Category.created_by_user_id,
                          Category.visibility)
            .filter(Category.id.in_(ids),
                    Category.deleted == False)  # noqa: E712
            .all()
        )
        return [tuple(r) for r in rows]

    def reorder_dimensions(self, ordered_ids: List[int]) -> Optional[List[int]]:
        """按数组顺序重排维度 sort_order（含 flush，未 commit）。

        主/子分段编码（对齐旧库）：ids 为前端按层级重组后的全量顺序，
        主维度先于其子维度出现——主维度占独立段（main_index * SORT_STEP），
        子维度挂到父维度段内（父段值 + 组内序号，1 起）。

        Args:
            ordered_ids: 维度 ID 数组，顺序即新展示顺序
        Returns:
            缺失的维度 ID 列表（存在不存在的 id 时），成功返回 None
        """
        session = get_db_session()
        id_list = [int(i) for i in ordered_ids]
        if not id_list:
            return []
        dims = session.query(Dimension).filter(
            Dimension.id.in_(id_list),
            Dimension.deleted == False,  # noqa: E712
        ).all()
        dim_map = {d.id: d for d in dims}
        missing = [i for i in id_list if i not in dim_map]
        if missing:
            return missing
        main_index = 0
        sub_counters: Dict[int, int] = {}
        for dim_id in id_list:
            dim = dim_map[dim_id]
            if dim.parent_dimension_id:
                parent = dim_map.get(dim.parent_dimension_id)
                if parent is None:
                    # 防御：父维度不在本次列表（如筛选态），取库中当前段值
                    parent = session.get(Dimension, dim.parent_dimension_id)
                base = parent.sort_order if parent else 0
                sub_counters[dim.parent_dimension_id] = (
                    sub_counters.get(dim.parent_dimension_id, 0) + 1)
                dim.sort_order = base + sub_counters[dim.parent_dimension_id]
            else:
                dim.sort_order = main_index * DIMENSION_SORT_STEP
                main_index += 1
        session.flush()
        return None

    def max_main_sort_order(self) -> int:
        """查询主维度当前最大 sort_order（无主维度返回 0）。"""
        session = get_db_session()
        max_sort = session.query(func.max(Dimension.sort_order)).filter(
            Dimension.deleted == False,  # noqa: E712
            (Dimension.parent_dimension_id.is_(None))
            | (Dimension.parent_dimension_id == 0),
        ).scalar()
        return max_sort if max_sort is not None else 0

    def max_sub_sort_order(self, parent_id: int) -> int:
        """查询某父维度下子维度当前最大 sort_order（无子维度返回父维度段基值）。

        父维度不存在时返回 0。
        """
        session = get_db_session()
        parent = session.get(Dimension, parent_id)
        if parent is None:
            return 0
        base = parent.sort_order if parent.sort_order is not None else 0
        max_sort = session.query(func.max(Dimension.sort_order)).filter(
            Dimension.parent_dimension_id == parent_id,
            Dimension.deleted == False,  # noqa: E712
        ).scalar()
        return max(max_sort, base) if max_sort is not None else base

    def list_descendant_ids(self, dim_ids: List[int]) -> List[int]:
        """收集维度 ID 及其全部未删除后代 ID（BFS 逐层查询，主/子联动）。

        对齐旧库 _collect_descendant_ids：仅按 parent_dimension_id 归属判定，
        不要求子维度 dimension_type 标记正确。
        """
        session = get_db_session()
        result = set(dim_ids)
        frontier = [int(i) for i in dim_ids]
        while frontier:
            rows = session.query(Dimension.id).filter(
                Dimension.parent_dimension_id.in_(frontier),
                Dimension.deleted == False,  # noqa: E712
            ).all()
            frontier = [sub_id for (sub_id,) in rows if sub_id not in result]
            result.update(frontier)
        return list(result)

    def max_sort_order(self) -> int:
        """查询当前最大 sort_order（含已删除，无数据返回 0）。"""
        session = get_db_session()
        max_sort = session.query(func.max(Dimension.sort_order)).scalar()
        return max_sort if max_sort is not None else 0

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
        return self._algo.create_dimension_relation(data)

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
