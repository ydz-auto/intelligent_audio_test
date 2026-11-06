# -*- coding: utf-8 -*-
"""INT-817 格式转换附加参数（目标采样率/声道数/位深度/比特率）单测。

覆盖：
- ConvertFormatRequest 契约扩展：可选字段 snake/camel 双写、字符串数字宽松转换、
  非法采样率/声道数/位深/比特率 → ValidationError（网关返回 400）。
- AudioConvertService 附加参数透传：ffmpeg export 参数构建与 bitrate 归一化。
"""
import os

# 服务模块 import 即触发 BaseConfig 必填键校验（conftest 只兜 DATABASE_URL）
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

import pytest
from pydantic import ValidationError

from api_gateway.schemas.audio import ConvertFormatRequest
from audio_service.application.services.audio_convert_service import AudioConvertService


class TestConvertFormatRequestSchema:
    def test_valid_snake_case(self):
        m = ConvertFormatRequest.model_validate({
            'format': 'wav',
            'sample_rate': 16000,
            'channels': 1,
            'bit_depth': 16,
        })
        assert m.sample_rate == 16000
        assert m.channels == 1
        assert m.bit_depth == 16
        assert m.bitrate is None

    def test_valid_camel_case_and_string_coercion(self):
        m = ConvertFormatRequest.model_validate({
            'format': 'MP3',
            'sampleRate': '16000',
            'channels': '2',
            'bitrate': '128',
        })
        assert m.sample_rate == 16000
        assert m.channels == 2
        assert m.bitrate == '128'

    def test_bitrate_with_k_suffix(self):
        m = ConvertFormatRequest.model_validate({'format': 'mp3', 'bitrate': '192k'})
        assert m.bitrate == '192k'

    def test_all_optional_absent(self):
        m = ConvertFormatRequest.model_validate({'format': 'wav'})
        assert m.sample_rate is None
        assert m.channels is None
        assert m.bit_depth is None
        assert m.bitrate is None

    @pytest.mark.parametrize('payload,expect_field', [
        ({'format': 'wav', 'sample_rate': 0}, 'sample_rate'),
        ({'format': 'wav', 'sample_rate': 999999}, 'sample_rate'),
        ({'format': 'wav', 'channels': 0}, 'channels'),
        ({'format': 'wav', 'channels': 9}, 'channels'),
        ({'format': 'wav', 'bit_depth': 12}, 'bit_depth'),
        ({'format': 'wav', 'bit_depth': 48}, 'bit_depth'),
        ({'format': 'mp3', 'bitrate': -1}, 'bitrate'),
        ({'format': 'mp3', 'bitrate': True}, 'bitrate'),
        ({'format': 'mp3', 'bitrate': 'abc'}, 'bitrate'),
    ])
    def test_invalid_values_raise_clear_validation_error(self, payload, expect_field):
        with pytest.raises(ValidationError) as exc:
            ConvertFormatRequest.model_validate(payload)
        errors = exc.value.errors()
        assert errors[0]['loc'][0] == expect_field
        assert '目标' in errors[0]['msg'] or '不能' in errors[0]['msg']


class TestAudioConvertServiceBuildParams:
    def _svc(self):
        return AudioConvertService.__new__(AudioConvertService)

    def test_lossless_with_bit_depth(self):
        params = self._svc()._build_export_params(
            {'format': 'wav', 'sample_rate': 16000, 'channels': 1, 'bit_depth': 16}, 'wav')
        assert params == ['-ar', '16000', '-ac', '1', '-acodec', 'pcm_s16le']

    def test_camel_case_keys(self):
        params = self._svc()._build_export_params(
            {'format': 'wav', 'sampleRate': '48000', 'channels': '2', 'bitDepth': '24'}, 'wav')
        assert params == ['-ar', '48000', '-ac', '2', '-acodec', 'pcm_s24le']

    def test_flac_bit_depth_via_sample_fmt(self):
        params = self._svc()._build_export_params(
            {'format': 'flac', 'sample_rate': 48000, 'bit_depth': 24}, 'flac')
        assert params == ['-ar', '48000', '-sample_fmt', 's32']

    def test_lossy_with_bitrate(self):
        params = self._svc()._build_export_params(
            {'format': 'mp3', 'sample_rate': 16000, 'channels': 2, 'bitrate': 128}, 'mp3')
        assert params == ['-ar', '16000', '-ac', '2', '-b:a', '128k']

    def test_bit_depth_ignored_for_lossy(self):
        params = self._svc()._build_export_params({'format': 'mp3', 'bit_depth': 24}, 'mp3')
        assert params == []

    def test_bitrate_ignored_for_lossless(self):
        params = self._svc()._build_export_params({'format': 'wav', 'bitrate': 128}, 'wav')
        assert params == []

    def test_no_params(self):
        assert self._svc()._build_export_params({'format': 'wav'}, 'wav') == []

    @pytest.mark.parametrize('bitrate,expected', [
        (128, '128k'),
        ('128', '128k'),
        ('192k', '192k'),
        ('1m', '1m'),
    ])
    def test_normalize_bitrate(self, bitrate, expected):
        assert self._svc()._normalize_bitrate(bitrate) == expected

    @pytest.mark.parametrize('bitrate,expected', [
        (128, 128000),
        ('192k', 192000),
        ('1m', 1000000),
        ('320', 320000),
    ])
    def test_bitrate_to_bps(self, bitrate, expected):
        assert self._svc()._bitrate_to_bps(bitrate) == expected
