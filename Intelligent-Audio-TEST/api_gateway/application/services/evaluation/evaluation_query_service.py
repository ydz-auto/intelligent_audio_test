"""评估维度查询读侧 Service（CQRS Query Side）。

按 DDD 原则，网关不再直接操作 DB，而是通过 gRPC 调用 evaluation_service。
"""
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.infrastructure.acl import EvaluationConfigAclRepositoryImpl

from api_gateway.schemas.evaluation import (
    CategoryItem,
    CategoryListData,
    DimensionHealthCheckData,
    DimensionItem,
    DimensionListData,
    HealthCheckResultItem,
)


_evaluation_acl = EvaluationConfigAclRepositoryImpl()


class EvaluationQueryService:
    """评估维度查询读侧 Service（CQRS Query Side）。"""

    # --- 分类管理 (Category Management) ---

    @staticmethod
    def get_categories():
        result = _evaluation_acl.list_categories()

        if not result.get('success'):
            return error_response(result.get('message', '获取分类列表失败'))

        raw = result.get('data') or {}
        items_raw = raw.get('items', []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        items = [CategoryItem(**item) for item in items_raw]

        return success_response(CategoryListData(items=items, total=len(items)))

    # --- 维度管理 (Dimension Management) ---

    # 获取维度选项列表（用于下拉选择，包含关联的算法信息）
    @staticmethod
    def get_dimension_options():
        algorithm_type = request.args.get('algorithm_type', '')

        result = _evaluation_acl.get_dimension_options(algorithm_type=algorithm_type)

        if not result.get('success'):
            return error_response(result.get('message', '获取维度选项失败'))

        return success_response(result.get('data'))

    # 获取所有评分维度
    @staticmethod
    def get_all():
        category_id = request.args.get('category_id', type=int)
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        search = request.args.get('search', '')

        result = _evaluation_acl.list_dimensions(
            category_id=category_id,
            page=page,
            per_page=per_page,
            search=search,
        )

        if not result.get('success'):
            return error_response(result.get('message', '获取维度列表失败'))

        raw = result.get('data') or {}
        items_raw = raw.get('items', []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        items = [DimensionItem(**item) for item in items_raw]

        return success_response(
            DimensionListData(
                items=items,
                total=raw.get('total', len(items)) if isinstance(raw, dict) else len(items),
                page=raw.get('page', page) if isinstance(raw, dict) else page,
                per_page=raw.get('per_page', per_page) if isinstance(raw, dict) else per_page,
                pages=raw.get('pages', 1) if isinstance(raw, dict) else 1,
            )
        )

    # 维度 API 健康探测
    @staticmethod
    def health_check(dim_id):
        result = _evaluation_acl.health_check(dim_id)

        if not result.get('success'):
            code = result.get('code', 400)
            if code == 404:
                return error_response("维度不存在", 404)
            return error_response(result.get('message', '健康检查失败'), code)

        return success_response(result.get('data'), result.get('message', '健康探测完成'))
