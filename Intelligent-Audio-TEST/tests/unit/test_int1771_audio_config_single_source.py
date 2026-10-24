# -*- coding: utf-8 -*-
"""INT-1771 audio_config 双源收敛单测

单一事实源为顶层列 `apis.audio_config`；`meta.audio_config` 仅作存量兼容
（列空时读一次）。HTTP / Realtime / 轮次渲染三条路径共用
`api_test_service.domain.entities.api` 的取值函数。

覆盖验收标准：
1. 列 16000（meta 无键）→ Realtime 与轮次渲染均 16000（改前均 24000）
2. 仅 meta 48000、列空 → 两处 48000（不抛错）
3. 两者都有 → 以列为准（列 16000 / meta 48000 → 16000）
4. 两者都没有 → 默认 24000/s16/mono，与改前一致
5. HTTP 路径（api_session_executor）行为不变
6. api_executor 配置转换保留 audio_config 顶层列（否则执行器拿不到列）
"""
import os
from types import SimpleNamespace

os.environ.setdefault('OSS_ACCESS_KEY', 'test-access')
os.environ.setdefault('OSS_SECRET_KEY', 'test-secret')

from api_test_service.application.round_render_service import RoundRenderService
from api_test_service.core.api_session_executor import APISessionExecutor
from api_test_service.core.realtime_session_executor import RealtimeSessionExecutor
from api_test_service.domain.entities.api import (
    DEFAULT_AUDIO_CONFIG,
    resolve_audio_config,
    resolve_audio_sample_rate,
    resolve_target_audio_format,
)


def _api(audio_config=None, meta=None, **extra):
    """API 配置替身：audio_config 缺省按「列不存在」处理（None）"""
    return SimpleNamespace(id=7, audio_config=audio_config, meta=meta or {}, **extra)


class TestResolveAudioConfig:
    def test_defaults_when_neither_source(self):
        assert resolve_audio_config(_api()) == {}
        assert resolve_target_audio_format(_api()) == {
            'sample_rate': 24000, 'bit_depth': 's16', 'channels': 1}
        assert resolve_audio_sample_rate(_api()) == 24000

    def test_column_source(self):
        api = _api(audio_config={'sample_rate': 16000})
        assert resolve_audio_config(api) == {'sample_rate': 16000}
        assert resolve_audio_sample_rate(api) == 16000

    def test_meta_legacy_source_when_column_empty(self):
        api = _api(audio_config=None, meta={'audio_config': {'sample_rate': 48000}})
        assert resolve_audio_config(api) == {'sample_rate': 48000}
        assert resolve_audio_sample_rate(api) == 48000

    def test_empty_column_falls_back_to_meta(self):
        api = _api(audio_config={}, meta={'audio_config': {'sample_rate': 48000}})
        assert resolve_audio_sample_rate(api) == 48000

    def test_column_wins_over_meta(self):
        api = _api(audio_config={'sample_rate': 16000},
                   meta={'audio_config': {'sample_rate': 48000}})
        assert resolve_audio_sample_rate(api) == 16000

    def test_unknown_keys_dropped_and_bad_meta_tolerated(self):
        api = _api(audio_config={'sample_rate': 16000, 'bogus': 1})
        assert resolve_audio_config(api) == {'sample_rate': 16000}
        # meta 非法形态不抛错，回退默认
        assert resolve_audio_sample_rate(_api(meta={'audio_config': 'x'})) == 24000
        assert resolve_audio_sample_rate(_api(meta='not-a-dict')) == 24000

    def test_dict_style_config_supported(self):
        assert resolve_audio_sample_rate({'audio_config': {'sample_rate': 16000}}) \
            == 16000


class TestRoundRenderTargetFormat:
    def test_column_only_16000(self):
        """验收 1：改前只有 meta 口径，轮次渲染恒 24000"""
        api = _api(audio_config={'sample_rate': 16000})
        assert RoundRenderService._resolve_target_format(api) == {
            'sample_rate': 16000, 'bit_depth': 's16', 'channels': 1}

    def test_meta_only_48000(self):
        """验收 2：存量 meta-only 行按兼容口径生效"""
        api = _api(meta={'audio_config': {'sample_rate': 48000}})
        assert RoundRenderService._resolve_target_format(api)['sample_rate'] == 48000

    def test_column_wins_over_meta(self):
        """验收 3：两者都有以列为准"""
        api = _api(audio_config={'sample_rate': 16000},
                   meta={'audio_config': {'sample_rate': 48000}})
        assert RoundRenderService._resolve_target_format(api)['sample_rate'] == 16000

    def test_defaults_unchanged(self):
        """验收 4：未配置时默认 24000/s16/mono（container 不出现）"""
        fmt = RoundRenderService._resolve_target_format(_api())
        assert fmt == {'sample_rate': 24000, 'bit_depth': 's16', 'channels': 1}

    def test_container_and_stream_override(self):
        api = _api(audio_config={'sample_rate': 16000, 'bit_depth': 's24',
                                 'channels': 2, 'container': 'wav'})
        assert RoundRenderService._resolve_target_format(api) == {
            'sample_rate': 16000, 'bit_depth': 's24', 'channels': 2,
            'container': 'wav'}
        assert RoundRenderService._resolve_target_format(api, stream=True) == {
            'sample_rate': 16000, 'bit_depth': 's16', 'channels': 1,
            'container': 'wav'}


class TestRealtimeSessionConfig:
    def test_input_sample_rate_from_column(self):
        """验收 1：Realtime 会话配置目标采样率取列（改前 24000）"""
        api = _api(audio_config={'sample_rate': 16000})
        cfg = RealtimeSessionExecutor._build_session_config(api, {})
        assert cfg['input_audio_sample_rate'] == 16000
        assert cfg['input_audio_format'] == 'pcm16'

    def test_input_sample_rate_from_meta_legacy(self):
        """验收 2：列空时 meta 存量兼容"""
        api = _api(meta={'audio_config': {'sample_rate': 48000}})
        assert RealtimeSessionExecutor._build_session_config(
            api, {})['input_audio_sample_rate'] == 48000

    def test_session_config_override_still_wins(self):
        api = _api(audio_config={'sample_rate': 16000})
        cfg = RealtimeSessionExecutor._build_session_config(
            api, {'input_audio_sample_rate': 8000})
        assert cfg['input_audio_sample_rate'] == 8000

    def test_default_when_unconfigured(self):
        assert RealtimeSessionExecutor._build_session_config(
            _api(), {})['input_audio_sample_rate'] == 24000


class TestHttpPathUnchanged:
    def test_output_sample_rate_from_column(self):
        """验收 5：HTTP 路径列配置行为不变"""
        api = SimpleNamespace(audio_config={'sample_rate': 16000})
        assert APISessionExecutor._resolve_output_sample_rate(api) == 16000
        assert APISessionExecutor._resolve_output_sample_rate(None) == 24000
        assert APISessionExecutor._resolve_output_sample_rate(
            SimpleNamespace(audio_config={'sample_rate': 'bad'})) == 24000

    def test_meta_legacy_effective_on_http_too(self):
        api = _api(meta={'audio_config': {'sample_rate': 48000}})
        assert APISessionExecutor._resolve_output_sample_rate(api) == 48000


class TestApiConfigPlumbing:
    def test_process_api_configs_keeps_column(self):
        """执行器配置转换必须保留顶层列，否则三条路径都读不到"""
        from api_test_service.core.api_executor import APIExecutor

        executor = APIExecutor.__new__(APIExecutor)
        po = SimpleNamespace(id=7, api_endpoints=[], default_max_process=5,
                             meta={}, max_timeout=30, vendor='openai',
                             audio_config={'sample_rate': 16000})
        processed = executor._process_api_configs([po])
        assert processed[0].audio_config == {'sample_rate': 16000}
        assert resolve_audio_sample_rate(processed[0]) == 16000
        assert RoundRenderService._resolve_target_format(
            processed[0])['sample_rate'] == 16000

    def test_default_audio_config_constant(self):
        assert DEFAULT_AUDIO_CONFIG == {'sample_rate': 24000, 'bit_depth': 's16',
                                        'channels': 1}
