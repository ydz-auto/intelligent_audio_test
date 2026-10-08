# -*- coding: utf-8 -*-
"""Benchmark 排行代理（Benchmark Config Proxy）

封装 report_service.BenchmarkConfigService 的 gRPC 调用，作为 api_gateway 的
ACL 层，避免 application 层直接 import shared.clients.grpc_clients。
所有方法返回 dict: {success, message, data, code}
"""
import json

from shared.clients.grpc_clients import get_benchmark_config_service_stub

from ._common import _grpc_call

from shared.proto import report_service_pb2 as report_pb


class _BenchmarkConfigProxy:
    """Benchmark 排行代理：把方法调用转发到 gRPC BenchmarkConfigService"""

    def _resp(self, resp):
        """统一解析 BenchmarkResponse 为 dict"""
        return {
            'success': resp.success,
            'message': resp.message,
            'data': json.loads(resp.data) if resp.data else None,
            'code': resp.code if resp.code else (0 if resp.success else 500),
        }

    # ---- 写操作 ----

    def compute_ranking(self, params):
        """触发排行计算（全量或按 suite/category/publishedTaskId/source 范围）"""
        def _call():
            stub = get_benchmark_config_service_stub()
            resp = stub.ComputeBenchmarkRanking(report_pb.BenchmarkCommandRequest(
                data=json.dumps(params or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'排行计算失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='排行计算失败',
        )

    def create_source(self, params):
        """创建外部基线数据源"""
        def _call():
            stub = get_benchmark_config_service_stub()
            resp = stub.CreateBenchmarkSource(report_pb.BenchmarkCommandRequest(
                data=json.dumps(params or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建数据源失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建数据源失败',
        )

    def import_baselines(self, params):
        """批量导入外部基线（导入即不可变快照新版本，幂等）"""
        def _call():
            stub = get_benchmark_config_service_stub()
            resp = stub.ImportBenchmarkBaselines(report_pb.BenchmarkCommandRequest(
                data=json.dumps(params or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'基线导入失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='基线导入失败',
        )

    def update_metric_mapping(self, mapping_id, params):
        """更新指标映射"""
        def _call():
            stub = get_benchmark_config_service_stub()
            payload = dict(params or {})
            payload['mapping_id'] = int(mapping_id)
            resp = stub.UpdateBenchmarkMetricMapping(report_pb.BenchmarkCommandRequest(
                data=json.dumps(payload, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新指标映射失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新指标映射失败',
        )

    # ---- 读操作 ----

    def get_ranking(self, params):
        """排行查询（只读 ReadModel）"""
        def _call():
            stub = get_benchmark_config_service_stub()
            resp = stub.GetBenchmarkRanking(report_pb.BenchmarkQueryRequest(
                data=json.dumps(params or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询排行失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询排行失败',
        )

    def get_ranking_subjects(self, params):
        """参与排行的被测主体列表"""
        def _call():
            stub = get_benchmark_config_service_stub()
            resp = stub.GetBenchmarkRankingSubjects(report_pb.BenchmarkQueryRequest(
                data=json.dumps(params or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询被测主体失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询被测主体失败',
        )

    def list_sources(self, params):
        """数据源列表"""
        def _call():
            stub = get_benchmark_config_service_stub()
            resp = stub.ListBenchmarkSources(report_pb.BenchmarkQueryRequest(
                data=json.dumps(params or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询数据源失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询数据源失败',
        )

    def list_baselines(self, params):
        """基线条目列表（当前生效版本）"""
        def _call():
            stub = get_benchmark_config_service_stub()
            resp = stub.ListBenchmarkBaselines(report_pb.BenchmarkQueryRequest(
                data=json.dumps(params or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询基线失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询基线失败',
        )

    def list_metric_mappings(self, params):
        """指标映射列表"""
        def _call():
            stub = get_benchmark_config_service_stub()
            resp = stub.ListBenchmarkMetricMappings(report_pb.BenchmarkQueryRequest(
                data=json.dumps(params or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询指标映射失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询指标映射失败',
        )


# Benchmark 排行代理模块级单例
benchmark_config_service = _BenchmarkConfigProxy()
