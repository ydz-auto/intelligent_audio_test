# -*- coding: utf-8 -*-
"""挑选合并 BFF Service（INT-339）——网关侧 ACL 编排。

CQRS：查询侧只读（购物车/挑选集/候选/预览/溯源），命令侧经 ACL 下发写命令
（加购/移除/清空/另存/恢复/下单三出口）。所有方法返回 (payload, http_code)
元组（对齐网关路由层 to_response 约定）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from api_gateway.infrastructure.acl import CherryPickAclRepositoryImpl
from api_gateway.infrastructure.request_adapter import request
from api_gateway.utils.response import success_response, error_response
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.schemas.cherry_pick import (
    CherryPickCartAddRequest,
    CherryPickCartRemoveRequest,
    CherryPickSaveSetRequest,
    CherryPickCandidatesQuery,
    CherryPickPickableTasksQuery,
    CherryPickCheckoutRequest,
    _CODE_HTTP_MAP,
)

logger = logging.getLogger(__name__)

_cherry_pick_acl = CherryPickAclRepositoryImpl()


def _parse_query_params(model_cls):
    params = {k: v[0] if isinstance(v, list) else v for k, v in request.args.to_dict().items()}
    return model_cls.model_validate(params)


def _split_ints(value) -> List[int]:
    """逗号分隔 ID 串 → int 列表（GET 查询串多值契约；空值安全）。"""
    if value is None or value == '' or value == []:
        return []
    if isinstance(value, (list, tuple)):
        raw = value
    else:
        raw = str(value).split(',')
    out = []
    for part in raw:
        try:
            out.append(int(str(part).strip()))
        except (TypeError, ValueError):
            continue
    return out


def _split_strs(value) -> List[str]:
    """逗号分隔字符串 → str 列表（空值安全）。"""
    if value is None or value == '' or value == []:
        return []
    if isinstance(value, (list, tuple)):
        return [str(v).strip() for v in value if str(v).strip()]
    return [p.strip() for p in str(value).split(',') if p.strip()]


class CherryPickService:
    """挑选合并 BFF Service（查询/命令经 ACL 下发，网关不触 DB）。"""

    # ---- 购物车 ----

    @staticmethod
    def get_cart():
        result = _cherry_pick_acl.get_cart()
        if not result.get('success'):
            return error_response(result.get('message', '查询购物车失败'))
        return success_response(result.get('data') or {})

    @staticmethod
    def add_cart_items():
        try:
            req = CherryPickCartAddRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {e}")
        result = _cherry_pick_acl.add_cart_items(req.result_ids)
        if not result.get('success'):
            return error_response(result.get('message', '加入购物车失败'),
                                  http_code=_CODE_HTTP_MAP.get(result.get('code'), 400))
        return success_response(result.get('data') or {}, result.get('message', '已加入购物车'))

    @staticmethod
    def remove_cart_items():
        try:
            req = CherryPickCartRemoveRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {e}")
        result = _cherry_pick_acl.remove_cart_items(req.item_ids)
        if not result.get('success'):
            return error_response(result.get('message', '移除失败'))
        return success_response(result.get('data') or {}, result.get('message', '已移除'))

    @staticmethod
    def clear_cart():
        result = _cherry_pick_acl.clear_cart()
        if not result.get('success'):
            return error_response(result.get('message', '清空失败'))
        return success_response(result.get('data') or {}, result.get('message', '已清空'))

    # ---- 挑选集 ----

    @staticmethod
    def save_set():
        try:
            req = CherryPickSaveSetRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {e}")
        result = _cherry_pick_acl.save_set(req.name, req.description)
        if not result.get('success'):
            return error_response(result.get('message', '另存挑选集失败'),
                                  http_code=_CODE_HTTP_MAP.get(result.get('code'), 400))
        return success_response(result.get('data') or {}, result.get('message', '挑选集已保存'))

    @staticmethod
    def list_sets():
        result = _cherry_pick_acl.list_sets()
        if not result.get('success'):
            return error_response(result.get('message', '查询挑选集列表失败'))
        return success_response(result.get('data') or {})

    @staticmethod
    def get_set(set_id):
        result = _cherry_pick_acl.get_set(set_id)
        if not result.get('success'):
            return error_response(result.get('message', '未找到挑选集'),
                                  http_code=_CODE_HTTP_MAP.get(result.get('code'), 400))
        return success_response(result.get('data') or {})

    @staticmethod
    def delete_set(set_id):
        result = _cherry_pick_acl.delete_set(set_id)
        if not result.get('success'):
            return error_response(result.get('message', '删除挑选集失败'),
                                  http_code=_CODE_HTTP_MAP.get(result.get('code'), 400))
        return success_response(result.get('data') or {}, result.get('message', '挑选集已删除'))

    @staticmethod
    def restore_set_to_cart(set_id):
        result = _cherry_pick_acl.restore_set_to_cart(set_id)
        if not result.get('success'):
            return error_response(result.get('message', '挑选集恢复失败'),
                                  http_code=_CODE_HTTP_MAP.get(result.get('code'), 400))
        return success_response(result.get('data') or {}, result.get('message', '已恢复进购物车'))

    # ---- 挑选候选查询（S2）----

    @staticmethod
    def list_candidates():
        try:
            query = _parse_query_params(CherryPickCandidatesQuery)
        except Exception as e:
            return error_response(f"数据验证失败: {e}")
        # 逗号分隔多值（GET 查询串契约，前端 cherryPickApi 统一 join(',')）
        payload = {
            'task_ids': _split_ints(query.task_ids),
            'device_ids': _split_ints(query.device_ids),
            'case_ids': _split_strs(query.case_ids),
            'execution_status': query.execution_status,
            'evaluation_status': query.evaluation_status,
            'start_date': query.start_date,
            'end_date': query.end_date,
            'page': query.page,
            'per_page': query.per_page,
        }
        result = _cherry_pick_acl.list_candidates(payload)
        if not result.get('success'):
            return error_response(result.get('message', '查询挑选候选失败'))
        return success_response(result.get('data') or {})

    # INT-1496 §8.1：挑选向导阶段 1 可挑选任务清单（替代候选首页 200 行客户端聚合）。
    # 网关只做参数校验与透传——聚合（GROUP BY t.id）与分页在 task_service 仓储
    # 单条 SQL 内完成，响应体只含任务级字段，不接收候选结果行。
    @staticmethod
    def list_pickable_tasks():
        try:
            query = _parse_query_params(CherryPickPickableTasksQuery)
        except Exception as e:
            return error_response(f"数据验证失败: {e}")
        payload = {
            'keyword': (query.keyword or '').strip() or None,
            'status': query.status.value if query.status else None,
            'sort_by': query.sort_by,
            'sort_order': query.sort_order,
            'page': query.page,
            'per_page': query.per_page,
        }
        result = _cherry_pick_acl.list_pickable_tasks(payload)
        if not result.get('success'):
            return error_response(result.get('message', '查询可挑选任务失败'),
                                  http_code=_CODE_HTTP_MAP.get(result.get('code'), 400))
        return success_response(result.get('data') or {})

    # INT-577 §11-4：全选当前筛选（POST body 携带与 candidates 相同筛选条件，
    # 返回命中全部 result_id 集合；网关不做页码分页，task_service 端拉全量）
    @staticmethod
    def select_all_candidates():
        try:
            body = request.get_json() or {}
        except Exception:
            body = {}
        payload = {
            'task_ids': _split_ints(body.get('task_ids')),
            'device_ids': _split_ints(body.get('device_ids')),
            'case_ids': _split_strs(body.get('case_ids')),
            'case_keyword': (body.get('case_keyword') or '').strip() or None,
            'execution_status': body.get('execution_status'),
            'evaluation_status': body.get('evaluation_status'),
            'start_date': body.get('start_date'),
            'end_date': body.get('end_date'),
            'select_all': True,
        }
        result = _cherry_pick_acl.list_candidates(payload)
        if not result.get('success'):
            return error_response(result.get('message', '全选当前筛选失败'))
        return success_response(result.get('data') or {})

    # ---- 下单（三出口 + 预览）----

    @staticmethod
    def preview():
        result = _cherry_pick_acl.preview()
        if not result.get('success'):
            return error_response(result.get('message', '合并预览失败'),
                                  http_code=_CODE_HTTP_MAP.get(result.get('code'), 400))
        return success_response(result.get('data') or {})

    @staticmethod
    def checkout():
        try:
            req = CherryPickCheckoutRequest.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"数据验证失败: {e}")
        payload = {
            'action': req.action,
            'name': req.name,
            'description': req.description,
            'algorithm_type': req.algorithm_type,
            'algorithm_params': req.algorithm_params,
            'config': req.config,
        }
        result = _cherry_pick_acl.checkout(payload)
        if not result.get('success'):
            return error_response(result.get('message', '下单失败'),
                                  http_code=_CODE_HTTP_MAP.get(result.get('code'), 400))
        return success_response(result.get('data') or {}, result.get('message', '下单成功'))

    # ---- 溯源 ----

    @staticmethod
    def get_source(task_id):
        result = _cherry_pick_acl.get_source(task_id)
        if not result.get('success'):
            return error_response(result.get('message', '未找到该任务的挑选溯源'),
                                  http_code=_CODE_HTTP_MAP.get(result.get('code'), 400))
        return success_response(result.get('data') or {})
