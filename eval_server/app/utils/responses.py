import logging
from flask import jsonify, request

# 配置日志
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('api_logger')

# 标准错误码
CODE_SUCCESS = 0
CODE_BUSINESS_ERROR = 3000
CODE_CONCURRENCY_EXCEEDED = 3001
CODE_VALIDATION_ERROR = 4000
CODE_SERVER_ERROR = 5000

def success_response(data=None, msg="success", code=CODE_SUCCESS):
    response = {
        "code": code,
        "msg": msg,
        "data": data or {}
    }
    # 记录请求和响应日志
    logger.info(f"Request: {request.method} {request.path} - Headers: {dict(request.headers)} - Body: {request.get_json() if request.is_json else request.data}")
    logger.info(f"Response: {code} {msg} - Data: {data}")
    return jsonify(response), 200

def error_response(msg="error", code=CODE_BUSINESS_ERROR, status_code=400, data=None):
    response = {
        "code": code,
        "msg": msg,
        "data": data or {}
    }
    # 记录请求和响应日志
    logger.info(f"Request: {request.method} {request.path} - Headers: {dict(request.headers)} - Body: {request.get_json() if request.is_json else request.data}")
    logger.error(f"Response: {code} {msg} - Status: {status_code} - Data: {data}")
    return jsonify(response), status_code
