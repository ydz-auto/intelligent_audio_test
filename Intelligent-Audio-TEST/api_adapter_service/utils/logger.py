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
