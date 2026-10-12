# -*- coding: utf-8 -*-
"""网关统一异常处理器（INT-233）。

service 层 model_validate（查询参数 / 请求体）抛出的 pydantic ValidationError
此前无统一出口：任一列表端点收到非法类型查询参数（如 page=abc、
testcases?dimension_id=abc）即以 500 裸错误漏出。此处统一捕获转
422 结构化错误（{"success": false, "code": ...}），由 create_app 注册；
测试侧用最小 app 复用同一注册函数，保证行为一致。
"""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from api_gateway.utils.error_codes import ErrorCode
from api_gateway.utils.response import error_response

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """注册网关级统一异常处理器（create_app 与测试最小 app 共用）。"""

    @app.exception_handler(ValidationError)
    async def _handle_pydantic_validation_error(request: Request, exc: ValidationError):
        # 响应侧模型构造失败（服务端数据契约破坏）也会落入此处，
        # 422 之外在服务端留 ERROR 级堆栈，保证可诊断
        logger.error("ValidationError 未在服务层捕获: %s", exc, exc_info=exc)
        payload, _ = error_response(
            f"参数验证失败: {exc}",
            code=ErrorCode.INVALID_PARAMS,
            http_code=422,
        )
        return JSONResponse(status_code=422, content=payload)
