# -*- coding: utf-8 -*-
"""
用例参数提取器

职责：
- 从用例配置字典中提取算法类型、算法参数、参考参数等
- 支持 rounds-as-top-level 架构：从 round.algorithmParams [{field_code, field_value}] 读取参数
- 构建设备参数、API参数、评估参数
- 提供表单schema生成
- 判断重叠播放场景
"""

import json as _json
import os
from typing import Dict, List, Any, Optional
from .algorithm_config_loader import get_config_loader
from .reference_params_generator import (
    get_reference_value as gen_reference_value,
    normalize_reference_params,
    ReferenceParamsGenerator as RefGenerator
)
from shared.utils.log_handler import log_not_emit


def _get_algo_param(algorithm_params: Optional[List[Dict]], field_code: str, default=None):
    """从 algorithmParams [{field_code, field_value}] 数组中读取参数值

    Args:
        algorithm_params: [{field_code, field_value}] 格式的列表
        field_code: 要查找的字段代码
        default: 未找到时返回的默认值
    """
    if not algorithm_params:
        return default
    if isinstance(algorithm_params, list):
        for item in algorithm_params:
            if isinstance(item, dict) and item.get('field_code') == field_code:
                return item.get('field_value', default)
    return default


def _get_round_algo_params(algorithm_params_col: list, round_number: int) -> list:
    """从 test_cases.algorithm_params 列（按轮分组）中读取指定轮的 params

    Args:
        algorithm_params_col: [{round_number, params:[{field_code, field_value}]}]
        round_number: 轮次序号
    Returns:
        该轮的 params 列表 [{field_code, field_value}]，找不到返回 []
    """
    if not algorithm_params_col:
        return []
    for item in algorithm_params_col:
        if item.get('round_number') == round_number:
            return item.get('params', [])
    return []


def _normalize_algorithm_params(algorithm_params) -> Dict[str, Any]:
    """将 algorithm_params 统一转为 dict 格式 {field_code: field_value}

    支持输入:
    - dict: 直接返回
    - list of {field_code, field_value}: 转为 dict
    """
    if isinstance(algorithm_params, dict):
        return algorithm_params
    if isinstance(algorithm_params, list):
        result = {}
        for item in algorithm_params:
            if isinstance(item, dict) and 'field_code' in item:
                result[item['field_code']] = item.get('field_value')
        return result
    return {}


def _normalize_algorithm_params_to_list(algorithm_params) -> List[Dict]:
    """将 algorithm_params 统一转为 list 格式 [{field_code, field_value}]

    支持输入:
    - dict: {field_code: field_value, ...} 转为 list
    - list of {field_code, field_value}: 标准化后返回
    - list of {fieldCode, fieldValue}: 驼峰命名转为下划线
    - pydantic model: 调用 model_dump() 后提取
    """
    if not algorithm_params:
        return []
    if isinstance(algorithm_params, dict):
        return [{'field_code': k, 'field_value': v} for k, v in algorithm_params.items()]
    if isinstance(algorithm_params, list):
        result = []
        for item in algorithm_params:
            if hasattr(item, 'model_dump'):
                d = item.model_dump()
                fc = d.get('field_code') or d.get('fieldCode')
                fv = d.get('field_value', d.get('fieldValue'))
                if fc is not None:
                    result.append({'field_code': fc, 'field_value': fv})
                else:
                    result.append(d)
            elif isinstance(item, dict):
                fc = item.get('field_code') or item.get('fieldCode')
                fv = item.get('field_value', item.get('fieldValue'))
                if fc is not None:
                    result.append({'field_code': fc, 'field_value': fv})
                else:
                    result.append(item)
        return result
    return []


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
        """获取算法参数 — 统一返回 dict 格式

        支持 case_config.algorithm_params 为:
        - dict: 直接返回
        - list [{field_code, field_value}]: 转为 dict
        """
        raw = case_config.get('algorithm_params', {})
        return _normalize_algorithm_params(raw)

    @classmethod
    def get_round_algorithm_params(cls, algorithm_params_col, round_number) -> Dict[str, Any]:
        """从独立列按轮获取算法参数 dict

        Args:
            algorithm_params_col: test_cases.algorithm_params 列，按轮分组
                [{round_number, params:[{field_code, field_value}]}]
            round_number: 轮次序号
        Returns:
            {field_code: field_value}，找不到返回 {}
        """
        params_list = _get_round_algo_params(algorithm_params_col, round_number)
        if not params_list:
            return {}
        result = {}
        for item in params_list:
            field_code = item.get('field_code')
            if field_code:
                result[field_code] = item.get('field_value')
        return result

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

        log_not_emit('DEBUG', 'case_parameter_extractor', f'get_evaluation_params: algorithm_type={algorithm_type}, mappings_count={len(mappings)}', category='algorithm')

        result = cls._build_evaluation_params(
            algorithm_type, case_config, mappings, dimension_ids, algorithm_result, test_type
        )
        log_not_emit('DEBUG', 'case_parameter_extractor', f'Built evaluation params for {algorithm_type}: keys={list(result.keys())}', category='algorithm')
        return result

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

        兼容两种数据来源：
        - 新格式：case_config 含 rounds（结构性字段），算法参数/参考参数从独立列
          algorithm_params_col / reference_params_col 按轮读取（取 rounds[0] 的 round_number）
        - 旧平面格式：case_config.algorithm_params / case_config.reference_params 直接读取

        Args:
            algorithm_type: 算法类型
            case_config: 用例配置
            mappings: 评估参数映射
            dimension_ids: 评估维度ID列表
            algorithm_result: 算法执行结果（可选）
            test_type: 测试类型 ('api' 或 'e2e')
        """
        eval_params = {}
        # 新格式：rounds 顶层存在时，从独立列按轮取参数
        rounds = case_config.get('rounds')
        algorithm_params_col = case_config.get('algorithm_params_col')
        reference_params_col = case_config.get('reference_params_col')

        if rounds and isinstance(rounds, list) and len(rounds) > 0:
            round_number = rounds[0].get('roundNumber') or rounds[0].get('round_number')
            # 优先从独立列按轮取
            if algorithm_params_col is not None:
                case_params = cls.get_round_algorithm_params(algorithm_params_col, round_number)
            else:
                # 兼容：独立列缺失但 round 内仍保留 algorithmParams
                case_params = _normalize_algorithm_params(rounds[0].get('algorithmParams', []))
            if reference_params_col is not None:
                ref_file_data = cls._load_round_ref_file(reference_params_col, round_number)
                # _load_round_ref_file 返回 dict {code: item}，转为 list 以兼容后续流程
                raw_reference_params = list(ref_file_data.values()) if ref_file_data else []
            else:
                # 兼容：旧平面格式
                raw_reference_params = case_config.get('reference_params', [])
        else:
            # 旧平面格式
            case_params = _normalize_algorithm_params(case_config.get('algorithm_params', {}))
            raw_reference_params = case_config.get('reference_params', [])
        reference_params = normalize_reference_params(raw_reference_params, test_type)

        if algorithm_result is None:
            algorithm_result = {}

        adjusted_reference_params = algorithm_result.get('adjusted_reference_params', [])

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
            elif source in ('device', 'api'):
                value = algorithm_result.get(source_param)
                # rounds 结构：顶层没有设备输出字段时，从 rounds[0].output 取
                # output 的 key 是 target_param 名（build_algorithm_result 已映射）
                if value is None and isinstance(algorithm_result, dict):
                    rounds_data = algorithm_result.get('rounds', [])
                    if rounds_data and isinstance(rounds_data[0], dict):
                        output = rounds_data[0].get('output', {})
                        value = output.get(target_param)
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

    # ========== rounds-as-top-level 架构：轮次级参数提取 ==========

    @classmethod
    def _load_ref_file(cls, reference_params_path: Optional[str]) -> Dict[str, Any]:
        """从 referenceParamsPath 文件加载参考参数

        Args:
            reference_params_path: 参考参数文件路径
        Returns:
            解析后的 JSON 内容，路径无效或文件不存在时返回空 dict
        """
        if not reference_params_path:
            return {}
        try:
            # 支持绝对路径和相对于项目根目录的路径
            if not os.path.isabs(reference_params_path):
                from flask import current_app
                base_dir = current_app.config.get('PROJECT_ROOT', os.getcwd())
                reference_params_path = os.path.join(base_dir, reference_params_path)

            if not os.path.exists(reference_params_path):
                log_not_emit('WARNING', 'case_parameter_extractor',
                             f'Reference params file not found: {reference_params_path}', category='algorithm')
                return {}

            with open(reference_params_path, 'r', encoding='utf-8') as f:
                data = _json.load(f)

            # 如果文件内容是列表 [{code, type, value}]，转为 dict 格式方便查找
            if isinstance(data, list):
                result = {}
                for item in data:
                    if isinstance(item, dict) and 'code' in item:
                        result[item['code']] = item
                return result
            elif isinstance(data, dict):
                return data
            return {}
        except Exception as e:
            log_not_emit('WARNING', 'case_parameter_extractor',
                         f'Failed to load reference params from {reference_params_path}: {e}', category='algorithm')
            return {}

    @classmethod
    def _load_round_ref_file(cls, reference_params_col, round_number) -> Dict[str, Any]:
        """从 reference_params 独立列按轮加载参考参数文件

        Args:
            reference_params_col: test_cases.reference_params 列，按轮分组
                [{round_number, reference_params_path}]
            round_number: 轮次序号
        Returns:
            解析后的参考参数 dict，找不到返回 {}
        """
        if not reference_params_col:
            return {}
        for item in reference_params_col:
            if item.get('round_number') == round_number:
                path = item.get('reference_params_path')
                return cls._load_ref_file(path)
        return {}

    @classmethod
    def get_round_evaluation_params(
        cls,
        algorithm_type: str,
        round_config: Dict,
        algorithm_params_col,
        reference_params_col,
        algorithm_result: Dict[str, Any] = None,
        test_type: str = 'api'
    ) -> Dict[str, Any]:
        """提取单轮评估参数（rounds-as-top-level 架构）

        新设计下算法参数和参考参数从 test_cases 表独立列按轮读取：
        - algorithm_params_col: [{round_number, params:[{field_code, field_value}]}]
        - reference_params_col: [{round_number, reference_params_path}]

        兼容旧格式：若 algorithm_params_col 为 None 且 round_config 内含 algorithmParams，
        则走旧逻辑从 round_config 读取。

        Args:
            algorithm_type: 算法类型
            round_config: 单轮配置 dict（含 roundNumber 等结构性字段）
            algorithm_params_col: 算法参数独立列（按轮分组）
            reference_params_col: 参考参数独立列（按轮分组）
            algorithm_result: 算法执行结果（可选）
            test_type: 测试类型 ('api' 或 'e2e')
        """
        if algorithm_type == 'unknown':
            return {}

        loader = cls._get_loader()
        mappings = loader.get_param_mapping(algorithm_type, 'evaluation')
        if not mappings:
            log_not_emit('WARNING', 'case_parameter_extractor',
                         f'No evaluation mappings for {algorithm_type}', category='algorithm')
            return {}

        # 获取轮次序号，兼容 roundNumber / round_number 两种键
        round_number = round_config.get('roundNumber')
        if round_number is None:
            round_number = round_config.get('round_number')

        # 读取算法参数：优先从独立列按轮取，兼容旧格式
        if algorithm_params_col is not None:
            algo_params = _get_round_algo_params(algorithm_params_col, round_number)
        else:
            # 兼容旧格式：round_config.algorithmParams
            algo_params = round_config.get('algorithmParams', [])
        algo_dict = _normalize_algorithm_params(algo_params)

        # 加载参考参数文件：优先从独立列按轮取，兼容旧格式
        if reference_params_col is not None:
            ref_file_data = cls._load_round_ref_file(reference_params_col, round_number)
        else:
            # 兼容旧格式：round_config.referenceParamsPath
            ref_file_data = cls._load_ref_file(round_config.get('referenceParamsPath'))
        reference_params_list = list(ref_file_data.values()) if ref_file_data else []

        if algorithm_result is None:
            algorithm_result = {}
        adjusted_reference_params = algorithm_result.get('adjusted_reference_params', [])

        eval_params = {}
        eval_params['round_number'] = round_number

        for m in mappings:
            source = m.get('source', 'api')
            source_param = m['source_param']
            target_param = m['target_param']
            value = None

            if source == 'case':
                value = algo_dict.get(source_param)
            elif source == 'reference':
                ref_type = None
                for ref_def in loader.get_reference_params(algorithm_type):
                    if ref_def.get('code') == source_param:
                        ref_type = ref_def.get('type')
                        break
                for param in reference_params_list:
                    if isinstance(param, dict) and param.get('code') == source_param:
                        value = gen_reference_value(
                            param, test_type, ref_type,
                            algorithm_type=algorithm_type,
                            case_config=algo_dict
                        )
                        break
            elif source in ('device', 'api'):
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
                                        value = {'text': text, 'json': json_data}
                                elif isinstance(ref_value, str):
                                    value = {'text': ref_value, 'json': []}
                            break

            if value is not None:
                eval_params[target_param] = value

        # 轮次级额外信息
        eval_params['algorithm_params'] = algo_params
        return eval_params

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
        """获取重叠率 — 支持 algorithm_params 为 list [{field_code, field_value}] 或 dict"""
        if not case_config:
            return 0
        algorithm_params = case_config.get('algorithm_params', {})
        if isinstance(algorithm_params, list):
            value = _get_algo_param(algorithm_params, 'overlap_rate', 0)
        else:
            value = algorithm_params.get('overlap_rate', 0)
        try:
            return max(0.0, min(1.0, float(value)))
        except (ValueError, TypeError):
            return 0
    
    @classmethod
    def get_overlap_time(cls, case_config: Dict) -> float:
        """获取重叠时间（秒） — 支持 algorithm_params 为 list [{field_code, field_value}] 或 dict"""
        if not case_config:
            return 0
        algorithm_params = case_config.get('algorithm_params', {})
        if isinstance(algorithm_params, list):
            value = _get_algo_param(algorithm_params, 'overlap_time', 0)
        else:
            value = algorithm_params.get('overlap_time', 0)
        try:
            return max(0.0, float(value))
        except (ValueError, TypeError):
            return 0



def get_parameter_extractor() -> CaseParameterExtractor:
    """获取参数提取器"""
    return CaseParameterExtractor
