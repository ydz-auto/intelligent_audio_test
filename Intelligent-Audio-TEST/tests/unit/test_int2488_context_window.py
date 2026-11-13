# -*- coding: utf-8 -*-
"""INT-2488 上下文窗口解析与预算派生（§6.4-9 / §8.3）。"""
import os

os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest

from agent_service.domain.enums import ContextWindowSource, LlmProtocol
from agent_service.domain.exceptions import InvalidContextWindow
from agent_service.domain.services.context_window_resolver import (
    ContextWindowResolver, WARNING_ABOVE_CATALOG,
)


@pytest.fixture(scope='module')
def resolver():
    return ContextWindowResolver.from_file()


def test_catalog_file_is_the_default_source(resolver):
    assert resolver.fallback_context_window == 131072
    assert resolver.bounds.min == 8192
    assert resolver.bounds.max == 2097152
    assert resolver.bounds.alignment == 1024
    assert resolver.match(LlmProtocol.OPENAI_COMPATIBLE, 'deepseek-chat')
    assert resolver.match(LlmProtocol.ANTHROPIC, 'claude-sonnet-4-5')
    # 协议必须匹配：Anthropic 协议不认 OpenAI 目录项
    assert resolver.match(LlmProtocol.ANTHROPIC, 'deepseek-chat') is None


def test_no_override_uses_catalog_default(resolver):
    resolution = resolver.resolve(LlmProtocol.OPENAI_COMPATIBLE,
                                  'deepseek-chat')
    assert resolution.effective_context_window == 65536
    assert resolution.source is ContextWindowSource.MODEL_DEFAULT
    assert resolution.catalog_context_window == 65536
    assert resolution.warning is None


def test_catalog_miss_falls_back_to_128k(resolver):
    resolution = resolver.resolve(LlmProtocol.OPENAI_COMPATIBLE,
                                  'self-hosted-unknown-model')
    assert resolution.effective_context_window == 131072
    assert resolution.source is ContextWindowSource.FALLBACK
    assert resolution.catalog_context_window is None


def test_user_override_32k(resolver):
    resolution = resolver.resolve(LlmProtocol.OPENAI_COMPATIBLE,
                                  'deepseek-chat', 32768)
    assert resolution.effective_context_window == 32768
    assert resolution.source is ContextWindowSource.USER_OVERRIDE
    assert resolution.warning is None


@pytest.mark.parametrize('value', [0, 4096, 8192 - 1024, 2097152 + 1024,
                                   33000, 40000])
def test_invalid_overrides_rejected(resolver, value):
    with pytest.raises(InvalidContextWindow):
        resolver.resolve(LlmProtocol.OPENAI_COMPATIBLE, 'deepseek-chat', value)


def test_override_above_catalog_max_is_allowed_with_warning(resolver):
    resolution = resolver.resolve(LlmProtocol.OPENAI_COMPATIBLE,
                                  'deepseek-chat', 131072)
    assert resolution.effective_context_window == 131072
    assert resolution.source is ContextWindowSource.USER_OVERRIDE
    assert resolution.warning == WARNING_ABOVE_CATALOG
    assert resolution.warning_message


def test_token_budget_is_2x_window(resolver):
    # W=32k → 总上限 64k
    assert resolver.token_budget(32768, 2) == 65536
    assert resolver.token_budget(131072, 2) == 262144
    assert resolver.token_budget(131072, 4) == 524288  # Auto


def test_output_limit_is_min_cap_and_10_percent_aligned(resolver):
    # 32k → 10% = 3276.8 → 1024 对齐下取整 = 3072（卡面要求 ≤ 3200）
    assert resolver.output_token_limit(
        32768, cap=8192, ratio=0.10,
        protocol=LlmProtocol.OPENAI_COMPATIBLE,
        model='deepseek-chat') == 3072
    # 128k → 10% = 13107 → 12288，再被 cap 8192 收紧
    assert resolver.output_token_limit(
        131072, cap=8192, ratio=0.10,
        protocol=LlmProtocol.OPENAI_COMPATIBLE,
        model='deepseek-chat') == 8192
    # 目录 max_output 更小时再收紧（claude-3-opus 目录上限 4096）
    assert resolver.output_token_limit(
        200704, cap=8192, ratio=0.10,
        protocol=LlmProtocol.ANTHROPIC,
        model='claude-3-opus-20240229') == 4096


def test_compaction_thresholds_based_on_available_window(resolver):
    soft, hard = resolver.compaction_thresholds(
        32768, 3072, soft_ratio=0.60, hard_ratio=0.80)
    available = 32768 - 3072
    assert soft == int(available * 0.60)
    assert hard == int(available * 0.80)
    assert soft < hard
