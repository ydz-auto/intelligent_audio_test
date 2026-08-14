# -*- coding: utf-8 -*-
"""algorithm_service 防腐层仓储（ACL Repository）

替代 evaluation_service 直接 `from algorithm_service.infrastructure.persistence.models import ...`
的跨域 ORM 引用。

本文件属于 infrastructure 层的防腐层（ACL），封装 gRPC 调用将 algorithm_service 的
数据模型转换为 evaluation_service 可用的 dataclass DTO，隔离上下游领域模型。
向上层（application/commands, application/queries）返回 dataclass DTO，不返回 ORM 对象。
"""
import logging
from typing import Any, Dict, List, Optional

from evaluation_service.domain.dto import (
    DimensionParamDTO,
    DimensionRelationDTO,
    ParamMappingDTO,
)
from evaluation_service.domain.repositories.algorithm_acl_repository import AlgorithmAclRepository as _AlgorithmAclRepositoryABC
from shared.clients.grpc_clients import get_algorithm_definition_service_stub
from shared.proto import algorithm_service_pb2 as algo_pb
from shared.utils.dto_utils import dict_list_to_dto
from shared.utils.grpc_json import loads as _loads, dumps as _dumps

logger = logging.getLogger(__name__)


class AlgorithmAclRepository(_AlgorithmAclRepositoryABC):
    """algorithm_service 防腐层仓储

    封装 gRPC 调用，提供领域层可用的 dataclass DTO 返回值。
    读方法返回 dataclass DTO，不返回 ORM 对象。
    """

    # ========== 维度关系管理 ==========

    def sync_dimension_relations(
        self, dimension_id: int, relations: List[Dict[str, Any]]
    ) -> bool:
        """同步算法-维度关联（先清空旧关联再插入新关联）。

        Args:
            dimension_id: 维度 ID
            relations: 关联列表 [{algorithm_type, is_default, weight}, ...]

        Returns:
            是否成功
        """
        try:
            stub = get_algorithm_definition_service_stub()
            resp = stub.SyncDimensionRelations(algo_pb.SyncDimensionRelationsRequest(
                dimension_id=dimension_id,
                data=_dumps(relations),
            ))
            if not resp.success:
                logger.warning('SyncDimensionRelations failed: %s', resp.message)
                return False
            return True
        except Exception as e:
            logger.exception('sync_dimension_relations failed: %s', e)
            return False

    def get_algorithm_dimensions(self, algorithm_type: str) -> List[int]:
        """查询算法关联的 dimension_ids 列表。

        封装 algorithm_service.AlgorithmDefinitionService.GetAlgorithmDimensions RPC。
        失败时返回空列表。
        """
        try:
            stub = get_algorithm_definition_service_stub()
            req = algo_pb.GetAlgorithmDimensionsRequest(
                algorithm_type=algorithm_type or ''
            )
            resp = stub.GetAlgorithmDimensions(req)
            if resp.success:
                data = _loads(resp.data, {}) or {}
                return [int(d) for d in data.get('dimension_ids', [])]
        except Exception:
            logger.warning("get_algorithm_dimensions 失败", exc_info=True)
        return []

    def create_dimension_relation(self, data: Dict[str, Any]) -> bool:
        """创建单条算法-维度关联。

        封装 algorithm_service.AlgorithmDefinitionService.CreateDimensionRelation RPC。
        """
        try:
            stub = get_algorithm_definition_service_stub()
            resp = stub.CreateDimensionRelation(algo_pb.CreateDimensionRelationRequest(
                data=_dumps(data),
            ))
            return resp.success
        except Exception:
            return False

    def get_relations_by_dimension(self, dimension_id: int) -> List[DimensionRelationDTO]:
        """按 dimension_id 查询未删除的算法-维度关联列表。"""
        try:
            stub = get_algorithm_definition_service_stub()
            resp = stub.GetRelationsByDimension(algo_pb.GetRelationsByDimensionRequest(
                dimension_id=dimension_id,
            ))
            if not resp.success:
                logger.warning('GetRelationsByDimension failed: %s', resp.message)
                return []
            data = _loads(resp.data, {})
            return dict_list_to_dto(data, DimensionRelationDTO, list_key='relations')
        except Exception as e:
            logger.exception('get_relations_by_dimension failed: %s', e)
            return []

    # ========== 评估维度参数管理 ==========

    def create_dimension_param(self, param_data: Dict[str, Any]) -> Optional[int]:
        """创建单条评估维度参数。返回新 param_id 或 None。"""
        try:
            stub = get_algorithm_definition_service_stub()
            resp = stub.CreateDimensionParam(algo_pb.CreateDimensionParamRequest(
                data=_dumps(param_data),
            ))
            if not resp.success:
                logger.warning('CreateDimensionParam failed: %s', resp.message)
                return None
            data = _loads(resp.data, {})
            return data.get('id')
        except Exception as e:
            logger.exception('create_dimension_param failed: %s', e)
            return None

    def delete_dimension_params_by_direction(
        self, dimension_id: int, param_direction: str
    ) -> bool:
        """按 dimension_id + param_direction 物理删除评估维度参数。"""
        try:
            stub = get_algorithm_definition_service_stub()
            resp = stub.DeleteDimensionParamsByDirection(
                algo_pb.DeleteDimensionParamsByDirectionRequest(
                    dimension_id=dimension_id,
                    param_direction=param_direction,
                )
            )
            if not resp.success:
                logger.warning('DeleteDimensionParamsByDirection failed: %s', resp.message)
                return False
            return True
        except Exception as e:
            logger.exception('delete_dimension_params_by_direction failed: %s', e)
            return False

    def get_dimension_params(self, dimension_id: int) -> List[DimensionParamDTO]:
        """获取评估维度的参数列表（含 output/input 完整字段）。"""
        try:
            stub = get_algorithm_definition_service_stub()
            resp = stub.GetDimensionParams(algo_pb.GetDimensionParamsRequest(
                dimension_id=dimension_id,
            ))
            if not resp.success:
                logger.warning('GetDimensionParams %s failed: %s', dimension_id, resp.message)
                return []
            data = _loads(resp.data, {})
            return dict_list_to_dto(data, DimensionParamDTO, list_key='params')
        except Exception as e:
            logger.exception('get_dimension_params failed: %s', e)
            return []

    def find_audio_dimension_ids(self, dim_ids: List[int]) -> set:
        """查询需要音频文件参数的维度 ID 集合。"""
        try:
            stub = get_algorithm_definition_service_stub()
            resp = stub.FindAudioDimensionIds(algo_pb.FindAudioDimensionIdsRequest(
                dimension_ids=_dumps(dim_ids),
            ))
            if not resp.success:
                logger.warning('FindAudioDimensionIds failed: %s', resp.message)
                return set()
            data = _loads(resp.data, {})
            result = data.get('audio_dimension_ids', []) if isinstance(data, dict) else []
            return set(int(d) for d in result)
        except Exception as e:
            logger.exception('find_audio_dimension_ids failed: %s', e)
            return set()

    def get_field_mappings(self, algorithm_type: str):
        """获取字段定义（original + mapped），返回 FieldMapperWrapper"""
        from shared.clients.grpc_clients import algo_get_field_mappings
        return algo_get_field_mappings(algorithm_type)

    def get_param_mapping(self, algorithm_type: str, component_type: str):
        """获取参数映射"""
        from shared.clients.grpc_clients import algo_get_param_mapping
        return algo_get_param_mapping(algorithm_type, component_type)

    def get_reference_params_list(self, *args, **kwargs):
        """获取参考参数列表"""
        from shared.clients.grpc_clients import algo_get_reference_params_list
        return algo_get_reference_params_list(*args, **kwargs)

    def load_reference_params_file(self, filepath: str = ''):
        """加载参考参数文件"""
        from shared.clients.grpc_clients import algo_load_reference_params_file
        return algo_load_reference_params_file(filepath)

    def extract_case_all_params(self, case_config=None):
        """提取用例所有参数"""
        from shared.clients.grpc_clients import algo_extract_case_all_params
        return algo_extract_case_all_params(case_config)

    def get_output_fields(self, algorithm_type: str, test_type: str = None):
        """获取结果输出字段（GetOutputFields）

        通过 gRPC 调用 algorithm_service.AlgorithmQueryService.GetOutputFields。
        """
        from shared.clients.grpc_clients import algo_get_output_fields
        return algo_get_output_fields(algorithm_type, test_type=test_type)

    # ========== 参数映射同步 ==========

    def list_param_mappings_for_dimension(self, dimension_id: int) -> List[ParamMappingDTO]:
        """查询某维度所有 ParamMapping（含软删除项，用于同步逻辑）。"""
        try:
            stub = get_algorithm_definition_service_stub()
            resp = stub.ListParamMappingsForDimension(
                algo_pb.ListParamMappingsForDimensionRequest(
                    dimension_id=dimension_id,
                )
            )
            if not resp.success:
                logger.warning('ListParamMappingsForDimension failed: %s', resp.message)
                return []
            data = _loads(resp.data, {})
            return dict_list_to_dto(data, ParamMappingDTO, list_key='mappings')
        except Exception as e:
            logger.exception('list_param_mappings_for_dimension failed: %s', e)
            return []

    def sync_param_mappings(
        self,
        dimension_id: int,
        params: Any,
        direction: str = 'output',
        algorithm_type: str = 'voice_llm',
    ) -> bool:
        """同步 ParamMapping：当评估维度的输入/输出字段变更时，
        自动为该维度创建/更新/删除对应的 ParamMapping 记录。

        Args:
            dimension_id: 维度 ID
            params: 参数列表（list 或 JSON 字符串）
            direction: 参数方向（input / output）
            algorithm_type: 默认算法类型

        Returns:
            是否成功
        """
        try:
            stub = get_algorithm_definition_service_stub()
            data = {
                'params': params,
                'direction': direction,
                'algorithm_type': algorithm_type,
            }
            resp = stub.SyncParamMappings(algo_pb.SyncParamMappingsRequest(
                dimension_id=dimension_id,
                data=_dumps(data),
            ))
            if not resp.success:
                logger.warning('SyncParamMappings failed: %s', resp.message)
                return False
            return True
        except Exception as e:
            logger.exception('sync_param_mappings failed: %s', e)
            return False


# 模块级单例
algorithm_acl_repository = AlgorithmAclRepository()
