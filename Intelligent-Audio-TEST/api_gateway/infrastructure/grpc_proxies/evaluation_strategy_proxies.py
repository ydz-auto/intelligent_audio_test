# -*- coding: utf-8 -*-
"""评估策略 gRPC 代理（INT-590）。

作为 api_gateway 的 ACL 层，转发到 task_service.EvaluationStrategyService，
避免 application 层直接 import shared.clients.grpc_clients。
所有方法返回 dict: {success, message, data, code}
"""
import json

from shared.clients.grpc_clients import get_evaluation_strategy_service_stub
from shared.proto import task_service_pb2 as task_pb

from ._common import _attach_code, _grpc_call


class _EvaluationStrategyProxy:
    """评估策略 CRUD 代理：把方法调用转发到 gRPC EvaluationStrategyService"""

    def _resp(self, resp):
        """统一解析 TaskConfigResponse 为 dict（业务码透传，INT-1759 proto code）"""
        data = json.loads(resp.data) if resp.data else None
        return _attach_code({'success': resp.success, 'message': resp.message,
                             'data': data}, resp)

    @property
    def stub(self):
        """获取 EvaluationStrategyService stub（供需要直接调 RPC 的场景使用）"""
        return get_evaluation_strategy_service_stub()

    # ---- 写操作 ----

    def create(self, data):
        def _call():
            stub = get_evaluation_strategy_service_stub()
            resp = stub.CreateEvaluationStrategy(task_pb.CreateEvaluationStrategyRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建评估策略失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='创建评估策略失败',
        )

    def update(self, strategy_id, data):
        def _call():
            stub = get_evaluation_strategy_service_stub()
            resp = stub.UpdateEvaluationStrategy(task_pb.UpdateEvaluationStrategyRequest(
                strategy_id=str(strategy_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新评估策略失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='更新评估策略失败',
        )

    def delete(self, strategy_id):
        def _call():
            stub = get_evaluation_strategy_service_stub()
            resp = stub.DeleteEvaluationStrategy(task_pb.DeleteEvaluationStrategyRequest(
                strategy_id=str(strategy_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除评估策略失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='删除评估策略失败',
        )

    # ---- 读操作 ----

    def list_strategies(self, page=1, per_page=10, keyword=None,
                        algorithm_type=None, enabled=None):
        def _call():
            stub = get_evaluation_strategy_service_stub()
            resp = stub.ListEvaluationStrategies(task_pb.ListEvaluationStrategiesRequest(
                page=int(page),
                per_page=int(per_page),
                keyword=keyword or '',
                algorithm_type=algorithm_type or '',
                enabled=enabled if enabled is not None else '',
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询评估策略列表失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='查询评估策略列表失败',
        )

    def get_strategy(self, strategy_id):
        def _call():
            stub = get_evaluation_strategy_service_stub()
            resp = stub.GetEvaluationStrategy(task_pb.GetEvaluationStrategyRequest(
                strategy_id=str(strategy_id),
            ))
            return self._resp(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'获取评估策略详情失败: {e}', 'data': None, 'code': 500},
            error_msg_prefix='获取评估策略详情失败',
        )


# 评估策略 CRUD 模块级单例
evaluation_strategy_service = _EvaluationStrategyProxy()
