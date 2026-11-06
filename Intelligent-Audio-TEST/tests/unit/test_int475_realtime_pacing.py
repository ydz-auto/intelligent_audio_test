# -*- coding: utf-8 -*-
"""INT-475 RealtimePacingService 节奏解析单测（纯逻辑，无 WS / 无 IO）

覆盖（评审修订后定稿接口）：
- 默认 = FIXED（现状恒定节奏，回归基准）
- 优先级：case_config['pacing'] → api_config.meta['pacing'] → 全局配置 → 默认
- 组合策略解析：列表 / 逗号分隔字符串；FIXED 与动态策略互斥
- 未知策略值告警忽略
- TIMEOUT_FALLBACK 组合时有效等待超时取更紧的兜底值
"""
import pytest

from shared.models.common_enums import RealtimePacingStrategy
from api_test_service.domain.services.realtime_pacing_service import (
    RealtimePacingService,
)
from types import SimpleNamespace

svc = RealtimePacingService()


def _api(meta=None):
    return SimpleNamespace(meta=meta or {})


class TestResolveDefaults:
    def test_default_is_fixed(self):
        ctx = svc.resolve(_api(), {}, lambda k, d=None: None)
        assert ctx.is_fixed() is True
        assert ctx.has(RealtimePacingStrategy.FIXED)

    def test_default_timeouts_from_global(self):
        ctx = svc.resolve(_api(), {},
                          lambda k, d=None: {'turn_end_wait_timeout_s': 5,
                                             'pacing_fallback_timeout_s': 2}.get(k, d))
        assert ctx.turn_end_wait_timeout_s == 5.0
        assert ctx.pacing_fallback_timeout_s == 2.0

    def test_global_strategy_single_string(self):
        ctx = svc.resolve(_api(), {},
                          lambda k, d=None: 'wait_turn_end' if k == 'pacing_strategy' else d)
        assert ctx.has(RealtimePacingStrategy.WAIT_TURN_END)
        assert not ctx.is_fixed()


class TestResolvePriority:
    def test_case_config_overrides_meta_and_global(self):
        api = _api({'pacing': {'pacing_strategy': 'allow_barge_in',
                               'pacing_fallback_timeout_s': 9}})
        case = {'pacing': {'pacing_strategy': 'wait_turn_end',
                           'turn_end_wait_timeout_s': 3,
                           'pacing_fallback_timeout_s': 4}}
        ctx = svc.resolve(api, case,
                          lambda k, d=None: 'timeout_fallback' if k == 'pacing_strategy' else d)
        assert ctx.has(RealtimePacingStrategy.WAIT_TURN_END)
        assert not ctx.has(RealtimePacingStrategy.ALLOW_BARGE_IN)
        assert ctx.turn_end_wait_timeout_s == 3.0
        assert ctx.pacing_fallback_timeout_s == 4.0

    def test_meta_overrides_global(self):
        api = _api({'pacing': {'pacing_strategy': 'allow_barge_in',
                               'turn_end_wait_timeout_s': 8}})
        ctx = svc.resolve(api, {},
                          lambda k, d=None: 'wait_turn_end' if k == 'pacing_strategy' else d)
        assert ctx.has(RealtimePacingStrategy.ALLOW_BARGE_IN)
        assert ctx.turn_end_wait_timeout_s == 8.0

    def test_meta_session_config_not_confused(self):
        """meta.session_config（WS 会话载荷）不是节奏覆盖层，pacing 段才是"""
        api = _api({'session_config': {'pacing_strategy': 'allow_barge_in'}})
        ctx = svc.resolve(api, {}, lambda k, d=None: None)
        assert ctx.is_fixed() is True


class TestNormalizeStrategies:
    def test_list_combination(self):
        ctx = svc.resolve(_api(), {'pacing': {'pacing_strategy': ['wait_turn_end',
                                                                  'timeout_fallback']}},
                          lambda k, d=None: None)
        assert ctx.has(RealtimePacingStrategy.WAIT_TURN_END)
        assert ctx.has(RealtimePacingStrategy.TIMEOUT_FALLBACK)
        assert not ctx.has(RealtimePacingStrategy.ALLOW_BARGE_IN)

    def test_comma_string_combination(self):
        ctx = svc.resolve(_api(), {'pacing': {'pacing_strategy': 'allow_barge_in,timeout_fallback'}},
                          lambda k, d=None: None)
        assert ctx.has(RealtimePacingStrategy.ALLOW_BARGE_IN)
        assert ctx.has(RealtimePacingStrategy.TIMEOUT_FALLBACK)

    def test_fixed_plus_dynamic_discards_fixed(self):
        ctx = svc.resolve(_api(), {'pacing': {'pacing_strategy': ['fixed', 'wait_turn_end']}},
                          lambda k, d=None: None)
        assert ctx.has(RealtimePacingStrategy.WAIT_TURN_END)
        assert not ctx.has(RealtimePacingStrategy.FIXED)

    def test_unknown_values_ignored(self):
        ctx = svc.resolve(_api(), {'pacing': {'pacing_strategy': 'teleport,wait_turn_end'}},
                          lambda k, d=None: None)
        assert ctx.has(RealtimePacingStrategy.WAIT_TURN_END)

    def test_empty_falls_back_to_fixed(self):
        ctx = svc.resolve(_api(), {'pacing': {'pacing_strategy': ''}},
                          lambda k, d=None: None)
        assert ctx.is_fixed() is True


class TestEffectiveTimeouts:
    def test_turn_end_timeout_without_fallback_uses_own(self):
        ctx = svc.resolve(_api(), {'pacing': {'pacing_strategy': 'wait_turn_end',
                                              'turn_end_wait_timeout_s': 10,
                                              'pacing_fallback_timeout_s': 2}},
                          lambda k, d=None: None)
        assert ctx.effective_turn_end_timeout() == 10.0

    def test_turn_end_timeout_with_fallback_takes_min(self):
        ctx = svc.resolve(_api(), {'pacing': {'pacing_strategy': ['wait_turn_end',
                                                                  'timeout_fallback'],
                                              'turn_end_wait_timeout_s': 10,
                                              'pacing_fallback_timeout_s': 2}},
                          lambda k, d=None: None)
        assert ctx.effective_turn_end_timeout() == 2.0

    def test_fallback_end_timeout_bounds_default(self):
        ctx = svc.resolve(_api(), {'pacing': {'pacing_strategy': 'timeout_fallback',
                                              'pacing_fallback_timeout_s': 0.5}},
                          lambda k, d=None: None)
        assert ctx.effective_fallback_end_timeout(60) == 0.5
        assert ctx.effective_fallback_end_timeout(0.2) == 0.2   # 不小于现有更紧超时

    def test_no_fallback_keeps_default(self):
        ctx = svc.resolve(_api(), {'pacing': {'pacing_strategy': 'wait_turn_end'}},
                          lambda k, d=None: None)
        assert ctx.effective_fallback_end_timeout(60) == 60
