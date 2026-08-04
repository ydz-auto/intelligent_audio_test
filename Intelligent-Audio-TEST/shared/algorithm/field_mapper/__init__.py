# -*- coding: utf-8 -*-
"""统一字段映射器

职责：
- 提供设备/API/评估的字段定义查询
- 字段类型转换和数据格式转换
- 构建API请求数据
- 不负责参数生成，只负责字段映射转换

本包将原 field_mapper.py 拆分为多个混入模块，此处重新导出以保持向后兼容：
    from shared.algorithm.field_mapper import get_field_mapper
    from shared.algorithm.field_mapper import FieldMapper
"""

from .mapper import FieldMapper, get_field_mapper

__all__ = ['FieldMapper', 'get_field_mapper']
