# -*- coding: utf-8 -*-
"""字段查询混入

提供按算法类型查询设备/API/评估等输入输出字段的便捷方法。
"""

from typing import Dict, List, Any


class FieldQueryMixin:
    """字段查询混入类

    依赖宿主类方法：``_get_field_definitions``、``_get_device_params``、
    ``get_device_output_fields``、``get_mapped_device_output_fields``。
    """

    def get_device_input_fields(self, algorithm_type: str) -> Dict[str, Any]:
        """获取设备输入字段"""
        field_defs = self._get_field_definitions(algorithm_type)
        return field_defs.get('original', {}).get('device', {}).get('input', {})

    def get_device_output_fields(self, algorithm_type: str) -> Dict[str, Any]:
        """获取设备输出字段"""
        field_defs = self._get_field_definitions(algorithm_type)
        return field_defs.get('original', {}).get('device', {}).get('output', {})

    def get_device_output_field_keys(self, algorithm_type: str) -> List[str]:
        """获取设备输出字段键列表"""
        output_fields = self.get_device_output_fields(algorithm_type)
        return list(output_fields.keys())

    def get_api_input_fields(self, algorithm_type: str) -> Dict[str, Any]:
        """获取API输入字段"""
        field_defs = self._get_field_definitions(algorithm_type)
        return field_defs.get('original', {}).get('api', {}).get('input', {})

    def get_api_output_fields(self, algorithm_type: str) -> Dict[str, Any]:
        """获取API输出字段"""
        field_defs = self._get_field_definitions(algorithm_type)
        return field_defs.get('original', {}).get('api', {}).get('output', {})

    def get_evaluation_input_fields(self, algorithm_type: str) -> Dict[str, Any]:
        """获取评估输入字段"""
        field_defs = self._get_field_definitions(algorithm_type)
        return field_defs.get('original', {}).get('evaluation', {}).get('input', {})

    def get_evaluation_output_fields(self, algorithm_type: str) -> Dict[str, Any]:
        """获取评估输出字段"""
        field_defs = self._get_field_definitions(algorithm_type)
        return field_defs.get('original', {}).get('evaluation', {}).get('output', {})

    def get_mapped_device_output_fields(self, algorithm_type: str) -> Dict[str, Any]:
        """获取设备输出字段（映射后）"""
        field_defs = self._get_field_definitions(algorithm_type)
        return field_defs.get('mapped', {}).get('device', {}).get('output', {})

    def get_mapped_api_output_fields(self, algorithm_type: str) -> List[Dict]:
        """获取API输出字段（映射后）"""
        field_defs = self._get_field_definitions(algorithm_type)
        return field_defs.get('mapped', {}).get('api', {}).get('output', [])

    def get_mapped_device_output_field_keys(self, algorithm_type: str) -> List[str]:
        """获取设备输出字段键列表（映射后）"""
        output_fields = self.get_mapped_device_output_fields(algorithm_type)
        if isinstance(output_fields, list):
            return [f.get('code') for f in output_fields]
        return list(output_fields.keys())

    def get_dimension_mapped_device_output_fields(self, algorithm_type: str, dimension_id: int) -> List[Dict]:
        """获取指定维度的设备输出字段映射（按维度分组）"""
        output_fields = self.get_mapped_device_output_fields(algorithm_type)
        if not isinstance(output_fields, list):
            return []
        # 按 dimension_id 过滤；dimension_id 为 None 的全局映射也保留
        result = []
        for f in output_fields:
            f_dim = f.get('dimension_id')
            if f_dim == dimension_id or f_dim is None:
                result.append(f)
        return result

    def get_dimension_mapped_device_output_field_keys(self, algorithm_type: str, dimension_id: int) -> List[str]:
        """获取指定维度的设备输出字段键列表"""
        output_fields = self.get_dimension_mapped_device_output_fields(algorithm_type, dimension_id)
        return [f.get('code') for f in output_fields]

    def get_device_output_field_codes_by_type(self, algorithm_type: str, param_type: str) -> List[str]:
        """根据 param_type 获取设备输出字段代码列表

        从 algorithm_device_params 中查找 direction='output' 且 param_type 匹配的字段。

        Args:
            algorithm_type: 算法类型
            param_type: 参数类型（如 'stm', 'rttm', 'text'）

        Returns:
            list: 匹配的字段代码列表
        """
        device_params = self._get_device_params(algorithm_type)
        return [
            p.get('code') for p in device_params
            if p.get('param_type') == param_type and p.get('direction') == 'output'
        ]

    def get_case_input_fields(self, algorithm_type: str) -> Dict[str, Any]:
        """获取用例参数字段"""
        field_defs = self._get_field_definitions(algorithm_type)
        return field_defs.get('case', {})

    def get_reference_input_fields(self, algorithm_type: str) -> Dict[str, Any]:
        """获取参考参数字段"""
        field_defs = self._get_field_definitions(algorithm_type)
        return field_defs.get('reference', {})
