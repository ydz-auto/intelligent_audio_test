# -*- coding: utf-8 -*-
"""B→C 第三方评估适配器单元测试（INT-29）。

三种适配形态（multipart / feature_extract / presigned_url）的载荷构造、
指数退避重试（5xx/网络错误重试，4xx 不重试）、EVAL_RESULT 校验与错误语义。
"""
import io
import json
import os
import sys

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
import requests

from evaluation_service.domain.repositories.third_party_eval_port import (
    ThirdPartyEvalFile,
    ThirdPartyEvalRequest,
)
from evaluation_service.infrastructure.acl.third_party_adapters import (
    AudioFeatureExtractor,
    FeatureExtractThirdPartyEvalAdapter,
    MultipartThirdPartyEvalAdapter,
    PresignedUrlThirdPartyEvalAdapter,
    ThirdPartyEvalAdapterFactory,
)
from shared.models.common_enums import ThirdPartyAdapterKind


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError('no json')
        return self._payload


class FakeSession:
    """按脚本顺序回放响应的替身 Session（记录全部请求）。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, timeout=None, **kwargs):
        self.calls.append({'method': method, 'url': url, **kwargs})
        if not self.responses:
            raise AssertionError('FakeSession 响应脚本耗尽')
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def make_request(eval_params=None):
    return ThirdPartyEvalRequest(
        transfer_id='tid-001',
        form_fields={'task_type': 'llm_judge', 'prompt': '评分'},
        files={'record_file': ThirdPartyEvalFile(
            name='record_file', filename='a.wav',
            content=b'RIFFxxxxWAVEfmt ', content_type='audio/wav')},
        eval_params=eval_params or {},
    )


OK_RESULT = {'code': 0, 'msg': 'ok', 'data': {'result': {'score': 0.92}}}


class TestMultipartAdapter:
    def test_multipart_sends_fields_files_and_transfer_id(self):
        session = FakeSession([FakeResponse(200, OK_RESULT)])
        adapter = MultipartThirdPartyEvalAdapter('http://c', session=session)
        result = adapter.evaluate(make_request())
        assert result.ok is True
        assert result.data['data']['result']['score'] == 0.92
        call = session.calls[0]
        assert call['method'] == 'POST'
        assert call['url'] == 'http://c/evaluate'
        assert call['data']['transfer_id'] == 'tid-001'
        assert call['data']['task_type'] == 'llm_judge'
        filename, content, ctype = call['files']['record_file']
        assert (filename, ctype) == ('a.wav', 'audio/wav')
        assert content.read() == b'RIFFxxxxWAVEfmt '

    def test_multipart_retries_on_5xx_then_succeeds(self):
        session = FakeSession([
            FakeResponse(500, None, text='boom'),
            FakeResponse(200, OK_RESULT),
        ])
        adapter = MultipartThirdPartyEvalAdapter(
            'http://c', max_retries=3, backoff_seconds=0.01, session=session)
        result = adapter.evaluate(make_request())
        assert result.ok is True
        assert len(session.calls) == 2

    def test_multipart_no_retry_on_4xx(self):
        session = FakeSession([FakeResponse(400, {'detail': 'bad'}, text='bad')])
        adapter = MultipartThirdPartyEvalAdapter(
            'http://c', max_retries=3, backoff_seconds=0.01, session=session)
        result = adapter.evaluate(make_request())
        assert result.ok is False
        assert 'HTTP 400' in result.error
        assert len(session.calls) == 1

    def test_multipart_exhausts_retries_on_network_error(self):
        session = FakeSession([requests.exceptions.ConnectionError('down')] * 4)
        adapter = MultipartThirdPartyEvalAdapter(
            'http://c', max_retries=3, backoff_seconds=0.01, session=session)
        result = adapter.evaluate(make_request())
        assert result.ok is False
        assert '不可达' in result.error
        assert len(session.calls) == 4  # 首次 + 3 次重试

    def test_required_keys_validation(self):
        session = FakeSession([FakeResponse(200, {'unexpected': 1})])
        adapter = MultipartThirdPartyEvalAdapter('http://c', session=session)
        result = adapter.evaluate(make_request({'response_required_keys': ['result']}))
        assert result.ok is False
        assert '缺少必填字段' in result.error


class TestFeatureExtractAdapter:
    def test_feature_extract_sends_features_only(self):
        session = FakeSession([FakeResponse(200, OK_RESULT)])
        adapter = FeatureExtractThirdPartyEvalAdapter('http://c', session=session)
        result = adapter.evaluate(make_request())
        assert result.ok is True
        body = session.calls[0]['json']
        assert body['transfer_id'] == 'tid-001'
        # 非法 WAV 内容 → wave 解析失败回退基础特征（size/sha256），无声道字段
        feats = body['features']['record_file']
        assert feats['size_bytes'] == len(b'RIFFxxxxWAVEfmt ')
        assert 'sha256' in feats and 'channels' not in feats
        assert 'files' not in body

    def test_audio_feature_extractor_parses_wav(self):
        import io
        import wave
        buf = io.BytesIO()
        with wave.open(buf, 'wb') as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(b'\x00\x00' * 16000)
        feats = AudioFeatureExtractor().extract('t.wav', buf.getvalue())
        assert feats['channels'] == 2
        assert feats['framerate'] == 16000
        # 32000 字节 / (2 声道 × 2 字节) = 8000 帧 → 0.5s
        assert feats['duration_seconds'] == 0.5


class TestPresignedUrlAdapter:
    def test_presigned_flow_upload_then_evaluate(self):
        session = FakeSession([
            FakeResponse(200, {'upload_url': 'http://c/upload/1', 'object_ref': 'obj-1'}),
            FakeResponse(200, {}),
            FakeResponse(200, OK_RESULT),
        ])
        adapter = PresignedUrlThirdPartyEvalAdapter('http://c', session=session)
        result = adapter.evaluate(make_request())
        assert result.ok is True
        assert len(session.calls) == 3
        assert session.calls[1]['method'] == 'PUT'
        assert session.calls[1]['data'] == b'RIFFxxxxWAVEfmt '
        body = session.calls[2]['json']
        assert body['objects'] == {'record_file': 'obj-1'}

    def test_presigned_missing_object_ref_fails(self):
        session = FakeSession([FakeResponse(200, {'upload_url': 'http://c/u'})])
        adapter = PresignedUrlThirdPartyEvalAdapter(
            'http://c', max_retries=0, backoff_seconds=0.01, session=session)
        result = adapter.evaluate(make_request())
        assert result.ok is False
        assert 'object_ref' in result.error


class TestFactory:
    def test_factory_builds_all_kinds(self):
        factory = ThirdPartyEvalAdapterFactory()
        settings = {'base_url': 'http://c', 'backoff_seconds': 0.01}
        assert isinstance(factory.create('multipart', settings), MultipartThirdPartyEvalAdapter)
        assert isinstance(factory.create('feature_extract', settings), FeatureExtractThirdPartyEvalAdapter)
        assert isinstance(factory.create('presigned_url', settings), PresignedUrlThirdPartyEvalAdapter)

    def test_factory_rejects_unknown_kind(self):
        with pytest.raises(ValueError, match='非法第三方评估适配形态'):
            ThirdPartyEvalAdapterFactory().create('smoke_signal', {'base_url': 'http://c'})

    def test_factory_requires_base_url(self):
        with pytest.raises(ValueError, match='base_url'):
            ThirdPartyEvalAdapterFactory().create('multipart', {})
