# -*- coding: utf-8 -*-
"""task_service.TestCaseConfigService / AlgorithmDefinitionService 防腐层仓储

封装 device_service 对 task_service / algorithm_service 的跨域 gRPC 调用，
替代 device_service/infrastructure/persistence/device_repository.py 中
直接 import shared.clients.grpc_clients。

- 读操作通过 gRPC 完成，返回 bool / dict / list，不返回 ORM 对象。
- 与 device_service/infrastructure/acl/task_acl_repository.py 风格一致，
  采用具体类 + 模块级单例（device_service ACL 层无统一 ABC）。
"""
import json
import logging

logger = logging.getLogger(__name__)


class TestcaseAclRepository:
    """task_service.TestCaseConfigService 防腐层仓储

    封装 gRPC 调用，提供 device_service persistence 层可用的返回值。
    所有方法返回纯 dict / list / bool，不返回 ORM 对象。
    """

    def list_testcases(self, page: int = 1, per_page: int = 100) -> dict:
        """查询测试用例列表（分页）。

        封装 task_service.TestCaseConfigService.ListTestCases RPC。
        返回 {'items': [...], 'total': N, 'pages': N}；失败返回空 dict。
        """
        from shared.clients.grpc_clients import get_testcase_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_testcase_config_service_stub()
            resp = stub.ListTestCases(task_pb.ListTestCasesRequest(
                page=page, per_page=per_page,
            ))
            if not resp.success:
                return {}
            return _loads(resp.data, {}) or {}
        except Exception:
            return {}

    def check_playback_in_testcases(self, device_id) -> int:
        """检查播放设备是否被测试用例引用。

        通过 ListTestCases 全量分页扫描测试用例 config 字符串，
        统计引用了指定 playback_device_id 的用例数。
        """
        count = 0
        page = 1
        per_page = 100
        while True:
            data = self.list_testcases(page=page, per_page=per_page)
            if not isinstance(data, dict):
                return 0
            items = data.get('items', []) or []
            for tc in items:
                config = tc.get('config')
                if not config:
                    continue
                config_str = json.dumps(config, ensure_ascii=False) if not isinstance(config, str) else config
                if f'"playback_device_id": "{device_id}"' in config_str or \
                   f'"playback_device_id":{device_id}' in config_str:
                    count += 1
            total_pages = data.get('pages', 1)
            if page >= total_pages or not items:
                return count
            page += 1

    def get_testcase_detail(self, test_case_id):
        """查询测试用例详情（含 config / algorithm_params / reference_params）

        通过 gRPC 调用 task_service.TestCaseConfigService.GetTestCaseDetail。
        返回用例详情 dict；gRPC 不可用时返回 None。
        """
        from shared.clients.grpc_clients import get_testcase_config_service_stub
        from shared.proto import task_service_pb2 as task_pb
        from shared.utils.grpc_json import loads as _loads
        try:
            stub = get_testcase_config_service_stub()
            resp = stub.GetTestCaseDetail(task_pb.GetTestCaseDetailRequest(tc_id=str(test_case_id)))
            if resp.success:
                return _loads(resp.data, {}) or {}
        except Exception as e:
            logger.warning(f"get_testcase_detail gRPC 调用失败: {e}")
        return None

    def get_testcase_config_stub(self):
        """获取 TestCaseConfigService gRPC stub。

        封装 shared.clients.grpc_clients.get_testcase_config_service_stub，
        供需要直接调用 stub 的场景使用。
        """
        from shared.clients.grpc_clients import get_testcase_config_service_stub
        return get_testcase_config_service_stub()


# 模块级单例
testcase_acl_repository = TestcaseAclRepository()
