"""
统一响应处理模块
确保前后端数据格式的一致性
"""

from flask import jsonify, Response
from pydantic.alias_generators import to_camel
from typing import Any, Dict, List, Optional
from backend.utils.web.error_codes import ErrorCode


def format_pagination_response(
    items: List[Any],
    total: int,
    page: int,
    per_page: int,
    pages: int
) -> Dict[str, Any]:
    """
    格式化分页响应数据
    确保前后端分页参数命名一致
    """
    return {
        'items': items,
        'total': total,
        'page': page,
        'perPage': per_page,
        'pages': pages
    }


def _convert_keys_to_camel(data: Any) -> Any:
    if isinstance(data, list):
        return [_convert_keys_to_camel(item) for item in data]
    if isinstance(data, dict):
        out: Dict[Any, Any] = {}
        for k, v in data.items():
            if isinstance(k, str):
                key = to_camel(k)
            else:
                key = k
            out[key] = _convert_keys_to_camel(v)
        return out
    return data


def format_response(
    code: int = ErrorCode.SUCCESS,
    message: str = "Success",
    data: Any = None,
    detail: Any = None
) -> Dict[str, Any]:
    """
    统一格式化响应数据
    确保所有响应具有一致的格式
    """
    response_data = {
        'success': int(code) == ErrorCode.SUCCESS or int(code) == 200,
        'code': int(code),
        'message': message,
    }
    
    if data is not None:
        response_data['data'] = data
    
    if detail is not None:
        response_data['detail'] = detail
    
    return response_data


def success_response(
    data: Any = None,
    message: str = "Success",
    code: int = ErrorCode.SUCCESS,
    http_code: int = 200
) -> Response:
    """
    统一成功响应格式
    """
    formatted_data = _convert_keys_to_camel(data) if data is not None else None
    response = jsonify(format_response(code=code, message=message, data=formatted_data))
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response, http_code


def error_response(
    message: str = "Error",
    code: int = ErrorCode.OPERATION_FAILED,
    http_code: int = 400,
    errors: Optional[List[str]] = None,
    detail: Any = None
) -> Response:
    """
    统一错误响应格式
    """
    response_data = format_response(code=code, message=message, detail=detail)
    
    if errors:
        response_data['errors'] = errors
    
    response = jsonify(response_data)
    response.headers['Content-Type'] = 'application/json; charset=utf-8'
    return response, http_code


def paginated_success_response(
    items: List[Any],
    total: int,
    page: int,
    per_page: int,
    message: str = "Success",
    http_code: int = 200
) -> Response:
    """
    统一分页成功响应格式
    确保分页参数命名与前端 PaginationComponent 一致
    """
    pages = (total + per_page - 1) // per_page if total > 0 else 0
    
    pagination_data = format_pagination_response(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages
    )
    
    return success_response(
        data=pagination_data,
        message=message,
        http_code=http_code
    )


class ResponseBuilder:
    """
    响应构建器
    提供链式调用方式构建复杂响应
    """
    
    def __init__(self):
        self._data = None
        self._message = "Success"
        self._code = ErrorCode.SUCCESS
        self._detail = None
        self._http_code = 200
    
    def data(self, data: Any) -> 'ResponseBuilder':
        self._data = data
        return self
    
    def message(self, message: str) -> 'ResponseBuilder':
        self._message = message
        return self
    
    def code(self, code: int) -> 'ResponseBuilder':
        self._code = code
        return self
    
    def detail(self, detail: Any) -> 'ResponseBuilder':
        self._detail = detail
        return self
    
    def http_code(self, http_code: int) -> 'ResponseBuilder':
        self._http_code = http_code
        return self
    
    def success(self) -> Response:
        return success_response(
            data=self._data,
            message=self._message,
            code=self._code,
            http_code=self._http_code
        )
    
    def error(self) -> Response:
        return error_response(
            message=self._message,
            code=self._code,
            http_code=self._http_code,
            detail=self._detail
        )
    
    def paginated(self, items: List[Any], total: int, page: int, per_page: int) -> Response:
        return paginated_success_response(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            message=self._message,
            http_code=self._http_code
        )


def create_success_response_builder() -> ResponseBuilder:
    """创建成功响应构建器"""
    return ResponseBuilder()


def create_error_response_builder() -> ResponseBuilder:
    """创建错误响应构建器"""
    return ResponseBuilder().code(ErrorCode.OPERATION_FAILED)
