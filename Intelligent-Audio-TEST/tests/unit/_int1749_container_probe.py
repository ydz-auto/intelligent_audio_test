# -*- coding: utf-8 -*-
"""INT-1749 容器内实测：执行侧批量变换经真实 gRPC 跨进程（shadow 包，镜像 env）

在 algorithm_service 镜像里以影子包（本 worktree 源码）启动 AlgorithmQueryService，
再用 api_test_service 的真实 ACL + EvalOutputTransformService 打一次批量变换：
- N 个字段只发 1 次 RPC（stub 计数 + 服务端接收计数）
- json_parse → dict、base64 编码语义、none 原值直传
"""
import logging
import sys
import threading

logging.basicConfig(level=logging.INFO)

import grpc
from concurrent import futures

from shared.proto import algorithm_service_pb2_grpc as pb_grpc
from algorithm_service.interfaces.grpc.algorithm_query_servicer import (
    AlgorithmQueryServicer,
)
from shared.clients import _grpc_stubs

PORT = 50999
server_received = []


class _CountingServicer(AlgorithmQueryServicer):
    def ConvertFieldValues(self, request, context):
        server_received.append(request)
        return super().ConvertFieldValues(request, context)


def main():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=2))
    pb_grpc.add_AlgorithmQueryServiceServicer_to_server(_CountingServicer(), server)
    server.add_insecure_port(f'127.0.0.1:{PORT}')
    server.start()
    try:
        channel = grpc.insecure_channel(f'127.0.0.1:{PORT}')
        stub = pb_grpc.AlgorithmQueryServiceStub(channel)
        _grpc_stubs.get_algorithm_query_service_stub = lambda: stub

        from api_test_service.infrastructure.acl.algorithm_acl_repository import (
            AlgorithmQueryAclRepositoryImpl,
        )
        from api_test_service.domain.services.eval_output_transform_service import (
            EvalOutputTransformService,
        )

        acl = AlgorithmQueryAclRepositoryImpl()
        fields = {'answer': '{"a": 1}', 'audio_out': 'abc', 'plain': 'p'}
        result = EvalOutputTransformService.apply(
            fields,
            {'answer': 'json_parse', 'audio_out': 'base64', 'plain': 'none'},
            acl)

        print('RESULT', result)
        print('SERVER_RPC_COUNT', len(server_received))
        assert result == {'answer': {'a': 1}, 'audio_out': 'YWJj', 'plain': 'p'}, result
        assert len(server_received) == 1, len(server_received)

        # none 回归：没有待变换字段时一次 RPC 都不发
        server_received.clear()
        same = EvalOutputTransformService.apply(
            {'plain': 'p'}, {'plain': 'none'}, acl)
        assert same == {'plain': 'p'} and not server_received

        # 非法输入：保留原值，不抛异常
        server_received.clear()
        bad = EvalOutputTransformService.apply(
            {'answer': '{bad'}, {'answer': 'json_parse'}, acl)
        print('BAD_RESULT', bad, 'RPC', len(server_received))
        assert bad == {'answer': '{bad'}, len(server_received) == 1
        print('CONTAINER_CHECK_OK')
    finally:
        server.stop(0)


if __name__ == '__main__':
    sys.exit(main())
