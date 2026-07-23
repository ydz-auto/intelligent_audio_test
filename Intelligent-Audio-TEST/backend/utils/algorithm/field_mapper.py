# -*- coding: utf-8 -*-
"""
统一字段映射器

职责：
- 提供设备/API/评估的字段定义查询
- 字段类型转换和数据格式转换
- 构建API请求数据
- 不负责参数生成，只负责字段映射转换
"""

from typing import Dict, List, Any, Optional, Callable
from threading import Lock
from .algorithm_config_loader import get_config_loader
from backend.utils.web.log_handler import log_not_emit


class FieldMapper:
    """
    统一字段映射器 - 单例模式

    提供设备/API/评估的字段映射和数据转换
    """

    _instance = None
    _instance_lock = Lock()
    _config_lock = Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._loader = get_config_loader()
        self._field_cache: Dict[str, Dict[str, Any]] = {}
        self._transforms: Dict[str, Callable] = {}
        self._register_builtin_transforms()
        log_not_emit('DEBUG', 'field_mapper', 'FieldMapper initialized', category='algorithm')

    def _register_builtin_transforms(self):
        """注册内置转换函数"""
        self._transforms = {
            'none': lambda x: x,
            'json_parse': self._json_parse,
            'base64': self._base64_encode,
            'to_string': lambda x: str(x) if x is not None else '',
            'to_int': lambda x: int(x) if x is not None else 0,
            'to_float': lambda x: float(x) if x is not None else 0.0,
            'to_bool': lambda x: bool(x) if x is not None else False,
            'rttm_to_obj': self._rttm_to_obj,
            'stm_to_obj': self._stm_to_obj,
        }

    @staticmethod
    def _json_parse(x):
        """JSON解析"""
        import json
        if isinstance(x, str):
            try:
                return json.loads(x)
            except Exception as e:
                log_not_emit('WARNING', 'field_mapper', f'JSON parse error: {e}', category='algorithm')
                return x
        return x

    @staticmethod
    def _base64_encode(x):
        """Base64编码"""
        import base64
        if isinstance(x, str):
            return base64.b64encode(x.encode()).decode()
        return x

    @staticmethod
    def _rttm_to_obj(text):
        """RTTM文本转{text, json}对象"""
        import json
        if not text:
            return {'text': '', 'json': '[]'}
        
        segments = []
        for line in text.split('\n'):
            parts = line.split()
            if parts and parts[0] == 'SPEAKER' and len(parts) >= 8:
                segments.append({
                    'speaker': parts[7],
                    'start': float(parts[3]),
                    'duration': float(parts[4]),
                })
        
        return {
            'text': text,
            'json': segments
        }

    @staticmethod
    def _stm_to_obj(text):
        """STM文本转{text, json}对象"""
        if not text:
            return {'text': '', 'json': '[]'}
        segments = []
        for line in text.split('\n'):
            parts = line.split()
            if not parts:
                continue
            # 跳过 RTTM 格式行
            if parts[0] == 'SPEAKER':
                continue
            
            # 兼容两种格式：
            # 1. 标准格式: file_id channel speaker start end <o> text (7+个部分，第6个是<o>)
            # 2. 简化格式: file_id channel speaker start end text (6个部分，没有<o>)
            try:

                if len(parts) >= 6:
                    # 简化格式（没有<o>标记）
                    segments.append({
                        'file_id': parts[0],
                        'channel': parts[1],
                        'speaker': parts[2],
                        'start': float(parts[3]),
                        'end': float(parts[4]),
                        'text': ' '.join(parts[5:]) if len(parts) > 5 else '',
                    })
            except (ValueError, IndexError):
                pass
        return {
            'text': text,
            'json': segments
        }

    def _get_device_params(self, algorithm_type: str) -> List[Dict[str, Any]]:
        """获取设备参数"""
        return self._loader.get_device_params(algorithm_type)

    def _get_api_params(self, algorithm_type: str) -> List[Dict[str, Any]]:
        """获取API参数"""
        return self._loader.get_api_params(algorithm_type)

    def _get_param_mappings(self, algorithm_type: str) -> Dict[str, List[Dict[str, Any]]]:
        """获取参数映射"""
        return {
            'device': self._loader.get_param_mapping(algorithm_type, 'device'),
            'api': self._loader.get_param_mapping(algorithm_type, 'api'),
            'case': self._loader.get_param_mapping(algorithm_type, 'case'),
            'reference': self._loader.get_param_mapping(algorithm_type, 'reference'),
            'evaluation': self._loader.get_param_mapping(algorithm_type, 'evaluation')
        }

    def _build_field_definitions(self, algorithm_type: str) -> Dict[str, Any]:
        """构建字段定义"""
        from backend.utils.web.log_handler import log_not_emit
        
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

    def get_output_field_code(self, algorithm_type: str, field_category: str = 'result') -> str:
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

    def convert_output_for_target(
        self,
        algorithm_type: str,
        source_data: Dict[str, Any],
        source_type: str,
        target_type: str
    ) -> Dict[str, Any]:
        """通用字段转换"""
        result = {}

        if source_type == 'case':
            source_fields = self.get_case_input_fields(algorithm_type)
        elif source_type == 'device':
            source_fields = self.get_device_output_fields(algorithm_type)
        elif source_type == 'api':
            source_fields = self.get_api_output_fields(algorithm_type)
        elif source_type == 'reference':
            source_fields = self.get_reference_input_fields(algorithm_type)
        else:
            return {}

        if target_type == 'device':
            target_fields = self.get_device_input_fields(algorithm_type)
        elif target_type == 'api':
            target_fields = self.get_api_input_fields(algorithm_type)
        elif target_type == 'evaluation':
            target_fields = self.get_evaluation_input_fields(algorithm_type)
        else:
            return {}

        for target_key, target_def in target_fields.items():
            source_key = target_def.get('source_param', target_key)
            value = source_data.get(source_key)
            if value is not None:
                result[target_key] = value

        return result

    def convert_device_output(
        self,
        algorithm_type: str,
        device_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换设备输出"""
        success = device_result.get('success', False)
        message = device_result.get('message', '')
        result_type = device_result.get('result_type', 'default')

        mapped_output_fields = self.get_mapped_device_output_fields(algorithm_type)
        
        # 不再需要过滤，因为现在使用列表保存所有映射
        
        orig_output_fields = self.get_device_output_fields(algorithm_type)

        result = {}

        if not success:
            for field_def in orig_output_fields:
                result[field_def.get('code')] = message or 'Error'
        elif mapped_output_fields:
            for field_def in mapped_output_fields:
                target_key = field_def.get('code')
                source_param = field_def.get('source_param', target_key)
                transform = field_def.get('transform', 'none')
                dim_id = field_def.get('dimension_id')
                value = device_result.get(source_param)
                log_not_emit('DEBUG', 'field_mapper', f'convert_device_output: target_key={target_key}, source_param={source_param}, transform={transform}, dim_id={dim_id}, value_is_none={value is None}, device_result_keys={list(device_result.keys())[:10]}', category='algorithm')
                if value is not None:
                    # 多对一映射：同一 target_key 有多条映射时，按维度分别存储
                    # target_key 相同但 dimension_id 不同时，用 target_key + '__dim_' + dim_id 区分
                    store_key = target_key
                    if dim_id is not None:
                        store_key = f'{target_key}__dim_{dim_id}'
                    if transform != 'none':
                        log_not_emit('DEBUG', 'field_mapper', f'Transform check: source_param={source_param}, target_key={store_key}, transform={transform}, in_transforms={transform in self._transforms}', category='algorithm')
                    if transform != 'none' and transform in self._transforms:
                        try:
                            result[store_key] = self._transforms[transform](value)
                            log_not_emit('DEBUG', 'field_mapper', f'Transform applied: {source_param} -> {store_key} ({transform})', category='algorithm')
                        except Exception as e:
                            log_not_emit('WARNING', 'field_mapper', f'Transform error for {store_key} ({transform}): {e}', category='algorithm')
                            result[store_key] = value
                    else:
                        result[store_key] = value
                    # 同时保留 target_key 指向第一个有效值（兼容旧逻辑）
                    if target_key not in result or not result[target_key]:
                        result[target_key] = result[store_key]
        elif orig_output_fields:
            for field_key, field_def in orig_output_fields.items():
                source_param = field_def.get('code')
                result[source_param] = device_result.get(source_param, '')
        else:
            for key, value in device_result.items():
                if key not in ('success', 'message'):
                    result[key] = value

        return result

    def build_create_task_data(
        self,
        algorithm_type: str,
        audio_path: str = None,
        vendor: str = None,
        max_process: int = None,
        max_timeout: int = None,
        endpoints: List[Dict] = None,
        case_config: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """构建API创建任务的请求数据"""
        log_not_emit('DEBUG', 'field_mapper', f'Building create task data for {algorithm_type}', category='algorithm')
        api_input_fields = self.get_api_input_fields(algorithm_type)

        task_data = {}

        case_params = case_config.get('algorithm_params', {}) if case_config else {}
        param_sources = {**case_params, **kwargs}

        explicit_params = {
            'audio_path': audio_path,
            'audio_url': audio_path,
            'vendor': vendor,
            'max_process': max_process,
            'max_timeout': max_timeout,
            'endpoints': endpoints
        }
        for k, v in explicit_params.items():
            if v is not None:
                param_sources[k] = v

        for field_code, field_def in api_input_fields.items():
            transform = field_def.get('transform', 'none')
            value = param_sources.get(field_code)

            if value is not None:
                transform_func = self._transforms.get(transform, lambda x: x)
                try:
                    task_data[field_code] = transform_func(value)
                except Exception as e:
                    log_not_emit('WARNING', 'field_mapper', f'Transform error for {field_code}: {e}', category='algorithm')
                    task_data[field_code] = value

        if vendor and 'vendor' not in task_data:
            task_data['vendor'] = vendor

        log_not_emit('DEBUG', 'field_mapper', f'Built task data with {len(task_data)} fields', category='algorithm')
        return task_data

    def reload(self):
        """重新加载字段定义"""
        with self._config_lock:
            log_not_emit('INFO', 'field_mapper', 'Reloading field definitions', category='algorithm')
            self._field_cache.clear()


def get_field_mapper() -> FieldMapper:
    """获取字段映射器单例"""
    return FieldMapper()
