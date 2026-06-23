# -*- coding: utf-8 -*-
"""
用例参数提取器

职责：
- 从用例配置字典中提取算法类型、算法参数、参考参数等
- 构建设备参数、API参数、评估参数
- 提供表单schema生成
- 判断重叠播放场景
"""

from typing import Dict, List, Any
from .algorithm_config_loader import get_config_loader
from .reference_params_generator import (
    get_reference_value as gen_reference_value,
    ReferenceParamsGenerator as RefGenerator
)
from backend.utils.log_handler import log_not_emit, log_and_emit


class CaseParameterExtractor:
    """
    用例参数提取器 - 静态类

    从用例配置中提取各类参数
    """

    _loader = None

    @classmethod
    def _get_loader(cls):
        if cls._loader is None:
            cls._loader = get_config_loader()
        return cls._loader

    @classmethod
    def get_algorithm_type(cls, case_config: Dict) -> str:
        """获取算法类型"""
        algorithm_type = case_config.get('algorithm_type', 'unknown')
        log_not_emit('DEBUG', 'case_parameter_extractor', f'Getting algorithm_type: {algorithm_type}', category='algorithm')
        return algorithm_type

    @classmethod
    def get_algorithm_params(cls, case_config: Dict) -> Dict[str, Any]:
        """获取算法参数"""
        return case_config.get('algorithm_params', {})

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

    @classmethod
    def get_evaluation_params(
        cls,
        case_config: Dict,
        dimension_ids: List[int] = None,
        algorithm_result: Dict[str, Any] = None,
        test_type: str = 'api'
    ) -> Dict[str, Any]:
        """获取评估参数
        
        Args:
            case_config: 用例配置
            dimension_ids: 评估维度ID列表
            algorithm_result: 算法执行结果（可选，用于从device/api来源获取值）
            test_type: 测试类型 ('api' 或 'e2e')
        """
        algorithm_type = cls.get_algorithm_type(case_config)
        if algorithm_type == 'unknown':
            log_not_emit('WARNING', 'case_parameter_extractor', 'Cannot get evaluation params: algorithm_type is unknown', category='algorithm')
            return {}

        loader = cls._get_loader()
        mappings = loader.get_param_mapping(algorithm_type, 'evaluation')
        if not mappings:
            log_not_emit('WARNING', 'case_parameter_extractor', f'No evaluation mappings found for algorithm: {algorithm_type}', category='algorithm')
            return {}

        result = cls._build_evaluation_params(
            algorithm_type, case_config, mappings, dimension_ids, algorithm_result, test_type
        )
        log_not_emit('DEBUG', 'case_parameter_extractor', f'Built evaluation params for {algorithm_type}: {list(result.keys())}', category='algorithm')
        return result

    @classmethod
    def _normalize_reference_params(cls, reference_params, test_type: str = 'api') -> List[Dict]:
        if not reference_params:
            return []

        if isinstance(reference_params, list):
            result = []
            for item in reference_params:
                if isinstance(item, dict):
                    result.append(cls._normalize_single_ref_param(item, test_type))
            return result

        if isinstance(reference_params, dict):
            if 'params' in reference_params and isinstance(reference_params['params'], list):
                return cls._normalize_reference_params(reference_params['params'], test_type)

            known_keys = {'default', 'api', 'e2e'}
            for key in known_keys:
                if key in reference_params and isinstance(reference_params[key], list):
                    return cls._normalize_reference_params(reference_params[key], test_type)

            result = []
            for code, item in reference_params.items():
                if isinstance(item, dict):
                    if 'code' not in item:
                        item = {**item, 'code': code}
                    result.append(cls._normalize_single_ref_param(item, test_type))
            return result

        return []

    @classmethod
    def _normalize_single_ref_param(cls, param: Dict, test_type: str = 'api') -> Dict:
        if 'value' in param and param['value'] is not None:
            return param

        test_type_value = param.get(test_type)
        if test_type_value is not None:
            return {**param, 'value': test_type_value}

        for fallback_key in ['api', 'e2e']:
            if fallback_key in param and param[fallback_key] is not None:
                return {**param, 'value': param[fallback_key]}

        return param

    @classmethod
    def _build_evaluation_params(
        cls,
        algorithm_type: str,
        case_config: Dict,
        mappings: List[Dict],
        dimension_ids: List[int] = None,
        algorithm_result: Dict[str, Any] = None,
        test_type: str = 'api'
    ) -> Dict[str, Any]:
        """构建评估参数
        
        Args:
            algorithm_type: 算法类型
            case_config: 用例配置
            mappings: 评估参数映射
            dimension_ids: 评估维度ID列表
            algorithm_result: 算法执行结果（可选）
            test_type: 测试类型 ('api' 或 'e2e')
        """
        eval_params = {}
        case_params = case_config.get('algorithm_params', {})
        raw_reference_params = case_config.get('reference_params', [])
        reference_params = cls._normalize_reference_params(raw_reference_params, test_type)
        
        log_not_emit('DEBUG', 'case_parameter_extractor',
            f'[_build_evaluation_params] reference_params normalized: raw_type={type(raw_reference_params).__name__}, '
            f'raw_len={len(raw_reference_params) if isinstance(raw_reference_params, (list, dict)) else "N/A"}, '
            f'normalized_count={len(reference_params)}, codes={[p.get("code") for p in reference_params]}',
            category='algorithm')
        
        if algorithm_result is None:
            algorithm_result = {}

        adjusted_reference_params = algorithm_result.get('adjusted_reference_params', [])
        log_not_emit('DEBUG', 'case_parameter_extractor', f'[_build_evaluation_params] adjusted_reference_params count: {len(adjusted_reference_params) if adjusted_reference_params else 0}', category='algorithm')

        for m in mappings:
            source = m.get('source', 'api')
            if dimension_ids and m.get('dimension_id') not in dimension_ids:
                continue
            source_param = m['source_param']
            target_param = m['target_param']
            value = None

            if source == 'case':
                value = case_params.get(source_param)
            elif source == 'reference':
                if reference_params:
                    ref_type = None
                    loader = cls._get_loader()
                    for ref_def in loader.get_reference_params(algorithm_type):
                        if ref_def.get('code') == source_param:
                            ref_type = ref_def.get('type')
                            break
                    for param in reference_params:
                        if param.get('code') == source_param:
                            if isinstance(param, dict):
                                value = gen_reference_value(
                                    param, test_type, ref_type,
                                    algorithm_type=algorithm_type,
                                    case_config=case_params
                                )
                                log_not_emit('DEBUG', 'case_parameter_extractor', f'[get_evaluation_params] source_param={source_param}, ref_type={ref_type}, value={value}, value_type={type(value)}', category='algorithm')
                            break
            elif source == 'device':
                value = algorithm_result.get(source_param)
            elif source == 'api':
                value = algorithm_result.get(source_param)
            elif source == 'adjusted_reference':
                if adjusted_reference_params:
                    for ref_param in adjusted_reference_params:
                        if ref_param.get('code') == source_param:
                            ref_value = ref_param.get('value')
                            if ref_value:
                                if isinstance(ref_value, dict):
                                    text = ref_value.get('text', '')
                                    json_data = ref_value.get('json', ref_value.get('segments', []))
                                    if text or json_data:
                                        value = {
                                            'text': text,
                                            'json': json_data
                                        }
                                        log_not_emit('DEBUG', 'case_parameter_extractor', f'[get_evaluation_params] from adjusted_reference: source_param={source_param}, text_len={len(text) if text else 0}, json_count={len(json_data) if isinstance(json_data, list) else 0}', category='algorithm')
                                elif isinstance(ref_value, str):
                                    value = {
                                        'text': ref_value,
                                        'json': []
                                    }
                            break

            if value is not None:
                eval_params[target_param] = value

        if dimension_ids:
            eval_params['dimension_ids'] = dimension_ids

        return eval_params

    @classmethod
    def get_all_params(cls, case_config: Dict) -> Dict[str, Any]:
        """获取所有参数（统一接口）"""
        log_not_emit('DEBUG', 'case_parameter_extractor', 'Getting all params for case', category='algorithm')
        result = {
            'algorithm_type': cls.get_algorithm_type(case_config),
            'device': cls.get_device_params(case_config),
            'api': cls.get_api_params(case_config),
            'evaluation': cls.get_evaluation_params(case_config)
        }
        log_not_emit('DEBUG', 'case_parameter_extractor', f'All params retrieved: {list(result.keys())}', category='algorithm')
        return result

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

    @classmethod
    def get_default_params(cls, algorithm_type: str) -> Dict[str, Any]:
        """获取算法默认参数"""
        loader = cls._get_loader()
        params = loader.get_algorithm_params(algorithm_type)

        defaults = {}
        for param in params:
            code = param.get('code')
            default_value = param.get('default_value')
            if default_value is not None:
                defaults[code] = default_value

        return defaults

    @classmethod
    def get_overlap_rate(cls, case_config: Dict) -> float:
        """获取重叠率"""
        log_not_emit('DEBUG', 'CaseParameterExtractor', f"[get_overlap_rate] case_config keys: {case_config.keys() if case_config else None}, algorithm_params: {case_config.get('algorithm_params') if case_config else None}", category='preview')
        algorithm_params = case_config.get('algorithm_params', {}) if case_config else {}
        if isinstance(algorithm_params, list):
            for p in algorithm_params:
                if p.get('field_code') == 'overlap_rate':
                    value = p.get('field_value') or 0
                    try:
                        result = max(0.0, min(1.0, float(value)))
                        log_not_emit('DEBUG', 'CaseParameterExtractor', f"[get_overlap_rate] found list format, value={value}, result={result}", category='preview')
                        return result
                    except (ValueError, TypeError):
                        return 0
            log_not_emit('DEBUG', 'CaseParameterExtractor', f"[get_overlap_rate] list format but not found overlap_rate", category='preview')
            return 0

        overlap_rate = algorithm_params.get('overlap_rate', 0)
        try:
            result = max(0.0, min(1.0, float(overlap_rate)))
            log_not_emit('DEBUG', 'CaseParameterExtractor', f"[get_overlap_rate] dict format, result={result}", category='preview')
            return result
        except (ValueError, TypeError):
            return 0
    
    @classmethod
    def get_overlap_time(cls, case_config: Dict) -> float:
        """获取重叠时间（秒）"""
        log_not_emit('DEBUG', 'CaseParameterExtractor', f"[get_overlap_time] case_config keys: {case_config.keys() if case_config else None}, algorithm_params: {case_config.get('algorithm_params') if case_config else None}", category='preview')
        algorithm_params = case_config.get('algorithm_params', {}) if case_config else {}
        if isinstance(algorithm_params, list):
            for p in algorithm_params:
                if p.get('field_code') == 'overlap_time':
                    value = p.get('field_value') or 0
                    try:
                        result = max(0.0, float(value))
                        log_not_emit('DEBUG', 'CaseParameterExtractor', f"[get_overlap_time] found list format, value={value}, result={result}", category='preview')
                        return result
                    except (ValueError, TypeError):
                        return 0
            log_not_emit('DEBUG', 'CaseParameterExtractor', f"[get_overlap_time] list format but not found overlap_time", category='preview')
            return 0

        overlap_time = algorithm_params.get('overlap_time', 0)
        try:
            result = max(0.0, float(overlap_time))
            log_not_emit('DEBUG', 'CaseParameterExtractor', f"[get_overlap_time] dict format, result={result}", category='preview')
            return result
        except (ValueError, TypeError):
            return 0



def get_parameter_extractor() -> CaseParameterExtractor:
    """获取参数提取器"""
    return CaseParameterExtractor
