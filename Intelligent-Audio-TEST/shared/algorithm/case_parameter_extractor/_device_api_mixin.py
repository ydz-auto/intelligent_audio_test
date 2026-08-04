# -*- coding: utf-8 -*-
"""DeviceApiParamsMixin - 提供设备驱动参数与 API 调用参数构建

拆分自原 case_parameter_extractor.py 的 CaseParameterExtractor：
- get_device_params
- _build_device_params
- get_api_params
- _build_api_params
"""

from typing import Dict, List, Any

from shared.utils.log_handler import log_not_emit


class DeviceApiParamsMixin:
    """设备/API 参数构建 mixin"""

    @classmethod
    def get_device_params(cls, case_config: Dict) -> Dict[str, Any]:
        """获取设备驱动参数"""
        algorithm_type = cls.get_algorithm_type(case_config)
        if algorithm_type == 'unknown':
            log_not_emit('WARNING', 'case_parameter_extractor', 'Cannot get device params: algorithm_type is unknown', category='algorithm')
            return {}

        loader = cls._get_loader()
        device_params = loader.get_device_params(algorithm_type)
        if not device_params:
            log_not_emit('WARNING', 'case_parameter_extractor', f'No device params found for algorithm: {algorithm_type}', category='algorithm')
            return {}

        params = cls.get_algorithm_params(case_config)
        result = cls._build_device_params(algorithm_type, params, device_params)
        log_not_emit('DEBUG', 'case_parameter_extractor', f'Built device params for {algorithm_type}: {list(result.keys())}', category='algorithm')
        return result

    @classmethod
    def _build_device_params(cls, algorithm_type: str, algorithm_params: Dict, device_params_config: List) -> Dict[str, Any]:
        """构建设备驱动参数"""
        result = {}
        for param in device_params_config:
            if param.get('direction') == 'input':
                code = param['code']
                value = algorithm_params.get(code)
                if value is not None:
                    result[code] = value
                elif param.get('default_value'):
                    result[code] = param['default_value']
        return result

    @classmethod
    def get_api_params(cls, case_config: Dict) -> Dict[str, Any]:
        """获取API调用参数"""
        algorithm_type = cls.get_algorithm_type(case_config)
        if algorithm_type == 'unknown':
            log_not_emit('WARNING', 'case_parameter_extractor', 'Cannot get api params: algorithm_type is unknown', category='algorithm')
            return {}

        loader = cls._get_loader()
        api_params = loader.get_api_params(algorithm_type)
        if not api_params:
            log_not_emit('WARNING', 'case_parameter_extractor', f'No api params found for algorithm: {algorithm_type}', category='algorithm')
            return {}

        params = cls.get_algorithm_params(case_config)
        result = cls._build_api_params(algorithm_type, params, api_params)
        log_not_emit('DEBUG', 'case_parameter_extractor', f'Built api params for {algorithm_type}: {list(result.keys())}', category='algorithm')
        return result

    @classmethod
    def _build_api_params(cls, algorithm_type: str, algorithm_params: Dict, api_params_config: List) -> Dict[str, Any]:
        """构建API调用参数"""
        result = {}
        for param in api_params_config:
            if param.get('direction') == 'input':
                code = param['code']
                value = algorithm_params.get(code)
                if value is not None:
                    result[code] = value
                elif param.get('default_value'):
                    result[code] = param['default_value']
        return result
