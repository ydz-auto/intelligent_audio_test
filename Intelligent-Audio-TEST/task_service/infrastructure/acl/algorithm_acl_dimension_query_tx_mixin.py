# -*- coding: utf-8 -*-
"""AlgorithmDimensionQueryTxMixin - 跨域维度查询 + 事务兼容 + 算法查询服务封装 Mixin。

从 algorithm_acl_repository.py 按职责拆分，承担：
- 跨域 Dimension 查询（evaluation_service gRPC，保持原有调用不变）
- 事务控制兼容 no-op（gRPC 每条写 RPC 均自动提交，commit/rollback/flush 仅为向后兼容）
- 算法查询服务封装（AlgorithmQueryService 系列 algo_* 方法）

由 AlgorithmRepository 组合复用，不单独实例化。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from shared.utils.grpc_json import loads as _loads
from shared.utils.dto_utils import dict_list_to_dto
from shared.proto import algorithm_service_pb2 as _pb
from task_service.domain.dto.task_acl_dto import DimensionDTO

from task_service.infrastructure.acl.algorithm_acl_grpc_helpers import _get_stub

_logger = logging.getLogger(__name__)


class AlgorithmDimensionQueryTxMixin:
    """跨域维度查询 / 事务兼容 no-op / 算法查询服务封装 Mixin。"""

    # ========== 跨域查询：Dimension（evaluation_service gRPC，保持不变）==========

    def _fetch_dimensions_via_grpc(self, dim_ids: List[int]) -> list:
        """通过 gRPC 批量查询 Dimension 基础信息。

        Dimension 是 evaluation_service 自有 PO，通过
        evaluation_service.EvaluationConfigService.GetDimensionByIds 获取。
        失败时返回空列表（仅日志告警）。
        """
        if not dim_ids:
            return []

        from shared.clients.grpc_clients import get_evaluation_config_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb

        try:
            stub = get_evaluation_config_service_stub()
            resp = stub.GetDimensionByIds(eval_pb.GetDimensionByIdsRequest(
                dim_ids=json.dumps(list(dim_ids)),
            ))
            if not resp.success:
                _logger.warning("GetDimensionByIds gRPC 失败: %s", resp.message)
                return []
            payload = _loads(resp.data, {}) if resp.data else {}
        except Exception as e:
            _logger.warning("GetDimensionByIds gRPC 异常: %s", e)
            return []

        if not isinstance(payload, dict):
            return []
        items = payload.get('items', []) or []
        return dict_list_to_dto(items, DimensionDTO)

    def get_dimension_by_id(self, dim_id):
        """按 ID 查询单个评价维度（返回 DimensionDTO 或 None）。"""
        if not dim_id:
            return None
        dims = self._fetch_dimensions_via_grpc([dim_id])
        return dims[0] if dims else None

    def list_dimensions_by_ids(
        self, dim_ids: List[int], only_not_deleted: bool = True
    ) -> list:
        """按 ID 列表查询评价维度（返回 DimensionDTO 列表）。

        only_not_deleted 参数保留向后兼容，gRPC 端默认只查未删除。
        """
        return self._fetch_dimensions_via_grpc(dim_ids)

    def list_dimensions_map_by_ids(
        self, dim_ids: List[int], only_not_deleted: bool = True
    ) -> Dict[int, Any]:
        """按 ID 列表查询评价维度，返回 {id: DimensionDTO} 映射。"""
        dims = self.list_dimensions_by_ids(dim_ids, only_not_deleted)
        return {d.id: d for d in dims if d.id is not None}

    def list_dimension_names_map_by_ids(
        self, dim_ids: List[int], only_not_deleted: bool = True
    ) -> Dict[int, str]:
        """按 ID 列表查询评价维度名称，返回 {id: name} 映射。"""
        dims = self.list_dimensions_by_ids(dim_ids, only_not_deleted)
        return {d.id: d.name for d in dims if d.id is not None}

    # ========== 事务控制（gRPC auto-commit，保留为兼容 no-op）==========

    def commit(self):
        """提交事务（gRPC 每条写 RPC 均自动提交，本调用为兼容 no-op）。"""
        try:
            _get_stub().CommitTransaction(_pb.CommitTransactionRequest())
        except Exception as e:  # noqa: BLE001
            _logger.debug("CommitTransaction no-op 失败（可忽略）: %s", e)

    def rollback(self):
        """回滚事务（gRPC 已自动提交的写操作无法回滚，本调用为兼容 no-op）。"""
        try:
            _get_stub().RollbackTransaction(_pb.RollbackTransactionRequest())
        except Exception as e:  # noqa: BLE001
            _logger.debug("RollbackTransaction no-op 失败（可忽略）: %s", e)

    def flush(self):
        """flush session（gRPC 每条写 RPC 均自动提交，本调用为兼容 no-op）。"""
        try:
            _get_stub().FlushTransaction(_pb.FlushTransactionRequest())
        except Exception as e:  # noqa: BLE001
            _logger.debug("FlushTransaction no-op 失败（可忽略）: %s", e)

    # ========== 算法查询服务封装（AlgorithmQueryService）==========

    def algo_load_reference_params_file(self, filepath: str = ''):
        """从 OSS 加载参考参数文件内容。

        封装 shared.clients.grpc_clients.algo_load_reference_params_file，
        通过 algorithm_service AlgorithmQueryService.LoadReferenceParamsFile RPC。
        """
        from shared.clients.grpc_clients import algo_load_reference_params_file
        return algo_load_reference_params_file(filepath)

    def algo_get_full_field_mapping(self, algorithm_type: str):
        """获取算法完整字段映射。

        封装 shared.clients.grpc_clients.algo_get_full_field_mapping，
        通过 algorithm_service AlgorithmQueryService.GetFullFieldMapping RPC。
        """
        from shared.clients.grpc_clients import algo_get_full_field_mapping
        return algo_get_full_field_mapping(algorithm_type)

    def algo_get_output_fields(self, algorithm_type: str, test_type: str = None):
        """获取算法结果输出字段。

        封装 shared.clients.grpc_clients.algo_get_output_fields，
        通过 algorithm_service AlgorithmQueryService.GetOutputFields RPC。
        """
        from shared.clients.grpc_clients import algo_get_output_fields
        return algo_get_output_fields(algorithm_type, test_type)

    def algo_generate_reference_params(self, test_case_config=None, round_data=None):
        """生成参考参数。

        封装 shared.clients.grpc_clients.algo_generate_reference_params，
        通过 algorithm_service AlgorithmQueryService.GenerateReferenceParams RPC。
        """
        from shared.clients.grpc_clients import algo_generate_reference_params
        return algo_generate_reference_params(test_case_config, round_data)

    def algo_get_all_reference_params(self, reference_params_col=None):
        """获取所有参考参数。

        封装 shared.clients.grpc_clients.algo_get_all_reference_params，
        通过 algorithm_service AlgorithmQueryService.GetAllReferenceParams RPC。
        """
        from shared.clients.grpc_clients import algo_get_all_reference_params
        return algo_get_all_reference_params(reference_params_col)

    def algo_extract_case_all_params(self, case_config=None):
        """提取用例全部算法参数。

        封装 shared.clients.grpc_clients.algo_extract_case_all_params，
        通过 algorithm_service AlgorithmQueryService.ExtractCaseAllParams RPC。
        """
        from shared.clients.grpc_clients import algo_extract_case_all_params
        return algo_extract_case_all_params(case_config)

    def algo_reload_config(self):
        """重新加载算法配置缓存（热更新）。

        封装 shared.clients.grpc_clients.algo_reload_config，
        通过 algorithm_service AlgorithmQueryService.ReloadConfig RPC。
        """
        from shared.clients.grpc_clients import algo_reload_config
        return algo_reload_config()
