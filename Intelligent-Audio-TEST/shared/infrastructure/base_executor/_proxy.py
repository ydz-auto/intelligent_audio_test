# -*- coding: utf-8 -*-
"""设备结果采集器代理：将本地对象方法调用封装为 gRPC DeviceResultService 调用"""


class _DeviceResultCollectorProxy:
    """设备结果采集器代理：将本地对象方法调用封装为 gRPC DeviceResultService 调用"""

    def __init__(self, stub):
        self._stub = stub

    def convert_results(self, all_results, algorithm_type):
        import json as _json
        from shared.proto import device_service_pb2
        req = device_service_pb2.CollectResultRequest(
            task_id='',
            collect_config=_json.dumps({
                'action': 'convert_results',
                'all_results': all_results,
                'algorithm_type': algorithm_type,
            })
        )
        resp = self._stub.CollectResult(req)
        if not resp.success or not resp.data:
            return all_results
        return _json.loads(resp.data)

    def build_case_result_log(self, algorithm_type, res, ref_fields=None, **kwargs):
        import json as _json
        from shared.proto import device_service_pb2
        req = device_service_pb2.CollectResultRequest(
            task_id='',
            collect_config=_json.dumps({
                'action': 'build_case_result_log',
                'algorithm_type': algorithm_type,
                'res': res,
                'ref_fields': ref_fields,
                'kwargs': kwargs,
            })
        )
        resp = self._stub.CollectResult(req)
        if not resp.success or not resp.data:
            return ''
        return resp.data

    def collect_raw_results(self, task_id, test_case_id, device_info_list, extra_params, log_callback=None, **kwargs):
        import json as _json
        from shared.proto import device_service_pb2
        # device_info_list 中的 driver 对象不可序列化，序列化前剥离 driver 对象
        serializable_device_info = [
            {k: v for k, v in info.items() if k != 'driver'}
            for info in device_info_list
        ]
        req = device_service_pb2.CollectResultRequest(
            task_id=str(task_id),
            collect_config=_json.dumps({
                'action': 'collect_raw_results',
                'test_case_id': test_case_id,
                'device_info_list': serializable_device_info,
                'extra_params': extra_params,
                'kwargs': kwargs,
            })
        )
        resp = self._stub.CollectResult(req)
        if not resp.success or not resp.data:
            return []
        return _json.loads(resp.data)
