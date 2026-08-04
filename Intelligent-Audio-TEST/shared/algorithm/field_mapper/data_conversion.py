# -*- coding: utf-8 -*-
"""数据转换混入

提供设备输出转换、通用字段转换与API任务请求数据构建。
"""

from typing import Dict, List, Any, Optional

from shared.utils.log_handler import log_not_emit


class DataConversionMixin:
    """数据转换混入类

    依赖宿主类方法：``get_case_input_fields``、``get_device_output_fields``、
    ``get_api_output_fields``、``get_reference_input_fields``、
    ``get_device_input_fields``、``get_api_input_fields``、
    ``get_evaluation_input_fields``、``get_mapped_device_output_fields``，
    以及宿主类属性 ``self._transforms``。
    """

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
            for field_def in orig_output_fields:
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
