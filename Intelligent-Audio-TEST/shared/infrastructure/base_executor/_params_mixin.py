# -*- coding: utf-8 -*-
"""算法额外参数处理"""
from shared.algorithm.field_mapper import get_field_mapper
from shared.models.database import db


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

        field_mapper = get_field_mapper()
        extra_config = field_mapper._get_algorithm_extra_config(algorithm_type)

        result_params = {}

        if extra_config.get('needs_extra_params'):
            case_fields = extra_config.get('case_fields', {})
            format_strings = extra_config.get('format_strings', {})
            db_model_name = extra_config.get('db_model')
            db_id_field = extra_config.get('db_id_field')

            db_model = None
            if db_model_name:
                import importlib
                model_module = importlib.import_module('shared.models.models')
                db_model = getattr(model_module, db_model_name, None)

            if format_strings:
                db_lang_fields = extra_config.get('db_lang_fields', {})
                default_lang = extra_config.get('default_lang', {})
            else:
                db_lang_fields = {}
                default_lang = {}

            for param_name, case_field in case_fields.items():
                param_value = case_field_values.get(param_name)

                format_str = format_strings.get(param_name)
                if format_str and param_value and db_model:
                    local_db_session = db.session()
                    try:
                        db_record = local_db_session.get(db_model, param_value)
                        if db_record:
                            format_kwargs = {}
                            for key, field in db_lang_fields.items():
                                format_kwargs[key] = getattr(db_record, field, default_lang.get(key))
                            result_params[param_name] = format_str.format(**format_kwargs)
                            if db_id_field:
                                result_params[db_id_field] = param_value
                    finally:
                        local_db_session.close()
                elif format_str and param_value:
                    result_params[param_name] = format_str.format(value=param_value)
                elif param_value is not None:
                    result_params[param_name] = param_value

            if include_format_strings and format_strings:
                for param_name, format_str in format_strings.items():
                    if param_name not in result_params:
                        format_kwargs = {k: default_lang.get(k, '') for k in db_lang_fields.keys()}
                        format_value = format_str.format(**format_kwargs)
                        result_params[param_name] = format_value

        return result_params

    def _get_result_mapper(self):
        """获取结果映射器"""
        # 跨服务调用：通过 gRPC DeviceResultService 获取结果采集器
        from shared.clients.grpc_clients import get_device_result_service_stub
        from shared.infrastructure.base_executor._proxy import _DeviceResultCollectorProxy
        return _DeviceResultCollectorProxy(get_device_result_service_stub())
