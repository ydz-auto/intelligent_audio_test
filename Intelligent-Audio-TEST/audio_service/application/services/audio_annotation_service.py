# -*- coding: utf-8 -*-
"""音频标注应用服务

从 audio_crud_service.py 中提取的标注相关逻辑：
- _persist_annotations_and_raw
- _collect_case_param_fields（静态方法 → 模块级函数）
- _persist_single_annotation
- _strip_case_params_from_annotation（静态方法 → 模块级函数）
"""
import copy
import logging

from audio_service.domain.repositories.audio_repository_abc import AudioRepositoryInterface
from audio_service.infrastructure.persistence.audio_repository import audio_repository

logger = logging.getLogger(__name__)


def _collect_case_param_fields(algorithm_type):
    """查用例参数字段列表

    通过 gRPC 调用 algorithm_service 获取跨域参数，避免 application 层直接 import PO。
    """
    from shared.clients.grpc_clients import get_algorithm_definition_service_stub
    from shared.proto import algorithm_service_pb2 as _algo_pb
    from shared.utils.grpc_json import loads as _grpc_loads

    case_param_fields = set()
    if not algorithm_type:
        return case_param_fields

    def _grpc_list_params(req_type):
        """调用 algorithm_service gRPC 获取参数列表（返回 dict 列表）。"""
        try:
            stub = get_algorithm_definition_service_stub()
            if req_type == 'ref':
                resp = stub.ListReferenceParams(_algo_pb.ListReferenceParamsRequest(algorithm_type=algorithm_type))
            else:
                resp = stub.ListCaseParams(_algo_pb.ListCaseParamsRequest(algorithm_type=algorithm_type))
            if resp.success:
                data = _grpc_loads(resp.data, {}) or {}
                return data.get('parameters', []) or []
        except Exception:
            pass
        return []

    ref_field_paths = set()
    ref_params = _grpc_list_params('ref')
    for rp in ref_params:
        fp = rp.get('field_path') or rp.get('code')
        if fp:
            if '[]' in fp:
                seg_key = fp.split('[].')[1] if '[].' in fp else fp
                ref_field_paths.add(seg_key)
            else:
                ref_field_paths.add(fp)

    case_params = _grpc_list_params('case')
    for p in case_params:
        fp = p.get('field_path') or p.get('param_code')
        if fp and '[]' in fp:
            seg_key = fp.split('[].')[1] if '[].' in fp else fp
            if seg_key not in ref_field_paths:
                case_param_fields.add(seg_key)
        else:
            if fp not in ref_field_paths:
                case_param_fields.add(fp)
    return case_param_fields


def _strip_case_params_from_annotation(ann_data, case_param_fields):
    """从标注数据中剔除用例参数字段"""
    if not (case_param_fields and isinstance(ann_data, dict)):
        return ann_data
    ann_data_clean = copy.deepcopy(ann_data)
    segments = ann_data_clean.get('segments', [])
    if isinstance(segments, list):
        for seg in segments:
            if isinstance(seg, dict):
                for field_key in list(seg.keys()):
                    if field_key in case_param_fields:
                        del seg[field_key]
    return ann_data_clean


class AudioAnnotationService:
    """音频标注应用服务"""

    def __init__(self, repo: AudioRepositoryInterface = None):
        self.repo = repo or audio_repository

    def persist_annotations_and_raw(self, audio_id, annotations_from_request, algorithm_type):
        """持久化音频标注，返回 raw_annotations_data"""
        case_param_fields = _collect_case_param_fields(algorithm_type)

        raw_annotations_data = []
        for ann in annotations_from_request or []:
            raw_entry = self._persist_single_annotation(audio_id, ann, case_param_fields)
            raw_annotations_data.append(raw_entry)

        if annotations_from_request:
            self.repo.flush()

        return raw_annotations_data or None

    def _persist_single_annotation(self, audio_id, ann, case_param_fields):
        """持久化单条音频标注"""
        ann_format = ann.get('format', 'json')
        ann_data = ann.get('data', {}) or {}
        ann_code = ann.get('code', '')
        ann_source_lang = ann.get('source_language', '')
        ann_target_lang = ann.get('target_language', '')

        raw_entry = {'code': ann_code, 'data': ann_data}

        ann_data = _strip_case_params_from_annotation(ann_data, case_param_fields)

        self.repo.soft_delete_annotation_by_code(audio_id, ann_code)
        self.repo.create_audio_annotation(audio_id, {
            'format': ann_format,
            'code': ann_code,
            'data': ann_data,
            'source_language': ann_source_lang,
            'target_language': ann_target_lang,
        })

        return raw_entry


# 模块级实例
audio_annotation_service = AudioAnnotationService()
