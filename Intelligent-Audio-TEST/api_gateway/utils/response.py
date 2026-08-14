"""
统一响应工具 —— FastAPI 兼容

success_response / error_response 返回 (dict_payload, http_code) 元组，
路由层用 JSONResponse 包装，或由 FastAPI 自动序列化。
"""
import logging
import math
import functools
from typing import Type, TypeVar, List, Any, Tuple, Dict, Optional, Callable
from pydantic import BaseModel
from pydantic.alias_generators import to_camel
from api_gateway.utils.error_codes import ErrorCode
from api_gateway.schemas.response import ApiResponse

logger = logging.getLogger(__name__)

T = TypeVar('T', bound=BaseModel)


def model_from_orm(model_class: Type[T], orm_obj: Any) -> T:
    return model_class.model_validate(orm_obj)


def models_from_orm(model_class: Type[T], orm_objs: List[Any]) -> List[T]:
    return [model_class.model_validate(obj) for obj in orm_objs]


def _normalize_payload_data(value):
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    try:
        import numpy as np
        if isinstance(value, (np.floating, np.integer)):
            if isinstance(value, np.floating) and (np.isnan(value) or np.isinf(value)):
                return None
            return value.item()
    except Exception:
        logger.debug("numpy 不可用或类型转换失败", exc_info=True)
    try:
        import pandas as pd
        if not isinstance(value, (BaseModel, list, dict)) and pd.isna(value):
            return None
    except Exception:
        logger.debug("pandas 不可用或 NaN 检测失败", exc_info=True)

    if isinstance(value, BaseModel):
        dumped = value.model_dump(by_alias=True, exclude_none=True)
        return _normalize_payload_data(dumped)
    if isinstance(value, list):
        return [_normalize_payload_data(v) for v in value]
    if isinstance(value, dict):
        new_data = {}
        for k, v in value.items():
            if isinstance(k, str) and '_' in k:
                new_key = to_camel(k)
            else:
                new_key = k
            new_data[new_key] = _normalize_payload_data(v)
        return new_data
    return value


def convert_keys_to_camel(data):
    if isinstance(data, list):
        return [convert_keys_to_camel(i) for i in data]
    if isinstance(data, dict):
        new_data = {}
        for k, v in data.items():
            if isinstance(k, str) and '_' in k:
                new_key = to_camel(k)
            else:
                new_key = k
            new_data[new_key] = convert_keys_to_camel(v)
        return new_data
    return data


def success_response(data=None, message="Success", code=ErrorCode.SUCCESS, http_code=200) -> Tuple[Dict, int]:
    formatted_data = _normalize_payload_data(data) if data is not None else None
    payload = ApiResponse.ok(data=formatted_data, message=message, code=int(code))
    return payload.model_dump(by_alias=True, exclude_none=True), http_code


def error_response(message="Error", code=ErrorCode.OPERATION_FAILED, http_code=400, errors=None, detail=None) -> Tuple[Dict, int]:
    formatted_detail = _normalize_payload_data(detail) if detail is not None else None
    payload = ApiResponse.fail(message=message, code=int(code), detail=formatted_detail)
    return payload.model_dump(by_alias=True, exclude_none=True), http_code


def wrap_grpc_response(
    result: Dict[str, Any],
    data_converter: Optional[Callable[[Any], Any]] = None,
    default_error_msg: str = '操作失败',
    error_code_mapping: Optional[Dict[int, Tuple[str, int]]] = None,
) -> Tuple[Dict, int]:
    """统一的 gRPC 响应包装器。

    封装 Service 层中重复的「判断 success → 转换响应」逻辑。

    :param result: gRPC 调用返回的字典
    :param data_converter: 数据转换函数（如将 dict 转 Pydantic 模型）
    :param default_error_msg: 默认错误消息
    :param error_code_mapping: 错误码映射，如 {404: ('未找到资源', 404)}
    :return: (response_dict, http_code) 元组
    """
    if result.get('success'):
        data = result.get('data')
        if data_converter and data is not None:
            data = data_converter(data)
        return success_response(data)

    error_msg = result.get('message') or default_error_msg
    error_code = result.get('code', 400)
    http_code = 400

    import logging as _logging
    _logging.getLogger(__name__).warning("gRPC error: msg=%s, code=%s", error_msg, error_code)

    if error_code_mapping and error_code in error_code_mapping:
        mapped_msg, mapped_http_code = error_code_mapping[error_code]
        error_msg = mapped_msg or error_msg
        http_code = mapped_http_code

    return error_response(error_msg, code=error_code, http_code=http_code)


def format_response(code=ErrorCode.SUCCESS, message="Success", data=None, detail=None):
    return {
        "success": int(code) == ErrorCode.SUCCESS or int(code) == 200,
        "code": int(code),
        "message": message,
        "data": data,
        "detail": detail
    }


def db_transaction(func):
    """TODO(DB穿透): 此装饰器仍通过 get_db_session() 做 commit/rollback。
    应由各后端服务通过 gRPC 自行管理事务，网关层不应直接操作 DB 会话。
    待 gRPC 迁移完成后移除此装饰器。当前 DB 调用已用 try/except 包裹，失败时不抛出。
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        from shared.models.database import get_db_session
        try:
            result = func(*args, **kwargs)
            if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], dict):
                return result
            if isinstance(result, dict):
                return result
            try:
                get_db_session().commit()
            except Exception:
                logger.warning("db_transaction commit 失败", exc_info=True)
            return success_response(None, result)
        except Exception as e:
            try:
                get_db_session().rollback()
            except Exception:
                logger.warning("db_transaction rollback 失败", exc_info=True)
            return error_response(str(e))
    return wrapper
