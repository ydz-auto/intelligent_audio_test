# -*- coding: utf-8 -*-
"""音频文件夹导入的用例名与幂等身份回归测试。"""
import os
import tempfile

os.environ.setdefault('DATABASE_URL',
                      'sqlite:///' + tempfile.mkdtemp(prefix='audio_case_id_') + '/audio.db')
os.environ.setdefault('OSS_ACCESS_KEY', 'unit-test')
os.environ.setdefault('OSS_SECRET_KEY', 'unit-test')

from types import SimpleNamespace

from audio_service.application.services.audio_testcase_creation_service import (
    AudioTestCaseCreationService,
)
from audio_service.application.services.audio_upload.round_config_service import (
    AudioRoundConfigService,
)


def _make_service(existing, captured, updated):
    audio = SimpleNamespace(id=1, name='a.wav', md5='md5-1',
                            original_filename='a.wav', created_at=None)

    class _Repo:
        def get_audio(self, _audio_id):
            return audio

        def find_audio_by_name(self, name):
            return audio if name == audio.name else None

    svc = AudioTestCaseCreationService.__new__(AudioTestCaseCreationService)
    svc.repo = _Repo()
    svc._playback_acl = SimpleNamespace(list_playback_devices=lambda: [])
    svc._algorithm_acl = SimpleNamespace(list_case_params=lambda _algorithm_type: [])
    svc._testcase_acl = SimpleNamespace(
        list_all_testcases=lambda: existing,
        create_testcase_config=lambda data: (captured.append(data), {'id': 'new-id'})[1],
        update_testcase_config=lambda case_id, data: (
            updated.append((case_id, data)), {})[1],
    )
    return svc


def test_same_group_and_name_updates_existing_case():
    existing = [{'id': 'old-id', 'name': '测试用例_case-from-json', 'group_name': '目标组'}]
    captured, updated = [], []
    svc = _make_service(existing, captured, updated)

    result = svc.create_test_case_from_audio(
        1, 'http_api', [], group_name='目标组',
        rounds_config=[{'round_number': 1, 'audios': [
            {'audio_name': 'a.wav', 'play_order': 1}]}],
        test_case_name='case-from-json')

    assert result == ['old-id']
    assert updated[0][0] == 'old-id'
    assert updated[0][1]['name'] == '测试用例_case-from-json'
    assert updated[0][1]['group'] == '目标组'
    assert captured == []


def test_same_name_in_different_group_creates_case():
    existing = [{'id': 'other-id', 'name': '测试用例_case-from-json', 'group_name': '其他组'}]
    captured, updated = [], []
    svc = _make_service(existing, captured, updated)

    svc.create_test_case_from_audio(
        1, 'http_api', [], group_name='目标组',
        rounds_config=[{'round_number': 1, 'audios': [
            {'audio_name': 'a.wav', 'play_order': 1}]}],
        test_case_name='case-from-json')

    assert captured[0]['name'] == '测试用例_case-from-json'
    assert captured[0]['group'] == '目标组'
    assert updated == []


def test_merge_params_extract_explicit_case_name():
    params = AudioRoundConfigService().extract_merge_params({
        'test_case_config': {
            'rounds': [{'round_number': 1, 'audios': [
                {'audio_name': 'a.wav', 'play_order': 1}]}],
            'test_case_name': 'case-from-json',
        }
    })

    assert params['test_case_name'] == 'case-from-json'


def test_gateway_schema_accepts_case_name():
    from api_gateway.schemas.audio import MergeChunksRequest

    request = MergeChunksRequest.model_validate({
        'file_id': 'f-1',
        'task_id': 't-1',
        'test_case_config': {
            'rounds': [{'round_number': 1, 'audios': [
                {'audio_name': 'a.wav', 'play_order': 1}]}],
            'test_case_name': 'case-from-json',
        },
    })

    assert request.test_case_config.test_case_name == 'case-from-json'
