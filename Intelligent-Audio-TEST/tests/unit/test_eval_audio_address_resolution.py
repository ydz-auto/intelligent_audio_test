# -*- coding: utf-8 -*-
"""评估服务音频地址（OSS / presigned URL）→ multipart 文件化单元测试（VEGA-72 / VEGA-69）。

覆盖开发卡 DEV-01~09、DEV-11、DEV-12：
- 单轮/多轮 oss:// 文件化（storage.load_file 下载路径）
- presigned URL http 流式下载（monkeypatch requests.get）
- 兼容性：data URI / 本地绝对路径 / 裸 key 提取行为与改前一致
- 安全边界：非音频字段（callback_url 等）的 http/oss 值原样保留，不触发下载
- 失败态：http 失败 → 业务级 __error__（不进 create_task_upload、不换端点）；
  oss:// 失败 → 降级回原值透传（eval_server 兜底），_has_oss_pass_through_value 仍生效
- 临时文件清理（http 与 storage 下载，成功/失败路径均无残留）
- 配置化（超时/大小上限读 concurrency_config.json，缺省可用）
- 下载失败早退的端点槽位恢复（不泄漏 max_process）
"""
import os
import sys

os.environ.setdefault('OSS_ACCESS_KEY', 'test')
os.environ.setdefault('OSS_SECRET_KEY', 'test')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import json
import shutil
import tempfile
from types import SimpleNamespace

import pytest
import requests

import evaluation_service.infrastructure.evaluation_api.api_request_handler as handler_mod
from evaluation_service.infrastructure.evaluation_api.api_request_handler import (
    AudioAddressResolutionError,
)
from evaluation_service.infrastructure.evaluation_api.evaluation_api_client import (
    evaluationApiClient,
)
from shared.models.common_enums import EvalErrorKind


class FakeStorage:
    """替身 shared.infrastructure.storage.storage：按 path 映射到本地源文件，
    load_file 语义对齐真实实现（拷贝到新临时文件，返回其路径）。"""

    def __init__(self, files=None, fail=False):
        self.files = files or {}          # 存储路径 -> 本地源文件
        self.fail = fail                  # True 时 load_file 抛异常（模拟 OSS 不可用）
        self.load_calls = []              # load_file 收到的 path 记录
        self.loaded_temp_paths = []       # load_file 产出的临时文件（供清理断言）

    def build_path(self, category, key):
        return f'oss://{category}/{key}'

    def exists(self, path):
        return (not self.fail) and path in self.files

    def load_file(self, path, local_path=None, allow_fallback=True):
        self.load_calls.append(path)
        if self.fail:
            raise RuntimeError('OSS 不可用（模拟）')
        suffix = os.path.splitext(path)[-1] or '.tmp'
        dst = tempfile.mktemp(suffix=suffix)
        shutil.copyfile(self.files[path], dst)
        self.loaded_temp_paths.append(dst)
        return dst


class FakeResponse:
    """替身 requests.Response（流式下载用）。"""

    def __init__(self, status_code=200, headers=None, chunks=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._chunks = list(chunks or [])
        self.closed = False

    def iter_content(self, chunk_size=None):
        return iter(self._chunks)

    def close(self):
        self.closed = True


@pytest.fixture
def handler():
    h = handler_mod.ApiRequestHandler()
    h._log = lambda *a, **k: None
    return h


@pytest.fixture(autouse=True)
def fake_storage(monkeypatch):
    """autouse：隔离 handler 模块的 storage 引用。

    payload 顶层普通字符串（如 task_type）会走 _is_file_value 的裸 key 分支
    探测 storage.exists，真实离线 OSS 会串行重试数十秒（见
    test_int2250_eval_poll_failfast 同款注释），故所有用例统一注入替身。"""
    storage = FakeStorage()
    monkeypatch.setattr(handler_mod, 'storage', storage)
    return storage


@pytest.fixture
def wav_pair(tmp_path):
    """两个本地 wav 源文件（字节不同，便于区分轮次）。"""
    a = tmp_path / 'src_a.wav'
    a.write_bytes(b'RIFF-audio-a')
    b = tmp_path / 'src_b.wav'
    b.write_bytes(b'RIFF-audio-b')
    return str(a), str(b)


def _patch_requests_get(monkeypatch, fake_get):
    """把 handler 模块的 requests.get 替换为 fake（其余 requests 引用不受影响）。"""
    monkeypatch.setattr(handler_mod, 'requests', SimpleNamespace(get=fake_get))


def _rounds(form_fields):
    return json.loads(form_fields['rounds'])


# ── DEV-01：单轮 oss:// 文件化 ───────────────────────────────


def test_dev01_single_round_oss_materialized(handler, fake_storage, wav_pair):
    wav_a, _ = wav_pair
    fake_storage.files = {'oss://audios/x.wav': wav_a}
    payload = {'task_type': 'wer', 'rounds': [{'record_file': 'oss://audios/x.wav'}]}

    form_fields, files = handler._extract_files_from_payload(
        payload, audio_field_names={'record_file'})

    # 文件被真正下载并进入 files（字节 + 文件名 + 类型）
    assert 'record_file' in files
    filename, file_bytes, content_type = files['record_file']
    assert file_bytes == b'RIFF-audio-a'
    assert filename.endswith('.wav')
    assert content_type == 'application/octet-stream'
    assert fake_storage.load_calls == ['oss://audios/x.wav']
    # rounds 不再含该字段；也不透传到顶层 form_fields
    assert 'record_file' not in _rounds(form_fields)[0]
    assert 'record_file' not in form_fields
    assert form_fields['task_type'] == 'wer'


# ── DEV-02：多轮 oss:// 文件化 ───────────────────────────────


def test_dev02_multi_round_oss_placeholders(handler, fake_storage, wav_pair):
    wav_a, wav_b = wav_pair
    fake_storage.files = {'oss://audios/a.wav': wav_a, 'oss://audios/b.wav': wav_b}
    payload = {'rounds': [
        {'record_file': 'oss://audios/a.wav'},
        {'record_file': 'oss://audios/b.wav'},
    ]}

    form_fields, files = handler._extract_files_from_payload(
        payload, audio_field_names={'record_file'})

    assert set(files) == {'rounds_0_record_file', 'rounds_1_record_file'}
    assert files['rounds_0_record_file'][1] == b'RIFF-audio-a'
    assert files['rounds_1_record_file'][1] == b'RIFF-audio-b'
    rounds = _rounds(form_fields)
    assert rounds[0]['record_file'] == '__MULTIPART__:rounds_0_record_file'
    assert rounds[1]['record_file'] == '__MULTIPART__:rounds_1_record_file'


# ── DEV-03：presigned URL 下载 ───────────────────────────────


def test_dev03_presigned_url_download_basename(handler, monkeypatch):
    captured = {}

    def fake_get(url, stream=True, timeout=None, **kw):
        captured.update(url=url, timeout=timeout, stream=stream)
        return FakeResponse(200, {'Content-Type': 'audio/wav'}, [b'RIFF', b'data'])

    _patch_requests_get(monkeypatch, fake_get)
    payload = {'task_type': 'wer', 'rounds': [{'record_file': 'https://host/path/audio.wav?sig=abc'}]}

    form_fields, files = handler._extract_files_from_payload(
        payload, audio_field_names={'record_file'})

    assert captured['url'] == 'https://host/path/audio.wav?sig=abc'
    assert captured['stream'] is True
    filename, file_bytes, content_type = files['record_file']
    assert filename == 'audio.wav'                      # URL path basename
    assert file_bytes == b'RIFFdata'
    assert content_type == 'audio/wav'                  # 取响应 Content-Type
    assert 'record_file' not in _rounds(form_fields)[0]


@pytest.mark.parametrize('url,expected_name', [
    ('https://host/get?sig=x', 'get.mp3'),        # path 无扩展名 → Content-Type 映射
    ('https://host?sig=x', 'record_file.mp3'),    # path 为空 → 字段名 + 映射扩展名
])
def test_dev03_filename_fallback_to_content_type(handler, monkeypatch, url, expected_name):
    _patch_requests_get(
        monkeypatch,
        lambda *a, **kw: FakeResponse(200, {'Content-Type': 'audio/mpeg'}, [b'ID3']))
    files = {}
    assert handler._extract_single_file('record_file', url, files) is True
    assert files['record_file'][0] == expected_name


def test_dev03_overlong_url_treated_as_plain_string(handler, monkeypatch):
    """≥4KB 的超长 http 地址按普通字符串处理（VEGA-70 §1.5 已知边界，与改前一致）。"""
    gets = []
    _patch_requests_get(monkeypatch, lambda *a, **kw: gets.append(a) or FakeResponse(200, {}, [b'x']))
    long_url = 'https://host/a.wav?sig=' + 'x' * 5000
    payload = {'rounds': [{'record_file': long_url}]}
    form_fields, files = handler._extract_files_from_payload(
        payload, audio_field_names={'record_file'})
    assert files == {}
    assert gets == []
    # 单轮回退：原值留在 form_fields（storage 解析失败降级，与改前长字符串行为一致）
    assert form_fields['record_file'] == long_url


# ── DEV-04：兼容原有输入（data URI / 本地绝对路径 / 裸 key） ──


def test_dev04_data_uri_extraction_unchanged(handler):
    import base64
    payload = {'task_type': 'wer', 'rounds': [{'record_file': 'data:audio/wav;base64,{}'
                                               .format(base64.b64encode(b'RIFF-legacy').decode())}]}
    form_fields, files = handler._extract_files_from_payload(
        payload, audio_field_names={'record_file'})
    filename, file_bytes, content_type = files['record_file']
    assert filename == 'record_file.wav'
    assert file_bytes == b'RIFF-legacy'
    assert content_type == 'audio/wav'
    assert 'record_file' not in _rounds(form_fields)[0]


def test_dev04_local_absolute_path_extraction_unchanged(handler, wav_pair):
    wav_a, _ = wav_pair
    payload = {'record_file': wav_a}
    form_fields, files = handler._extract_files_from_payload(
        payload, audio_field_names={'record_file'})
    filename, file_bytes, _ = files['record_file']
    assert filename == os.path.basename(wav_a)
    assert file_bytes == b'RIFF-audio-a'
    # 本地真实文件不是临时下载文件，不得被删除
    assert os.path.exists(wav_a)


def test_dev04_bare_key_extraction_unchanged(handler, fake_storage, wav_pair):
    wav_a, _ = wav_pair
    fake_storage.files = {'oss://audios/x.wav': wav_a}
    payload = {'record_file': 'x.wav'}
    form_fields, files = handler._extract_files_from_payload(
        payload, audio_field_names={'record_file'})
    filename, file_bytes, _ = files['record_file']
    assert filename.endswith('.wav')
    assert file_bytes == b'RIFF-audio-a'
    assert fake_storage.load_calls == ['oss://audios/x.wav']


# ── DEV-05：非音频字段不受影响 ───────────────────────────────


def test_dev05_non_audio_fields_untouched(handler, monkeypatch, fake_storage):
    gets = []
    _patch_requests_get(monkeypatch, lambda *a, **kw: gets.append(a) or FakeResponse(200, {}, [b'x']))
    payload = {
        'task_type': 'wer',
        'callback_url': 'https://example.com/cb?token=1',     # 顶层非音频 http
        'oss_hint': 'oss://audios/other.wav',                 # 顶层非音频 oss://
        'meta': {'note': 'https://example.com/note'},         # 顶层嵌套非 audio_path 的 http
        'rounds': [{'utterance': 'plain-text',
                    'callback_url': 'https://example.com/inner'}],
    }

    form_fields, files = handler._extract_files_from_payload(
        payload, audio_field_names={'record_file'})

    assert files == {}
    assert gets == []                                        # 未尝试任何下载
    assert form_fields['callback_url'] == 'https://example.com/cb?token=1'
    assert form_fields['oss_hint'] == 'oss://audios/other.wav'
    assert json.loads(form_fields['meta'])['note'] == 'https://example.com/note'
    rounds = _rounds(form_fields)
    assert rounds[0]['callback_url'] == 'https://example.com/inner'
    assert rounds[0]['utterance'] == 'plain-text'


def test_dev05_nested_audio_path_is_audio_context(handler, monkeypatch, fake_storage, wav_pair):
    """audio_path 键是音频上下文：其 oss:///http 值仍会被文件化。"""
    wav_a, _ = wav_pair
    fake_storage.files = {'oss://audios/n.wav': wav_a}
    payload = {'rounds': [{'played_audios': [{'audio_path': 'oss://audios/n.wav', 'spl': 65}]}]}

    form_fields, files = handler._extract_files_from_payload(
        payload, audio_field_names={'record_file'})

    assert 'rounds_0_played_audios_0_audio_path' in files
    assert files['rounds_0_played_audios_0_audio_path'][1] == b'RIFF-audio-a'
    item = _rounds(form_fields)[0]['played_audios'][0]
    assert item['audio_path'] == '__MULTIPART__:rounds_0_played_audios_0_audio_path'
    assert item['spl'] == 65


# ── DEV-06：http 失败态（业务级错误，不进 create_task_upload、不换端点） ──


def _make_client():
    client = evaluationApiClient()
    logs = []
    client._log = lambda *a, **k: logs.append((a, k))
    client.logs = logs
    return client


def _error_log_count(client):
    return sum(1 for a, k in client.logs
               if (k.get('level') or (a[0] if a else None)) == 'ERROR')


def test_dev06_http_404_business_error_without_fallback(monkeypatch):
    client = _make_client()
    _patch_requests_get(monkeypatch, lambda *a, **kw: FakeResponse(404, {}, [b'']))

    uploads, creates = [], []
    client.create_task_upload = lambda *a, **k: uploads.append(a) or {'code': 1}
    client.create_task = lambda *a, **k: creates.append(a) or {'code': 1}

    def no_fallback(*a, **k):
        raise AssertionError('下载失败不得换端点重投')

    client._try_fallback_endpoints = no_fallback
    client._try_configured_fallback_urls = no_fallback

    selected, resp = client.make_api_request_with_fallback(
        endpoints=[], method='POST', headers={},
        payload={'task_type': 'wer', 'rounds': [{'record_file': 'https://h/a.wav?sig=x'}]},
        task_id=1, dim_names=['wer'], api_url='http://eval-404:5001',
        test_case_id='d6-404', dim_info={}, audio_field_names={'record_file'})

    assert selected == 'http://eval-404:5001'
    assert resp['__error_kind__'] == EvalErrorKind.BUSINESS.value
    assert '音频地址下载失败' in resp['__error__']
    assert 'record_file' in resp['__error__'] and 'HTTP 404' in resp['__error__']
    assert uploads == [] and creates == []       # 未进入 create_task_upload / create_task
    assert _error_log_count(client) >= 1         # ERROR 日志留痕


def test_dev06_http_timeout_exception_business_error(monkeypatch):
    client = _make_client()

    def boom_get(*a, **kw):
        raise requests.exceptions.ReadTimeout('read timed out')

    _patch_requests_get(monkeypatch, boom_get)
    client.create_task_upload = lambda *a, **k: pytest.fail('不应进入 create_task_upload')
    client.create_task = lambda *a, **k: pytest.fail('不应进入 create_task')

    resp = client._execute_async_api_flow(
        'http://eval-timeout:5001', {'task_type': 'wer', 'rounds': [{'record_file': 'https://h/a.wav'}]},
        {}, [], None, 1, 'd6-timeout', 1, ['wer'], audio_field_names={'record_file'})

    assert resp['__error_kind__'] == EvalErrorKind.BUSINESS.value
    assert '音频地址下载失败' in resp['__error__'] and 'record_file' in resp['__error__']


def test_dev06_content_length_precheck_over_limit(monkeypatch):
    client = _make_client()
    _patch_requests_get(monkeypatch, lambda *a, **kw: FakeResponse(
        200, {'Content-Type': 'audio/wav', 'Content-Length': '999999999999'}, [b'RIFF']))
    client.create_task_upload = lambda *a, **k: pytest.fail('不应进入 create_task_upload')

    resp = client._execute_async_api_flow(
        'http://eval-cl:5001', {'task_type': 'wer', 'rounds': [{'record_file': 'https://h/big.wav'}]},
        {}, [], None, 1, 'd6-cl', 1, ['wer'], audio_field_names={'record_file'})

    assert resp['__error_kind__'] == EvalErrorKind.BUSINESS.value
    assert '音频地址下载超限' in resp['__error__'] and '999999999999' in resp['__error__']


# ── DEV-07：oss:// 失败降级回透传 ─────────────────────────────


def test_dev07_single_round_oss_failure_degrades_to_pass_through(handler, fake_storage):
    fake_storage.fail = True
    payload = {'task_type': 'wer', 'rounds': [{'record_file': 'oss://audios/x.wav'}]}

    form_fields, files = handler._extract_files_from_payload(
        payload, audio_field_names={'record_file'})

    assert files == {}
    # 单轮回退 form_fields 原值（eval_server 兜底解析路径可用）
    assert form_fields['record_file'] == 'oss://audios/x.wav'
    assert 'record_file' not in _rounds(form_fields)[0]
    # _has_oss_pass_through_value 仍使其选择 multipart 端点
    client = _make_client()
    assert client._has_oss_pass_through_value(form_fields) is True


def test_dev07_multi_round_oss_failure_keeps_rounds_value(handler, fake_storage):
    fake_storage.fail = True
    payload = {'rounds': [{'record_file': 'oss://audios/a.wav'}, {'record_file': 'oss://audios/b.wav'}]}

    form_fields, files = handler._extract_files_from_payload(
        payload, audio_field_names={'record_file'})

    assert files == {}
    rounds = _rounds(form_fields)
    assert rounds[0]['record_file'] == 'oss://audios/a.wav'
    assert rounds[1]['record_file'] == 'oss://audios/b.wav'
    # rounds JSON 串内含 oss:// 子串 → _has_oss_pass_through_value 仍为 True，
    # 端点选择仍走 create_task_upload（eval_server 兜底路径可用）
    client = _make_client()
    assert client._has_oss_pass_through_value(form_fields) is True


# ── DEV-08：临时文件清理（成功/失败路径均无残留） ─────────────


@pytest.fixture
def mkstemp_recorder(monkeypatch):
    created = []
    real_mkstemp = tempfile.mkstemp

    def recording_mkstemp(*a, **k):
        fd, path = real_mkstemp(*a, **k)
        created.append(path)
        return fd, path

    monkeypatch.setattr(handler_mod.tempfile, 'mkstemp', recording_mkstemp)
    return created


def test_dev08_http_temp_file_cleaned_on_success(handler, monkeypatch, mkstemp_recorder):
    _patch_requests_get(monkeypatch, lambda *a, **kw: FakeResponse(
        200, {'Content-Type': 'audio/wav'}, [b'RIFF', b'data']))
    files = {}
    assert handler._extract_single_file('record_file', 'https://h/a.wav', files) is True
    assert files['record_file'][1] == b'RIFFdata'
    assert mkstemp_recorder, '应有 mkstemp 临时文件产生'
    assert all(not os.path.exists(p) for p in mkstemp_recorder)


def test_dev08_http_temp_file_cleaned_on_stream_over_limit(handler, monkeypatch, mkstemp_recorder):
    cfg = {'audio_url_download_max_bytes': 4}
    monkeypatch.setattr(
        handler_mod, 'config_manager',
        SimpleNamespace(get_value=lambda s, k, d=None: cfg.get(k, d)))
    _patch_requests_get(monkeypatch, lambda *a, **kw: FakeResponse(
        200, {'Content-Type': 'audio/wav'}, [b'12345678']))
    with pytest.raises(AudioAddressResolutionError):
        handler._extract_single_file('record_file', 'https://h/a.wav', {})
    assert mkstemp_recorder, '流式超限路径应已产生临时文件'
    assert all(not os.path.exists(p) for p in mkstemp_recorder)


def test_dev08_storage_temp_file_cleaned(handler, fake_storage, wav_pair):
    wav_a, _ = wav_pair
    fake_storage.files = {'oss://audios/x.wav': wav_a}
    payload = {'rounds': [{'record_file': 'oss://audios/x.wav'}]}
    form_fields, files = handler._extract_files_from_payload(
        payload, audio_field_names={'record_file'})
    assert 'record_file' in files
    assert fake_storage.loaded_temp_paths
    assert all(not os.path.exists(p) for p in fake_storage.loaded_temp_paths)


def test_dev08_storage_temp_file_cleaned_on_failure(handler, fake_storage):
    """storage 下载产出临时文件后读取失败（源文件被并发删除等）也须清理。"""
    wav_src = tempfile.mktemp(suffix='.wav')
    with open(wav_src, 'wb') as f:
        f.write(b'RIFF-tmp')
    fake_storage.files = {'oss://audios/gone.wav': wav_src}
    # load 成功后立即删除源 → open(resolved) 前文件不存在，走失败路径
    real_load = fake_storage.load_file

    def load_then_vanish(path, *a, **k):
        dst = real_load(path, *a, **k)
        os.remove(dst)
        return dst

    fake_storage.load_file = load_then_vanish
    payload = {'rounds': [{'record_file': 'oss://audios/gone.wav'}]}
    form_fields, files = handler._extract_files_from_payload(
        payload, audio_field_names={'record_file'})
    assert files == {}
    assert all(not os.path.exists(p) for p in fake_storage.loaded_temp_paths)


# ── DEV-09：配置化（超时/大小上限，缺省可用） ─────────────────


def test_dev09_config_timeout_and_max_bytes(monkeypatch):
    cfg = {}
    monkeypatch.setattr(
        handler_mod, 'config_manager',
        SimpleNamespace(get_value=lambda s, k, d=None: cfg.get(k, d)))
    captured = {}

    def fake_get(url, stream=True, timeout=None, **kw):
        captured['timeout'] = timeout
        return FakeResponse(200, {'Content-Type': 'audio/wav'}, [b'RIFF', b'data'])

    _patch_requests_get(monkeypatch, fake_get)

    # 配置缺失 → 代码缺省 60 秒
    assert handler_mod.ApiRequestHandler._extract_single_file('record_file', 'https://h/a.wav', {}) is True
    assert captured['timeout'] == 60

    # 配置改值 → 生效
    cfg['audio_url_download_timeout_seconds'] = 12.5
    assert handler_mod.ApiRequestHandler._extract_single_file('record_file', 'https://h/a.wav', {}) is True
    assert captured['timeout'] == 12.5

    # 大小上限改值 → 流式累计超限即失败
    cfg['audio_url_download_max_bytes'] = 5
    with pytest.raises(AudioAddressResolutionError) as ei:
        handler_mod.ApiRequestHandler._extract_single_file('record_file', 'https://h/a.wav', {})
    assert '超过上限' in str(ei.value) and '5' in str(ei.value)

    # 删除键 → 缺省路径可用（默认 200MB 不触发超限）
    cfg.clear()
    assert handler_mod.ApiRequestHandler._extract_single_file('record_file', 'https://h/a.wav', {}) is True


# ── DEV-11：静态检查（模块可导入、_is_oss_pass_through 已删除） ──


def test_dev11_module_importable_and_pass_through_removed():
    import importlib
    mod = importlib.import_module(
        'evaluation_service.infrastructure.evaluation_api.api_request_handler')
    assert hasattr(mod, 'AudioAddressResolutionError')
    assert not hasattr(mod.ApiRequestHandler, '_is_oss_pass_through')


# ── DEV-12：下载失败早退后端点槽位恢复（不泄漏 max_process） ──


def test_dev12_endpoint_slot_released_on_download_failure(monkeypatch):
    client = _make_client()
    client.max_wait_time = 1  # 泄漏时排队 1 秒即失败，测试不空转
    url = 'http://dev12-slot-check:5001'  # 独立端点 key，不与其他用例共享信号量
    # 并发上限 1：泄漏 1 个槽位即满，再 acquire 必然排队超时
    client.endpoint_configs[url] = 1

    def boom_get(*a, **kw):
        raise requests.exceptions.ConnectionError('connection refused')

    _patch_requests_get(monkeypatch, boom_get)

    resp = client._acquire_and_execute(
        url, 'POST', {}, {'task_type': 'wer', 'rounds': [{'record_file': 'https://h/a.wav'}]},
        task_id=1, dim_names=['wer'], endpoints=[], api_url=url,
        test_case_id='d12', api_id=None, dim_info={}, audio_field_names={'record_file'})

    assert resp['__error_kind__'] == EvalErrorKind.BUSINESS.value
    assert '音频地址下载失败' in resp['__error__']
    # 槽位已恢复：上限 1 的端点可立即再次 acquire（若泄漏则排队 1 秒后 False）
    assert client.acquire_endpoint_slot(url) is True
    client.release_endpoint_slot(url)  # 复原计数
