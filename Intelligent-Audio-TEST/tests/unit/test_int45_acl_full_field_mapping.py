# -*- coding: utf-8 -*-
"""INT-45 验收补充：report_service ACL get_full_field_mapping 单测。

原缺陷：AlgorithmConfigAclRepositoryImpl 缺少 get_full_field_mapping 方法，
report_task_generator._collect_field_mappings_snapshot 经
_grpc_algo_get_field_mapping → ACL 仓储调用时抛 AttributeError，被快照收集的
try/except 吞成 WARNING → field_mappings 快照恒空，报告算法结果区静默降级
（不阻断生成，缺正常路径的字段映射快照）。

修复（47ccec33）：ACL 仓储补 get_full_field_mapping（调 shared 客户端
algo_get_full_field_mapping → dict_to_dto 转 AlgoFieldMappingDTO → _attach
附加 result_data），抽象接口补 abstractmethod，DTO 包导出。

本文件覆盖（对应 INT-45 交付评论建议测试点中无需真实服务的部分）：
- 接口契约：抽象接口声明 get_full_field_mapping 且实现类可实例化
  （若实现方法被删，ABC 实例化即 TypeError，守卫住原缺陷模式）。
- 成功路径：payload 经 ACL → DTO → dto_to_dict 无损往返（动态键 dict 完整还原）。
- 降级面：非 dict 返回 → None；gRPC 异常 → None 不抛出；空 dict → {} 被
  调用方 if mapping 跳过。
- 兼容层：_grpc_algo_get_field_mapping 委托 ACL 仓储并透传 algorithm_type。
- 快照收集：多算法类型各自产快照条目，单类型失败不阻断其他类型（降级不扩散）。

algorithm_service 停机/在线的端到端验证由真实链路回归
（tests/integration/test_task_execute_real_chain.py）覆盖，不在本文件范围。
"""
import os

# BaseConfig 在 import 时校验环境变量（本用例纯单测不触库，与仓库既有测试同款兜底）
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from unittest.mock import MagicMock

import shared.clients.grpc_clients as shared_grpc_clients
from report_service.domain.dto import AlgoFieldMappingDTO
from report_service.domain.repositories.acl.algorithm_acl_repository import (
    AlgorithmConfigAclRepository,
)
from report_service.infrastructure.acl.algorithm_acl_repository import (
    AlgorithmConfigAclRepositoryImpl,
)
from report_service.infrastructure.clients import grpc_clients as report_grpc_clients
from shared.utils.dto_utils import dto_to_dict


_PAYLOAD = {
    'result': [
        {'param_code': 'answer', 'source_param': 'answer',
         'param_type': 'text', 'label': '识别结果'},
    ],
    'reference': [
        {'param_code': 'standard_text', 'source_param': 'standard_text',
         'param_type': 'text', 'label': 'standard_text'},
    ],
}


def _patch_shared_client(monkeypatch, fn):
    """替换 ACL 仓储方法内延迟导入的 shared 客户端函数（调用时才取属性，打补丁生效）。"""
    monkeypatch.setattr(shared_grpc_clients, 'algo_get_full_field_mapping', fn)


class TestInt45AclInterfaceContract:

    def test_abstract_interface_declares_get_full_field_mapping(self):
        """接口契约：abstractmethod 已声明（原缺陷即接口与实现双侧同时缺失）。"""
        assert 'get_full_field_mapping' in AlgorithmConfigAclRepository.__abstractmethods__

    def test_impl_instantiable_with_method(self):
        """实现类可实例化（缺实现时 ABC 实例化即 TypeError）且方法可达。"""
        impl = AlgorithmConfigAclRepositoryImpl()
        assert callable(impl.get_full_field_mapping)


class TestInt45AclGetFullFieldMapping:

    def test_success_payload_roundtrip_lossless(self, monkeypatch):
        captured = {}

        def _fake(algorithm_type):
            captured['algorithm_type'] = algorithm_type
            return dict(_PAYLOAD)

        _patch_shared_client(monkeypatch, _fake)
        dto = AlgorithmConfigAclRepositoryImpl().get_full_field_mapping('translation')

        assert isinstance(dto, AlgoFieldMappingDTO)
        assert captured['algorithm_type'] == 'translation'
        assert dto.result_data == _PAYLOAD
        assert dto_to_dict(dto) == _PAYLOAD, '动态键 payload 必须经 dto_to_dict 无损还原'

    def test_non_dict_returns_none(self, monkeypatch):
        _patch_shared_client(monkeypatch, lambda algorithm_type: ['not-a-dict'])
        assert AlgorithmConfigAclRepositoryImpl().get_full_field_mapping('translation') is None

    def test_grpc_exception_returns_none_no_raise(self, monkeypatch):
        def _boom(algorithm_type):
            raise ConnectionError('simulated algorithm_service outage')

        _patch_shared_client(monkeypatch, _boom)
        assert AlgorithmConfigAclRepositoryImpl().get_full_field_mapping('translation') is None

    def test_empty_dict_degrades_to_falsy(self, monkeypatch):
        """空结果经兼容层还原为 {}（falsy），被快照收集的 if mapping 跳过。"""
        _patch_shared_client(monkeypatch, lambda algorithm_type: {})
        dto = AlgorithmConfigAclRepositoryImpl().get_full_field_mapping('translation')
        assert dto_to_dict(dto) == {}


class TestInt45CompatLayer:

    def test_compat_layer_delegates_to_acl_and_passes_algorithm_type(self, monkeypatch):
        """_grpc_algo_get_field_mapping（report_task_generator 的真实入口）委托
        ACL 仓储并透传 algorithm_type，返回还原后的 dict。"""
        _patch_shared_client(monkeypatch, lambda algorithm_type: dict(_PAYLOAD))
        out = report_grpc_clients._grpc_algo_get_field_mapping('translation')
        assert out == _PAYLOAD


class TestInt45CollectSnapshot:

    def test_multi_algorithm_types_each_get_entry_and_failure_isolated(self, monkeypatch):
        """建议测试点 2（单测层）：多算法类型任务每种类型均有快照条目；
        单类型失败仅该类型缺失，不阻断其他类型（降级不扩散）。"""
        import report_service.application.services.report_task_generator as gen_mod

        def _fake(algorithm_type):
            if algorithm_type == 'ocr':
                raise ConnectionError('boom')
            return dict(_PAYLOAD)

        monkeypatch.setattr(gen_mod, '_grpc_algo_get_field_mapping', _fake)
        test_cases = [{'algorithm_type': 'translation'}, {'algorithm_type': 'asr'},
                      {'algorithm_type': 'ocr'}]
        snapshot = gen_mod.ReportTaskGenerator._collect_field_mappings_snapshot(
            test_cases, [])

        assert set(snapshot) == {'translation', 'asr'}, \
            f'成功类型均应有条目且失败类型不阻断其他: {set(snapshot)}'
        assert snapshot['translation'] == _PAYLOAD
        assert snapshot['asr'] == _PAYLOAD
