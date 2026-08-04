# -*- coding: utf-8 -*-
"""字段定义构建混入

负责根据设备/API 参数与映射关系构建原始字段定义与映射后字段定义。
"""

from typing import Dict, List, Any

from shared.utils.log_handler import log_not_emit


class FieldBuilderMixin:
    """字段定义构建混入类

    依赖宿主类方法：``_get_device_params``、``_get_api_params``、
    ``_get_param_mappings`` 以及 ``self._loader``。
    """

    def _build_field_definitions(self, algorithm_type: str) -> Dict[str, Any]:
        """构建字段定义"""
        from shared.utils.log_handler import log_not_emit

        log_not_emit('DEBUG', 'field_mapper', f'_build_field_definitions START for {algorithm_type}', category='algorithm')

        device_params = self._get_device_params(algorithm_type)
        log_not_emit('DEBUG', 'field_mapper', f'device_params count: {len(device_params)}', category='algorithm')
        api_params = self._get_api_params(algorithm_type)
        mappings = self._get_param_mappings(algorithm_type)
        log_not_emit('DEBUG', 'field_mapper', f'mappings keys: {list(mappings.keys())}', category='algorithm')

        log_not_emit('DEBUG', 'field_mapper', f'api mappings type: {type(mappings.get("api"))}', category='algorithm')
        if not isinstance(mappings.get('api'), list):
            log_not_emit('WARNING', 'field_mapper', f'api mappings is not a list!', category='algorithm')

        original_fields = {
            'device': {'input': {}, 'output': []},
            'api': {'input': {}, 'output': []},
            'case': {},
            'reference': {},
            'evaluation': {'input': {}, 'output': []}
        }

        mapped_fields = {
            'device': {'input': {}, 'output': []},
            'api': {'input': {}, 'output': []},
            'case': {},
            'reference': {},
            'evaluation': {'input': {}, 'output': []}
        }

        for param in device_params:
            code = param.get('code')
            direction = param.get('direction', 'output')
            if direction == 'input':
                original_fields['device']['input'][code] = {
                    'code': code,
                    'name': param.get('name', code),
                    'type': param.get('type', 'text'),
                    'source': 'case',
                    'required': param.get('required', False),
                    'default_value': param.get('default_value'),
                    'transform': 'none',
                    'param_type': param.get('type', 'text'),
                    'component_type': 'device'
                }
            else:
                original_fields['device']['output'].append({
                    'code': code,
                    'name': param.get('name', code),
                    'type': param.get('type', 'text'),
                    'source': 'device_output',
                    'required': param.get('required', False),
                    'default_value': param.get('default_value'),
                    'transform': 'none',
                    'param_type': param.get('type', 'text'),
                    'component_type': 'device'
                })

        for param in api_params:
            code = param.get('code')
            direction = param.get('direction', 'output')
            if direction == 'input':
                original_fields['api']['input'][code] = {
                    'code': code,
                    'name': param.get('name', code),
                    'type': param.get('type', 'text'),
                    'source': 'device',
                    'required': param.get('required', False),
                    'default_value': param.get('default_value'),
                    'transform': 'none',
                    'param_type': param.get('type', 'text'),
                    'component_type': 'api'
                }
            else:
                original_fields['api']['output'].append({
                    'code': code,
                    'name': param.get('name', code),
                    'type': param.get('type', 'text'),
                    'source': 'api',
                    'required': param.get('required', False),
                    'default_value': param.get('default_value'),
                    'transform': 'none',
                    'param_type': param.get('type', 'text'),
                    'component_type': 'api'
                })

        param_type_lookup = {}
        for param in device_params + api_params:
            code = param.get('code')
            p_type = param.get('param_type') or param.get('type', 'text')
            if code:
                param_type_lookup[code] = p_type

        reference_params = self._loader.get_reference_params(algorithm_type)
        for ref_param in reference_params:
            code = ref_param.get('code')
            p_type = ref_param.get('type', 'text')
            if code:
                param_type_lookup[code] = p_type

        eval_mappings = mappings.get('evaluation', [])
        for m in eval_mappings:
            target_param = m.get('target_param')
            source = m.get('source', 'api')
            source_param = m.get('source_param', '')
            resolved_type = param_type_lookup.get(source_param, 'text')
            original_fields['evaluation']['input'][target_param] = {
                'code': target_param,
                'name': m.get('dimension_name', target_param),
                'type': resolved_type,
                'source': source,
                'required': True,
                'transform': m.get('transform_type', 'none'),
                'param_type': resolved_type,
                'dimension_id': m.get('dimension_id'),
                'component_type': 'evaluation'
            }

        self._build_mapped_fields(algorithm_type, device_params, api_params, mappings, original_fields, mapped_fields)

        return {'original': original_fields, 'mapped': mapped_fields}

    def _build_mapped_fields(self, algorithm_type: str, device_params: List[Dict], api_params: List[Dict],
                            mappings: Dict, original_fields: Dict, mapped_fields: Dict):
        """构建映射字段"""
        device_mappings = mappings.get('device', [])
        api_mappings = mappings.get('api', [])
        case_mappings = mappings.get('case', [])
        reference_mappings = mappings.get('reference', [])

        for m in device_mappings:
            source_param = m.get('source_param')
            target_param = m.get('target_param')
            transform = m.get('transform_type', 'none')

            if source_param and target_param:
                # 使用列表保存映射，而不是字典（避免相同 target_param 被覆盖）
                mapped_fields['device']['output'].append({
                    'code': target_param,
                    'source_param': source_param,
                    'transform': transform,
                    'component_type': 'device'
                })

        for m in api_mappings:
            log_not_emit('DEBUG', 'field_mapper', f'Before api mapping, mapped_fields["api"]: {mapped_fields.get("api")}', category='algorithm')
            source_param = m.get('source_param')
            target_param = m.get('target_param')
            transform = m.get('transform_type', 'none')

            if source_param and target_param:
                mapped_fields['api']['output'].append({
                    'code': target_param,
                    'source_param': source_param,
                    'transform': transform,
                    'component_type': 'api'
                })

        for m in case_mappings:
            source_param = m.get('source_param')
            target_param = m.get('target_param')
            transform = m.get('transform_type', 'none')

            if source_param and target_param:
                mapped_fields['case'][target_param] = {
                    'code': target_param,
                    'source_param': source_param,
                    'transform': transform,
                    'component_type': 'case'
                }

        for m in reference_mappings:
            source_param = m.get('source_param')
            target_param = m.get('target_param')
            transform = m.get('transform_type', 'none')

            if source_param and target_param:
                mapped_fields['reference'][target_param] = {
                    'code': target_param,
                    'source_param': source_param,
                    'transform': transform,
                    'component_type': 'reference'
                }

    def _get_field_definitions(self, algorithm_type: str) -> Dict[str, Any]:
        """获取字段定义（不使用缓存，每次重新加载）"""
        log_not_emit('DEBUG', 'field_mapper', f'Building field definitions for {algorithm_type}', category='algorithm')
        return self._build_field_definitions(algorithm_type)
