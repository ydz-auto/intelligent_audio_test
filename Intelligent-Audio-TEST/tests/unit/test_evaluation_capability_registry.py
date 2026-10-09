# -*- coding: utf-8 -*-
"""评估能力注册表单元测试（INT-29）。

验收标准 1：能力注册表可注册/发现/禁用 THIRD_PARTY_C 能力。
- 注册（含非法枚举 fail-closed 拒绝）
- 发现（list / resolve 按 task_type_code → name → id 匹配）
- 禁用/启用（禁用后 resolve 未命中 → LOCAL）
- 配置持久化与 mtime 热加载（运行时配置切换）
"""
import json
import os
import sys

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest

from evaluation_service.domain.services.evaluation_capability_registry import (
    EvaluationCapabilityRegistry,
)
from shared.models.common_enums import EvalCapabilityTarget, ThirdPartyAdapterKind


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / 'evaluation_capability_config.json'
    path.write_text(json.dumps({'dimension_capabilities': []}, ensure_ascii=False), encoding='utf-8')
    return str(path)


@pytest.fixture
def registry(config_path):
    return EvaluationCapabilityRegistry(config_path=config_path)


class TestRegisterAndDiscover:
    def test_register_third_party_capability(self, registry):
        entry = registry.register('llm_judge', 'THIRD_PARTY_C', adapter='multipart')
        assert entry['target'] == 'THIRD_PARTY_C'
        assert entry['adapter'] == 'multipart'
        assert entry['enabled'] is True

    def test_register_defaults_adapter_for_third_party(self, registry):
        entry = registry.register('mos', 'THIRD_PARTY_C')
        assert entry['adapter'] == ThirdPartyAdapterKind.MULTIPART.value

    def test_register_local_clears_adapter(self, registry):
        entry = registry.register('wer', 'LOCAL', adapter='multipart')
        assert entry['target'] == 'LOCAL'
        assert entry['adapter'] is None

    def test_register_rejects_invalid_target(self, registry):
        with pytest.raises(ValueError, match='非法评估归属'):
            registry.register('x', 'THIRD_PARTY_Z')

    def test_register_rejects_invalid_adapter(self, registry):
        with pytest.raises(ValueError, match='非法第三方评估适配形态|非法'):
            registry.register('x', 'THIRD_PARTY_C', adapter='carrier_pigeon')

    def test_register_rejects_empty_dimension(self, registry):
        with pytest.raises(ValueError):
            registry.register('', 'LOCAL')

    def test_list_capabilities(self, registry):
        registry.register('llm_judge', 'THIRD_PARTY_C')
        registry.register('wer', 'LOCAL')
        listed = registry.list_capabilities()
        assert {item['dimension'] for item in listed} == {'llm_judge', 'wer'}


class TestResolve:
    def test_resolve_by_task_type_code(self, registry):
        registry.register('llm_judge', 'THIRD_PARTY_C', adapter='presigned_url')
        entry = registry.resolve({'id': 7, 'name': '大模型评估', 'task_type_code': 'llm_judge'})
        assert entry is not None
        assert entry.target == EvalCapabilityTarget.THIRD_PARTY_C
        assert entry.adapter == ThirdPartyAdapterKind.PRESIGNED_URL

    def test_resolve_by_name_then_id(self, registry):
        registry.register('大模型评估', 'THIRD_PARTY_C')
        entry = registry.resolve({'id': 7, 'name': '大模型评估'})
        assert entry is not None
        assert entry.dimension == '大模型评估'

    def test_resolve_miss_returns_none(self, registry):
        assert registry.resolve({'id': 1, 'name': 'wer', 'task_type_code': 'wer'}) is None

    def test_resolve_disabled_returns_none(self, registry):
        registry.register('llm_judge', 'THIRD_PARTY_C')
        registry.disable('llm_judge')
        assert registry.resolve({'task_type_code': 'llm_judge'}) is None
        registry.enable('llm_judge')
        assert registry.resolve({'task_type_code': 'llm_judge'}) is not None

    def test_disable_unregistered_raises(self, registry):
        with pytest.raises(KeyError):
            registry.disable('no_such_dim')

    def test_remove_persists_and_does_not_revive_after_hot_reload(self, registry, config_path):
        registry.register('llm_judge', 'THIRD_PARTY_C')
        assert registry.remove('llm_judge') is True
        assert registry.remove('llm_judge') is False
        data = json.loads(open(config_path, encoding='utf-8').read())
        assert data['dimension_capabilities'] == []
        # 外部改写配置触发 mtime 热加载后，已移除条目不得从文件复活
        data['dimension_capabilities'] = [{'dimension': 'mos', 'target': 'THIRD_PARTY_C'}]
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        os.utime(config_path, None)
        assert registry.resolve({'task_type_code': 'llm_judge'}) is None
        assert registry.resolve({'task_type_code': 'mos'}) is not None


class TestPersistAndHotReload:
    def test_register_persists_to_config_file(self, registry, config_path):
        registry.register('llm_judge', 'THIRD_PARTY_C', adapter='feature_extract')
        data = json.loads(open(config_path, encoding='utf-8').read())
        assert data['dimension_capabilities'][0]['adapter'] == 'feature_extract'

    def test_hot_reload_on_mtime_change(self, registry, config_path):
        registry.register('llm_judge', 'THIRD_PARTY_C')
        assert registry.resolve({'task_type_code': 'llm_judge'}) is not None
        # 模拟另一实例改写配置文件（运行时配置切换）
        data = json.loads(open(config_path, encoding='utf-8').read())
        data['dimension_capabilities'][0]['enabled'] = False
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        os.utime(config_path, None)  # 确保 mtime 变化
        assert registry.resolve({'task_type_code': 'llm_judge'}) is None

    def test_corrupt_config_fails_closed(self, config_path):
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write('{not json')
        registry = EvaluationCapabilityRegistry(config_path=config_path)
        assert registry.list_capabilities() == []


class TestDefaultConfigGuard:
    def test_default_config_file_loads_all_disabled(self):
        """仓库默认配置必须存在且全部禁用（fail-safe：默认不改变现有评估链路）。"""
        from evaluation_service.domain.services.evaluation_capability_registry import (
            DEFAULT_CONFIG_PATH,
        )
        assert os.path.isfile(DEFAULT_CONFIG_PATH), f'默认配置缺失: {DEFAULT_CONFIG_PATH}'
        registry = EvaluationCapabilityRegistry(config_path=DEFAULT_CONFIG_PATH, persist=False)
        entries = registry.list_capabilities()
        assert entries, '默认配置应含预置能力注册项'
        assert all(e['enabled'] is False for e in entries)
