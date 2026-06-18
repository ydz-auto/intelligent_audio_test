from flask import jsonify, Response
import math
from typing import Type, TypeVar, List, Any
from pydantic import BaseModel
from pydantic.alias_generators import to_camel
from backend.utils.web.error_codes import ErrorCode
from backend.schemas.response import ApiResponse

T = TypeVar('T', bound=BaseModel)


def model_from_orm(model_class: Type[T], orm_obj: Any) -> T:
    """从 ORM 对象创建 Pydantic 模型"""
    return model_class.model_validate(orm_obj)


def models_from_orm(model_class: Type[T], orm_objs: List[Any]) -> List[T]:
    """从 ORM 对象列表创建 Pydantic 模型列表"""
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
        pass
    try:
        import pandas as pd
        if not isinstance(value, (BaseModel, list, dict)) and pd.isna(value):
            return None
    except Exception:
        pass

    if isinstance(value, BaseModel):
        return value.model_dump(by_alias=True, exclude_none=True)
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
    """将字典中的snake_case键名转换为camelCase，只转换包含下划线的键"""
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

# 统一成功响应格式
def success_response(data=None, message="Success", code=ErrorCode.SUCCESS, http_code=200):
    formatted_data = _normalize_payload_data(data) if data is not None else None
    payload = ApiResponse.ok(data=formatted_data, message=message, code=int(code))
    response = jsonify(payload.model_dump(by_alias=True, exclude_none=True))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response, http_code

# 统一错误响应格式
def error_response(message="Error", code=ErrorCode.OPERATION_FAILED, http_code=400, errors=None, detail=None):
    formatted_detail = _normalize_payload_data(detail) if detail is not None else None
    payload = ApiResponse.fail(message=message, code=int(code), detail=formatted_detail)
    response = jsonify(payload.model_dump(by_alias=True, exclude_none=True))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response, http_code

def format_response(code=ErrorCode.SUCCESS, message="Success", data=None, detail=None):
    return {
        "success": int(code) == ErrorCode.SUCCESS or int(code) == 200,
        "code": int(code),
        "message": message,
        "data": data,
        "detail": detail
    }
