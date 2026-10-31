# -*- coding: utf-8 -*-
"""字段映射查询处理器

CQRS 读侧 - 迁移自 shared/algorithm/field_mapper 的查询逻辑。
通过 config_cache + 领域服务提供字段映射查询。
"""

from typing import Dict, List, Any, Optional
import logging

from algorithm_service.infrastructure.persistence.config_cache import get_config_cache
from algorithm_service.domain.services.field_transforms import FieldTransformService
from algorithm_service.application.queries.algorithm_config_queries import AlgorithmConfigQueryHandler

logger = logging.getLogger(__name__)


class FieldMappingQueryHandler:
    """字段映射查询处理器"""

    @staticmethod
    def get_field_definitions(
        algorithm_type: str, api_id: int | None = None, device_id: int | None = None
    ) -> Dict[str, Any]:
        """构建字段定义（original + mapped）

        ``api_id`` / ``device_id`` 传入时，对应作用域的参数与映射都按「实例级
        覆盖算法级、未覆盖键回落算法级」的合并口径取；不传时按算法级默认。
        """
        cache = get_config_cache()
        device_params = cache.get_device_params(algorithm_type, device_id)
        api_params = cache.get_api_params(algorithm_type, api_id)
        reference_params = cache.get_reference_params(algorithm_type)
        mappings = cache.get_param_mapping(
            algorithm_type, 'evaluation', api_id, device_id)
        case_params = cache.get_case_params(algorithm_type)

        original = {
            'device': {'input': {}, 'output': {}},
            'api': {'input': {}, 'output': {}},
            'case': {'input': {}, 'output': {}},
            'reference': {'input': {}, 'output': {}},
            'evaluation': {'input': {}, 'output': {}},
        }

        for p in device_params:
            direction = p.get('direction', 'output')
            code = p.get('code')
            if code:
                original['device'][direction][code] = p

        for p in api_params:
            direction = p.get('direction', 'output')
            code = p.get('code')
            if code:
                original['api'][direction][code] = p

        for p in case_params:
            direction = p.get('direction', 'output')
            code = p.get('code')
            if code:
                original['case'][direction][code] = p

        for p in reference_params:
            code = p.get('code')
            if code:
                original['reference']['input'][code] = p

        for m in mappings:
            source = m.get('source', 'api')
            source_param = m.get('source_param')
            target_param = m.get('target_param')
            transform = m.get('transform_type', 'none')
            dim_id = m.get('dimension_id')
            dim_name = m.get('dimension_name')
            if source_param and target_param:
                # reference 参数只有 input 方向，其余 source 查 output
                direction = 'input' if source == 'reference' else 'output'
                # 在所有 source 的对应方向里查找 source_param（mapping 的 source 字段
                # 标记的是参数来源类型，但 source_param 可能属于任意 source 的参数定义）
                found = False
                for src_key in original:
                    if source_param in original[src_key].get(direction, {}):
                        entry = {
                            'source_param': source_param,
                            'source': source,
                            'target_param': target_param,
                            'transform_type': transform,
                            'dimension_id': dim_id,
                            'dimension_name': dim_name,
                        }
                        original['evaluation']['output'][target_param] = entry
                        found = True
                        break

        mapped = {'device': {}, 'api': {}, 'evaluation': {}}

        for source in ('device', 'api'):
            for code, p in original[source].get('output', {}).items():
                transform = 'none'
                target = code
                for m in mappings:
                    if m.get('source_param') == code and m.get('source') == source:
                        target = m.get('target_param', target)
                        transform = m.get('transform_type', 'none')
                        break
                mapped[source][target] = {
                    'source_param': code,
                    'target_param': target,
                    'transform_type': transform,
                    'param_type': p.get('param_type') or p.get('type'),
                    'label': p.get('label') or p.get('name'),
                }

        for target, m in original['evaluation'].get('output', {}).items():
            mapped['evaluation'][target] = m

        return {'original': original, 'mapped': mapped}

    @staticmethod
    def get_device_input_fields(algorithm_type: str) -> Dict[str, Any]:
        defs = FieldMappingQueryHandler.get_field_definitions(algorithm_type)
        return defs['original']['device']['input']

    @staticmethod
    def get_device_output_fields(algorithm_type: str) -> Dict[str, Any]:
        defs = FieldMappingQueryHandler.get_field_definitions(algorithm_type)
        return defs['original']['device']['output']

    @staticmethod
    def get_api_input_fields(algorithm_type: str) -> Dict[str, Any]:
        defs = FieldMappingQueryHandler.get_field_definitions(algorithm_type)
        return defs['original']['api']['input']

    @staticmethod
    def get_api_output_fields(algorithm_type: str) -> Dict[str, Any]:
        defs = FieldMappingQueryHandler.get_field_definitions(algorithm_type)
        return defs['original']['api']['output']

    @staticmethod
    def get_evaluation_input_fields(algorithm_type: str) -> Dict[str, Any]:
        defs = FieldMappingQueryHandler.get_field_definitions(algorithm_type)
        return defs['original']['evaluation']['input']

    @staticmethod
    def get_evaluation_output_fields(algorithm_type: str) -> Dict[str, Any]:
        defs = FieldMappingQueryHandler.get_field_definitions(algorithm_type)
        return defs['original']['evaluation']['output']

    @staticmethod
    def get_mapped_device_output_fields(algorithm_type: str) -> Dict[str, Any]:
        defs = FieldMappingQueryHandler.get_field_definitions(algorithm_type)
        return defs['mapped']['device']

    @staticmethod
    def get_mapped_api_output_fields(algorithm_type: str) -> List[Dict]:
        defs = FieldMappingQueryHandler.get_field_definitions(algorithm_type)
        return list(defs['mapped']['api'].values())

    @staticmethod
    def get_case_fields(algorithm_type: str) -> Dict[str, str]:
        """获取用例字段 code→name 映射"""
        cache = get_config_cache()
        case_params = cache.get_case_params(algorithm_type)
        return {p.get('code'): p.get('name', p.get('code')) for p in case_params}

    @staticmethod
    def get_reference_field_codes(algorithm_type: str) -> Dict[str, str]:
        """获取参考字段 code→name 映射"""
        cache = get_config_cache()
        ref_params = cache.get_reference_params(algorithm_type)
        return {p.get('code'): p.get('name', p.get('code')) for p in ref_params}

    @staticmethod
    def build_api_request_data(
        algorithm_type: str,
        device_params: Dict[str, Any],
        api_params: Dict[str, Any] = None,
        case_config: Dict[str, Any] = None,
        api_id: Optional[int] = None,
        **kwargs,
    ) -> Dict[str, Any]:
        """构建 API 请求数据。

        ``api_id`` 非空时输入声明按「策略 + 实例覆盖」解析；缺省则没有可套的声明
        （算法类型级默认层已废弃），返回空 dict。
        """
        if api_id is None:
            return {}
        cache = get_config_cache()
        api_input_fields = cache.get_api_params(algorithm_type, api_id)
        result = {}
        case_config = case_config or {}

        for field in api_input_fields:
            if field.get('direction') != 'input':
                continue
            code = field.get('code')
            if not code:
                continue
            default = field.get('default_value')
            transform = field.get('transform_type', 'none') or 'none'

            value = None
            if code in (api_params or {}):
                value = api_params[code]
            elif code in case_config:
                value = case_config[code]
            elif code in kwargs:
                value = kwargs[code]
            elif default is not None:
                value = default

            if value is not None:
                if transform and transform != 'none':
                    value = FieldTransformService.apply_transform(transform, value)
                result[code] = value

        return result

    @staticmethod
    def convert_field_value(transform_type: str, value: Any) -> Any:
        """应用转换"""
        return FieldTransformService.apply_transform(transform_type, value)

    @staticmethod
    def convert_field_values(items: List[Dict[str, Any]]) -> Dict[str, Any]:
        """批量应用字段值转换（INT-1749，一次请求 N 个值）。

        Args:
            items: ``[{'transform_type': str, 'value': Any}, ...]``

        Returns:
            ``{'values': [...与 items 同序...],
               'errors': [{'index': int, 'transform_type': str, 'error': str}, ...]}``

        非法输入（未知转换类型 / 转换抛异常）按「保留原值 + errors 回传」
        处理，同时服务端记 WARNING；不抛异常、不吞成空串。
        """
        values: List[Any] = []
        errors: List[Dict[str, Any]] = []
        for index, item in enumerate(items or []):
            if not isinstance(item, dict):
                errors.append({'index': index, 'transform_type': '',
                               'error': f'非法 item 类型: {type(item).__name__}'})
                values.append(item)
                continue
            transform_type = item.get('transform_type') or 'none'
            value, error = FieldTransformService.apply_transform_with_error(
                transform_type, item.get('value'))
            if error:
                logger.warning(
                    "批量字段值转换失败，保留原值 (index=%s, transform_type=%s): %s",
                    index, transform_type, error)
                errors.append({'index': index, 'transform_type': transform_type,
                               'error': error})
            values.append(value)
        return {'values': values, 'errors': errors}
