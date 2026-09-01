"""spl_service 代理：_SplServiceProxy 及模块级单例 spl_service。"""
import json

from shared.clients.grpc_clients import get_audio_service_stub

from ._common import _grpc_call


class _SplServiceProxy:
    """spl_service 代理：把方法调用转发到 gRPC AudioService 的 SPL 相关 RPC"""

    def measure_spl(self, task_id=None, **kwargs):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_service_stub()
            resp = stub.MeasureSPL(audio_pb.MeasureSPLRequest(
                task_id=str(task_id or ''),
                measure_config=json.dumps(kwargs)
            ))
            if resp.success and resp.data:
                return json.loads(resp.data)
            return None

        return _grpc_call(_call, default_return=None, error_msg_prefix="测量 SPL 失败")

    def start_spl(self, task_id=None, **kwargs):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_service_stub()
            resp = stub.StartSPL(audio_pb.StartSPLRequest(
                task_id=str(task_id or ''),
                spl_config=json.dumps(kwargs)
            ))
            return resp.success

        return _grpc_call(_call, default_return=False, error_msg_prefix="启动 SPL 失败")

    def stop_spl(self, task_id=None, **kwargs):
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_service_stub()
            resp = stub.StopSPL(audio_pb.StopSPLRequest(task_id=str(task_id or '')))
            return resp.success

        return _grpc_call(_call, default_return=False, error_msg_prefix="停止 SPL 失败")

    def spl_to_gain(self, mapping_id, target_spl, app=None):
        """通过 gRPC MeasureSPL 计算 SPL 到增益的映射"""
        from shared.proto import audio_service_pb2 as audio_pb

        def _call():
            stub = get_audio_service_stub()
            measure_config = {'mapping_id': mapping_id, 'target_spl': target_spl}
            resp = stub.MeasureSPL(audio_pb.MeasureSPLRequest(
                task_id='',
                measure_config=json.dumps(measure_config)
            ))
            if resp.success and resp.data:
                result = json.loads(resp.data)
                return result.get('gain', 1.0)
            return 1.0

        return _grpc_call(_call, default_return=1.0, error_msg_prefix="SPL 转增益失败")


spl_service = _SplServiceProxy()
