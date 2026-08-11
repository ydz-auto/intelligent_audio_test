# -*- coding: utf-8 -*-
"""用例参数提取查询处理器

CQRS 读侧 - 迁移自 shared/algorithm/case_parameter_extractor
"""

from typing import Dict, List, Any, Optional

from algorithm_service.domain.services.param_normalizer import ParamNormalizerService
from algorithm_service.domain.services.reference_helpers import ReferenceHelpersService
from algorithm_service.infrastructure.persistence.config_cache import get_config_cache
from algorithm_service.application.queries.field_mapping_queries import FieldMappingQueryHandler
from shared.utils.log_handler import log_not_emit


class CaseParameterQueryHandler:
    """用例参数提取查询处理器"""

    @staticmethod
    def get_algorithm_type(case_config: Dict) -> str:
        return case_config.get('algorithm_type', 'unknown')

    @staticmethod
    def get_algorithm_params(case_config: Dict) -> Dict[str, Any]:
        raw = case_config.get('algorithm_params', {})
        return ParamNormalizerService.normalize_algorithm_params(raw)

    @staticmethod
    def get_round_algorithm_params(algorithm_params_col, round_number: int) -> Dict[str, Any]:
        params_list = ParamNormalizerService.get_round_algo_params(algorithm_params_col, round_number)
        if not params_list:
            return {}
        result = {}
        for item in params_list:
            field_code = item.get('field_code')
            if field_code:
                result[field_code] = item.get('field_value')
        return result

    @staticmethod
    def get_all_params(case_config: Dict) -> Dict[str, Any]:
        return {
            'algorithm_type': CaseParameterQueryHandler.get_algorithm_type(case_config),
            'device': CaseParameterQueryHandler.get_device_params(case_config),
            'api': CaseParameterQueryHandler.get_api_params(case_config),
            'evaluation': CaseParameterQueryHandler.get_evaluation_params(case_config),
        }

    @staticmethod
    def get_device_params(case_config: Dict) -> Dict[str, Any]:
        algorithm_type = CaseParameterQueryHandler.get_algorithm_type(case_config)
        algorithm_params = CaseParameterQueryHandler.get_algorithm_params(case_config)
        cache = get_config_cache()
        device_params_config = cache.get_device_params(algorithm_type)

        result = {}
        for p in device_params_config:
            if p.get('direction') != 'input':
                continue
            code = p.get('code')
            if not code:
                continue
            if code in algorithm_params:
                result[code] = algorithm_params[code]
            elif p.get('default_value') is not None:
                result[code] = p.get('default_value')
        return result

    @staticmethod
    def get_api_params(case_config: Dict) -> Dict[str, Any]:
        algorithm_type = CaseParameterQueryHandler.get_algorithm_type(case_config)
        algorithm_params = CaseParameterQueryHandler.get_algorithm_params(case_config)
        cache = get_config_cache()
        api_params_config = cache.get_api_params(algorithm_type)

        result = {}
        for p in api_params_config:
            if p.get('direction') != 'input':
                continue
            code = p.get('code')
            if not code:
                continue
            if code in algorithm_params:
                result[code] = algorithm_params[code]
            elif p.get('default_value') is not None:
                result[code] = p.get('default_value')
        return result

    @staticmethod
    def get_evaluation_params(
        case_config: Dict,
        dimension_ids: List[int] = None,
        algorithm_result: Dict[str, Any] = None,
        test_type: str = 'api',
    ) -> Dict[str, Any]:
        algorithm_type = CaseParameterQueryHandler.get_algorithm_type(case_config)
        cache = get_config_cache()
        mappings = cache.get_param_mapping(algorithm_type, 'evaluation')

        result = {}
        for m in mappings:
            source = m.get('source')
            source_param = m.get('source_param')
            target_param = m.get('target_param')
            transform_type = m.get('transform_type', 'none')

            if source == 'case':
                algo_params = CaseParameterQueryHandler.get_algorithm_params(case_config)
                value = algo_params.get(source_param)
            elif source == 'reference':
                ref_params_col = case_config.get('reference_params')
                ref_params = ReferenceParamsGeneratorQueryHandler.get_all_reference_params(ref_params_col)
                value = None
                for p in ref_params:
                    if p.get('code') == source_param:
                        value = ReferenceHelpersService.get_reference_value(p, test_type, target_param)
                        break
            elif source in ('device', 'api'):
                if algorithm_result and source in algorithm_result:
                    value = algorithm_result[source].get(source_param)
                else:
                    value = case_config.get(source_param)
            elif source == 'adjusted_reference':
                ref_params_col = case_config.get('reference_params')
                ref_params = ReferenceParamsGeneratorQueryHandler.get_all_reference_params(ref_params_col)
                value = None
                for p in ref_params:
                    if p.get('code') == source_param:
                        value = ReferenceHelpersService.get_reference_value(p, test_type, source_param)
                        break
            else:
                value = None

            if value is not None:
                if transform_type and transform_type != 'none':
                    from algorithm_service.domain.services.field_transforms import FieldTransformService
                    value = FieldTransformService.apply_transform(transform_type, value)
                result[target_param] = value

        return result

    @staticmethod
    def get_default_params(algorithm_type: str) -> Dict[str, Any]:
        cache = get_config_cache()
        params = cache.get_algorithm_params(algorithm_type)
        return {p.get('code'): p.get('default_value') for p in params if p.get('default_value') is not None}

    @staticmethod
    def get_overlap_rate(case_config: Dict) -> float:
        return ParamNormalizerService.get_overlap_rate(case_config)

    @staticmethod
    def get_overlap_time(case_config: Dict) -> float:
        return ParamNormalizerService.get_overlap_time(case_config)

    @staticmethod
    def build_form_schema(algorithm_type: str) -> Dict[str, Any]:
        cache = get_config_cache()
        config = cache.get_algorithm_config(algorithm_type)
        if not config:
            return {}

        case_params = config.get('case_params', [])
        fields = []
        for p in case_params:
            field_type = p.get('param_type') or p.get('type', 'text')
            fields.append({
                'fieldCode': p.get('code'),
                'fieldName': p.get('name'),
                'fieldType': field_type,
                'required': p.get('required') or p.get('is_required', False),
                'defaultValue': p.get('default_value'),
                'component': CaseParameterQueryHandler._get_default_component(field_type),
                'options': p.get('options'),
                'validation': p.get('validation_rules'),
                'helpText': p.get('help_text'),
                'hidden': p.get('hidden', False),
                'uiOrder': p.get('ui_order'),
                'uiGroup': p.get('ui_group', 'default'),
            })

        fields.sort(key=lambda f: (f.get('uiGroup', 'default'), f.get('uiOrder') or 0))

        groups = {}
        for f in fields:
            group = f.get('uiGroup', 'default')
            if group not in groups:
                groups[group] = {
                    'label': CaseParameterQueryHandler._get_group_label(group),
                    'fields': [],
                }
            groups[group]['fields'].append(f)

        return {'algorithm_type': algorithm_type, 'groups': groups}

    @staticmethod
    def _get_default_component(field_type: str) -> str:
        mapping = {
            'select': 'select',
            'text': 'input',
            'textarea': 'textarea',
            'number': 'input-number',
            'boolean': 'switch',
            'json': 'code-editor',
            'slider': 'slider',
        }
        return mapping.get(field_type, 'input')

    @staticmethod
    def _get_group_label(group_name: str) -> str:
        mapping = {
            'default': '基本配置',
            'basic': '基本配置',
            'model': '模型配置',
            'inference': '推理参数',
            'advanced': '高级选项',
        }
        return mapping.get(group_name, group_name)


class ReferenceParamsGeneratorQueryHandler:
    """参考参数生成查询处理器 - 委托给 application/queries/reference_params_queries"""
    pass
