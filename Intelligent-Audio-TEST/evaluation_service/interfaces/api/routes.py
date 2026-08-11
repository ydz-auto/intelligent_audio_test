# -*- coding: utf-8 -*-
"""evaluation_service HTTP 路由

提供评估维度的 CRUD HTTP 接口（通过 FastAPI APIRouter）。
gRPC 接口详见 interfaces/grpc/servicers.py。
"""
from typing import Optional

from fastapi import APIRouter, Query

router = APIRouter(prefix='/api/evaluation', tags=['evaluation'])


@router.get('/dimensions')
def list_dimensions(
    category_id: Optional[int] = Query(None),
    page: int = Query(1),
    per_page: int = Query(20),
    search: str = Query(''),
):
    """查询维度列表"""
    try:
        from evaluation_service.application.queries.evaluation_query_service import evaluation_query_service
        result = evaluation_query_service.list_dimensions(
            category_id=category_id,
            page=page,
            per_page=per_page,
            search=search,
        )
        return result
    except Exception as e:
        return {'success': False, 'message': str(e)}


@router.get('/dimensions/{dim_id}')
def get_dimension(dim_id: int):
    """查询单个维度"""
    try:
        from evaluation_service.application.queries.evaluation_query_service import evaluation_query_service
        result = evaluation_query_service.get_dimension(dim_id)
        return result
    except Exception as e:
        return {'success': False, 'message': str(e)}


@router.post('/dimensions')
def create_dimension(body: dict):
    """创建维度"""
    try:
        from evaluation_service.application.handlers.evaluation_config_handler import evaluation_config_handler
        result = evaluation_config_handler.create_dimension(body)
        return result
    except Exception as e:
        return {'success': False, 'message': str(e)}


@router.put('/dimensions/{dim_id}')
def update_dimension(dim_id: int, body: dict):
    """更新维度"""
    try:
        from evaluation_service.application.handlers.evaluation_config_handler import evaluation_config_handler
        result = evaluation_config_handler.update_dimension(dim_id, body)
        return result
    except Exception as e:
        return {'success': False, 'message': str(e)}


@router.delete('/dimensions/{dim_id}')
def delete_dimension(dim_id: int):
    """删除维度"""
    try:
        from evaluation_service.application.handlers.evaluation_config_handler import evaluation_config_handler
        result = evaluation_config_handler.delete_dimension(dim_id)
        return result
    except Exception as e:
        return {'success': False, 'message': str(e)}


@router.post('/dimensions/batch')
def batch_action_dimension(body: dict):
    """批量操作维度"""
    try:
        from evaluation_service.application.handlers.evaluation_config_handler import evaluation_config_handler
        result = evaluation_config_handler.batch_action(body)
        return result
    except Exception as e:
        return {'success': False, 'message': str(e)}


@router.get('/categories')
def list_categories():
    """查询分类列表"""
    try:
        from evaluation_service.application.handlers.evaluation_config_handler import evaluation_config_handler
        result = evaluation_config_handler.list_categories()
        return result
    except Exception as e:
        return {'success': False, 'message': str(e)}


@router.post('/categories')
def create_category(body: dict):
    """创建分类"""
    try:
        from evaluation_service.application.handlers.evaluation_config_handler import evaluation_config_handler
        result = evaluation_config_handler.create_category(body)
        return result
    except Exception as e:
        return {'success': False, 'message': str(e)}


@router.put('/categories/{cat_id}')
def update_category(cat_id: int, body: dict):
    """更新分类"""
    try:
        from evaluation_service.application.handlers.evaluation_config_handler import evaluation_config_handler
        result = evaluation_config_handler.update_category(cat_id, body)
        return result
    except Exception as e:
        return {'success': False, 'message': str(e)}


@router.delete('/categories/{cat_id}')
def delete_category(cat_id: int):
    """删除分类"""
    try:
        from evaluation_service.application.handlers.evaluation_config_handler import evaluation_config_handler
        result = evaluation_config_handler.delete_category(cat_id)
        return result
    except Exception as e:
        return {'success': False, 'message': str(e)}


@router.post('/reevaluate')
def reevaluate(body: dict):
    """重新评估"""
    try:
        from evaluation_service.application.handlers.reevaluation_executor import ReevaluationExecutor
        executor = ReevaluationExecutor.get_instance()
        success, message = executor.submit(
            body.get('task_id'),
            reextract_device_output=body.get('reextract_device_output', False),
            reevaluate_type=body.get('reevaluate_type', 'all'),
        )
        return {'success': success, 'message': message}
    except Exception as e:
        return {'success': False, 'message': str(e)}


@router.get('/dimensions/options')
def get_dimension_options(algorithm_type: str = Query('')):
    """查询维度选项"""
    try:
        from evaluation_service.application.handlers.evaluation_config_handler import evaluation_config_handler
        result = evaluation_config_handler.get_dimension_options(algorithm_type)
        return result
    except Exception as e:
        return {'success': False, 'message': str(e)}


@router.get('/dimensions/{dim_id}/health')
def health_check(dim_id: int):
    """维度健康检查"""
    try:
        from evaluation_service.application.handlers.evaluation_config_handler import evaluation_config_handler
        result = evaluation_config_handler.health_check(dim_id)
        return result
    except Exception as e:
        return {'success': False, 'message': str(e)}
