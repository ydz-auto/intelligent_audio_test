"""API RMS→SPL 映射配置代理：_ApiRmsSplConfigProxy 及单例 api_rms_spl_config_service（UC-0902）"""
import json

from shared.clients.grpc_clients import get_api_rms_spl_config_service_stub

from ._common import _grpc_call


def _envelope(resp):
    """gRPC 信封 → {success, message, data, code}

    code 优先取微服务填的业务码（200/201/400/404/409）；旧版本 servicer
    未填（0）时按 success 回退 200/400，保持向后兼容。
    """
    return {
        'success': resp.success,
        'message': resp.message,
        'data': json.loads(resp.data) if resp.data else None,
        'code': resp.code or (200 if resp.success else 400),
    }


class _ApiRmsSplConfigProxy:
    """被测 API RMS→SPL 映射 CRUD/校准/默认项代理（api_test_service.ApiRmsSplConfigService）"""

    def create(self, data):
        from shared.proto import api_test_service_pb2 as api_pb

        def _call():
            resp = get_api_rms_spl_config_service_stub().CreateRmsSplMapping(
                api_pb.CreateRmsSplMappingRequest(
                    data=json.dumps(data or {}, ensure_ascii=False, default=str),
                )
            )
            return _envelope(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建RMS→SPL映射失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='创建RMS→SPL映射失败',
        )

    def update(self, mapping_id, data):
        from shared.proto import api_test_service_pb2 as api_pb

        def _call():
            resp = get_api_rms_spl_config_service_stub().UpdateRmsSplMapping(
                api_pb.UpdateRmsSplMappingRequest(
                    mapping_id=int(mapping_id),
                    data=json.dumps(data or {}, ensure_ascii=False, default=str),
                )
            )
            return _envelope(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新RMS→SPL映射失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='更新RMS→SPL映射失败',
        )

    def delete(self, mapping_id):
        from shared.proto import api_test_service_pb2 as api_pb

        def _call():
            resp = get_api_rms_spl_config_service_stub().DeleteRmsSplMapping(
                api_pb.DeleteRmsSplMappingRequest(mapping_id=int(mapping_id))
            )
            return _envelope(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除RMS→SPL映射失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='删除RMS→SPL映射失败',
        )

    def get_all(self, **kwargs):
        from shared.proto import api_test_service_pb2 as api_pb

        def _call():
            resp = get_api_rms_spl_config_service_stub().ListRmsSplMappings(
                api_pb.ListRmsSplMappingsRequest(
                    page=kwargs.get('page') or 1,
                    per_page=kwargs.get('per_page') or 10,
                    api_id=kwargs.get('api_id') or 0,
                    calibration_status=kwargs.get('calibration_status') or '',
                )
            )
            return _envelope(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询RMS→SPL映射列表失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='查询RMS→SPL映射列表失败',
        )

    def get_one(self, mapping_id):
        from shared.proto import api_test_service_pb2 as api_pb

        def _call():
            resp = get_api_rms_spl_config_service_stub().GetRmsSplMapping(
                api_pb.GetRmsSplMappingRequest(mapping_id=int(mapping_id))
            )
            return _envelope(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询RMS→SPL映射失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='查询RMS→SPL映射失败',
        )

    def get_by_api(self, api_id):
        from shared.proto import api_test_service_pb2 as api_pb

        def _call():
            resp = get_api_rms_spl_config_service_stub().GetRmsSplMappingsByApi(
                api_pb.GetRmsSplMappingsByApiRequest(api_id=int(api_id))
            )
            return _envelope(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'按API查询RMS→SPL映射失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='按API查询RMS→SPL映射失败',
        )

    def calibrate(self, mapping_id, calibration_data=None):
        from shared.proto import api_test_service_pb2 as api_pb

        def _call():
            resp = get_api_rms_spl_config_service_stub().CalibrateRmsSplMapping(
                api_pb.CalibrateRmsSplMappingRequest(
                    mapping_id=int(mapping_id),
                    calibration_data=json.dumps(calibration_data or {}, ensure_ascii=False, default=str),
                )
            )
            return _envelope(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'执行RMS→SPL校准失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='执行RMS→SPL校准失败',
        )

    def set_default(self, api_id, mapping_id=None):
        from shared.proto import api_test_service_pb2 as api_pb

        def _call():
            resp = get_api_rms_spl_config_service_stub().SetDefaultRmsSplMapping(
                api_pb.SetDefaultRmsSplMappingRequest(
                    api_id=int(api_id),
                    mapping_id=int(mapping_id) if mapping_id else 0,
                )
            )
            return _envelope(resp)

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'设置默认RMS→SPL映射失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='设置默认RMS→SPL映射失败',
        )


api_rms_spl_config_service = _ApiRmsSplConfigProxy()
