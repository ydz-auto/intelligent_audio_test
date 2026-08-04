# -*- coding: utf-8 -*-
"""配置访问混入

封装对配置加载器的访问，以及基于参数/映射派生的 case/字段代码查询。
"""

from typing import Dict, List, Any


class ConfigAccessMixin:
    """配置访问混入类

    依赖宿主类属性 ``self._loader``。
    """

    def _get_device_params(self, algorithm_type: str) -> List[Dict[str, Any]]:
        """获取设备参数"""
        return self._loader.get_device_params(algorithm_type)

    def _get_api_params(self, algorithm_type: str) -> List[Dict[str, Any]]:
        """获取API参数"""
        return self._loader.get_api_params(algorithm_type)

    def _get_param_mappings(self, algorithm_type: str) -> Dict[str, List[Dict[str, Any]]]:
        """获取参数映射"""
        # 先检查配置是否变化，刷新缓存
        self._loader.reload_if_changed()
        return {
            'device': self._loader.get_param_mapping(algorithm_type, 'device'),
            'api': self._loader.get_param_mapping(algorithm_type, 'api'),
            'case': self._loader.get_param_mapping(algorithm_type, 'case'),
            'reference': self._loader.get_param_mapping(algorithm_type, 'reference'),
            'evaluation': self._loader.get_param_mapping(algorithm_type, 'evaluation')
        }

    def _get_algorithm_extra_config(self, algorithm_type: str) -> Dict[str, Any]:
        """获取算法额外配置"""
        device_params = self._get_device_params(algorithm_type)
        api_params = self._get_api_params(algorithm_type)
        params = device_params + api_params

        config = {
            'needs_extra_params': False,
            'case_fields': {},
            'query_fields': {},
            'format_strings': {},
            'db_model': None,
            'db_id_field': None,
            'db_lang_fields': {},
            'default_lang': {},
            'output_keys': {},
        }

        for param in params:
            code = param.get('code', '')
            param_type = param.get('param_type', '')
            source = param.get('source', '')
            param_model = param.get('model', '')

            if source in ['case_table', 'case_field'] or param_type in ['direction', 'language', 'voice', 'model']:
                config['needs_extra_params'] = True
                config['case_fields'][code] = code

                if param_model:
                    config['db_model'] = param_model

                if 'format' in param:
                    config['format_strings'][code] = param.get('format')
                elif 'direction' in code.lower():
                    config['format_strings'][code] = '{source}2{target}'
                    config['output_keys']['direction'] = code
                elif 'source' in code.lower() and 'lang' in code.lower():
                    config['output_keys']['source_lang'] = code
                elif 'target' in code.lower() and 'lang' in code.lower():
                    config['output_keys']['target_lang'] = code

            if 'id' in code.lower() and param_type in ['direction', 'language']:
                config['query_fields'][code] = code
                if not config.get('db_id_field'):
                    config['db_id_field'] = code

        mappings = self._get_param_mappings(algorithm_type)
        for comp_type, comp_mappings in mappings.items():
            for mapping in comp_mappings:
                source = mapping.get('source', '')
                source_param = mapping.get('source_param', '')

                if source in ['case_table', 'case_field']:
                    config['needs_extra_params'] = True
                    config['case_fields'][source_param] = source_param

        if config['case_fields']:
            config['needs_extra_params'] = True

        return config

    def get_case_fields(self, algorithm_type: str) -> Dict[str, str]:
        """获取算法需要的case表字段"""
        case_fields = {}

        device_params = self._get_device_params(algorithm_type)
        api_params = self._get_api_params(algorithm_type)
        params = device_params + api_params

        for param in params:
            param_code = param.get('code', '')
            param_type = param.get('param_type', '')
            source = param.get('source', '')

            if source == 'case_table' or param_type in ['direction', 'language']:
                case_fields[param_code] = param_code

        mappings = self._get_param_mappings(algorithm_type)
        for comp_type, comp_mappings in mappings.items():
            for mapping in comp_mappings:
                source_param = mapping.get('source_param', '')
                target_key = mapping.get('target_key', source_param)
                source = mapping.get('source', '')

                if source == 'case_table':
                    case_fields[target_key] = source_param

        return case_fields

    def get_required_case_fields(self, algorithm_type: str) -> List[str]:
        """获取必需的case表字段"""
        required_fields = []

        device_params = self._get_device_params(algorithm_type)
        api_params = self._get_api_params(algorithm_type)
        params = device_params + api_params

        for param in params:
            param_code = param.get('code', '')
            source = param.get('source', '')
            required = param.get('required', False)

            if source == 'case_table' and required:
                required_fields.append(param_code)

        return required_fields

    def get_output_field_codes(self, algorithm_type: str, field_category: str = 'result') -> str:
        """获取算法输出字段代码"""
        device_params = self._get_device_params(algorithm_type)
        api_params = self._get_api_params(algorithm_type)
        params = device_params + api_params

        for param in params:
            code = param.get('code', '')
            param_type = param.get('param_type', '')

            if param_type == 'output' or 'result' in code.lower():
                if field_category == 'result':
                    return code
                if field_category in code.lower():
                    return code

        return self._get_default_output_field(algorithm_type)

    def _get_default_output_field(self, algorithm_type: str) -> str:
        """获取默认输出字段"""
        mappings = self._get_param_mappings(algorithm_type)

        for comp_type in ['device', 'api', 'evaluation']:
            comp_mappings = mappings.get(comp_type, [])
            for mapping in comp_mappings:
                if mapping.get('direction') == 'output':
                    return mapping.get('target_key', 'result')

        return 'result'

    def get_reference_field_codes(self, algorithm_type: str) -> Dict[str, str]:
        """获取参考文本字段代码"""
        device_params = self._get_device_params(algorithm_type)
        api_params = self._get_api_params(algorithm_type)
        params = device_params + api_params

        field_codes = {
            'reference': [],
            'input_reference': None,
            'output_reference': None,
            'input_field': None,
            'output_field': None,
        }

        for param in params:
            code = param.get('code', '')
            param_type = param.get('param_type', '')
            ui_group = param.get('ui_group', '')

            if param_type == 'reference':
                field_codes['reference'].append(code)
                if ui_group == 'input':
                    field_codes['input_reference'] = code
                elif ui_group == 'output':
                    field_codes['output_reference'] = code

            if 'input' in code.lower() and not field_codes['input_field']:
                field_codes['input_field'] = code
            if 'output' in code.lower() or 'result' in code.lower():
                if not field_codes['output_field']:
                    field_codes['output_field'] = code

        mappings = self._get_param_mappings(algorithm_type)

        for comp_type in ['device', 'api', 'evaluation']:
            comp_mappings = mappings.get(comp_type, [])
            for mapping in comp_mappings:
                direction = mapping.get('source_direction', mapping.get('direction', 'output'))
                target_key = mapping.get('target_key', mapping.get('source_param'))

                if direction == 'output' and not field_codes.get('output_field'):
                    field_codes['output_field'] = target_key
                elif direction == 'input' and not field_codes.get('input_field'):
                    field_codes['input_field'] = target_key

        return field_codes
