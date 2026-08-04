# -*- coding: utf-8 -*-
"""Logging utility for api_adapter_service."""

import logging
import sys

_formatter = logging.Formatter(
    '[%(asctime)s] %(levelname)-8s %(name)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
)

_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(_formatter)

logger = logging.getLogger('api_adapter')
logger.setLevel(logging.INFO)
if not logger.handlers:
    logger.addHandler(_handler)

# 将 DatabaseLogHandler 挂到 root logger，使标准 logging.getLogger() 调用也走分流逻辑
from shared.utils.log_handler import get_db_handler
_root = logging.getLogger()
if not any(isinstance(h, get_db_handler().__class__) for h in _root.handlers):
    _root.addHandler(get_db_handler())
    _root.setLevel(logging.INFO)
