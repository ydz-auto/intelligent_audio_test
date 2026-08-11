# -*- coding: utf-8 -*-
"""参考参数辅助领域服务

纯逻辑，无 I/O 依赖。迁移自 shared/algorithm/reference_params/helpers.py
"""

from typing import Dict, List, Any

_REF_PARAMS_BUCKET = 'ref_params'
_KNOWN_DATA_KEYS = {'segments', 'text', 'annotations', 'timestamps', 'timestamps_global'}


class ReferenceHelpersService:
    """参考参数辅助服务 - 静态方法"""

    @staticmethod
    def build_ref_params_key(case_id, round_number, filename=None):
        """构建 OSS key"""
        if filename:
            return f'{case_id}/{filename}'
        return f'{case_id}/round_{round_number}.json'

    @staticmethod
    def normalize_reference_params(params, test_type: str = 'api') -> List[Dict[str, Any]]:
        """规范化参考参数列表"""
        if not params:
            return []
        if isinstance(params, dict):
            if 'params' in params:
                params = params['params']
            elif 'default' in params:
                params = params['default']
            elif test_type in params:
                params = params[test_type]
            else:
                params = [params]
        if not isinstance(params, list):
            params = [params]

        result = []
        for param in params:
            if not isinstance(param, dict):
                continue
            normalized = ReferenceHelpersService._normalize_single_ref_param(param, test_type)
            if normalized:
                result.append(normalized)
        return result

    @staticmethod
    def _normalize_single_ref_param(param: Dict, test_type: str = 'api') -> Dict:
        """单条规范化"""
        code = param.get('code')
        if not code:
            return None
        param_type = param.get('param_type') or param.get('type')
        value = param.get('value')

        if value is None:
            if test_type in param:
                value = param[test_type]
            elif 'api' in param:
                value = param['api']
            elif 'e2e' in param:
                value = param['e2e']

        result = {
            'code': code,
            'type': param_type,
            'value': value,
        }

        if param.get('annotation_code'):
            result['annotation_code'] = param['annotation_code']
        if param.get('annotation_format'):
            result['annotation_format'] = param['annotation_format']

        extra_keys = set(param.keys()) - _KNOWN_DATA_KEYS - {
            'code', 'param_type', 'type', 'value', 'api', 'e2e',
            'annotation_code', 'annotation_format', 'default', 'params',
        }
        for k in extra_keys:
            result[k] = param[k]

        return result

    @staticmethod
    def get_overlap_rate(config: Dict) -> float:
        """从 algorithm_params 取 overlap_rate"""
        ap = config.get('algorithm_params', {})
        if isinstance(ap, list):
            normalized = {}
            for item in ap:
                if isinstance(item, dict) and 'field_code' in item:
                    normalized[item['field_code']] = item.get('field_value')
            ap = normalized
        rate = ap.get('overlap_rate', 0.0) if isinstance(ap, dict) else 0.0
        try:
            rate = float(rate)
        except (TypeError, ValueError):
            rate = 0.0
        return max(0.0, min(1.0, rate))

    @staticmethod
    def get_overlap_time(config: Dict) -> float:
        """从 algorithm_params 取 overlap_time"""
        ap = config.get('algorithm_params', {})
        if isinstance(ap, list):
            normalized = {}
            for item in ap:
                if isinstance(item, dict) and 'field_code' in item:
                    normalized[item['field_code']] = item.get('field_value')
            ap = normalized
        time_val = ap.get('overlap_time', 0.0) if isinstance(ap, dict) else 0.0
        try:
            time_val = float(time_val)
        except (TypeError, ValueError):
            time_val = 0.0
        return max(0.0, time_val)

    @staticmethod
    def get_reference_value(
        param: Dict[str, Any],
        test_type: str,
        ref_type: str = None,
        algorithm_type: str = None,
        case_config: Dict[str, Any] = None,
    ) -> Any:
        """根据用例配置获取参考参数的值"""
        value = param.get('value')

        if value is None:
            return ''

        if isinstance(value, list):
            if not value:
                return ''
            if ref_type == 'json':
                return value
            first_item = value[0]
            if isinstance(first_item, dict):
                return first_item.get('text', '')
            return str(first_item)

        if not ref_type or ref_type in ('text', 'audio'):
            if isinstance(value, dict):
                return {'text': value.get('text', ''), 'json': value.get('json', value.get('segments', []))}
            return {'text': str(value) if value else '', 'json': []}

        if ref_type in ('rttm_text', 'stm_text'):
            if isinstance(value, dict):
                return {'text': value.get('text', ''), 'json': value.get('json', value.get('segments', []))}
            return {'text': str(value) if value else '', 'json': []}

        if ref_type in ('rttm_json', 'stm_json', 'rttm', 'stm'):
            if isinstance(value, dict):
                return {'text': value.get('text', ''), 'segments': value.get('segments', [])}
            return {'text': '', 'segments': []}

        if isinstance(value, dict):
            return value.get('text', '')
        return value
