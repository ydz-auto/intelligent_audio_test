# -*- coding: utf-8 -*-
"""INT-46 验收：e2e / device 重提取链路 algorithm_result 双重编码残留修复守卫。

原缺陷（INT-44 同类残留，两处）：
- shared/infrastructure/base_executor/_db_mixin.py `_save_result`（e2e 链路）
- device_service/application/device_result_reextractor_service.py `_create_test_result`
  （device 重提取链路）
写侧对 algorithm_result 做 json.dumps 后写入 JSON 列（task_service
TestResult.algorithm_result = Column(JSON)），整个 dict 被双重编码成 JSON
字符串标量；读侧各处都要靠 builder 入口 str→dict 幂等规范化兜底。

修复（与 INT-44 写侧对齐）：写侧直接传 dict，JSON 列由 SQLAlchemy 序列化；
读侧兜底规范化保留不动（兼容历史字符串标量数据）。

本文件锁「写侧落库必须 dict」：payload 经 ACL → gRPC（整体 json.dumps
传输）→ 服务端 json.loads → ORM JSON 列的全链路序列化语义，用
json.dumps/loads 往返模拟传输层，断言 algorithm_result 全程保持 dict 形态。
落库为 dict 的端到端验证由真实链路回归（tests/integration/）覆盖。
"""
import json
import os

# BaseConfig 在 import 时校验环境变量（本用例纯单测不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from shared.infrastructure.base_executor._db_mixin import DbMixin

_ALGO_RESULT = {
    'answer': '今天天气怎么样',
    'detail': {'score': 0.98, 'rounds': [1, 2, 3]},
}


class _FakeTaskDataAcl:
    """捕获 submit_result payload 的 ACL 替身（返回 result_id 模拟成功写库）。"""

    def __init__(self):
        self.captured = None

    def submit_result(self, task_id, result_payload):
        self.captured = (task_id, result_payload)
        return 101


class _E2EExecutorStub(DbMixin):
    """e2e 执行器最小替身：仅注入 ACL（与 preparation_mixin 调用面一致）。"""

    def __init__(self, acl):
        self._acl = acl

    def _get_task_data_acl(self):
        return self._acl


def _grpc_roundtrip(payload):
    """模拟跨服务传输语义：shared.clients._grpc_task_data.submit_result 把
    整个 payload json.dumps 后经 gRPC 传输，task_service 服务端 json.loads
    还原后再交 ORM 写 JSON 列。dict 必须全程不被字符串标量化。"""
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))


class TestInt46E2eChainSaveResult:

    def test_algorithm_result_stored_as_dict_not_json_string(self):
        """e2e 链路：_save_result 交给 ACL 的 algorithm_result 必须是 dict 原样，
        经 gRPC 传输语义往返后仍为 dict（修复前 json.dumps 会双重编码成 str）。"""
        acl = _FakeTaskDataAcl()
        executor = _E2EExecutorStub(acl)

        executor._save_result(
            task_id=7, test_case_id='c1',
            result_data={'multi_round': True, 'total_rounds': 2},
            algo_result=dict(_ALGO_RESULT),
            algorithm_type='translation',
            device_id=3, api_id=None,
            execution_status='running',
        )

        assert acl.captured is not None, 'submit_result 应被调用'
        task_id, payload = acl.captured
        assert task_id == 7
        assert isinstance(payload['algorithm_result'], dict), \
            f'e2e 链路落库 payload 的 algorithm_result 应为 dict: {payload["algorithm_result"]!r}'
        assert payload['algorithm_result'] == _ALGO_RESULT

        transported = _grpc_roundtrip(payload)
        assert isinstance(transported['algorithm_result'], dict), \
            '经 gRPC 传输语义往返后 algorithm_result 仍应为 dict（双重编码即变字符串标量）'

    def test_falsy_algo_result_still_stored_as_none(self):
        """空结果（None / {}）保持 None 语义，不受本次修复影响。"""
        for falsy in (None, {}):
            acl = _FakeTaskDataAcl()
            _E2EExecutorStub(acl)._save_result(
                task_id=7, test_case_id='c1', result_data=None,
                algo_result=falsy, algorithm_type='translation',
            )
            _, payload = acl.captured
            assert payload['algorithm_result'] is None


class TestInt46DeviceReextractChainCreateResult:

    def test_algorithm_result_stored_as_dict_not_json_string(self, monkeypatch):
        """device 重提取链路：_create_test_result 交给 ACL 的 algorithm_result
        必须是 dict 原样，经 gRPC 传输语义往返后仍为 dict。"""
        import device_service.infrastructure.acl.task_data_acl_repository as acl_mod
        import shared.utils.result_data_store as store_mod
        from device_service.application.device_result_reextractor_service import (
            DeviceResultReextractor,
        )

        captured = {}

        def _fake_submit(task_id, result_payload):
            captured['task_id'] = task_id
            captured['payload'] = result_payload
            return 202

        monkeypatch.setattr(acl_mod.task_data_acl_repository, 'submit_result', _fake_submit)
        monkeypatch.setattr(store_mod, 'write_result_data_file',
                            lambda task_id, test_case_id, device_id, result_data: 'oss://case_result/fake-key')
        monkeypatch.setattr(store_mod, 'split_result_data',
                            lambda result_data: ({'result_type': 'wer'}, False))

        DeviceResultReextractor()._create_test_result(
            task_id=9, test_case_id='c2', device_id=5,
            algorithm_type='asr', algo_result=dict(_ALGO_RESULT),
            result_data={'wer': 0.07, 'recording': 'heavy-blob'},
        )

        assert captured['task_id'] == 9
        payload = captured['payload']
        assert isinstance(payload['algorithm_result'], dict), \
            f'device 重提取链路落库 payload 的 algorithm_result 应为 dict: {payload["algorithm_result"]!r}'
        assert payload['algorithm_result'] == _ALGO_RESULT

        transported = _grpc_roundtrip(payload)
        assert isinstance(transported['algorithm_result'], dict), \
            '经 gRPC 传输语义往返后 algorithm_result 仍应为 dict（双重编码即变字符串标量）'

    def test_falsy_algo_result_still_stored_as_none(self, monkeypatch):
        """空结果（None / {}）保持 None 语义，不受本次修复影响。"""
        import device_service.infrastructure.acl.task_data_acl_repository as acl_mod
        import shared.utils.result_data_store as store_mod
        from device_service.application.device_result_reextractor_service import (
            DeviceResultReextractor,
        )

        monkeypatch.setattr(acl_mod.task_data_acl_repository, 'submit_result',
                            lambda task_id, result_payload: 203)
        monkeypatch.setattr(store_mod, 'write_result_data_file',
                            lambda task_id, test_case_id, device_id, result_data: '')
        monkeypatch.setattr(store_mod, 'split_result_data',
                            lambda result_data: ({}, False))

        for falsy in (None, {}):
            result_id = DeviceResultReextractor()._create_test_result(
                task_id=9, test_case_id='c2', device_id=5,
                algorithm_type='asr', algo_result=falsy,
                result_data={},
            )
            assert result_id == 203
