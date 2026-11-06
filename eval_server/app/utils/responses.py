import logging
from flask import jsonify, request

logger = logging.getLogger('api')

# 标准错误码
CODE_SUCCESS = 0
CODE_BUSINESS_ERROR = 3000
CODE_CONCURRENCY_EXCEEDED = 3001
CODE_VALIDATION_ERROR = 4000
CODE_SERVER_ERROR = 5000

_SENSITIVE_HEADERS = {'authorization', 'x-api-key', 'cookie', 'set-cookie'}


def _filter_headers(headers):
    """过滤敏感 header，用 *** 替换"""
    filtered = dict(headers)
    for key in list(filtered.keys()):
        if key.lower() in _SENSITIVE_HEADERS:
            filtered[key] = '***'
    return filtered


def _get_request_body_for_logging():
    """获取请求体用于日志记录，对 multipart 请求只记录字段名和文件名"""
    content_type = request.content_type or ''
    if 'multipart/form-data' in content_type:
        form_fields = list(request.form.keys())
        file_names = [f.filename for f in request.files.values() if f.filename]
        return f"multipart form fields: {form_fields}, files: {file_names}"
    if request.is_json:
        return request.get_json()
    data = request.data
    if len(data) > 2048:
        return f"<binary data, {len(data)} bytes>"
    return data


def success_response(data=None, msg="success", code=CODE_SUCCESS):
    response = {
        "code": code,
        "msg": msg,
        "data": data or {}
    }
    logger.info(f"Request: {request.method} {request.path} - Headers: {_filter_headers(request.headers)} - Body: {_get_request_body_for_logging()}")
    logger.info(f"Response: {code} {msg} - Data: {data}")
    return jsonify(response), 200


def error_response(msg="error", code=CODE_BUSINESS_ERROR, status_code=400, data=None):
    response = {
        "code": code,
        "msg": msg,
        "data": data or {}
    }
    logger.info(f"Request: {request.method} {request.path} - Headers: {_filter_headers(request.headers)} - Body: {_get_request_body_for_logging()}")
    logger.error(f"Response: {code} {msg} - Status: {status_code} - Data: {data}")
    return jsonify(response), status_code
