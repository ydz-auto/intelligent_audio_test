"""API 测试配置代理：_ApiConfigProxy 及单例 api_config_service。"""
import json

from shared.clients.grpc_clients import get_api_test_service_stub

from ._common import _grpc_call


class _ApiConfigProxy:
    """API 配置 CRUD 代理：把方法调用转发到 gRPC APITestService 的 CRUD RPC

    替代原 ApiCommandService/ApiQueryService 直接操作 DB 的方式，
    网关侧不再 import API 模型和 get_db_session()，统一走 gRPC。
    """

    def create(self, data):
        """创建 API 配置

        Args:
            data: API 配置参数字典

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import api_test_service_pb2 as api_pb

        def _call():
            stub = get_api_test_service_stub()
            resp = stub.CreateAPIConfig(api_pb.CreateAPIConfigRequest(
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            result = {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }
            return result

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'创建API配置失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='创建API配置失败',
        )

    def update(self, api_id, data):
        """更新 API 配置

        Args:
            api_id: API ID
            data: 更新字段字典

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import api_test_service_pb2 as api_pb

        def _call():
            stub = get_api_test_service_stub()
            resp = stub.UpdateAPIConfig(api_pb.UpdateAPIConfigRequest(
                api_id=int(api_id),
                data=json.dumps(data or {}, ensure_ascii=False, default=str),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'更新API配置失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='更新API配置失败',
        )

    def delete(self, api_id):
        """删除 API 配置（软删除）

        Args:
            api_id: API ID

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import api_test_service_pb2 as api_pb

        def _call():
            stub = get_api_test_service_stub()
            resp = stub.DeleteAPIConfig(api_pb.DeleteAPIConfigRequest(
                api_id=int(api_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'删除API配置失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='删除API配置失败',
        )

    def get_all(self, page=1, per_page=10, keyword=None, status=None, algorithm_type=None):
        """分页查询 API 列表

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import api_test_service_pb2 as api_pb

        def _call():
            stub = get_api_test_service_stub()
            resp = stub.ListAPIConfigs(api_pb.ListAPIConfigsRequest(
                page=int(page or 1),
                per_page=int(per_page or 10),
                keyword=keyword or '',
                status=status or '',
                algorithm_type=algorithm_type or '',
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询API列表失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='查询API列表失败',
        )

    def get_one(self, api_id):
        """查询单个 API 详情

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import api_test_service_pb2 as api_pb

        def _call():
            stub = get_api_test_service_stub()
            resp = stub.GetAPIConfig(api_pb.GetAPIConfigRequest(
                api_id=int(api_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'查询API详情失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='查询API详情失败',
        )

    def test_connection(self, api_id):
        """测试 API 连接

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import api_test_service_pb2 as api_pb

        def _call():
            stub = get_api_test_service_stub()
            resp = stub.TestAPIConnection(api_pb.TestAPIConnectionRequest(
                api_id=int(api_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'测试API连接失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='测试API连接失败',
        )

    def health_check(self, api_id):
        """兼容别名，等同 test_connection"""
        return self.test_connection(api_id)

    def stop_test(self, api_id):
        """停止测试 API

        Returns:
            dict: {success, message, data, code}
        """
        from shared.proto import api_test_service_pb2 as api_pb

        def _call():
            stub = get_api_test_service_stub()
            resp = stub.StopAPITestConfig(api_pb.StopAPITestConfigRequest(
                api_id=int(api_id),
            ))
            return {
                'success': resp.success,
                'message': resp.message,
                'data': json.loads(resp.data) if resp.data else None,
            }

        return _grpc_call(
            _call,
            default_return=lambda e: {'success': False, 'message': f'停止测试失败: {e}', 'data': None, 'code': 400},
            error_msg_prefix='停止测试失败',
        )


# API 配置 CRUD 模块级单例
api_config_service = _ApiConfigProxy()
