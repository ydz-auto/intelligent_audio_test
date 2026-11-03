# -*- coding: utf-8 -*-
"""evaluation_service ACL 仓储 — gRPC 实现。

从 report_service/infrastructure/clients/grpc_clients.py 迁出，
维度配置与维度评估结果查询返回 dataclass DTO。
"""
from __future__ import annotations

import json as _json
import logging
import os as _os
from typing import Dict, List

import grpc

from report_service.domain.dto import DimensionDTO, DimensionResultDTO, DimensionResultsWithBody
from report_service.domain.repositories.acl.evaluation_acl_repository import (
    EvaluationConfigAclRepository,
    EvaluationDataAclRepository,
)
from shared.utils.aggregation_gate import heavy_include_body_aggregation
from shared.utils.dto_utils import dict_to_dto, dict_list_to_dto
from shared.config.query_constants import QueryConstants

logger = logging.getLogger(__name__)

# INT-2149：include_body 拉取的 result_id 分批大小。
# 带 api_raw_response 时单条维度结果可到 MB 级（多轮任务的原始响应快照），
# 一次拉数百条会超过 gRPC 单条消息上限（GRPC_MAX_MESSAGE_MB，默认 64MB），
# 被 RESOURCE_EXHAUSTED 拦下后旧实现整个返回 {}，加权维度（weighted_sum_ratio /
# weighted_wer）静默降级为简单平均。按块拉取把单条响应压在上限内；
# 单块仍超限时再二分（见 _call_with_shrink），直到单条为止。
_DIM_RESULT_BODY_CHUNK_SIZE = max(
    int(_os.getenv('REPORT_DIM_RESULT_BODY_CHUNK_SIZE', '16')), 1)


def _attach(dto, payload):
    if dto is not None and payload is not None:
        try:
            dto.result_data = payload
        except Exception:
            logger.debug("附加 result_data 到 DTO 失败", exc_info=True)
    return dto


class EvaluationDataAclRepositoryImpl(EvaluationDataAclRepository):
    """evaluation_service.EvaluationDataService 跨域只读查询 gRPC 实现。"""

    def _call(self, result_ids, include_body: bool) -> Dict[int, List[DimensionResultDTO]]:
        """单次 gRPC 调用；异常/失败向上抛，由调用方决定分块或降级。"""
        from shared.clients.grpc_clients import get_evaluation_data_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb
        from shared.utils.grpc_json import loads as _loads

        stub = get_evaluation_data_service_stub()
        resp = stub.GetDimensionResultsByResultIds(
            eval_pb.GetDimensionResultsByResultIdsRequest(
                result_ids=_json.dumps(list(result_ids), ensure_ascii=False, default=str),
                include_body=bool(include_body),
            ))
        if not resp.success:
            raise RuntimeError(resp.message or 'GetDimensionResultsByResultIds failed')
        data = _loads(resp.data, {})
        items = data.get('items', []) if isinstance(data, dict) else []
        result_map: Dict[int, List[DimensionResultDTO]] = {}
        for it in items:
            if not isinstance(it, dict):
                continue
            rid = it.get('test_result_id') or it.get('result_id')
            if rid is None:
                continue
            result_map.setdefault(rid, []).append(_attach(dict_to_dto(it, DimensionResultDTO), it))
        return result_map

    def _call_with_shrink(self, result_ids, include_body: bool, dropped_ids=None):
        """单块调用；撞 gRPC 收包上限时二分重试，最小到单条。

        单条结果本身就超过上限时只丢弃这一条（返回空 map），同块其余结果照常返回，
        避免一条异常大的原始响应把整块（乃至整批）原始响应带走。
        dropped_ids（可选列表）收集被丢弃的 result_id，供上层打覆盖标记。
        """
        try:
            return self._call(result_ids, include_body)
        except Exception as e:  # noqa: BLE001 —— 只有超限可二分/丢弃，其余原样抛
            if not (isinstance(e, grpc.RpcError)
                    and e.code() == grpc.StatusCode.RESOURCE_EXHAUSTED):
                raise
            if len(result_ids) <= 1:
                logger.warning(
                    "dimension result %s exceeds gRPC message limit, skipped: %s",
                    result_ids[0], e)
                if dropped_ids is not None and result_ids[0] not in dropped_ids:
                    dropped_ids.append(result_ids[0])
                return {}
            mid = len(result_ids) // 2
            merged: Dict[int, List[DimensionResultDTO]] = {}
            for part in (result_ids[:mid], result_ids[mid:]):
                for rid, rows in self._call_with_shrink(
                        part, include_body, dropped_ids=dropped_ids).items():
                    merged.setdefault(rid, []).extend(rows)
            return merged

    def _collect_body_map(self, ids, use_gate: bool):
        """按块拉取带 body 的维度结果，返回 (map, failed_chunks, dropped_ids)。

        INT-2379 C3：非超限失败（如服务端 success=False / 瞬断）的块先重试 1 次，
        OSS 瞬断可自愈；仍失败才记入 failed_chunks，由上层保留基础行并打标记。
        """
        result_map: Dict[int, List[DimensionResultDTO]] = {}
        failed_chunks = []
        dropped_ids = []

        def _run():
            for start in range(0, len(ids), _DIM_RESULT_BODY_CHUNK_SIZE):
                chunk = ids[start:start + _DIM_RESULT_BODY_CHUNK_SIZE]
                try:
                    part = self._call_with_shrink(
                        chunk, True, dropped_ids=dropped_ids)
                except Exception as e:  # noqa: BLE001 —— 重试一次后再收口
                    logger.warning(
                        "get_dimension_results_with_body chunk [%s:%s] failed, "
                        "retrying once: %s", start, start + len(chunk), e)
                    try:
                        part = self._call_with_shrink(
                            chunk, True, dropped_ids=dropped_ids)
                    except Exception as e2:  # noqa: BLE001
                        logger.warning(
                            "get_dimension_results_with_body chunk [%s:%s] failed "
                            "after retry: %s", start, start + len(chunk), e2)
                        failed_chunks.append((start, start + len(chunk), str(e2)))
                        continue
                for rid, rows in part.items():
                    result_map.setdefault(rid, []).extend(rows)

        if use_gate:
            # INT-2379 C6：大体量 include_body 拉取串行化，避免并发叠加峰值
            with heavy_include_body_aggregation():
                _run()
        else:
            _run()
        return result_map, failed_chunks, dropped_ids

    def get_dimension_results_by_result_ids(
        self, result_ids, include_body: bool = False,
    ) -> Dict[int, List[DimensionResultDTO]]:
        if not result_ids:
            return {}
        ids = list(result_ids)
        if not include_body:
            # 轻量载荷（无原始响应）单次即可，保持既有调用开销
            try:
                return self._call(ids, include_body=False)
            except Exception as e:
                logger.warning("get_dimension_results_by_result_ids gRPC failed: %s", e)
                return {}

        # 详情入口（按用例+维度按需展开）只取小块，不进大体量聚合护栏，避免被
        # 长批量聚合排队阻塞；覆盖信息由 get_dimension_results_with_body 提供。
        result_map, _, _ = self._collect_body_map(ids, use_gate=False)
        return result_map

    def get_dimension_results_with_body(
        self, result_ids,
    ) -> DimensionResultsWithBody:
        """带原始响应拉取维度结果，上抛覆盖信息（INT-2379 C2/C3/C6）。"""
        if not result_ids:
            return DimensionResultsWithBody({}, [], [], [], [])
        requested = list(dict.fromkeys(result_ids))
        result_map, failed_chunks, dropped_ids = self._collect_body_map(
            requested, use_gate=True)
        covered = [rid for rid in requested if rid in result_map]
        return DimensionResultsWithBody(
            dim_map=result_map,
            requested_ids=requested,
            covered_ids=covered,
            failed_chunks=failed_chunks,
            dropped_ids=list(dropped_ids),
        )


class EvaluationConfigAclRepositoryImpl(EvaluationConfigAclRepository):
    """evaluation_service.EvaluationConfigService 跨域只读查询 gRPC 实现。"""

    def list_dimensions_all(self) -> List[DimensionDTO]:
        from shared.clients.grpc_clients import get_evaluation_config_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_evaluation_config_service_stub()
            resp = stub.ListDimensions(eval_pb.ListDimensionsRequest(
                category_id=0, page=1, per_page=QueryConstants.EXPORT_PAGE_SIZE, search='',
            ))
            if not resp.success:
                return []
            data = _loads(resp.data, {})
            if isinstance(data, dict):
                items = data.get('items', []) or data.get('list', [])
            else:
                items = data if isinstance(data, list) else []
            return [
                _attach(dict_to_dto(d, DimensionDTO), d)
                for d in items
                if isinstance(d, dict) and d.get('status', True) and not d.get('deleted', False)
            ]
        except Exception as e:
            logger.warning("list_dimensions_all gRPC failed: %s", e)
            return []

    def get_dimension_by_ids(self, dim_ids) -> Dict[str, DimensionDTO]:
        if not dim_ids:
            return {}
        from shared.clients.grpc_clients import get_evaluation_config_service_stub
        from shared.proto import evaluation_service_pb2 as eval_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_evaluation_config_service_stub()
            ids_list = [int(d) for d in dim_ids if d is not None]
            resp = stub.GetDimensionByIds(eval_pb.GetDimensionByIdsRequest(
                dim_ids=_json.dumps(ids_list, ensure_ascii=False, default=str),
            ))
            if not resp.success:
                return {}
            data = _loads(resp.data, {})
            items = data.get('items', []) if isinstance(data, dict) else data
            result_map: Dict[str, DimensionDTO] = {}
            if isinstance(items, list):
                for d in items:
                    if isinstance(d, dict) and d.get('id') is not None:
                        result_map[str(d.get('id'))] = _attach(dict_to_dto(d, DimensionDTO), d)
            elif isinstance(items, dict):
                for k, d in items.items():
                    if isinstance(d, dict):
                        result_map[str(k)] = _attach(dict_to_dto(d, DimensionDTO), d)
            return result_map
        except Exception as e:
            logger.warning("get_dimension_by_ids gRPC failed: %s", e)
            return {}
