# -*- coding: utf-8 -*-
"""算法额外参数处理"""
from shared.clients.grpc_clients import (
    algo_get_device_params,
    algo_get_api_params,
    algo_get_param_mapping,
)


class ParamsMixin:
    """执行器基类算法参数处理方法"""

    def _execute_extra_params(self, algorithm_type, passed_kwargs=None, include_format_strings=True):
        """从配置动态获取算法特定参数"""
        if passed_kwargs is None:
            passed_kwargs = {}

        if isinstance(passed_kwargs, dict):
            if 'algorithm_type' in passed_kwargs:
                case_field_values = passed_kwargs
                passed_kwargs = {}
            else:
                case_field_values = getattr(self, 'current_case_field_values', {})
        else:
            case_field_values = getattr(self, 'current_case_field_values', {})

        extra_config = _get_algorithm_extra_config(algorithm_type)

        result_params = {}

        if extra_config.get('needs_extra_params'):
            case_fields = extra_config.get('case_fields', {})
            format_strings = extra_config.get('format_strings', {})

            for param_name, case_field in case_fields.items():
                param_value = case_field_values.get(param_name)

                format_str = format_strings.get(param_name)
                # TODO: 待 task_service / device_service proto 扩展 model/lang 查询 RPC 后，
                # 此处 format_str 需查库补全 source/target 语言字段的场景应改为 gRPC 调用。
                # 原 shared.models.models 模块已随 PO 下沉删除，无法再动态 import。
                if format_str and param_value:
                    try:
                        result_params[param_name] = format_str.format(value=param_value)
                    except KeyError:
                        result_params[param_name] = param_value
                elif param_value is not None:
                    result_params[param_name] = param_value

            if include_format_strings and format_strings:
                for param_name, format_str in format_strings.items():
                    if param_name not in result_params:
                        try:
                            format_value = format_str.format()
                        except KeyError:
                            format_value = ''
                        result_params[param_name] = format_value

        return result_params

    def _get_result_mapper(self):
        """获取结果映射器"""
        # 跨服务调用：通过 gRPC DeviceResultService 获取结果采集器
        from shared.clients.grpc_clients import get_device_result_service_stub
        from shared.infrastructure.base_executor._proxy import _DeviceResultCollectorProxy
        return _DeviceResultCollectorProxy(get_device_result_service_stub())


def _get_algorithm_extra_config(algorithm_type):
    """获取算法额外配置（迁移自 FieldMapper._get_algorithm_extra_config）

    通过 gRPC 获取 device/api params + param mappings，派生 extra_config。
    """
    params = (algo_get_device_params(algorithm_type) or []) + (algo_get_api_params(algorithm_type) or [])

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

    for comp_type in ('device', 'api', 'case', 'reference', 'evaluation'):
        comp_mappings = algo_get_param_mapping(algorithm_type, comp_type) or []
        for mapping in comp_mappings:
            source = mapping.get('source', '')
            source_param = mapping.get('source_param', '')

            if source in ['case_table', 'case_field']:
                config['needs_extra_params'] = True
                config['case_fields'][source_param] = source_param

    if config['case_fields']:
        config['needs_extra_params'] = True

    return config
