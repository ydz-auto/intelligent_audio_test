"""统一的 JSON 响应工具

解决 FastAPI JSONResponse 不支持 datetime/Decimal 等类型的问题。
替代 Flask jsonify 的自动序列化能力。
"""
import json
from datetime import datetime, date, timedelta
from decimal import Decimal
from enum import Enum

from fastapi.responses import JSONResponse


def _default_encoder(obj):
    """处理 Flask jsonify 自动处理但 FastAPI 不处理的类型"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, timedelta):
        return obj.total_seconds()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, bytes):
        try:
            return obj.decode('utf-8')
        except Exception:
            return str(obj)
    if hasattr(obj, '__dict__') and hasattr(obj, 'to_dict') and callable(obj.to_dict):
        return obj.to_dict()
    raise TypeError(f'Object of type {obj.__class__.__name__} is not JSON serializable')


class CustomJSONResponse(JSONResponse):
    """支持 datetime/Decimal 等类型的 JSONResponse"""

    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(',', ':'),
            default=_default_encoder,
        ).encode('utf-8')


def to_response(result):
    """
    将 controller 返回的 (dict, int) tuple 转为 CustomJSONResponse。
    如果 result 已经是 Response 对象，直接返回。
    """
    if isinstance(result, tuple) and len(result) == 2:
        return CustomJSONResponse(content=result[0], status_code=result[1])
    return result
