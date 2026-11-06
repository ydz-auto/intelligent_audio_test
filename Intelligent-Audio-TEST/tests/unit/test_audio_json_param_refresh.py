# -*- coding: utf-8 -*-
"""按 JSON 更新标注后，用例参数应使用原始标注并覆盖旧值。"""
from audio_service.application.services._creation_refresh_mixin import (
    CreationRefreshMixin,
)
from audio_service.application.services.testcase_refresh_scheduler import (
    TestCaseRefreshScheduler,
)


class FakeAlgorithmAcl:
    def list_case_params(self, algorithm_type):
        return [{
            'param_code': 'query',
            'field_path': 'query',
            'annotation_code': 'annotation',
        }]


class FakeTestcaseAcl:
    def __init__(self):
        self.updates = []

    def update_testcase_config(self, testcase_id, data):
        self.updates.append((testcase_id, data))


class FakeRepo:
    def get_annotations_by_audio(self, audio_id):
        return []


class DummyRefresh(CreationRefreshMixin):
    def __init__(self):
        self._algorithm_acl = FakeAlgorithmAcl()
        self._testcase_acl = FakeTestcaseAcl()
        self.repo = FakeRepo()
        self.raw_seen = None

    def _build_name_to_id_maps(self):
        return {}, {}

    @staticmethod
    def _ensure_round_params_entry(algo_params_col, round_number):
        for entry in algo_params_col:
            if entry.get('round_number') == round_number:
                return entry
        entry = {'round_number': round_number, 'params': []}
        algo_params_col.append(entry)
        return entry

    def _extract_round_params_from_annotations(
            self, scoped_params, raw_anns, algo_type,
            audio_name_to_id_map, dev_name_to_id):
        self.raw_seen = raw_anns
        return [{'field_code': 'query', 'field_value': '新 JSON 值'}]


def test_raw_annotations_override_existing_case_param():
    service = DummyRefresh()
    testcase = {
        'id': 9,
        'algorithm_type': 'asr',
        'config': {
            'rounds': [{
                'round_number': 1,
                'audios': [{'audio_id': 1}],
            }],
        },
        'algorithm_params': [{
            'round_number': 1,
            'params': [{
                'field_code': 'query',
                'field_value': '旧参数',
            }],
        }],
    }
    raw_annotations_by_audio = {
        1: [{
            'code': 'annotation',
            'data': {'segments': [{'query': '新 JSON 值'}]},
        }],
    }

    service._refresh_single_testcase_params(
        testcase, 9, 'asr', raw_annotations_by_audio)

    assert service.raw_seen == raw_annotations_by_audio[1]
    _, update_data = service._testcase_acl.updates[0]
    params = update_data['algorithm_params'][0]['params']
    assert params == [{'field_code': 'query', 'field_value': '新 JSON 值'}]


def test_scheduler_passes_raw_annotations_to_refresh():
    seen = []

    def refresh(audio_ids, algorithm_type, raw_annotations_by_audio=None):
        seen.append((audio_ids, algorithm_type, raw_annotations_by_audio))
        return []

    scheduler = TestCaseRefreshScheduler(refresh)
    raw = {1: [{'code': 'annotation', 'data': {'segments': []}}]}
    scheduler.enqueue([1], 'asr', None, raw)

    assert scheduler.wait_idle(5)
    assert seen == [([1], 'asr', raw)]
