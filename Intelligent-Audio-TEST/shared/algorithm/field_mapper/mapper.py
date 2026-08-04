# -*- coding: utf-8 -*-
"""统一字段映射器主类

组合各功能混入，实现单例模式的字段映射器。
"""

from typing import Dict
from threading import Lock

from ..algorithm_config_loader import get_config_loader
from shared.utils.log_handler import log_not_emit
from .transforms import TransformMixin
from .field_builder import FieldBuilderMixin
from .config_access import ConfigAccessMixin
from .field_query import FieldQueryMixin
from .data_conversion import DataConversionMixin


class FieldMapper(
    TransformMixin,
    FieldBuilderMixin,
    ConfigAccessMixin,
    FieldQueryMixin,
    DataConversionMixin,
):
    """
    统一字段映射器 - 单例模式

    提供设备/API/评估的字段映射和数据转换
    """

    _instance = None
    _instance_lock = Lock()
    _config_lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._loader = get_config_loader()
        self._field_cache: Dict[str, Dict] = {}
        self._transforms: Dict = {}
        self._register_builtin_transforms()
        log_not_emit('DEBUG', 'field_mapper', 'FieldMapper initialized', category='algorithm')

    def reload(self):
        """重新加载字段定义"""
        with self._config_lock:
            log_not_emit('INFO', 'field_mapper', 'Reloading field definitions', category='algorithm')
            self._field_cache.clear()


def get_field_mapper() -> FieldMapper:
    """获取字段映射器单例"""
    return FieldMapper()
