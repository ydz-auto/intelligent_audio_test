# -*- coding: utf-8 -*-
"""INT-98 api_executor._execute_linear 线性流 RenderService 消费链路接线单测

覆盖（验收标准）：
1. 线性流音频交付契约裁定落地：混音产物落存储后按引用交付
   - _run_single_api：RenderAudioFile 产物引用替换 file_path 后进入既有
     health_check / create_task 链路（厂商契约由统一存储层解析满足）；
     渲染失败定用例失败，不静默回退原始路径
   - _resolve_linear_round_config：顶层 audios 优先（多源全量进混音）/
     为空回退唯一 rounds[0]（轮次级噪声随其生效）
   - _execute_linear：渲染失败沿既有 per-API 失败收敛 → TaskCase FAILED
2. 执行器模块零 get_render_service_stub / proto 直触（源级守卫延续 INT-82）
"""
import threading
from types import SimpleNamespace
from unittest import mock

import pytest

import os
os.environ.setdefault('DATABASE_URL', 'sqlite:///:memory:')
os.environ.setdefault('OSS_ACCESS_KEY', 'test-access')
os.environ.setdefault('OSS_SECRET_KEY', 'test-secret')

import api_test_service.core.api_executor as api_executor_module
from api_test_service.core.api_executor import APIExecutor


RENDERED_REF = 'local://audios/T1/7/rendered/linear_1700000000000.wav'
RAW_REF = 'local://audios/raw/a.wav'


class _EngineStub:
    stop_flags = {}
    pause_flags = {}
    api_entry_lock = threading.Lock()
    api_entry_status = {}
    round_progress_cache = {}

    def _emit_progress(self, task_id, force=False):
        pass

    def notify_case_completed(self, task_id):
        pass

    def update_case_round_progress(self, task_id, tc_rel_id, current, total):
        pass


class _ConcurrencyStub:
    def acquire(self, *a, **k):
        return True

    def release(self, *a, **k):
        pass


class _TaskDataAclStub:
    """TaskCase ACL 桩：记录状态更新，返回单个 pending TaskCase（dict 直通）"""

    def __init__(self, tc_rel_id=1, test_case_id=11):
        self.tc_rel_id = tc_rel_id
        self.test_case_id = test_case_id
        self.status_updates = []

    def get_task_case_by_ids(self, task_id):
        return [{'id': self.tc_rel_id, 'test_case_id': self.test_case_id,
                 'execution_status': 'pending', 'evaluation_status': 'pending',
                 'status': 'in_progress'}]

    def update_task_case_status(self, **kwargs):
        self.status_updates.append(kwargs)


def _make_executor():
    executor = APIExecutor(_EngineStub())
    executor._concurrency = _ConcurrencyStub()
    return executor


def _api_config(api_id=7):
    return SimpleNamespace(
        id=api_id, endpoint='http://vendor/api', api_endpoints=[],
        default_max_process=2, meta={}, max_timeout=30, vendor='volc_ast')


def _stub_render_service(executor, rendered, calls):
    service = mock.Mock()
    service.render_round_file_to_storage.side_effect = \
        lambda api_config, round_config, case_config, task_id, name_hint='': (
            calls.append({'round_config': round_config,
                          'case_config': case_config,
                          'api_id': api_config.id,
                          'name_hint': name_hint}) or rendered)
    executor._render_service = service
    return service


def _stub_task_runner_happy_path(executor, delivered):
    """task_runner 桩：捕获 health_check / create_task 实际收到的音频路径"""
    executor._task_runner.setup_endpoints = \
        lambda *a, **k: ({'health': '/health'}, lambda: 'http://v', lambda u: None)
    executor._task_runner.health_check = mock.Mock(
        side_effect=lambda task_id, case_name, audio, *a, **k:
            delivered.__setitem__('health_file_path', audio.get('file_path')))
    executor._task_runner.create_task = mock.Mock(
        side_effect=lambda task_id, audio, *a, **k:
            (delivered.__setitem__('create_file_path', audio.get('file_path')),
             'API-T1')[1])
    executor._task_runner.wait_for_completion = \
        lambda *a, **k: (0.0, True, None)
    executor._task_runner.get_final_result = \
        lambda *a, **k: {'json': {'data': {}}, 'latency': 5}
    executor._task_runner.get_frame_results = lambda *a, **k: None
    executor._task_runner.extract_final_result = lambda *a, **k: ({'t': 'o'}, 5)
    executor._task_runner.delete_task = lambda *a, **k: None
    executor._result_processor.create_test_result = mock.Mock(return_value=99)
    executor._evaluate_result = mock.Mock()
    executor._log_case_result = mock.Mock()


# ── _run_single_api：产物引用替换 file_path 接线 ──────────

class TestLinearRenderWiring:
    def test_rendered_reference_replaces_file_path(self):
        """混音产物引用替换 file_path 后进入 health_check / create_task"""
        executor = _make_executor()
        delivered = {}
        _stub_render_service(executor, {'path': RENDERED_REF,
                                        'duration_ms': 1500}, [])
        _stub_task_runner_happy_path(executor, delivered)

        audio = {'id': 3, 'name': 'a.wav', 'asr_text': 'ref',
                 'file_path': RAW_REF}
        executor._run_single_api(
            'T1', 1, 11, 'case', 'translation', _api_config(), {}, audio,
            12.0, {'audios': [{'audio_id': 3, 'type': 'speaker', 'spl': 65}]}, {})

        assert delivered['health_file_path'] == RENDERED_REF
        assert delivered['create_file_path'] == RENDERED_REF
        # 交付的是混音产物引用，非原始 file_path 直传
        assert delivered['health_file_path'] != RAW_REF
        executor._task_runner.health_check.assert_called_once()

    def test_render_failure_fails_case_without_silent_fallback(self):
        """渲染失败：抛错定用例失败，health_check / create_task 不启动、原始路径不交付"""
        executor = _make_executor()
        _stub_render_service(executor, None, [])
        executor._task_runner.setup_endpoints = \
            lambda *a, **k: ({'health': '/health'}, lambda: 'http://v', lambda u: None)
        executor._task_runner.health_check = mock.Mock()
        executor._task_runner.create_task = mock.Mock()

        audio = {'id': 3, 'name': 'a.wav', 'asr_text': '', 'file_path': RAW_REF}
        with pytest.raises(Exception, match='线性流混音渲染失败'):
            executor._run_single_api(
                'T1', 1, 11, 'case', 'translation', _api_config(), {}, audio,
                12.0, {'audios': [{'audio_id': 3, 'type': 'speaker'}]}, {})
        assert not executor._task_runner.health_check.called
        assert not executor._task_runner.create_task.called

    def test_render_receives_linear_round_config_and_case_config(self):
        """消费链路组装：round_config 经线性解析，case_config 原样透传（两级噪声语义）"""
        executor = _make_executor()
        calls = []
        _stub_render_service(executor, {'path': RENDERED_REF}, calls)
        _stub_task_runner_happy_path(executor, {})

        case_config = {
            'audios': [{'audio_id': 3, 'type': 'speaker', 'spl': 65}],
            'background_noise': {'audio_id': 99, 'spl': 50},
        }
        executor._run_single_api(
            'T1', 1, 11, 'case', 'translation', _api_config(), {},
            {'id': 3, 'file_path': RAW_REF}, 1.0, case_config, {})
        assert len(calls) == 1
        assert calls[0]['api_id'] == 7
        assert calls[0]['round_config'] == {
            'audios': [{'audio_id': 3, 'type': 'speaker', 'spl': 65}]}
        assert calls[0]['case_config'] is case_config
        assert calls[0]['name_hint'] == 'linear'


# ── _resolve_linear_round_config：线性音频源语义 ──────────

class TestResolveLinearRoundConfig:
    def test_top_level_audios_priority_multi_source(self):
        """顶层 audios 优先，多源全量进入混音（镜像 _get_audio_data 音频源语义）"""
        case_config = {
            'audios': [{'audio_id': 1, 'type': 'speaker', 'spl': 65},
                       {'audio_id': 2, 'type': 'interferer', 'spl': 55}],
            'rounds': [{'round_number': 1,
                        'audios': [{'audio_id': 9, 'type': 'speaker'}]}],
        }
        config = APIExecutor._resolve_linear_round_config(case_config)
        assert config == {'audios': [
            {'audio_id': 1, 'type': 'speaker', 'spl': 65},
            {'audio_id': 2, 'type': 'interferer', 'spl': 55}]}

    def test_fallback_to_single_round_config(self):
        """顶层 audios 为空 → 唯一 rounds[0] 整体作轮次配置（噪声随轮次级生效）"""
        round1 = {'round_number': 1,
                  'audios': [{'audio_id': 5, 'type': 'speaker', 'spl': 70}],
                  'background_noise': {'audio_id': 6, 'spl': 45, 'loop': True}}
        config = APIExecutor._resolve_linear_round_config({'rounds': [round1]})
        assert config is round1

    def test_no_audios_yields_empty_config(self):
        """无任何音频条目 → 空 audios 配置（上游 _get_audio_data 已先失败）"""
        assert APIExecutor._resolve_linear_round_config({}) == {'audios': []}
        assert APIExecutor._resolve_linear_round_config(None) == {'audios': []}


# ── _execute_linear：渲染失败收敛为 TaskCase FAILED ───────

class TestLinearFailureConvergence:
    def test_render_failure_marks_task_case_failed(self):
        """渲染失败沿既有 per-API 失败链路 → TaskCase 置 FAILED"""
        executor = _make_executor()
        acl = _TaskDataAclStub(tc_rel_id=1, test_case_id=11)
        calls = []
        _stub_render_service(executor, None, calls)
        executor._handle_control = lambda task_id: None

        data = {'test_case_id': 11, 'case_name': 'case',
                'api_configs': [_api_config()],
                'audio': {'id': 3, 'file_path': RAW_REF},
                'api_specific_config': {}, 'total_audio_duration': 1.0}

        with mock.patch.object(api_executor_module, '_task_data_acl', acl):
            assert executor._execute_linear('T1', 1, data,
                                            {'audios': []}, 'translation', {}) is True

        assert len(calls) == 1
        failed = [u for u in acl.status_updates
                  if u.get('execution_status') == 'failed']
        assert failed, f"TaskCase 未被置 FAILED: {acl.status_updates}"
