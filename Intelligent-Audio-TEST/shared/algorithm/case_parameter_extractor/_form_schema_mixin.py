# -*- coding: utf-8 -*-
"""FormSchemaMixin - 提供算法表单 schema 生成

拆分自原 case_parameter_extractor.py 的 CaseParameterExtractor：
- get_algorithm_form_schema
- _get_default_component
- _get_group_label
"""

from typing import Dict, Any


class FormSchemaMixin:
    """算法表单 schema 生成 mixin"""

    @classmethod
    def get_algorithm_form_schema(cls, algorithm_type: str) -> Dict[str, Any]:
        """获取算法表单schema"""
        loader = cls._get_loader()
        algo_config = loader.get_algorithm_config(algorithm_type)

        if not algo_config:
            return {}

        definition = algo_config.get('definition', {})
        params = algo_config.get('case_params', [])

        fields = []
        for param in params:
            param_code = param.get('code')
            field = {
                'fieldCode': param_code,
                'fieldName': param.get('name', param_code),
                'fieldType': param.get('type', 'text'),
                'required': param.get('required', False),
                'defaultValue': param.get('default_value'),
                'component': param.get('component', cls._get_default_component(param.get('type', 'text'))),
                'options': param.get('options', []),
                'validation': param.get('validation_rules'),
                'helpText': param.get('help_text'),
                'hidden': param.get('hidden', False),
                'uiOrder': param.get('ui_order', 0),
                'uiGroup': param.get('ui_group', 'basic')
            }
            fields.append(field)

        fields.sort(key=lambda x: (x['uiGroup'], x['uiOrder']))

        groups = {}
        for field in fields:
            group_name = field.pop('uiGroup')
            if group_name not in groups:
                groups[group_name] = {
                    'name': group_name,
                    'label': cls._get_group_label(group_name),
                    'fields': []
                }
            groups[group_name]['fields'].append(field)

        return {
            'algorithmType': algorithm_type,
            'algorithmName': definition.get('name', algorithm_type),
            'category': definition.get('category'),
            'description': definition.get('description'),
            'groups': list(groups.values()),
            'fields': fields
        }

    @classmethod
    def _get_default_component(cls, field_type: str) -> str:
        """获取默认前端组件"""
        component_map = {
            'select': 'select',
            'text': 'input',
            'textarea': 'textarea',
            'number': 'input-number',
            'boolean': 'switch',
            'json': 'code-editor',
            'slider': 'slider'
        }
        return component_map.get(field_type, 'input')

    @classmethod
    def _get_group_label(cls, group_name: str) -> str:
        """获取分组标签"""
        labels = {
            'default': '基本配置',
            'basic': '基本配置',
            'model': '模型配置',
            'inference': '推理参数',
            'advanced': '高级选项'
        }
        return labels.get(group_name, group_name)
