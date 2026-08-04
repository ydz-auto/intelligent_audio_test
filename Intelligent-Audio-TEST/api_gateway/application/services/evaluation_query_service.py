"""评估维度查询读侧 Service（CQRS Query Side）。

承载 EvaluationController 中所有只读查询方法，保持原有逻辑不变。
"""
import time
import requests

from api_gateway.infrastructure.request_adapter import request
from shared.models.models import Dimension, Category
from shared.models.algorithm_models import (
    EvaluationDimensionParam,
    AlgorithmDimensionRelation,
)
from shared.models.database import db
from shared.utils.response import success_response, error_response
from api_gateway.schemas.evaluation import (
    CategoryItem,
    CategoryListData,
    DimensionHealthCheckData,
    DimensionItem,
    DimensionListData,
    HealthCheckResultItem,
)
from datetime import datetime


class EvaluationQueryService:
    """评估维度查询读侧 Service（CQRS Query Side）。"""

    # --- 分类管理 (Category Management) ---

    @staticmethod
    def get_categories():
        categories = Category.query.filter(Category.deleted == False).all()
        data = []
        for cat in categories:
            # Handle datetime conversion safely
            created_at = cat.created_at
            updated_at = cat.updated_at

            # Ensure we're dealing with datetime objects before calling isoformat
            if isinstance(created_at, datetime):
                created_at_iso = created_at.isoformat()
            else:
                # Fallback for invalid datetime values
                created_at_iso = str(created_at)

            if isinstance(updated_at, datetime):
                updated_at_iso = updated_at.isoformat()
            else:
                # Fallback for invalid datetime values
                updated_at_iso = str(updated_at)

            data.append(
                CategoryItem(
                    id=cat.id,
                    name=cat.name,
                    description=cat.description,
                    icon=cat.icon,
                    created_at=created_at_iso,
                    updated_at=updated_at_iso,
                )
            )
        return success_response(CategoryListData(items=data, total=len(data)))

    # --- 维度管理 (Dimension Management) ---

    # 获取维度选项列表（用于下拉选择，包含关联的算法信息）
    @staticmethod
    def get_dimension_options():
        algorithm_type = request.args.get('algorithm_type', '')
        query = Dimension.query.filter_by(deleted=False)
        if algorithm_type:
            associated_dim_ids = [r.dimension_id for r in
                                  AlgorithmDimensionRelation.query.filter_by(algorithm_type=algorithm_type,
                                                                             deleted=False).all()]
            if associated_dim_ids:
                query = query.filter(Dimension.id.in_(associated_dim_ids))
            else:
                return success_response({'dimensions': []})
        dimensions = query.order_by(Dimension.id).all()

        # 查询哪些维度需要音频文件参数（field_type='audio' 的输入参数）
        dim_ids = [d.id for d in dimensions]
        audio_dim_ids = set()
        if dim_ids:
            from shared.models.algorithm_models import EvaluationDimensionParam
            audio_params = EvaluationDimensionParam.query.filter(
                EvaluationDimensionParam.dimension_id.in_(dim_ids),
                EvaluationDimensionParam.field_type == 'audio',
                EvaluationDimensionParam.param_direction == 'input',
                EvaluationDimensionParam.deleted == False
            ).all()
            audio_dim_ids = {p.dimension_id for p in audio_params}

        return success_response({
            'dimensions': [
                {
                    'id': d.id,
                    'name': d.name,
                    'description': d.description,
                    'type': d.type,
                    'dimension_type': d.dimension_type,
                    'category_id': d.category_id,
                    'task_type_code': d.task_type_code,
                    'requires_audio': d.id in audio_dim_ids
                }
                for d in dimensions
            ]
        })

    # 获取所有评分维度
    @staticmethod
    def get_all():
        category_id = request.args.get('category_id', request.args.get('category_id', type=int))
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', request.args.get('per_page', 10, type=int), type=int)
        search = request.args.get('search', '')

        query = Dimension.query.filter_by(deleted=False)

        if category_id:
            query = query.filter_by(category_id=category_id)

        if search:
            query = query.filter(
                (Dimension.name.ilike(f'%{search}%')) |
                (Dimension.description.ilike(f'%{search}%')) |
                (Dimension.keywords.ilike(f'%{search}%'))
            )

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        dimensions = pagination.items

        data = []
        for dim in dimensions:
            # 从 EvaluationDimensionParam 表获取参数
            dim_params = EvaluationDimensionParam.query.filter_by(
                dimension_id=dim.id, deleted=False
            ).order_by(EvaluationDimensionParam.ui_order).all()
            required_inputs = [p.to_dict() for p in dim_params if p.param_direction == 'input']
            output_fields = [p.to_dict() for p in dim_params if p.param_direction == 'output']

            # 从 algorithm_dimension_relations 表获取关联的算法
            dim_relations = AlgorithmDimensionRelation.query.filter_by(
                dimension_id=dim.id, deleted=False
            ).all()
            associated_algorithms = [
                {
                    'algorithmType': rel.algorithm_type,
                    'isDefault': rel.is_default,
                    'weight': rel.weight
                }
                for rel in dim_relations
            ]

            data.append(
                DimensionItem(
                    id=dim.id,
                    name=dim.name,
                    description=dim.description,
                    keywords=dim.keywords,
                    dimension_type=dim.dimension_type,
                    parent_dimension_id=dim.parent_dimension_id,
                    task_type_code=dim.task_type_code,
                    category_id=dim.category_id,
                    api_url=dim.api_url,
                    api_endpoints=dim.api_endpoints,
                    api_settings=dim.api_settings,
                    api_status=dim.api_status,
                    score_unit=dim.score_unit,
                    type=dim.type,
                    result_type=dim.result_type,
                    result_min=dim.result_min,
                    result_max=dim.result_max,
                    decimal_places=dim.decimal_places,
                    weight=dim.weight,
                    estimated_exec_time=dim.estimated_exec_time,
                    rule=dim.rule,
                    required_inputs=required_inputs,
                    output_fields=output_fields,
                    statistic_method=getattr(dim, 'statistic_method', 'average') or 'average',
                    associated_algorithms=associated_algorithms,
                    status=dim.status,
                    created_at=dim.created_at.isoformat() if dim.created_at else None,
                    updated_at=dim.updated_at.isoformat() if dim.updated_at else None,
                )
            )

        return success_response(
            DimensionListData(
                items=data,
                total=pagination.total,
                page=page,
                per_page=per_page,
                pages=pagination.pages,
            )
        )

    # 维度 API 健康探测
    @staticmethod
    def health_check(dim_id):
        dim = db.session.get(Dimension, dim_id)
        if not dim or dim.deleted:
            return error_response("维度不存在", 404)

        # 检查是否配置了多个API端点
        if dim.api_endpoints and isinstance(dim.api_endpoints, list) and len(dim.api_endpoints) > 0:
            results = []
            all_online = True

            for endpoint in dim.api_endpoints:
                url = endpoint.get('url') or endpoint.get('endpoint')
                if not url:
                    continue

                settings = dim.api_settings or {}
                method = settings.get('method', 'GET').upper()
                headers = settings.get('headers', {})

                health_check_url = url

                start_time = time.time()
                try:
                    if method == 'POST':
                        # 对于 POST 请求，我们使用简单的健康检查 GET 请求替代
                        response = requests.get(health_check_url, headers=headers, timeout=10)
                    else:
                        response = requests.get(health_check_url, headers=headers, timeout=10)

                    duration = (time.time() - start_time) * 1000

                    if 200 <= response.status_code < 400:
                        endpoint_status = 'online'
                        message = "健康探测完成"
                    else:
                        endpoint_status = 'offline'
                        message = f"探测失败，状态码: {response.status_code}"
                        all_online = False

                    results.append(
                        HealthCheckResultItem(
                            url=url,
                            status=endpoint_status,
                            status_code=response.status_code,
                            response_time=f"{duration:.2f}ms",
                            message=message,
                        )
                    )
                except Exception as e:
                    results.append(
                        HealthCheckResultItem(
                            url=url,
                            status="offline",
                            error=str(e),
                            message="健康探测失败",
                        )
                    )
                    all_online = False

            # 更新维度的整体状态
            dim.api_status = 'online' if all_online else 'offline'
            db.session.commit()

            return success_response(
                DimensionHealthCheckData(results=results, overall_status=dim.api_status),
                "健康探测完成",
            )
        else:
            # 未配置任何API端点
            dim.api_status = 'offline'
            db.session.commit()
            return error_response("未配置任何 API 端点")
