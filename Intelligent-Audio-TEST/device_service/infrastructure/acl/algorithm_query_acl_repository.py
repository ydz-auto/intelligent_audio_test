# -*- coding: utf-8 -*-
"""algorithm_service 查询防腐层仓储（ACL Repository）

封装对 algorithm_service.AlgorithmQueryService 的 gRPC 调用，
替代 device_service 中对原 shared/algorithm 包的直接 import。
通过 gRPC 调用 algorithm_service.AlgorithmQueryService 获取字段映射和参考参数数据。

- 读操作通过 shared.clients.grpc_clients.algo_* 便捷函数完成，
  返回 dict / list，不返回 ORM 对象。
- 对 field_mappings 的结构进行适配，使上层（domain/application）拿到的
  数据形状与原 FieldMapper 单例返回的一致。

相关便捷函数：shared.clients.grpc_clients.algo_get_field_mappings /
algo_generate_reference_params / algo_get_reference_params_for_report
"""
import logging
from typing import Any, Dict, List, Optional

from device_service.domain.dto import FieldMappingDTO, DeviceParamDTO, ReferenceParamDTO
from shared.clients.grpc_clients import (
    algo_get_field_mappings,
    algo_generate_reference_params,
    algo_get_reference_params_for_report,
    algo_get_device_params,
)
from shared.utils.dto_utils import dict_list_to_dto

logger = logging.getLogger(__name__)


class AlgorithmQueryACLRepository:
    """algorithm_service 查询防腐层仓储

    封装 gRPC 调用，返回 DTO 或 dict（结构化数据用 DTO，配置型数据用 dict）。
    """

    # ========== 字段映射查询 ==========

    def get_field_mappings(self, algorithm_type: str) -> Dict[str, Any]:
        """获取完整字段定义（original + mapped）

        对应原 FieldMapper._get_field_definitions(algorithm_type)。

        Args:
            algorithm_type: 算法类型

        Returns:
            {'original': {...}, 'mapped': {...}}，失败返回空结构
        """
        if not algorithm_type:
            return {'original': {}, 'mapped': {}}
        data = algo_get_field_mappings(algorithm_type) or {}
        if not isinstance(data, dict):
            return {'original': {}, 'mapped': {}}
        return data

    def get_device_output_fields(self, algorithm_type: str) -> Dict[str, Any]:
        """获取设备输出字段（原始，未映射）

        对应原 FieldMapper.get_device_output_fields(algorithm_type)。
        返回 {code: param_dict} 形式。

        Args:
            algorithm_type: 算法类型

        Returns:
            设备输出字段字典
        """
        defs = self.get_field_mappings(algorithm_type)
        return defs.get('original', {}).get('device', {}).get('output', {}) or {}

    def get_mapped_device_output_fields(self, algorithm_type: str) -> List[FieldMappingDTO]:
        """获取设备输出字段（映射后）

        对应原 FieldMapper.get_mapped_device_output_fields(algorithm_type)。
        返回 List[FieldMappingDTO]，每个元素含 code/source_param/transform/...

        gRPC 端 mapped.device 是 dict（target_param -> entry），此处转换为
        list 以保持与原 FieldMapper 返回形状一致。

        Args:
            algorithm_type: 算法类型

        Returns:
            映射后的设备输出字段 DTO 列表
        """
        defs = self.get_field_mappings(algorithm_type)
        mapped_device = defs.get('mapped', {}).get('device', {}) or {}
        if isinstance(mapped_device, list):
            return dict_list_to_dto(mapped_device, FieldMappingDTO)
        if isinstance(mapped_device, dict):
            # gRPC 返回 {target_param: entry}，转为 list[entry]
            result = []
            for target_param, entry in mapped_device.items():
                if isinstance(entry, dict):
                    item = dict(entry)
                    # 确保有 code 字段（与原 FieldMapper 的 list 元素一致）
                    if 'code' not in item:
                        item['code'] = target_param
                    result.append(item)
                else:
                    result.append({'code': target_param, 'source_param': target_param,
                                   'transform': 'none', 'component_type': 'device'})
            return dict_list_to_dto(result, FieldMappingDTO)
        return []

    def get_mapped_device_output_field_keys(self, algorithm_type: str) -> List[str]:
        """获取设备输出字段键列表（映射后）

        对应原 FieldMapper.get_mapped_device_output_field_keys(algorithm_type)。

        Args:
            algorithm_type: 算法类型

        Returns:
            字段代码列表
        """
        output_fields = self.get_mapped_device_output_fields(algorithm_type)
        return [f.code for f in output_fields if f.code]

    def get_device_output_field_codes_by_type(
        self, algorithm_type: str, param_type: str
    ) -> List[str]:
        """根据 param_type 获取设备输出字段代码列表

        对应原 FieldMapper.get_device_output_field_codes_by_type(algorithm_type, param_type)。
        从设备参数中查找 direction='output' 且 param_type 匹配的字段。

        Args:
            algorithm_type: 算法类型
            param_type: 参数类型（如 'stm', 'rttm', 'text'）

        Returns:
            匹配的字段代码列表
        """
        device_params = dict_list_to_dto(
            algo_get_device_params(algorithm_type) or [], DeviceParamDTO
        )
        return [
            p.code for p in device_params
            if p.param_type == param_type
            and p.direction == 'output'
            and p.code
        ]

    def convert_device_output(
        self, algorithm_type: str, device_result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """转换设备输出为映射后的格式

        对应原 FieldMapper.convert_device_output(algorithm_type, device_result)。
        在 ACL 层本地执行映射逻辑（数据来源为 gRPC），避免回引 FieldMapper。

        Args:
            algorithm_type: 算法类型
            device_result: 设备驱动返回的原始数据

        Returns:
            映射后的结果字典
        """
        success = device_result.get('success', False)
        message = device_result.get('message', '')

        mapped_output_fields = self.get_mapped_device_output_fields(algorithm_type)
        orig_output_fields = self.get_device_output_fields(algorithm_type)

        result: Dict[str, Any] = {}

        if not success:
            for code, _field_def in orig_output_fields.items():
                result[code] = message or 'Error'
        elif mapped_output_fields:
            for field_def in mapped_output_fields:
                target_key = field_def.code
                source_param = field_def.source_param or target_key
                value = device_result.get(source_param)
                if value is not None:
                    # 多对一映射：按 dimension_id 区分存储键
                    dim_id = field_def.dimension_id
                    store_key = target_key
                    if dim_id is not None:
                        store_key = f'{target_key}__dim_{dim_id}'
                    result[store_key] = value
                    # 同时保留 target_key 指向第一个有效值
                    if target_key not in result or not result[target_key]:
                        result[target_key] = result[store_key]
        elif orig_output_fields:
            for code, _field_def in orig_output_fields.items():
                result[code] = device_result.get(code, '')
        else:
            for key, value in device_result.items():
                if key not in ('success', 'message'):
                    result[key] = value

        return result

    def get_algorithm_extra_config(self, algorithm_type: str) -> Dict[str, Any]:
        """获取算法额外配置

        对应原 FieldMapper._get_algorithm_extra_config(algorithm_type)。
        在 ACL 层本地构建（数据来源为 gRPC），避免回引 FieldMapper。

        Args:
            algorithm_type: 算法类型

        Returns:
            额外配置字典
        """
        from shared.clients.grpc_clients import (
            algo_get_device_params,
            algo_get_api_params,
            algo_get_param_mapping,
        )

        device_params = algo_get_device_params(algorithm_type) or []
        api_params = algo_get_api_params(algorithm_type) or []
        params = list(device_params) + list(api_params)

        config: Dict[str, Any] = {
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
            if not isinstance(param, dict):
                continue
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

        # 各 component 的映射
        for comp_type in ('device', 'api', 'case', 'reference', 'evaluation'):
            mappings = algo_get_param_mapping(algorithm_type, comp_type) or []
            for mapping in mappings:
                if not isinstance(mapping, dict):
                    continue
                src = mapping.get('source', '')
                source_param = mapping.get('source_param', '')
                if src in ['case_table', 'case_field']:
                    config['needs_extra_params'] = True
                    config['case_fields'][source_param] = source_param

        if config['case_fields']:
            config['needs_extra_params'] = True

        return config

    # ========== 参考参数查询 ==========

    _REF_PARAM_KNOWN = frozenset({
        'code', 'type', 'value', 'annotation_code',
        'annotation_format', 'round_number', 'result_data',
    })

    def _to_ref_param_list(self, raw_list: list) -> List[ReferenceParamDTO]:
        """将 raw list[dict] 转换为 List[ReferenceParamDTO]，动态字段收纳到 result_data。"""
        dtos = dict_list_to_dto(raw_list or [], ReferenceParamDTO)
        for dto, raw in zip(dtos, raw_list or []):
            if isinstance(raw, dict):
                dto.result_data = {
                    k: v for k, v in raw.items()
                    if k not in self._REF_PARAM_KNOWN
                }
        return dtos

    def generate_reference_params(
        self, test_case_config: Optional[Dict] = None, round_data: Optional[Dict] = None
    ) -> List[ReferenceParamDTO]:
        """生成参考参数

        对应原 ReferenceParamsGenerator.generate_for_round(test_case, round_data)。

        Args:
            test_case_config: 用例配置
            round_data: 单轮配置

        Returns:
            参考参数 DTO 列表
        """
        raw = algo_generate_reference_params(test_case_config, round_data) or []
        return self._to_ref_param_list(raw)

    def get_all_reference_params(self, reference_params_col) -> List[ReferenceParamDTO]:
        """获取所有参考参数

        对应原 ReferenceParamsGenerator.get_all_reference_params(reference_params_col)。

        Args:
            reference_params_col: reference_params 集合

        Returns:
            参考参数 DTO 列表
        """
        from shared.clients.grpc_clients import algo_get_all_reference_params
        raw = algo_get_all_reference_params(reference_params_col) or []
        return self._to_ref_param_list(raw)

    def get_reference_params_for_report(self, reference_params_col) -> Dict[str, Any]:
        """获取用于报告展示的参考参数字典

        对应原 ReferenceParamsGenerator.get_reference_params_for_report(reference_params_col)。

        Args:
            reference_params_col: reference_params 集合

        Returns:
            按 code 分组的参考参数字典
        """
        return algo_get_reference_params_for_report(reference_params_col) or {}


# 模块级单例
algorithm_query_acl_repository = AlgorithmQueryACLRepository()
