# -*- coding: utf-8 -*-
"""API 领域服务 — 封装 API 相关的校验逻辑，纯逻辑，无 IO。"""
from __future__ import annotations

import re
from typing import Dict


class APIValidator:
    """API 校验领域服务

    封装对 API 配置（URL、HTTP 方法、请求头）的纯逻辑校验，
    不涉及任何 IO 依赖。
    """

    _URL_PATTERN = re.compile(r"^https?://[^\s]+$", re.IGNORECASE)
    _ALLOWED_METHODS = {"GET", "POST", "PUT", "DELETE", "PATCH"}

    @staticmethod
    def validate_url(url: str) -> bool:
        """校验 URL 合法性

        要求以 http/https 开头且不含空白字符。
        """
        if not isinstance(url, str) or not url.strip():
            return False
        return bool(APIValidator._URL_PATTERN.match(url.strip()))

    @staticmethod
    def validate_method(method: str) -> bool:
        """校验 HTTP 方法合法性"""
        if not isinstance(method, str):
            return False
        return method.upper() in APIValidator._ALLOWED_METHODS

    @staticmethod
    def validate_headers(headers: Dict) -> bool:
        """校验请求头字典合法性

        要求键为非空字符串，值为字符串类型。
        """
        if not isinstance(headers, dict):
            return False
        for key, value in headers.items():
            if not isinstance(key, str) or not key.strip():
                return False
            if not isinstance(value, str):
                return False
        return True
