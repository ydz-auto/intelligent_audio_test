# -*- coding: utf-8 -*-
"""字段映射共享工具

将 gRPC 调用返回的 dict（algo_get_field_mappings 结果）
包装为提供方法接口的对象，供各服务统一使用。
"""


class FieldMapperWrapper:
    """字段映射包装器

    将原始 dict 数据包装为与原 FieldMappingQueryHandler
    兼容的方法接口，供各服务 domain 层调用。
    """

    def __init__(self, data: dict):
        self._data = data or {}

    # ========== 兼容 dict 访问 ==========

    def get(self, key, default=None):
        return self._data.get(key, default)

    def __getitem__(self, key):
        return self._data[key]

    def __contains__(self, key):
        return key in self._data

    # ========== 原方法接口 ==========

    def get_evaluation_input_fields(self, algorithm_type: str = '') -> dict:
        """获取评估输入字段定义"""
        return self._data.get('original', {}).get('evaluation', {}).get('input', {})

    def get_mapped_device_output_field_keys(self, algorithm_type: str = '') -> list:
        """获取映射后的设备输出字段 key 列表"""
        mapped_device_output = self._data.get('mapped', {}).get('device', {})
        if isinstance(mapped_device_output, dict):
            return list(mapped_device_output.keys())
        return [f.get('code') for f in mapped_device_output if isinstance(f, dict)]

    def get_mapped_device_output(self, algorithm_type: str = '') -> dict:
        """获取映射后的设备输出字段（raw dict，key=target_param）"""
        return self._data.get('mapped', {}).get('device', {}) or {}

    def get_mapped_device_output_fields(self, algorithm_type: str = '') -> dict:
        """获取映射后的设备输出字段（key=target_param，value=字段定义）

        mapped.device 是扁平结构，key 为 target_param，无嵌套 output 层级。
        """
        return self._data.get('mapped', {}).get('device', {}) or {}

    def get_mapped_device_fields_list(self, algorithm_type: str = '') -> list:
        """获取映射后的设备字段列表（统一为 list 结构，兼容 dict/list）"""
        mapped_device = self._data.get('mapped', {}).get('device', {})
        if isinstance(mapped_device, dict):
            return [{'code': k, **(v if isinstance(v, dict) else {})} for k, v in mapped_device.items()]
        if isinstance(mapped_device, list):
            return mapped_device
        return []
