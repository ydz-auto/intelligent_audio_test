# -*- coding: utf-8 -*-
"""JSON 标注刷新测试用例参数：input_gap_ms 提取链路。"""
import os
import sys

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from audio_service.application.services._creation_annotation_mixin import (
    CreationAnnotationMixin,
)


class _FakeAlgorithmAcl:
    @staticmethod
    def list_case_params(algorithm_type):
        return [{
            'param_code': 'input_gap_ms',
            'param_type': 'number',
            'scope': 'common',
            'annotation_code': None,
            'field_path': 'input_gap_ms',
        }] if algorithm_type == 'voice_llm' else []


def test_input_gap_ms_is_extracted_into_case_params():
    service = CreationAnnotationMixin()
    service._algorithm_acl = _FakeAlgorithmAcl()
    service._build_name_to_id_maps = lambda: ({}, {})

    rounds = [{
        'round_number': 1,
        'audios': [{'audio_id': 2126}],
    }]
    raw_annotations = [{
        'code': 'reference',
        'data': {'segments': [{'input_gap_ms': 12345}]},
    }]
    algorithm_params = []

    service._extract_case_params_from_annotations(
        rounds, raw_annotations, 'voice_llm', 'digital', algorithm_params
    )

    params = algorithm_params[0]['params']
    assert params == [{'field_code': 'input_gap_ms', 'field_value': 12345}]
