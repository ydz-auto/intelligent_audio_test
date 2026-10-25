# -*- coding: utf-8 -*-
"""INT-1692 单元测试：关联算法载荷 is_default 双键兼容。

缺陷：extract_associated_relations 同函数的 algorithm_type 已做
algorithmType / algorithm_type 双键兼容，is_default 却只读驼峰 isDefault，
后端内部/脚本用 snake_case 传 is_default 时被静默丢成 False 落库，
读模型回 false 而调用方以为设置成功。

修复：is_default 双键兼容（缺省 False）；get_default_algorithm_type
的默认算法判定同步，避免「碰巧落在第一个」掩盖口径不一致。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

from evaluation_service.application.commands._command_utils import (
    DEFAULT_ALGORITHM_TYPE,
    extract_associated_relations,
    get_default_algorithm_type,
)


# ==================== 1. extract_associated_relations：is_default 双键 ====================

class TestIsDefaultKeyCompat:
    def test_snake_case_is_default_true(self):
        """本卡核心回归：snake_case 的 is_default 不再被丢弃。"""
        rels = extract_associated_relations(
            [{'algorithm_type': 'voice_llm', 'is_default': True}])
        assert rels[0]['is_default'] is True

    def test_camel_case_is_default_true(self):
        """React 侧驼峰口径保持 True（用户路径不回归）。"""
        rels = extract_associated_relations(
            [{'algorithmType': 'voice_llm', 'isDefault': True}])
        assert rels[0]['is_default'] is True

    def test_missing_both_defaults_false(self):
        rels = extract_associated_relations(
            [{'algorithm_type': 'voice_llm', 'weight': 1.0}])
        assert rels[0]['is_default'] is False

    def test_camel_case_is_default_false(self):
        rels = extract_associated_relations(
            [{'algorithmType': 'voice_llm', 'isDefault': False}])
        assert rels[0]['is_default'] is False

    def test_snake_case_is_default_false(self):
        rels = extract_associated_relations(
            [{'algorithm_type': 'voice_llm', 'is_default': False}])
        assert rels[0]['is_default'] is False

    def test_camel_key_wins_when_both_present(self):
        """两键同时存在时以驼峰为准（dict.get 键存在即生效，与 algorithmType 的口径一致）。"""
        rels = extract_associated_relations(
            [{'algorithm_type': 'voice_llm', 'is_default': True, 'isDefault': False}])
        assert rels[0]['is_default'] is False
        rels = extract_associated_relations(
            [{'algorithm_type': 'voice_llm', 'is_default': False, 'isDefault': True}])
        assert rels[0]['is_default'] is True


# ==================== 2. algorithm_type / weight 无同类问题（核对） ====================

class TestOtherKeysUnchanged:
    def test_algorithm_type_snake_case(self):
        rels = extract_associated_relations([{'algorithm_type': 'asr'}])
        assert rels[0]['algorithm_type'] == 'asr'

    def test_algorithm_type_camel_case(self):
        rels = extract_associated_relations([{'algorithmType': 'asr'}])
        assert rels[0]['algorithm_type'] == 'asr'

    def test_weight_passthrough(self):
        """weight 两端键名一致（均为 weight），无需兼容分支。"""
        rels = extract_associated_relations(
            [{'algorithm_type': 'voice_llm', 'is_default': True, 'weight': 0.7}])
        assert rels[0]['weight'] == 0.7

    def test_weight_default_when_absent(self):
        rels = extract_associated_relations([{'algorithm_type': 'voice_llm'}])
        assert rels[0]['weight'] == 1.0

    def test_string_list_fallback(self):
        """纯字符串列表：原样作为 type，is_default 恒 False。"""
        rels = extract_associated_relations(['voice_llm'])
        assert rels == [{'algorithm_type': 'voice_llm', 'is_default': False, 'weight': 1.0}]

    def test_empty_and_none(self):
        assert extract_associated_relations(None) == []
        assert extract_associated_relations([]) == []


# ==================== 3. get_default_algorithm_type 同步 ====================

class TestGetDefaultAlgorithmType:
    def test_snake_case_is_default_selects_second(self):
        """snake_case 标记的非首个算法应被选为默认（不再「碰巧取第一个」）。"""
        got = get_default_algorithm_type([
            {'algorithm_type': 'asr'},
            {'algorithm_type': 'voice_llm', 'is_default': True},
        ])
        assert got == 'voice_llm'

    def test_camel_case_is_default_selects_second(self):
        got = get_default_algorithm_type([
            {'algorithmType': 'asr'},
            {'algorithmType': 'voice_llm', 'isDefault': True},
        ])
        assert got == 'voice_llm'

    def test_no_flag_falls_back_to_first(self):
        got = get_default_algorithm_type([
            {'algorithm_type': 'asr'},
            {'algorithm_type': 'voice_llm'},
        ])
        assert got == 'asr'

    def test_empty_falls_back_to_constant(self):
        assert get_default_algorithm_type(None) == DEFAULT_ALGORITHM_TYPE
        assert get_default_algorithm_type([]) == DEFAULT_ALGORITHM_TYPE

    def test_string_list_keeps_original_semantics(self):
        assert get_default_algorithm_type(['asr']) == 'asr'
