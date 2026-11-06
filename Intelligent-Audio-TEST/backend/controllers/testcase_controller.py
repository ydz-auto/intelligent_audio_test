import os
from flask import request, send_file, current_app
from backend.models.models import (
    TestCase, TestCaseGroup, Tag, Dimension, Audio, PlaybackDevice,
    Task, Report, ReportSummary, ReportSummaryMeta, ReportRawData,
    ReportCase, ReportMetricStats, ReportStatus, ReportType, TaskStatus,
)
from backend.models.database import db
from backend.models.soft_delete import bulk_soft_delete, include_deleted
from backend.utils.web.response import success_response, error_response
from backend.utils.web.log_handler import log_not_emit
from backend.utils.common.task_utils import has_running_e2e_tasks
from sqlalchemy.orm import joinedload

from backend.schemas.common import StringIdData
from backend.schemas.testcase import (
    TagListData,
    TestCaseAudioConfigItem,
    TestCaseDetailData,
    TestCaseDimensionBrief,
    TestCaseExportItem,
    TestCaseExportJsonData,
    TestCaseListData,
    TestCaseListItem,
    TestCasePreviewData,
    TestCaseStatsData,
    TestCaseStopPreviewData,
    TestCaseCreateSchema,
    TestCaseUpdateSchema,
    TestCasePreviewRequest,
    TestCaseBatchActionRequest,
    TestCaseExportRequest,
    RoundConfigItem,
)
from backend.utils.algorithm.reference_params_generator import ReferenceParamsGenerator


import uuid
import json
import io
import hashlib
import zipfile
import logging
import pandas as pd
from datetime import datetime, timezone, timedelta
from pathlib import PurePosixPath
from backend.utils.common.query_utils import now_cst

logger = logging.getLogger(__name__)

INTERRUPTION_METRIC_DEFINITIONS = [
    ('success_count', '打断成功数量', '%', 2),
    ('failure_count', '打断失败数量', '%', 2),
    ('inquiry_count', '打断询问数量', '%', 2),
    ('reply_behavior_count', '打断回复行为数量', '%', 2),
    ('recover_behavior_count', '打断恢复行为数量', '%', 2),
    ('irrelevant_behavior_count', '打断无关行为数量', '%', 2),
    ('silence_behavior_count', '打断静默行为数量', '%', 2),
    ('ask_behavior_count', '打断询问行为数量', '%', 2),
    ('reply_content_score', '打断回复内容评分', '分', 2),
    ('stop_compliance_rate', '停止指令遵循', '%', 2),
    ('resume_content_score', '恢复首轮内容评分', '分', 2),
    ('response_latency_avg_ms', '响应时延', 'ms', 0),
    ('reply_latency_avg_ms', '回复时延', 'ms', 0),
    ('resume_first_reply_latency_ms', '恢复首轮内容时延', 'ms', 0),
]
INTERRUPTION_METRIC_FIELDS = {
    '打断成功数量': 'success_count',
    '打断失败数量': 'failure_count',
    '打断询问数量': 'inquiry_count',
    '打断回复行为数量': 'reply_behavior_count',
    '打断恢复行为数量': 'recover_behavior_count',
    '打断无关行为数量': 'irrelevant_behavior_count',
    '打断静默行为数量': 'silence_behavior_count',
    '打断询问行为数量': 'ask_behavior_count',
    '打断回复内容评分': 'reply_content_score',
    '停止指令遵循': 'stop_compliance_rate',
    '恢复首轮内容评分': 'resume_content_score',
    '响应时延': 'response_latency_avg_ms',
    '回复时延': 'reply_latency_avg_ms',
    '恢复首轮内容时延': 'resume_first_reply_latency_ms',
}
INTERRUPTION_METRIC_CODES = {
    metric_code for metric_code in INTERRUPTION_METRIC_FIELDS.values()
}
LEGACY_INTERRUPTION_EXECUTION_METRICS = {
    'duration_ms',
    'turns',
    'round_count',
    'completed_step_count',
    'trigger_error_ms',
    'input_end_output_ms',
    'audio_output_detected_rate',
}
TURN_EVAL_DIMENSION_IDS = (72, 84, 85, 86, 87, 88)
TURN_EVAL_DIMENSION_FIELDS = {
    84: ('takeover_rate', 'turn_classification.takeover_rate'),
    85: ('no_takeover_rate', 'turn_classification.no_takeover_rate'),
    86: ('false_takeover_rate', 'turn_classification.false_takeover_rate'),
    87: ('takeover_latency_avg_ms', 'takeover_latency.takeover_latency_avg_ms'),
    88: ('reply_quality_avg_score', 'reply_quality.reply_quality_avg_score'),
}
TURN_EVAL_LEGACY_METRICS = {'round_count', 'completed_step_count'}
REJECT_DIMENSION_IDS = tuple(range(121, 133))
REJECT_DIMENSION_FIELDS = {
    121: ('n_rate_success', 'n_reject_rounds'),
    122: ('n_rate_inquiry', 'n_reject_rounds'),
    123: ('n_rate_failure', 'n_reject_rounds'),
    124: ('n_success_silent_recover', 'n_rate_success'),
    125: ('n_success_reply_recover', 'n_rate_success'),
    126: ('n_inquiry_silent', 'n_rate_inquiry'),
    127: ('n_inquiry_reply', 'n_rate_inquiry'),
    128: ('n_failure_silent_respond', 'n_rate_failure'),
    129: ('n_failure_reply_respond', 'n_rate_failure'),
    130: ('n_failure_silent_irrelevant', 'n_rate_failure'),
    131: ('n_failure_reply_irrelevant', 'n_rate_failure'),
    132: ('n_failure_reply_silent', 'n_rate_failure'),
}
REJECT_LEGACY_METRICS = {'round_count', 'completed_step_count'}
ENV_DIMENSION_IDS = (133, 134, 135)
ENV_DIMENSION_FIELDS = {
    133: 'understand_correct_pass',
    134: 'response_latency_ms',
    135: 'score',
}
ENV_LEGACY_METRICS = {'round_count', 'completed_step_count'}


def _normalize_interruption_path(path: str) -> str:
    """把 ZIP 内路径规范成 POSIX 相对路径。"""
    return str(PurePosixPath(str(path or '').replace('\\', '/')).as_posix()).lstrip('/')


def _interruption_md5(content: bytes) -> str:
    return hashlib.md5(content).hexdigest()


def _safe_interruption_zip_names(names):
    normalized_names = []
    for raw_name in names:
        normalized_name = _normalize_interruption_path(raw_name)
        if not normalized_name or normalized_name.endswith('/'):
            continue
        if normalized_name.startswith('..') or '/..' in normalized_name:
            raise ValueError(f"ZIP 内存在非法路径: {raw_name}")
        normalized_names.append(normalized_name)
    return set(normalized_names)


def _find_interruption_zip_root(names):
    report_candidates = sorted(
        [name for name in names if name == 'report.json' or name.endswith('/report.json')],
        key=len,
    )
    if not report_candidates:
        raise ValueError("ZIP 包中未找到 report.json")
    report_path = report_candidates[0]
    if report_path == 'report.json':
        return ''
    return report_path[:-len('report.json')]


def _resolve_interruption_zip_entry(logical_path, names, path_mapping):
    normalized_logical_path = _normalize_interruption_path(logical_path)
    actual_path = path_mapping.get(normalized_logical_path)
    if actual_path and actual_path in names:
        return actual_path
    if normalized_logical_path in names:
        return normalized_logical_path
    suffix = f'/{normalized_logical_path}'
    candidates = sorted([name for name in names if name.endswith(suffix)], key=len)
    if candidates:
        return candidates[0]
    return None

class TestCaseController:
    @staticmethod
    def _log(level, content, task_id=None, test_case_id=None, api_id=None, category='execution', module='TestCase', **kwargs):
        """统一日志记录方法"""
        log_not_emit(
            level=level,
            module=module,
            content=content,
            category=category,
            source='backend',
            task_id=task_id,
            api_id=api_id,
            test_case_id=test_case_id,
            **kwargs
        )

    @staticmethod
    def _normalize_optional_int(value):
        if value is None:
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if value.is_integer():
                return int(value)
            return None
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return None
            try:
                return int(text)
            except Exception:
                try:
                    f = float(text)
                    return int(f) if f.is_integer() else None
                except Exception:
                    return None
        try:
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _has_overlap_param_changed(old_params: list, new_params: list) -> bool:
        overlap_fields = {'overlap_rate', 'overlap_time', 'overlapRate', 'overlapTime'}
        
        def get_overlap_values(params: list) -> dict:
            result = {}
            for p in params:
                if not isinstance(p, dict):
                    continue
                field_code = p.get('field_code') or p.get('fieldCode')
                if field_code in overlap_fields:
                    result[field_code] = p.get('field_value', p.get('fieldValue'))
            return result
        
        old_overlap = get_overlap_values(old_params)
        new_overlap = get_overlap_values(new_params)
        
        return old_overlap != new_overlap

    @staticmethod
    def _get_algo_params_list_from_config(config: dict) -> list:
        """从 config 中提取 algorithm_params 列表格式（兼容旧数据）

        新数据：config.rounds[] 不含 algorithmParams，应从独立列读取（见 _get_algo_params_list_from_columns）
        旧数据：config.rounds[0].algorithmParams 为 dict，转换为 [{field_code, field_value}] 列表
        """
        if not config:
            return []
        rounds = config.get('rounds', [])
        if rounds:
            first_round = rounds[0] if rounds else {}
            if isinstance(first_round, dict):
                ap_dict = first_round.get('algorithmParams', {})
                if isinstance(ap_dict, dict):
                    return [{'field_code': k, 'field_value': v} for k, v in ap_dict.items()]
        return []

    @staticmethod
    def _get_algo_params_list_from_columns(algorithm_params_col, round_number=1):
        """从 algorithm_params 独立列按轮获取 [{field_code, field_value}] 列表"""
        if not algorithm_params_col:
            return []
        for item in algorithm_params_col:
            if isinstance(item, dict) and item.get('round_number') == round_number:
                return item.get('params', [])
        return []

    @staticmethod
    def _get_algorithm_params_dict_for_columns(algorithm_params_col, round_number=1):
        """从 algorithm_params 独立列按轮获取 dict"""
        params_list = TestCaseController._get_algo_params_list_from_columns(algorithm_params_col, round_number)
        result = {}
        for p in params_list:
            if not isinstance(p, dict):
                continue
            fc = p.get('field_code')
            if fc:
                result[fc] = p.get('field_value')
        return result

    @staticmethod
    def _has_rounds(config: dict) -> bool:
        """判断 config 是否为 rounds-as-top-level 格式"""
        return bool(config and isinstance(config.get('rounds'), list) and len(config['rounds']) > 0)

    @staticmethod
    def _convert_flat_config_to_rounds(config: dict) -> dict:
        """将平面格式 config 转换为 rounds-as-top-level 格式

        只构建结构性字段（roundNumber/audios/backgroundNoise/evaluation），
        不再写入 algorithmParams 和 referenceParamsPath。
        algorithm_params 由调用方从 schema 获取并赋值给独立列。
        """
        if TestCaseController._has_rounds(config):
            return config

        result = dict(config)
        audios = result.pop('audios', [])
        bg_noise = result.pop('background_noise', None) or result.pop('backgroundNoise', None)
        dimensions = result.pop('dimensions', [])

        # 剥离非结构性字段（algorithm_params 由独立列存储）
        result.pop('algorithm_params', None)
        for key in ('reference_params', 'referenceParamsPath'):
            result.pop(key, None)

        round_data = {
            'roundNumber': 1,
            'audios': audios or [],
            'backgroundNoise': bg_noise,
            'evaluation': {'dimensions': dimensions or []},
        }

        result['rounds'] = [round_data]
        return result

    @staticmethod
    def _collect_audios(config: dict) -> list:
        """从 config 中提取所有音频配置项（从 rounds[].audios 收集）"""
        if not config:
            return []
        all_audios = []
        for round_item in config.get('rounds', []):
            if isinstance(round_item, dict):
                round_audios = round_item.get('audios', [])
                if isinstance(round_audios, list):
                    all_audios.extend(round_audios)
        return all_audios

    @staticmethod
    def _collect_dimensions(config: dict) -> list:
        """从 config 中提取评测维度
        合并 rounds[].evaluation.dimensions（单轮维度）和 config.dimensions（多轮维度）
        """
        if not config:
            return []
        result = []
        seen_ids = set()
        rounds = config.get('rounds', [])
        if rounds:
            for round_item in rounds:
                if isinstance(round_item, dict):
                    evaluation = round_item.get('evaluation', {})
                    if isinstance(evaluation, dict):
                        for d in evaluation.get('dimensions', []):
                            dim_id = d.get('id') if isinstance(d, dict) else d
                            if dim_id and dim_id not in seen_ids:
                                seen_ids.add(dim_id)
                                result.append(d)
        # 合并顶层 config.dimensions（多轮聚合维度）
        for d in config.get('dimensions', []):
            dim_id = d.get('id') if isinstance(d, dict) else d
            if dim_id and dim_id not in seen_ids:
                seen_ids.add(dim_id)
                result.append(d)
        return result

    @staticmethod
    def _audios_changed(old_config: dict, new_config: dict) -> bool:
        """比较两个 config 中的音频配置是否发生变化"""
        old_audios = TestCaseController._collect_audios(old_config)
        new_audios = TestCaseController._collect_audios(new_config)
        # 统一转为字符串再排序，避免 audio_id 为 int/str 混合类型时
        # 触发 "'<' not supported between instances of 'str' and 'int'"
        old_ids = sorted([str(a.get('audio_id')) for a in old_audios if isinstance(a, dict) and a.get('audio_id')])
        new_ids = sorted([str(a.get('audio_id')) for a in new_audios if isinstance(a, dict) and a.get('audio_id')])
        return old_ids != new_ids

    @staticmethod
    def _get_algorithm_params_dict_for_executor(config: dict) -> dict:
        """从 rounds[0].algorithmParams 读取（兼容旧数据）

        新数据：config.rounds[] 不含 algorithmParams，返回空 dict。
        调用方应从独立列读取（见 _get_algorithm_params_dict_for_columns）。
        """
        if not config:
            return {}
        rounds = config.get('rounds', [])
        if rounds:
            first_round = rounds[0] if rounds else {}
            if isinstance(first_round, dict):
                return first_round.get('algorithmParams', {}) or {}
        return {}

    # 公共方法：刷新测试用例的ASR和翻译参考文本
    @staticmethod
    def refresh_reference_texts(test_case):
        """
        刷新测试用例的参考参数
        根据算法类型和测试用例配置，自动生成并更新config中的参考参数
        使用 ReferenceParamsGenerator 组件生成不同算法类型的参考字段
        """
        ReferenceParamsGenerator.apply_to_config(test_case)
    
    # 获取所有测试用例，支持搜索、标签过滤和分组过滤
    @staticmethod
    def get_all():
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        keyword = request.args.get('keyword')
        tag_name = request.args.get('tag')
        group_id = request.args.get('group_id')
        test_type = request.args.get('type')
        algorithm_type = request.args.get('algorithm_type')
        dimension_id = request.args.get('dimension_id', type=int)
        view = request.args.get('view')
        include_deleted_raw = request.args.get('include_deleted', 'false')
        include_deleted = str(include_deleted_raw).lower() in ('true', '1', 'yes')

        # ===== 标签视图：按标签聚合返回 =====
        if view == 'tag':
            return TestCaseController._get_tag_view(
                page=page, per_page=per_page, keyword=keyword,
                test_type=test_type, algorithm_type=algorithm_type,
                include_deleted=include_deleted, dimension_id=dimension_id,
            )

        query = TestCase.query.options(
            joinedload(TestCase.group),
            joinedload(TestCase.tags)
        ).order_by(TestCase.created_at.desc())
        # 软删过滤由 models.soft_delete 全局单一入口负责；include_deleted=true 时显式放开
        if include_deleted:
            query = query.execution_options(include_deleted=True)

        if keyword:
            query = query.filter(
                (TestCase.id.like(f'%{keyword}%')) |
                (TestCase.name.like(f'%{keyword}%')) |
                (TestCase.description.like(f'%{keyword}%'))
            )

        if tag_name:
            query = query.join(TestCase.tags).filter(Tag.name == tag_name)

        if group_id:
            query = query.filter(TestCase.group_id == group_id)

        if algorithm_type:
            query = query.filter(TestCase.algorithm_type == algorithm_type)

        # 按 test_type 列过滤（新双记录架构）
        if test_type and test_type in ['api', 'e2e']:
            query = query.filter(TestCase.test_type == test_type)

        # 按评估维度过滤：搜索 config JSON 中包含该 dimension_id 的用例
        if dimension_id:
            dim_str = str(dimension_id)
            # config 中 id 可能存为整数 "id": 3 或字符串 "id": "3"，两种都要匹配
            query = query.filter(
                TestCase.config.cast(db.Text).like(f'"id": {dim_str}') |
                TestCase.config.cast(db.Text).like(f'"id":{dim_str}') |
                TestCase.config.cast(db.Text).like(f'"id": "{dim_str}"') |
                TestCase.config.cast(db.Text).like(f'"id":"{dim_str}"')
            )

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        test_cases = pagination.items

        audio_ids = set()
        for tc in test_cases:
            config = tc.config or {}
            for audio_item in TestCaseController._collect_audios(config):
                aid = audio_item.get('audio_id')
                if aid is not None:
                    audio_ids.add(aid)

        audio_map = {}
        if audio_ids:
            audio_list = Audio.query.filter(Audio.id.in_(audio_ids)).all()
            audio_map = {a.id: a for a in audio_list}

        data = []
        for tc in test_cases:
            config = tc.config or {}
            # 直接使用 test_type 列，不再从音频配置推导
            tc_test_type = tc.test_type or 'api'

            # 计算时长：根据记录的 test_type 分配
            total_duration = 0.0
            for audio_item in TestCaseController._collect_audios(config):
                audio_id = audio_item.get('audio_id')
                if audio_id:
                    audio = audio_map.get(audio_id)
                    if audio and audio.duration:
                        total_duration += float(audio.duration)

            data.append(
                TestCaseListItem(
                    id=tc.id,
                    name=tc.name,
                    description=tc.description,
                    group_id=tc.group_id,
                    group_name=tc.group.name if tc.group else None,
                    type=tc_test_type,
                    tags=[tag.name for tag in tc.tags],
                    config=tc.config.copy() if tc.config else {},
                    algorithm_params=tc.algorithm_params,
                    reference_params=tc.reference_params,
                    algorithm_type=tc.algorithm_type,
                    created_at=tc.created_at.isoformat() if tc.created_at else None,
                    updated_at=tc.updated_at.isoformat() if tc.updated_at else None,
                    total_duration=round(total_duration, 2) if total_duration > 0 else None,
                )
            )

        return success_response(
            TestCaseListData(
                items=data,
                total=pagination.total,
                page=pagination.page,
                per_page=pagination.per_page,
                pages=pagination.pages,
            )
        )

    @staticmethod
    def _get_tag_view(page=1, per_page=10, keyword=None, test_type=None, algorithm_type=None, include_deleted=False, dimension_id=None):
        """标签视图：按标签聚合用例，分页返回标签维度。

        返回结构：
        {
            "items": [
                { "tag": "男声", "testCases": [TestCaseListItem, ...] },
                ...
            ],
            "total": <标签总数>,
            "page": 1,
            "per_page": 20,
            "pages": <总页数>
        }
        """
        # 1. 分页查询标签（按名称排序）
        tag_query = Tag.query.order_by(Tag.name)
        tag_pagination = tag_query.paginate(page=page, per_page=per_page, error_out=False)
        page_tags = tag_pagination.items

        items = []
        if not page_tags:
            return success_response({
                "items": [],
                "total": tag_pagination.total,
                "page": tag_pagination.page,
                "per_page": tag_pagination.per_page,
                "pages": tag_pagination.pages,
            })

        # 2. 一次性查询所有分页标签关联的用例（避免 N+1）
        tag_ids = [t.id for t in page_tags]
        tc_query = TestCase.query.options(
            joinedload(TestCase.group),
            joinedload(TestCase.tags),
        ).join(TestCase.tags).filter(Tag.id.in_(tag_ids))

        # 软删过滤由 models.soft_delete 全局单一入口负责；include_deleted=true 时显式放开
        if include_deleted:
            tc_query = tc_query.execution_options(include_deleted=True)
        if keyword:
            tc_query = tc_query.filter(
                (TestCase.id.like(f'%{keyword}%')) |
                (TestCase.name.like(f'%{keyword}%')) |
                (TestCase.description.like(f'%{keyword}%'))
            )
        if test_type and test_type in ['api', 'e2e']:
            tc_query = tc_query.filter(TestCase.test_type == test_type)
        if algorithm_type:
            tc_query = tc_query.filter(TestCase.algorithm_type == algorithm_type)

        # 按评估维度过滤
        if dimension_id:
            dim_str = str(dimension_id)
            tc_query = tc_query.filter(
                TestCase.config.cast(db.Text).like(f'"id": {dim_str}') |
                TestCase.config.cast(db.Text).like(f'"id":{dim_str}') |
                TestCase.config.cast(db.Text).like(f'"id": "{dim_str}"') |
                TestCase.config.cast(db.Text).like(f'"id":"{dim_str}"')
            )

        test_cases = tc_query.all()

        # 3. 收集音频 ID，批量查询音频时长（避免逐条查询）
        audio_ids = set()
        for tc in test_cases:
            config = tc.config or {}
            for audio_item in TestCaseController._collect_audios(config):
                aid = audio_item.get('audio_id')
                if aid is not None:
                    audio_ids.add(aid)

        audio_map = {}
        if audio_ids:
            audio_list = Audio.query.filter(Audio.id.in_(audio_ids)).all()
            audio_map = {a.id: a for a in audio_list}

        # 4. 按标签分组聚合用例
        cases_by_tag = {t.id: [] for t in page_tags}
        for tc in test_cases:
            for t in tc.tags:
                if t.id in cases_by_tag:
                    cases_by_tag[t.id].append(tc)

        for tag in page_tags:
            case_list = []
            for tc in cases_by_tag.get(tag.id, []):
                config = tc.config or {}
                total_duration = 0.0
                for audio_item in TestCaseController._collect_audios(config):
                    audio_id = audio_item.get('audio_id')
                    if audio_id:
                        audio = audio_map.get(audio_id)
                        if audio and audio.duration:
                            total_duration += float(audio.duration)

                case_list.append({
                    "id": tc.id,
                    "name": tc.name,
                    "description": tc.description,
                    "groupId": tc.group_id,
                    "groupName": tc.group.name if tc.group else None,
                    "type": tc.test_type or 'api',
                    "tags": [t.name for t in tc.tags],
                    "config": tc.config.copy() if tc.config else {},
                    "algorithmParams": tc.algorithm_params,
                    "referenceParams": tc.reference_params,
                    "algorithmType": tc.algorithm_type,
                    "createdAt": tc.created_at.isoformat() if tc.created_at else None,
                    "updatedAt": tc.updated_at.isoformat() if tc.updated_at else None,
                    "totalDuration": round(total_duration, 2) if total_duration > 0 else None,
                })

            items.append({
                "tag": tag.name,
                "testCases": case_list,
            })

        return success_response({
            "items": items,
            "total": tag_pagination.total,
            "page": tag_pagination.page,
            "per_page": tag_pagination.per_page,
            "pages": tag_pagination.pages,
        })

    # 获取单个测试用例详细信息
    @staticmethod
    def get_one(tc_id):
        tc = TestCase.query.filter_by(id=tc_id, deleted=False).first()
        if not tc:
            return error_response("未找到测试用例", 404)

        config = tc.config or {}
        tc_test_type = tc.test_type or 'api'
        
        # 从config中提取音频配置
        audios = []
        for i, audio_item in enumerate(TestCaseController._collect_audios(config)):
            audio = db.session.get(Audio, audio_item.get('audio_id'))
            audios.append(
                TestCaseAudioConfigItem(
                    id=i,
                    audio_id=audio_item.get('audio_id'),
                    audio_name=audio.name if audio else None,
                    test_type=tc_test_type,
                    spl=audio_item.get('spl'),
                    playback_device_id=TestCaseController._normalize_optional_int(audio_item.get('playback_device_id')),
                    play_order=audio_item.get('play_order'),
                )
            )

        # 从config中提取评测维度配置（兼容新旧格式）
        dimensions = []
        dim_config = TestCaseController._collect_dimensions(config)
        dimension_ids = []

        for item in dim_config:
            if isinstance(item, dict):
                dim_id = item.get('id')
                if dim_id:
                    dimension_ids.append(dim_id)
            else:
                dimension_ids.append(item)

        # 去重
        unique_dimension_ids = list(set(dimension_ids))
        for dim_id in unique_dimension_ids:
            dim = db.session.get(Dimension, dim_id)
            if dim:
                dimensions.append(TestCaseDimensionBrief(id=dim.id, name=dim.name, type=dim.type))

        # 计算时长（兼容新旧格式）
        total_duration = 0.0
        for audio_item in TestCaseController._collect_audios(config):
            audio_id = audio_item.get('audio_id')
            if audio_id:
                audio = db.session.get(Audio, audio_id)
                if audio and audio.duration:
                    total_duration += float(audio.duration)

        # Debug logging
        import json as json_debug
        log_not_emit('DEBUG', 'testcase_controller', f'get_one: tc.id={tc.id}, config type={type(config)}, is None={config is None}, is empty={config == {}}', category='testcase')
        if isinstance(config, dict):
            log_not_emit('DEBUG', 'testcase_controller', f'get_one: config keys={list(config.keys())}, JSON={json_debug.dumps(config, ensure_ascii=False)[:300]}', category='testcase')

        # Create TestCaseDetailData and check config
        detail_data = TestCaseDetailData(
            id=tc.id,
            name=tc.name,
            description=tc.description,
            group_id=tc.group_id,
            group_name=tc.group.name if tc.group else None,
            group={"id": tc.group.id, "name": tc.group.name} if tc.group else None,
            type=tc_test_type,
            config=config,
            algorithm_params=getattr(tc, 'algorithm_params', None),
            reference_params=getattr(tc, 'reference_params', None),
            algorithm_type=tc.algorithm_type,
            tags=[tag.name for tag in tc.tags],
            audios=audios,
            dimensions=dimensions,
            created_at=tc.created_at.isoformat() if tc.created_at else None,
            updated_at=tc.updated_at.isoformat() if tc.updated_at else None,
            total_duration=round(total_duration, 2) if total_duration > 0 else None,
        )
        
        dumped = detail_data.model_dump(by_alias=True)
        log_not_emit('DEBUG', 'testcase_controller', f'get_one: dumped config={json_debug.dumps(dumped.get("config"), ensure_ascii=False)[:300]}', category='testcase')

        return success_response(detail_data)

    # 创建测试用例
    @staticmethod
    def create():
        raw_data = request.get_json()
        
        try:
            data = TestCaseCreateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}")
        
        group_id = data.group_id
        
        if group_id is None and data.group:
            group_name = data.group
            group = TestCaseGroup.query.filter_by(name=group_name, deleted=False).first()
            if group:
                group_id = group.id
            else:
                group_id = str(uuid.uuid4())
                new_group = TestCaseGroup(
                    id=group_id,
                    name=group_name,
                    description=f"自动创建的分组: {group_name}"
                )
                db.session.add(new_group)
        
        if not raw_data or not data.name or group_id is None:
            return error_response("缺少必要字段: name, group_id 或 group")

        # 获取 test_type（新双记录架构）
        test_type_val = data.test_type or 'api'
        if test_type_val not in ['api', 'e2e']:
            return error_response(f"test_type 无效: {test_type_val}，必须为 api 或 e2e")

        # 数据验证: 校验 config 中的结构
        config = data.config or {}
        
        # 统一为 rounds 格式
        if TestCaseController._has_rounds(config):
            merged_config = config.copy()
            # 剥离 rounds 里的 algorithmParams 和 referenceParamsPath（新设计存独立列）
            for round_item in merged_config.get('rounds', []):
                if isinstance(round_item, dict):
                    round_item.pop('algorithmParams', None)
                    round_item.pop('algorithm_params', None)
                    round_item.pop('referenceParamsPath', None)
                    round_item.pop('reference_params_path', None)
            # 验证各轮音频配置
            if test_type_val == 'e2e':
                for rn, round_item in enumerate(merged_config.get('rounds', []), 1):
                    for ai, audio_item in enumerate(round_item.get('audios', []), 1):
                        if not audio_item.get('playback_device_id'):
                            return error_response(f"第{rn}轮第{ai}个音频配置为 E2E 类型用例，必须指定 playback_device_id")
        else:
            # 前端传入平面数据，构建配置后转换为 rounds
            merged_config = config.copy() if config else {}
            
            if 'background_noise' not in merged_config:
                bg_noise_audio_id = data.background_noise_id
                bg_noise_spl = data.background_noise_spl
                bg_noise_device_ids = getattr(data, 'background_noise_device_ids', None)
                if bg_noise_audio_id is not None:
                    merged_config['background_noise'] = {
                        'audio_id': bg_noise_audio_id,
                        'spl': bg_noise_spl
                    }
                    if bg_noise_device_ids:
                        merged_config['background_noise']['device_ids'] = bg_noise_device_ids
            
            audios_data = data.audios
            if audios_data:
                for i, audio_item in enumerate(audios_data):
                    aid = audio_item.audio_id
                    spl = audio_item.spl
                    porder = audio_item.play_order
                    pdid = TestCaseController._normalize_optional_int(audio_item.playback_device_id)
                    if aid is None or spl is None or porder is None:
                        return error_response(f"第 {i+1} 个音频配置缺少必要字段: audio_id, spl, play_order")
                    if test_type_val == 'e2e' and not pdid:
                        return error_response(f"第 {i+1} 个音频配置为 E2E 类型用例，必须指定 playback_device_id")
                standard_audios = []
                for audio_item in audios_data:
                    standard_audios.append({
                        'audio_id': audio_item.audio_id,
                        'spl': audio_item.spl,
                        'playback_device_id': TestCaseController._normalize_optional_int(audio_item.playback_device_id),
                        'play_order': audio_item.play_order
                    })
                merged_config['audios'] = standard_audios
            
            dimensions_data = data.dimensions
            if dimensions_data:
                merged_config['dimensions'] = dimensions_data
            
            # 转换为 rounds 格式
            merged_config = TestCaseController._convert_flat_config_to_rounds(merged_config)
        
        # algorithm_params 存入独立列（按轮分组格式 [{round_number, params:[{field_code, field_value}]}]）
        algo_params_col = data.get_algorithm_params_dict()
        # 兼容旧平面格式 [{field_code, field_value}]：包装为 round_number=1 的单轮
        if algo_params_col:
            first = algo_params_col[0] if isinstance(algo_params_col[0], dict) else {}
            if 'round_number' not in first and 'params' not in first:
                algo_params_col = [{'round_number': 1, 'params': algo_params_col}]

        algorithm_type = data.algorithm_type

        try:
            tc_id = str(uuid.uuid4())
            new_tc = TestCase(
                id=tc_id,
                name=data.name,
                description=data.description,
                group_id=group_id,
                config=merged_config,
                algorithm_params=algo_params_col,
                algorithm_type=algorithm_type,
                test_type=test_type_val,
            )
            db.session.add(new_tc)

            # 处理标签关联（从 data.tags 获取，而非从 config 获取）
            tags_data = data.tags
            if tags_data:
                for tag_name in tags_data:
                    tag = Tag.query.filter_by(name=tag_name).first()
                    if not tag:
                        tag = Tag(name=tag_name)
                        db.session.add(tag)
                    new_tc.tags.append(tag)

            # 刷新用例参考文本（新格式会写入文件并设置 referenceParamsPath）
            TestCaseController.refresh_reference_texts(new_tc)

            db.session.commit()

            from backend.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()

            return success_response(StringIdData(id=tc_id), "测试用例创建成功", 0, 201)
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 更新测试用例信息
    @staticmethod
    def update(tc_id):
        raw_data = request.get_json()
        
        try:
            data = TestCaseUpdateSchema.model_validate(request.get_json())
        except Exception as e:
            return error_response(f"请求数据验证失败: {str(e)}")
        
        if data.id and data.id != tc_id:
            return error_response("请求URL中的id与请求体中的id不一致")
            
        # 先检查用例是否存在
        tc = TestCase.query.filter_by(id=tc_id, deleted=False).first()
        if not tc:
            return error_response("未找到测试用例", 404)

        current_config = tc.config or {}
        tc_test_type = tc.test_type or 'api'  # 使用记录的 test_type
        
        try:
            # 先处理分组信息，确保使用正确的分组ID进行后续操作
            # 1. 获取分组ID
            group_id = data.group_id
            
            # 2. 如果没有group_id，但有group名称，根据名称查找或创建分组
            if group_id is None and data.group:
                group_name = data.group
                group = TestCaseGroup.query.filter_by(name=group_name, deleted=False).first()
                if group:
                    group_id = group.id
                else:
                    # 创建新分组
                    group_id = str(uuid.uuid4())
                    new_group = TestCaseGroup(
                        id=group_id,
                        name=group_name,
                        description=f"自动创建的分组: {group_name}"
                    )
                    db.session.add(new_group)
            
            # 3. 更新测试用例的分组ID
            if group_id is not None:
                tc.group_id = group_id
            
            # 4. 处理测试用例名称
            if data.name is not None:
                tc.name = data.name
            
            if data.description is not None:
                tc.description = data.description
            
            # 判断是否为 rounds-as-top-level 格式（当前或传入）
            incoming_config = data.config if data.config is not None else {}
            
            if data.config is not None:
                if TestCaseController._has_rounds(data.config):
                    merged_config = data.config.copy()
                    # 剥离 rounds 里的 algorithmParams 和 referenceParamsPath（新设计存独立列）
                    # 同时剥离 interferers（干扰人数据存于 algorithm_params 独立列，避免冗余）
                    for round_item in merged_config.get('rounds', []):
                        if isinstance(round_item, dict):
                            round_item.pop('algorithmParams', None)
                            round_item.pop('algorithm_params', None)
                            round_item.pop('referenceParamsPath', None)
                            round_item.pop('reference_params_path', None)
                            round_item.pop('interferers', None)
                else:
                    # 传入平面格式，转换为 rounds
                    merged_config = TestCaseController._convert_flat_config_to_rounds(data.config.copy())
            elif TestCaseController._has_rounds(current_config):
                merged_config = current_config.copy()
                # 剥离 rounds 里的 algorithmParams 和 referenceParamsPath（新设计存独立列）
                # 同时剥离 interferers（干扰人数据存于 algorithm_params 独立列，避免冗余）
                for round_item in merged_config.get('rounds', []):
                    if isinstance(round_item, dict):
                        round_item.pop('algorithmParams', None)
                        round_item.pop('algorithm_params', None)
                        round_item.pop('referenceParamsPath', None)
                        round_item.pop('reference_params_path', None)
                        round_item.pop('interferers', None)
            else:
                # 当前配置也是平面格式（不应发生），转换后继续
                merged_config = TestCaseController._convert_flat_config_to_rounds(current_config.copy())
            
            # algorithm_params 存入独立列（按轮分组格式 [{round_number, params:[{field_code, field_value}]}]）
            algo_params_col = data.get_algorithm_params_dict()
            # 兼容旧平面格式 [{field_code, field_value}]：包装为 round_number=1 的单轮
            if algo_params_col:
                first = algo_params_col[0] if isinstance(algo_params_col[0], dict) else {}
                if 'round_number' not in first and 'params' not in first:
                    algo_params_col = [{'round_number': 1, 'params': algo_params_col}]
            if algo_params_col is not None:
                tc.algorithm_params = algo_params_col
            
            # 处理前端传入的平面字段（更新到 rounds[0]）
            bg_noise_audio_id = data.background_noise_id
            bg_noise_spl = data.background_noise_spl
            bg_noise_device_ids = getattr(data, 'background_noise_device_ids', None)
            if bg_noise_audio_id is not None:
                first_round = merged_config.get('rounds', [{}])[0]
                if isinstance(first_round, dict):
                    noise_cfg = {'audio_id': bg_noise_audio_id, 'spl': bg_noise_spl}
                    if bg_noise_device_ids:
                        noise_cfg['device_ids'] = bg_noise_device_ids
                    first_round['backgroundNoise'] = noise_cfg
            
            audios_data = data.audios
            if audios_data is not None:
                for i, audio_item in enumerate(audios_data):
                    aid = audio_item.audio_id
                    spl = audio_item.spl
                    porder = audio_item.play_order
                    pdid = TestCaseController._normalize_optional_int(audio_item.playback_device_id)
                    if aid is None or spl is None or porder is None:
                        return error_response(f"第 {i+1} 个音频配置缺少必要字段: audio_id, spl, play_order")
                    if tc_test_type == 'e2e' and not pdid:
                        return error_response(f"第 {i+1} 个音频配置为 E2E 类型用例，必须指定 playback_device_id")
                standard_audios = []
                for audio_item in audios_data:
                    standard_audios.append({
                        'audio_id': audio_item.audio_id,
                        'spl': audio_item.spl,
                        'playback_device_id': TestCaseController._normalize_optional_int(audio_item.playback_device_id),
                        'play_order': audio_item.play_order
                    })
                # 写入 rounds[0].audios
                first_round = merged_config.get('rounds', [{}])[0]
                if isinstance(first_round, dict):
                    first_round['audios'] = standard_audios
            
            dimensions_data = data.dimensions
            if dimensions_data is not None:
                first_round = merged_config.get('rounds', [{}])[0]
                if isinstance(first_round, dict):
                    if 'evaluation' not in first_round:
                        first_round['evaluation'] = {}
                    first_round['evaluation']['dimensions'] = dimensions_data
            
            # 更新标签
            tags_data = data.tags
            if tags_data is not None:
                tc.tags = []
                for tag_name in tags_data:
                    tag = Tag.query.filter_by(name=tag_name).first()
                    if not tag:
                        tag = Tag(name=tag_name)
                        db.session.add(tag)
                    tc.tags.append(tag)
            
            tc.config = merged_config
            
            algorithm_type = data.algorithm_type
            need_refresh_reference = False
            
            if TestCaseController._audios_changed(current_config, merged_config):
                need_refresh_reference = True
            
            if algorithm_type is not None and algorithm_type != tc.algorithm_type:
                need_refresh_reference = True
                tc.algorithm_type = algorithm_type
            
            if algo_params_col:
                # 优先从独立列读旧参数，兼容旧数据从 config 读
                old_params = TestCaseController._get_algo_params_list_from_columns(tc.algorithm_params, 1)
                if not old_params:
                    old_params = TestCaseController._get_algo_params_list_from_config(current_config)
                # 新参数从按轮分组格式提取 round_number=1
                new_params = TestCaseController._get_algo_params_list_from_columns(algo_params_col, 1)
                if TestCaseController._has_overlap_param_changed(old_params, new_params):
                    need_refresh_reference = True
            
            tc.updated_at = now_cst()
            
            if need_refresh_reference:
                TestCaseController.refresh_reference_texts(tc)
            
            db.session.commit()

            from backend.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()

            return success_response(None, "测试用例更新成功")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 删除测试用例（逻辑删除）
    @staticmethod
    def delete(tc_id):
        tc = TestCase.query.filter_by(id=tc_id, deleted=False).first()
        if not tc:
            return error_response("未找到测试用例", 404)

        try:
            tc.deleted = True
            tc.updated_at = now_cst()
            db.session.commit()

            from backend.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()

            return success_response(None, "测试用例已删除")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 复制测试用例
    @staticmethod
    def copy(tc_id):
        tc = TestCase.query.filter_by(id=tc_id, deleted=False).first()
        if not tc:
            return error_response("未找到原始测试用例", 404)

        try:
            import copy as _copy
            new_id = str(uuid.uuid4())
            new_tc = TestCase(
                id=new_id,
                name=f"{tc.name}_copy",
                description=tc.description,
                group_id=tc.group_id,
                config=tc.config.copy() if tc.config else {},
                algorithm_params=_copy.deepcopy(tc.algorithm_params) if tc.algorithm_params else None,
                reference_params=_copy.deepcopy(tc.reference_params) if tc.reference_params else None,
                algorithm_type=tc.algorithm_type,
                test_type=tc.test_type or 'api',
            )
            db.session.add(new_tc)

            # 复制标签关联
            for tag in tc.tags:
                new_tc.tags.append(tag)

            # 刷新ASR和翻译参考文本
            TestCaseController.refresh_reference_texts(new_tc)

            db.session.commit()
            return success_response(StringIdData(id=new_id), "测试用例复制成功", 0, 201)
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 预览测试用例（放音验证）
    @staticmethod
    def preview(tc_id):
        """
        预览测试用例：支持前端播放和后端播放两种模式
        - frontend: 返回音频流URL，由前端浏览器播放
        - backend: 通过后端扬声器播放
        """
        tc = TestCase.query.filter_by(id=tc_id, deleted=False).first()
        if not tc:
            return error_response("未找到测试用例", 404)
        
        req_data = TestCasePreviewRequest.model_validate(request.get_json() or {})
        
        offset = req_data.offset
        preview_type = req_data.preview_type
        playback_mode = req_data.playback_mode or 'backend'
        
        config = tc.config or {}
        
        # 注入 algorithm_params 到 config
        # 优先从独立列读，兼容旧数据从 config 读
        algorithm_params = TestCaseController._get_algorithm_params_dict_for_columns(tc.algorithm_params, 1)
        if not algorithm_params:
            algorithm_params = TestCaseController._get_algorithm_params_dict_for_executor(config)
        if algorithm_params:
            config = config.copy() if config else {}
            config['algorithm_params'] = algorithm_params
        
        # 从 rounds 获取音频
        audios_config = TestCaseController._collect_audios(config)
        
        # 1. 检查音频配置
        if not audios_config:
            return error_response("用例未配置任何音频资源，无法预览")

        # 新双记录架构：记录已是单类型，直接使用所有音频
        # preview_type 保留用于向后兼容，但优先使用记录的 test_type
        preview_audios = audios_config
        
        if not preview_audios:
            return error_response("用例未配置有效的音频资源")

        # 获取第一个有效音频的ID
        first_audio_id = None
        for audio_config in preview_audios:
            audio_id = audio_config.get('audio_id') or audio_config.get('audioId')
            if audio_id:
                first_audio_id = audio_id
                break
        
        if not first_audio_id:
            return error_response("用例未配置有效的音频ID")

        # 计算总时长
        from backend.utils.algorithm.case_parameter_extractor import CaseParameterExtractor
        overlap_time = CaseParameterExtractor.get_overlap_time(config) if config else 0
        overlap_rate = CaseParameterExtractor.get_overlap_rate(config) if config else 0
        
        total_duration = 0
        try:
            from backend.models.models import Audio
            audio_record = Audio.query.filter_by(id=first_audio_id, deleted=False).first()
            if audio_record and audio_record.duration:
                total_duration = audio_record.duration
        except:
            pass

        # 前端播放模式：返回音频流URL
        if playback_mode == 'frontend':
            from flask import url_for
            audio_stream_url = f"/audios/{first_audio_id}/stream"
            
            return success_response(
                TestCasePreviewData(
                    test_case_id=tc_id,
                    preview_task_id=None,
                    status="frontend_preview_ready",
                    message="前端播放模式，返回音频流URL",
                    duration=total_duration,
                    playback_mode='frontend',
                    audio_id=first_audio_id,
                    audio_stream_url=audio_stream_url,
                )
            )
        
        # 后端播放模式：检查E2E任务并执行播放
        if has_running_e2e_tasks():
            return error_response("当前有待执行的E2E测试任务，不允许使用后端扬声器播放", 403)

        from backend.services.audio.audio_engine import audio_service
        from backend.services.audio.spl_service import spl_service
        from backend.models.models import PlaybackDevice, Audio
        
        preview_task_id = f"PREVIEW_{tc_id}"
        
        # 停止之前的预览
        audio_service.stop_task_audio_by_pattern("PREVIEW_")
        
        # 清除设备缓存，强制重新扫描
        audio_service._device_cache = None
        
        import time
        time.sleep(0.2)

        # 初始化预览停止标志
        global preview_stop_flags
        if 'preview_stop_flags' not in globals():
            preview_stop_flags = {}
        preview_stop_flags[tc_id] = False

        try:
            from backend.services.audio.playback_orchestrator import playback_orchestrator

            preview_result = playback_orchestrator.preview(
                audio_configs=preview_audios,
                case_config=config,
                task_id=preview_task_id,
                offset=offset,
                overlap_rate=overlap_rate,
                overlap_time=overlap_time,
            )
            if not preview_result:
                return error_response("用例未配置有效的干声音频")

            total_duration = preview_result.get('total_duration', 0)
            TestCaseController._log(
                'info',
                f"Previewing test case {tc_id}: offset={offset}, duration={total_duration:.2f}s",
                test_case_id=tc_id,
                category='preview',
            )

            return success_response(
                TestCasePreviewData(
                    test_case_id=tc_id,
                    preview_task_id=preview_task_id,
                    status="preview_started",
                    message="已启动用例预览放音",
                    duration=total_duration,
                    playback_mode='backend',
                    audio_id=first_audio_id,
                    audio_stream_url=None,
                )
            )
        except Exception as e:
            return error_response(f"预览失败: {str(e)}")

    # 停止预览测试用例
    @staticmethod
    def stop_preview(tc_id):
        """
        停止预览测试用例：向音频引擎发送停止信号
        """
        from backend.services.audio.audio_engine import audio_service
        preview_task_id = f"PREVIEW_{tc_id}"
        
        # 设置停止标志，通知播放线程停止
        global preview_stop_flags
        if 'preview_stop_flags' in globals():
            preview_stop_flags[tc_id] = True
        
        # 停止音频播放 - 停止所有 PREVIEW_ 开头的任务
        audio_service.stop_task_audio_by_pattern("PREVIEW_")
        
        return success_response(TestCaseStopPreviewData(test_case_id=tc_id, status="preview_stopped", message="预览已停止"))
    # 批量操作
    @staticmethod
    def batch_action():
        """批量操作入口：验证请求并分发到对应处理函数"""
        req_data = TestCaseBatchActionRequest.model_validate(request.get_json())
        action = req_data.action

        # action → handler 映射
        handlers = {
            'delete': TestCaseController._batch_delete,
            'move_to_group': TestCaseController._batch_move_to_group,
            'copy_to_group': TestCaseController._batch_copy_to_group,
            'copy': TestCaseController._batch_copy,
            'copy_by_group': TestCaseController._batch_copy_by_group,
            'copy_by_tag': TestCaseController._batch_copy_by_tag,
            'update_algorithm_params': TestCaseController._batch_update_algorithm_params,
            'update_playback_devices': TestCaseController._batch_update_playback_devices,
            'update_spl': TestCaseController._batch_update_spl,
            'update_dimensions': TestCaseController._batch_update_dimensions,
            'update_noise': TestCaseController._batch_update_noise,
            'auto_generate_name': TestCaseController._batch_auto_generate_name,
            'add_tags': TestCaseController._batch_add_tags,
            'remove_tags': TestCaseController._batch_remove_tags,
            'rename_tag': TestCaseController._batch_rename_tag,
            'refresh_reference': TestCaseController._batch_refresh_reference,
        }

        handler = handlers.get(action)
        if not handler:
            return error_response(f"不支持的操作类型: {action}")

        try:
            result = handler(req_data)
            # handler 返回 dict 表示提前返回（如异步任务提交）
            if isinstance(result, dict):
                return result
            # handler 返回 tuple (response_obj, skip_commit) 表示提前返回错误
            if isinstance(result, tuple) and len(result) == 2 and hasattr(result[0], 'status_code'):
                return result[0]
            # handler 返回 response 对象直接返回
            if hasattr(result, 'status_code'):
                return result
            # 否则 result 是 message 字符串
            message = result

            db.session.commit()
            from backend.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()
            return success_response(None, message)
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    @staticmethod
    def _batch_delete(req_data):
        """批量删除用例"""
        ids = req_data.ids
        bulk_soft_delete(TestCase.query.filter(TestCase.id.in_(ids)))
        return f"已成功批量删除 {len(ids)} 个用例"

    @staticmethod
    def _find_move_name_conflicts(ids, target_group_id):
        """列出批量移动后会与目标分组内活跃用例重名的用例名（去重、保序）

        冲突有两个来源：
        1. 目标分组**已有**同名活跃用例（排除本次要移动的行自身——用例本来就在目标分组
           时移动是幂等的，不算冲突）；
        2. 本次**一起移入**的用例之间互相同名（若这些同名行本来就都在目标分组，则是既存
           状态，移动不新增，不计冲突）。

        :param ids: 待移动的用例 ID 列表
        :param target_group_id: 目标分组 ID
        :return: 冲突的用例名列表；无冲突时返回空列表
        """
        moving = TestCase.query.filter(
            TestCase.id.in_(ids), TestCase.deleted == False  # noqa: E712
        ).all()
        if not moving:
            return []

        conflicts = []
        moving_ids = {tc.id for tc in moving}

        # 来源 2：一起移入的行互相同名
        by_name = {}
        for tc in moving:
            by_name.setdefault(tc.name, []).append(tc)
        for name, same_name_cases in by_name.items():
            if len(same_name_cases) > 1 and any(
                tc.group_id != target_group_id for tc in same_name_cases
            ):
                conflicts.append(name)

        # 来源 1：目标分组已有同名活跃用例
        existing = TestCase.query.filter(
            TestCase.name.in_(list(by_name.keys())),
            TestCase.group_id == target_group_id,
            TestCase.deleted == False,  # noqa: E712
        ).all()
        for tc in existing:
            if tc.id not in moving_ids and tc.name not in conflicts:
                conflicts.append(tc.name)

        return conflicts

    @staticmethod
    def _batch_move_to_group(req_data):
        """批量移动到分组

        移动会把用例带进目标分组；目标分组若已有同名活跃用例，就会产生「**同组内**同名两条
        活跃」，恰好击穿用例创建路径（`audio_controller.py` 同名去重键 `(name, group_id)`）
        想维护的那条不变量——按名字/编号匹配会命中配置不同的行。故移动前先做冲突校验，
        有冲突**一律拦下**并给出可见提示（这是缺陷，不是产品能力）。

        注意与 `_batch_copy_to_group` 的区别：复制到分组产生的**跨组**同名是**有意保留**的
        产品能力，不在此拦；这里拦的只是「同组内」同名。
        """
        ids = req_data.ids
        target_group_id = req_data.target_group_id
        if not target_group_id:
            return error_response("移动操作需要 'target_group_id'")

        conflicts = TestCaseController._find_move_name_conflicts(ids, target_group_id)
        if conflicts:
            detail = '、'.join(f'「{name}」' for name in conflicts)
            return error_response(
                f'目标分组已存在同名活跃用例 {detail}，移动会产生同组同名用例，已取消本次移动；'
                f'请先重命名，或改用「复制到分组」'
            )

        TestCase.query.filter(TestCase.id.in_(ids)).update({"group_id": target_group_id}, synchronize_session=False)
        return f"已成功将 {len(ids)} 个用例移动至目标分组"

    @staticmethod
    def _batch_copy_to_group(req_data):
        """复制到指定分组"""
        ids = req_data.ids
        target_group_id = req_data.target_group_id
        if not target_group_id:
            return error_response("复制到分组操作需要 'target_group_id'")
        target_group = TestCaseGroup.query.filter_by(id=target_group_id, deleted=False).first()
        if not target_group:
            return error_response(f"未找到目标分组: {target_group_id}")
        copied_count = 0
        for tc_id in ids:
            tc = TestCase.query.filter_by(id=tc_id, deleted=False).first()
            if tc:
                new_id = str(uuid.uuid4())
                new_tc = TestCase(
                    id=new_id,
                    name=tc.name,
                    description=tc.description,
                    group_id=target_group_id,
                    config=tc.config.copy() if tc.config else {},
                    algorithm_type=tc.algorithm_type,
                    test_type=tc.test_type or 'api',
                )
                db.session.add(new_tc)
                for tag in tc.tags:
                    new_tc.tags.append(tag)
                TestCaseController.refresh_reference_texts(new_tc)
                copied_count += 1
        return f"已成功复制 {copied_count} 个用例到分组 '{target_group.name}'"

    @staticmethod
    def _batch_copy(req_data):
        """批量复制用例"""
        ids = req_data.ids
        copied_count = 0
        for tc_id in ids:
            tc = TestCase.query.filter_by(id=tc_id, deleted=False).first()
            if tc:
                new_id = str(uuid.uuid4())
                new_tc = TestCase(
                    id=new_id,
                    name=f"{tc.name}_copy",
                    description=tc.description,
                    group_id=tc.group_id,
                    config=tc.config.copy() if tc.config else {},
                    algorithm_type=tc.algorithm_type,
                    test_type=tc.test_type or 'api',
                )
                db.session.add(new_tc)
                for tag in tc.tags:
                    new_tc.tags.append(tag)
                TestCaseController.refresh_reference_texts(new_tc)
                copied_count += 1
        return f"已成功批量复制 {copied_count} 个用例"

    @staticmethod
    def _batch_copy_by_group(req_data):
        """按分组复制用例"""
        group_name = req_data.group_name
        if not group_name:
            return error_response("复制分组操作需要 'group_name'")
        source_group = TestCaseGroup.query.filter_by(name=group_name, deleted=False).first()
        if not source_group:
            return error_response(f"未找到分组: {group_name}")

        new_group_name = f"{group_name}_copy"
        existing_group = TestCaseGroup.query.filter_by(name=new_group_name, deleted=False).first()
        if existing_group:
            new_group = existing_group
        else:
            new_group = TestCaseGroup(
                id=str(uuid.uuid4()),
                name=new_group_name,
                description=source_group.description
            )
            db.session.add(new_group)

        test_cases = TestCase.query.filter_by(group_id=source_group.id, deleted=False).all()
        copied_count = 0
        for tc in test_cases:
            new_id = str(uuid.uuid4())
            new_tc = TestCase(
                id=new_id,
                name=tc.name,
                description=tc.description,
                group_id=new_group.id,
                config=tc.config.copy() if tc.config else {},
                algorithm_type=tc.algorithm_type,
                test_type=tc.test_type or 'api',
            )
            db.session.add(new_tc)
            for tag in tc.tags:
                new_tc.tags.append(tag)
            TestCaseController.refresh_reference_texts(new_tc)
            copied_count += 1
        return f"已成功复制分组 '{new_group_name}' 的 {copied_count} 个用例"

    @staticmethod
    def _batch_copy_by_tag(req_data):
        """按标签复制用例：将标签下所有用例复制，副本关联到新标签 tag_name_copy。
        若 copy_to_new_group=True，同时创建新分组 tag_name_copy 并将副本归入新分组。"""
        tag_name = req_data.tag_name
        if not tag_name:
            return error_response("复制标签操作需要 'tag_name'")
        tag = Tag.query.filter_by(name=tag_name).first()
        if not tag:
            return error_response(f"未找到标签: {tag_name}")

        # 创建新标签
        new_tag_name = f"{tag_name}_copy"
        new_tag = Tag.query.filter_by(name=new_tag_name).first()
        if not new_tag:
            new_tag = Tag(id=str(uuid.uuid4()), name=new_tag_name)
            db.session.add(new_tag)

        # 按用户选择决定是否创建新分组
        new_group = None
        if req_data.copy_to_new_group:
            new_group_name = f"{tag_name}_copy"
            existing_group = TestCaseGroup.query.filter_by(name=new_group_name, deleted=False).first()
            if existing_group:
                new_group = existing_group
            else:
                new_group = TestCaseGroup(
                    id=str(uuid.uuid4()),
                    name=new_group_name,
                    description=f"从标签 '{tag_name}' 复制"
                )
                db.session.add(new_group)

        test_cases = [tc for tc in tag.test_cases if not tc.deleted]
        copied_count = 0
        for tc in test_cases:
            new_id = str(uuid.uuid4())
            new_tc = TestCase(
                id=new_id,
                name=tc.name,
                description=tc.description,
                group_id=new_group.id if new_group else tc.group_id,
                config=tc.config.copy() if tc.config else {},
                algorithm_type=tc.algorithm_type,
                test_type=tc.test_type or 'api',
            )
            db.session.add(new_tc)
            # 关联新标签
            new_tc.tags.append(new_tag)
            TestCaseController.refresh_reference_texts(new_tc)
            copied_count += 1
        return f"已成功复制标签 '{tag_name}' 的 {copied_count} 个用例"

    @staticmethod
    def _batch_update_algorithm_params(req_data):
        """批量更新用例专属参数"""
        ids = req_data.ids
        algorithm_params = req_data.algorithm_params
        if algorithm_params is None:
            return error_response("更新用例专属参数需要 'algorithm_params'")
        
        # 获取轮次范围
        round_mode = getattr(req_data, 'round_mode', None) or 'all'
        round_numbers = getattr(req_data, 'round_numbers', None) or []
        
        test_cases = TestCase.query.filter(TestCase.id.in_(ids), TestCase.deleted == False).all()
        updated_count = 0
        for tc in test_cases:
            tc_config = tc.config or {}
            ap_dict = {}
            if isinstance(algorithm_params, list):
                for item in algorithm_params:
                    if isinstance(item, dict):
                        code = item.get('field_code') or item.get('fieldCode', '')
                        value = item.get('field_value') or item.get('fieldValue', '')
                        if code:
                            ap_dict[code] = value
            elif isinstance(algorithm_params, dict):
                ap_dict = algorithm_params
            tc_config = tc_config.copy()
            
            new_params = [{'field_code': k, 'field_value': v} for k, v in ap_dict.items()]
            
            if round_mode == 'all':
                # 所有轮次统一设为同一组参数
                existing = tc.algorithm_params or []
                max_round = max([r.get('round_number', 1) for r in existing if isinstance(r, dict)] or [1])
                tc.algorithm_params = [
                    {'round_number': rn, 'params': new_params}
                    for rn in range(1, max_round + 1)
                ]
            else:
                # 只更新指定轮次，保留其他轮次原有参数
                existing = tc.algorithm_params or []
                updated_map = {rn: False for rn in round_numbers}
                for item in existing:
                    if not isinstance(item, dict):
                        continue
                    rn = item.get('round_number', 1)
                    if rn in round_numbers:
                        item['params'] = new_params
                        updated_map[rn] = True
                # 追加不存在的轮次
                for rn in round_numbers:
                    if not updated_map.get(rn):
                        existing.append({'round_number': rn, 'params': new_params})
                tc.algorithm_params = existing
            
            tc.config = tc_config
            tc.updated_at = now_cst()
            updated_count += 1
        return f"已成功更新 {updated_count} 个用例的专属参数"

    @staticmethod
    def _batch_update_playback_devices(req_data):
        """批量更新播放设备"""
        import sqlalchemy.orm.attributes
        ids = req_data.ids
        logger.info(f"[update_playback_devices] 开始处理, ids: {ids}, playback_devices: {req_data.playback_devices}")

        playback_devices = req_data.playback_devices
        if playback_devices is None:
            logger.error("[update_playback_devices] 缺少 playback_devices 参数")
            return error_response("更新播放设备需要 'playback_devices'")

        # 获取轮次范围和层级目标
        round_mode = getattr(req_data, 'round_mode', None) or 'all'
        round_numbers = getattr(req_data, 'round_numbers', None) or []
        targets = getattr(req_data, 'targets', None) or ['audio']
        
        device_id = playback_devices.get('deviceId') or playback_devices.get('device_id')

        test_cases = TestCase.query.filter(TestCase.id.in_(ids), TestCase.deleted == False).all()
        logger.info(f"[update_playback_devices] 查询到 {len(test_cases)} 个用例")

        updated_count = 0
        for tc in test_cases:
            if (tc.test_type or 'api') != 'e2e':
                continue
            if tc.config:
                config = tc.config.copy()
                
                for round_item in config.get('rounds', []):
                    if not isinstance(round_item, dict):
                        continue
                    # 轮次过滤
                    rn = round_item.get('round_number') or round_item.get('roundNumber')
                    if round_mode == 'specific' and rn not in round_numbers:
                        continue
                    
                    # 1. 目标人音频
                    if 'audio' in targets and device_id is not None:
                        for audio_config in round_item.get('audios', []):
                            audio_config['playback_device_id'] = device_id
                    
                    # 2-5. segment 级背景噪声/干扰人/声纹
                    for audio_config in round_item.get('audios', []):
                        if 'segmentBackgroundNoise' in targets and device_id is not None:
                            bn = audio_config.get('background_noise') or audio_config.get('backgroundNoise')
                            if bn and isinstance(bn, dict):
                                bn['playback_device_id'] = device_id
                        if 'interferers' in targets and device_id is not None:
                            for inf in audio_config.get('interferers', []):
                                if isinstance(inf, dict):
                                    inf['playback_device_id'] = device_id
                        if 'voiceprint' in targets and device_id is not None:
                            vp = audio_config.get('voiceprint')
                            if vp and isinstance(vp, dict):
                                vp['playback_device_id'] = device_id
                    
                    # 4. case 级 / round 级背景噪声
                    if 'caseBackgroundNoise' in targets and device_id is not None:
                        rbn = round_item.get('background_noise') or round_item.get('backgroundNoise')
                        if rbn and isinstance(rbn, dict):
                            if 'playback_device_ids' in rbn:
                                rbn['playback_device_ids'] = [device_id]
                            elif 'device_ids' in rbn:
                                rbn['device_ids'] = [device_id]
                            else:
                                rbn['playback_device_id'] = device_id
                
                # config 级背景噪声
                if 'caseBackgroundNoise' in targets and device_id is not None:
                    cbn = config.get('background_noise')
                    if cbn and isinstance(cbn, dict):
                        if 'playback_device_ids' in cbn:
                            cbn['playback_device_ids'] = [device_id]
                        elif 'device_ids' in cbn:
                            cbn['device_ids'] = [device_id]
                        else:
                            cbn['playback_device_id'] = device_id
                
                tc.config = config
                sqlalchemy.orm.attributes.flag_modified(tc, 'config')
                logger.debug(f"[update_playback_devices] 更新后 config: {tc.config}")
            tc.updated_at = now_cst()
            db.session.add(tc)
            updated_count += 1

        logger.info(f"[update_playback_devices] 更新完成，共更新 {updated_count} 个用例")
        return f"已成功更新 {updated_count} 个用例的播放设备"

    @staticmethod
    def _batch_update_spl(req_data):
        """批量更新声压"""
        import sqlalchemy.orm.attributes
        ids = req_data.ids
        logger.info(f"[update_spl] 开始处理, ids: {ids}, spl_data: {req_data.spl}")

        spl_data = req_data.spl
        if spl_data is None:
            logger.error("[update_spl] 缺少 spl 参数")
            return error_response("更新声压需要 'spl'")

        # 获取轮次范围和层级目标
        round_mode = getattr(req_data, 'round_mode', None) or 'all'
        round_numbers = getattr(req_data, 'round_numbers', None) or []
        targets = getattr(req_data, 'targets', None) or ['audio']
        
        # 兼容 spl 为 float 或 dict
        if isinstance(spl_data, (int, float)):
            spl_value = float(spl_data)
        else:
            spl_value = spl_data.get('value')

        test_cases = TestCase.query.filter(TestCase.id.in_(ids), TestCase.deleted == False).all()
        logger.info(f"[update_spl] 查询到 {len(test_cases)} 个用例")

        updated_count = 0
        for tc in test_cases:
            if (tc.test_type or 'api') != 'e2e':
                continue
            if tc.config:
                config = tc.config.copy()
                
                for round_item in config.get('rounds', []):
                    if not isinstance(round_item, dict):
                        continue
                    # 轮次过滤
                    rn = round_item.get('round_number') or round_item.get('roundNumber')
                    if round_mode == 'specific' and rn not in round_numbers:
                        continue
                    
                    # 1. 目标人音频
                    if 'audio' in targets:
                        for audio_config in round_item.get('audios', []):
                            if spl_value is not None:
                                audio_config['spl'] = spl_value
                    
                    # 2 & 3. segment 级背景噪声 / 干扰人 / 声纹（在 audio 内部）
                    for audio_config in round_item.get('audios', []):
                        # segment 级背景噪声
                        if 'segmentBackgroundNoise' in targets:
                            bn = audio_config.get('background_noise') or audio_config.get('backgroundNoise')
                            if bn and isinstance(bn, dict):
                                if spl_value is not None:
                                    bn['spl'] = spl_value
                        # 干扰人
                        if 'interferers' in targets:
                            for inf in audio_config.get('interferers', []):
                                if isinstance(inf, dict) and spl_value is not None:
                                    inf['spl'] = spl_value
                        # 声纹
                        if 'voiceprint' in targets:
                            vp = audio_config.get('voiceprint')
                            if vp and isinstance(vp, dict) and spl_value is not None:
                                vp['spl'] = spl_value
                    
                    # 4. case 级 / round 级背景噪声
                    if 'caseBackgroundNoise' in targets:
                        rbn = round_item.get('background_noise') or round_item.get('backgroundNoise')
                        if rbn and isinstance(rbn, dict) and spl_value is not None:
                            rbn['spl'] = spl_value
                
                # config 级背景噪声
                if 'caseBackgroundNoise' in targets:
                    cbn = config.get('background_noise')
                    if cbn and isinstance(cbn, dict) and spl_value is not None:
                        cbn['spl'] = spl_value
                
                tc.config = config
                sqlalchemy.orm.attributes.flag_modified(tc, 'config')
            tc.updated_at = now_cst()
            db.session.add(tc)
            updated_count += 1

        logger.info(f"[update_spl] 更新完成，共更新 {updated_count} 个用例")
        return f"已成功更新 {updated_count} 个用例的声压"

    @staticmethod
    def _batch_update_dimensions(req_data):
        """批量更新评价维度"""
        import sqlalchemy.orm.attributes
        ids = req_data.ids
        dimensions_data = req_data.dimensions
        logger.info(f"[update_dimensions] 开始处理, ids: {ids}, dimensions: {dimensions_data}")

        # 获取轮次范围
        round_mode = getattr(req_data, 'round_mode', None) or 'all'
        round_numbers = getattr(req_data, 'round_numbers', None) or []
        # 逐轮设置模式：round_dimensions = {1: [...], 2: [...], "-1": [...]}
        # -1 代表"最后一轮"，按用例实际轮次数动态解析
        round_dimensions = getattr(req_data, 'round_dimensions', None) or {}
        # 多轮整体评估维度（config.dimensions）
        multi_dimensions = getattr(req_data, 'multi_dimensions', None)

        # 逐轮设置模式不需要 dimensions 参数（可能只需要 round_dimensions 和/或 multi_dimensions）
        # 允许空 dimensions（用于清空所有轮次维度）
        has_single_dims = dimensions_data is not None and len(dimensions_data) > 0
        has_round_dims = round_dimensions and len(round_dimensions) > 0
        has_multi_dims = multi_dimensions is not None

        # 统一模式：dimensions 可以是空列表（清空），但不能是 None 且没有 multi_dimensions
        if round_mode != 'per_round' and dimensions_data is None and not has_multi_dims:
            logger.error("[update_dimensions] 缺少 dimensions 参数")
            return error_response("更新评价维度需要 'dimensions' 或 'multi_dimensions'")

        # 逐轮模式：round_dimensions 至少要有数据（即使是空列表也需要有 key）
        if round_mode == 'per_round' and not has_round_dims and not has_multi_dims:
            logger.error("[update_dimensions] 逐轮设置模式缺少 round_dimensions 和 multi_dimensions")
            return error_response("逐轮设置模式需要 'round_dimensions' 或 'multi_dimensions'")

        test_cases = TestCase.query.filter(TestCase.id.in_(ids), TestCase.deleted == False).all()
        logger.info(f"[update_dimensions] 查询到 {len(test_cases)} 个用例")

        def _build_dim_list(dim_data):
            """从维度数据构建标准化的维度列表"""
            result = []
            for dim in dim_data:
                result.append({
                    'id': dim.get('id'),
                    'name': dim.get('name', ''),
                    'weight': dim.get('weight', 50),
                    'threshold': dim.get('threshold', 60)
                })
            return result

        def _get_round_dims(rn, last_rn):
            """获取轮次对应的维度列表，支持 -1 = 最后一轮"""
            rn_key = str(rn) if isinstance(round_dimensions, dict) else rn
            dims = round_dimensions.get(rn_key) or round_dimensions.get(rn) or []
            # 如果是最后一轮，叠加 -1 的维度
            if rn == last_rn and round_dimensions:
                last_key = '-1' if isinstance(round_dimensions, dict) else -1
                last_dims = round_dimensions.get(last_key) or round_dimensions.get(-1) or []
                if last_dims:
                    existing_ids = {d.get('id') for d in dims}
                    for d in last_dims:
                        if d.get('id') not in existing_ids:
                            dims = list(dims) + [d]
            return dims

        updated_count = 0
        for tc in test_cases:
            if tc.config:
                config = tc.config.copy()
                rounds = config.get('rounds', [])
                last_rn = len(rounds) if rounds else 0

                if round_mode == 'per_round':
                    # 逐轮设置模式：每个轮次独立设置维度
                    for round_item in rounds:
                        if not isinstance(round_item, dict):
                            continue
                        rn = round_item.get('round_number') or round_item.get('roundNumber')
                        round_dim_data = _get_round_dims(rn, last_rn)
                        new_dim_list = _build_dim_list(round_dim_data)
                        if 'evaluation' not in round_item:
                            round_item['evaluation'] = {}
                        round_item['evaluation']['dimensions'] = new_dim_list
                        logger.debug(f"[update_dimensions] 用例 {tc.id} 轮次 {rn} 设置维度 {len(new_dim_list)} 个")
                elif dimensions_data is not None:
                    # 统一模式：所有/指定轮次共用同一套维度（含空列表=清空）
                    new_dim_list = _build_dim_list(dimensions_data)
                    for dim in dimensions_data:
                        logger.debug(f"[update_dimensions] 用例 {tc.id} 设置维度 {dim.get('id')}")

                    for round_item in rounds:
                        if not isinstance(round_item, dict):
                            continue
                        # 轮次过滤
                        rn = round_item.get('round_number') or round_item.get('roundNumber')
                        if round_mode == 'specific' and round_numbers:
                            is_selected = rn in round_numbers or \
                                (rn == last_rn and -1 in round_numbers)
                            if not is_selected:
                                continue
                        if 'evaluation' not in round_item:
                            round_item['evaluation'] = {}
                        round_item['evaluation']['dimensions'] = new_dim_list

                # 多轮整体评估维度（config.dimensions）：非 None 就写入（空列表=清空）
                if multi_dimensions is not None:
                    config['dimensions'] = _build_dim_list(multi_dimensions)
                    logger.debug(f"[update_dimensions] 用例 {tc.id} 设置整体评估维度 {len(multi_dimensions)} 个")

                tc.config = config
                sqlalchemy.orm.attributes.flag_modified(tc, 'config')
            tc.updated_at = now_cst()
            db.session.add(tc)
            updated_count += 1

        logger.info(f"[update_dimensions] 更新完成，共更新 {updated_count} 个用例")
        return f"已成功更新 {updated_count} 个用例的评价维度"

    @staticmethod
    def _batch_update_noise(req_data):
        """批量更新噪声配置"""
        import sqlalchemy.orm.attributes
        ids = req_data.ids
        logger.info(f"[update_noise] 开始处理, ids: {ids}")

        audio_id = req_data.noise_audio_id
        spl = req_data.noise_spl
        device_ids = req_data.noise_device_ids or []

        # 获取轮次范围和层级目标
        round_mode = getattr(req_data, 'round_mode', None) or 'all'
        round_numbers = getattr(req_data, 'round_numbers', None) or []
        targets = getattr(req_data, 'targets', None) or ['caseBackgroundNoise', 'segmentBackgroundNoise']

        logger.info(f"[update_noise] audio_id: {audio_id}, spl: {spl}, device_ids: {device_ids}, targets: {targets}")

        test_cases = TestCase.query.filter(TestCase.id.in_(ids), TestCase.deleted == False).all()
        logger.info(f"[update_noise] 查询到 {len(test_cases)} 个用例")

        updated_count = 0
        for tc in test_cases:
            if (tc.test_type or 'api') != 'e2e':
                continue
            if tc.config is None:
                config = {}
            else:
                config = tc.config.copy()

            for round_item in config.get('rounds', []):
                if not isinstance(round_item, dict):
                    continue
                # 轮次过滤
                rn = round_item.get('round_number') or round_item.get('roundNumber')
                if round_mode == 'specific' and rn not in round_numbers:
                    continue

                noise_config = {
                    'audio_id': audio_id if audio_id is not None else '',
                    'spl': spl if spl is not None else 0,
                    'device_ids': device_ids if device_ids is not None else [],
                }

                # round 级 / case 级背景噪声
                if 'caseBackgroundNoise' in targets:
                    if 'backgroundNoise' not in round_item:
                        round_item['backgroundNoise'] = {}
                    if audio_id is not None:
                        round_item['backgroundNoise']['audio_id'] = audio_id
                    if spl is not None:
                        round_item['backgroundNoise']['spl'] = spl
                    if device_ids is not None:
                        round_item['backgroundNoise']['device_ids'] = device_ids

                # segment 级背景噪声 + 干扰人
                if 'segmentBackgroundNoise' in targets or 'interferers' in targets:
                    for audio_config in round_item.get('audios', []):
                        if 'segmentBackgroundNoise' in targets:
                            bn = audio_config.get('background_noise') or audio_config.get('backgroundNoise')
                            if bn is None:
                                bn = {}
                                audio_config['background_noise'] = bn
                            if audio_id is not None:
                                bn['audio_id'] = audio_id
                            if spl is not None:
                                bn['spl'] = spl
                            if device_ids is not None:
                                bn['device_ids'] = device_ids
                        if 'interferers' in targets:
                            for inf in audio_config.get('interferers', []):
                                if isinstance(inf, dict):
                                    if audio_id is not None:
                                        inf['audio_id'] = audio_id
                                    if spl is not None:
                                        inf['spl'] = spl
                                    if device_ids is not None:
                                        inf['playback_device_id'] = device_ids[0] if device_ids else ''

            # config 级背景噪声
            if 'caseBackgroundNoise' in targets:
                cbn = config.get('background_noise')
                if cbn is None:
                    cbn = {}
                    config['background_noise'] = cbn
                if audio_id is not None:
                    cbn['audio_id'] = audio_id
                if spl is not None:
                    cbn['spl'] = spl
                if device_ids is not None:
                    cbn['device_ids'] = device_ids

            tc.config = config
            sqlalchemy.orm.attributes.flag_modified(tc, 'config')
            logger.info(f"[update_noise] 更新用例 {tc.id} noise config")

            tc.updated_at = now_cst()
            db.session.add(tc)
            updated_count += 1

        logger.info(f"[update_noise] 更新完成，共更新 {updated_count} 个用例")
        return f"已成功更新 {updated_count} 个用例的噪声配置"

    @staticmethod
    def _batch_auto_generate_name(req_data):
        """批量自动生成名称"""
        ids = req_data.ids
        logger.info(f"[auto_generate_name] 开始处理, ids: {ids}")

        test_cases = TestCase.query.filter(TestCase.id.in_(ids), TestCase.deleted == False).all()
        logger.info(f"[auto_generate_name] 查询到 {len(test_cases)} 个用例")

        updated_count = 0
        for tc in test_cases:
            tag_names = sorted([tag.name for tag in tc.tags if len(tag.name) <= 25], key=lambda x: len(x))
            if tag_names:
                tc.name = '-'.join(tag_names)
                logger.info(f"[auto_generate_name] 用例 {tc.id} 新名称: {tc.name}")
            tc.updated_at = now_cst()
            db.session.add(tc)
            updated_count += 1

        logger.info(f"[auto_generate_name] 更新完成，共更新 {updated_count} 个用例")
        return f"已成功为 {updated_count} 个用例自动生成名称"

    @staticmethod
    def _batch_add_tags(req_data):
        """批量添加标签"""
        ids = req_data.ids
        logger.info(f"[add_tags] 开始处理, ids: {ids}, tags: {req_data.tags}")

        tags_to_add = req_data.tags or []
        if not tags_to_add:
            return error_response("添加标签需要 'tags' 参数")

        test_cases = TestCase.query.filter(TestCase.id.in_(ids), TestCase.deleted == False).all()
        logger.info(f"[add_tags] 查询到 {len(test_cases)} 个用例")

        updated_count = 0
        for tc in test_cases:
            existing_tag_names = {tag.name for tag in tc.tags}
            for tag_name in tags_to_add:
                if tag_name not in existing_tag_names:
                    tag = Tag.query.filter_by(name=tag_name).first()
                    if not tag:
                        tag = Tag(name=tag_name)
                        db.session.add(tag)
                    tc.tags.append(tag)
            tc.updated_at = now_cst()
            db.session.add(tc)
            updated_count += 1

        logger.info(f"[add_tags] 更新完成，共更新 {updated_count} 个用例")
        return f"已成功为 {updated_count} 个用例添加标签"

    @staticmethod
    def _batch_remove_tags(req_data):
        """批量移除标签"""
        ids = req_data.ids
        logger.info(f"[remove_tags] 开始处理, ids: {ids}, tags: {req_data.tags}")

        tags_to_remove = req_data.tags or []
        if not tags_to_remove:
            return error_response("移除标签需要 'tags' 参数")

        test_cases = TestCase.query.filter(TestCase.id.in_(ids), TestCase.deleted == False).all()
        logger.info(f"[remove_tags] 查询到 {len(test_cases)} 个用例")

        updated_count = 0
        for tc in test_cases:
            tags_to_remove_set = set(tags_to_remove)
            tc.tags = [tag for tag in tc.tags if tag.name not in tags_to_remove_set]
            tc.updated_at = now_cst()
            db.session.add(tc)
            updated_count += 1

        logger.info(f"[remove_tags] 更新完成，共更新 {updated_count} 个用例")
        return f"已成功为 {updated_count} 个用例移除标签"

    @staticmethod
    def _batch_rename_tag(req_data):
        """重命名标签"""
        old_tag_name = req_data.old_tag_name
        new_tag_name = req_data.new_tag_name
        logger.info(f"[rename_tag] 开始处理, old_tag: {old_tag_name}, new_tag: {new_tag_name}")

        if not old_tag_name or not new_tag_name:
            return error_response("重命名标签需要 'old_tag_name' 和 'new_tag_name' 参数")

        if old_tag_name == new_tag_name:
            return error_response("新标签名不能与原标签名相同")

        old_tag = Tag.query.filter_by(name=old_tag_name).first()
        if not old_tag:
            return error_response(f"未找到标签: {old_tag_name}")

        new_tag_exists = Tag.query.filter_by(name=new_tag_name).first()
        if new_tag_exists:
            return error_response(f"标签名 {new_tag_name} 已存在")

        old_tag.name = new_tag_name
        old_tag.updated_at = now_cst()
        db.session.add(old_tag)

        logger.info(f"[rename_tag] 标签 {old_tag_name} 已重命名为 {new_tag_name}")
        return f"已成功将标签 {old_tag_name} 重命名为 {new_tag_name}"

    @staticmethod
    def _batch_refresh_reference(req_data):
        """刷新参考参数"""
        ids = req_data.ids
        round_mode = getattr(req_data, 'round_mode', None) or 'all'
        round_numbers = getattr(req_data, 'round_numbers', None) or []
        logger.info(f"[refresh_reference] 开始处理, ids: {ids}, round_mode: {round_mode}, round_numbers: {round_numbers}")

        test_cases = TestCase.query.filter(
            TestCase.id.in_(ids),
            TestCase.deleted == False
        ).all()
        logger.info(f"[refresh_reference] 查询到 {len(test_cases)} 个用例")

        if len(ids) > 50:
            from backend.utils.common.reference_refresh_task import submit_reference_refresh_task
            task_id = submit_reference_refresh_task(ids)
            logger.info(f"[refresh_reference] 异步任务已提交: {task_id}")
            # 返回 dict，batch_action 会直接返回（跳过 commit）
            return {
                'success': True,
                'task_id': task_id,
                'message': f'已提交异步刷新任务，预计处理 {len(test_cases)} 个用例'
            }
        else:
            updated_count = 0
            for tc in test_cases:
                try:
                    TestCaseController.refresh_reference_texts(tc)
                    tc.updated_at = now_cst()
                    db.session.add(tc)
                    updated_count += 1
                except Exception as e:
                    logger.error(f"[refresh_reference] 处理用例 {tc.id} 失败: {e}")

            db.session.commit()
            logger.info(f"[refresh_reference] 更新完成，共更新 {updated_count} 个用例")
            return f"已成功刷新 {updated_count} 个用例的参考参数"

    @staticmethod
    def fetch_case_ids():
        """按筛选条件返回全量用例ID（不分页）"""
        from flask import request, jsonify
        try:
            data = request.get_json() or {}
            query = TestCase.query.filter(TestCase.deleted == False)

            if data.get('group'):
                # 通过 group_name 查找 group_id
                group = TestCaseGroup.query.filter_by(name=data['group'], deleted=False).first()
                if group:
                    query = query.filter(TestCase.group_id == group.id)
                else:
                    # 未找到分组则返回空
                    return jsonify({'ids': []})

            if data.get('test_type'):
                query = query.filter(TestCase.test_type == data['test_type'])

            if data.get('algorithm_type'):
                query = query.filter(TestCase.algorithm_type == data['algorithm_type'])

            if data.get('dimension_id'):
                dim_str = str(data['dimension_id'])
                query = query.filter(
                    TestCase.config.cast(db.Text).like(f'"id": {dim_str}') |
                    TestCase.config.cast(db.Text).like(f'"id":{dim_str}') |
                    TestCase.config.cast(db.Text).like(f'"id": "{dim_str}"') |
                    TestCase.config.cast(db.Text).like(f'"id":"{dim_str}"')
                )

            if data.get('search'):
                keyword = f"%{data['search']}%"
                query = query.filter(
                    (TestCase.id.like(keyword)) |
                    (TestCase.name.like(keyword)) |
                    (TestCase.description.like(keyword))
                )

            if data.get('tag'):
                # 按标签筛选
                query = query.join(TestCase.tags).filter(Tag.name == data['tag'])

            if data.get('algorithm_type'):
                query = query.filter(TestCase.algorithm_type == data['algorithm_type'])

            ids = [row[0] for row in query.with_entities(TestCase.id).all()]
            return jsonify({'ids': ids})
        except Exception as e:
            logger.error(f"[fetch_case_ids] 查询失败: {e}")
            from backend.utils.web.response import error_response
            return error_response(str(e))

    # 获取统计信息
    @staticmethod
    def get_stats():
        try:
            total_count = TestCase.query.filter_by(deleted=False).count()
            
            # 按分组统计
            group_stats = db.session.query(
                TestCaseGroup.name, db.func.count(TestCase.id)
            ).join(TestCase, TestCase.group_id == TestCaseGroup.id)\
             .filter(
                 TestCase.deleted == False,
                 TestCaseGroup.deleted == False
             )\
             .group_by(TestCaseGroup.name).all()
            
            # 最近更新 (前5条)
            recent_updates = TestCase.query.filter_by(deleted=False)\
                .order_by(TestCase.updated_at.desc())\
                .limit(5).all()

            return success_response(
                TestCaseStatsData(
                    total_count=total_count,
                    by_group={name: count for name, count in group_stats},
                    recent_updates=[
                        {"id": tc.id, "name": tc.name, "updated_at": tc.updated_at.isoformat()}
                        for tc in recent_updates
                    ],
                )
            )
        except Exception as e:
            return error_response(str(e))
    
    # 获取所有标签
    @staticmethod
    def get_tags():
        try:
            # 查询所有标签
            tags = Tag.query.order_by(Tag.updated_at.desc()).all()
            
            # 提取标签名称列表
            tag_names = [tag.name for tag in tags]
            
            return success_response(TagListData(items=tag_names))
        except Exception as e:
            return error_response(str(e))

    # 导出测试用例
    @staticmethod
    def export_cases():
        try:
            req_data = TestCaseExportRequest.model_validate(request.get_json() or {})
            
            ids = req_data.ids
            format_type = req_data.format
            include_deleted = req_data.include_deleted
            
            if not ids:
                return error_response("未指定要导出的用例ID")
            
            # 查询指定的测试用例（软删过滤由 models.soft_delete 全局单一入口负责）
            query = TestCase.query.filter(TestCase.id.in_(ids))
            if include_deleted:
                query = query.execution_options(include_deleted=True)
            test_cases = query.all()
            
            if not test_cases:
                return error_response("未找到指定的测试用例")
            
            export_data = []
            for tc in test_cases:
                # 导出前实时刷新参考文本，确保信息完整
                TestCaseController.refresh_reference_texts(tc)
                config = tc.config or {}
                
                # 从config中提取音频信息
                audios = []
                playback_device_names = set()
                for i, audio_item in enumerate(TestCaseController._collect_audios(config)):
                    audio_id = audio_item.get('audio_id')
                    audio = db.session.get(Audio, audio_id)
                    # 优先使用数据库中的最新名称，如果找不到则保留原样或标记未知
                    audio_name = audio.name if audio else (audio_item.get('audio_name') or "未知音频")
                    
                    device_id = TestCaseController._normalize_optional_int(audio_item.get('playback_device_id'))
                    device_name = "未知设备"
                    if device_id:
                        device = db.session.get(PlaybackDevice, device_id)
                        if device:
                            device_name = device.name
                            playback_device_names.add(device_name)
                    
                    audios.append({
                        "audio_id": audio_id,
                        "audio_name": audio_name,
                        "test_type": getattr(tc, 'test_type', 'api') or 'api',
                        "spl": audio_item.get('spl'),
                        "playback_device_id": device_id,
                        "playback_device_name": device_name,
                        "play_order": audio_item.get('play_order', i + 1)
                    })
                
                # 获取评分维度名称（兼容新旧格式）
                dimensions_data = TestCaseController._collect_dimensions(config)
                
                def get_dim_names(dim_list):
                    names = []
                    if not dim_list: return names
                    for item in dim_list:
                        d_id = None
                        if isinstance(item, dict):
                            d_id = item.get('id')
                        else:
                            d_id = item
                        
                        if d_id:
                            dim = db.session.get(Dimension, d_id)
                            if dim: names.append(dim.name)
                    return names

                def get_dim_ids(dim_list):
                    ids = []
                    if not dim_list:
                        return ids
                    for item in dim_list:
                        d_id = None
                        if isinstance(item, dict):
                            d_id = item.get('id') or item.get('dimension_id') or item.get('dimensionId')
                        else:
                            d_id = item
                        if d_id is None:
                            continue
                        try:
                            ids.append(int(d_id))
                        except Exception:
                            continue
                    return ids

                dimension_names = get_dim_names(dimensions_data)
                dimension_ids = get_dim_ids(dimensions_data)
                
                # 格式化音频详细信息列
                audio_details = []
                # 按播放顺序排序
                sorted_audios = sorted(audios, key=lambda x: x.get('play_order', 0))
                for i, audio_item in enumerate(sorted_audios):
                    order = i + 1 # 导出时序号从1开始
                    a_name = audio_item.get('audio_name', '未知音频')
                    a_spl = audio_item.get('spl', '-')
                    a_device = audio_item.get('playback_device_name', '-')
                    audio_details.append(f"[{order}] {a_name}({a_spl}dB, 设备:{a_device})")
                
                # 获取背景噪声名称及SPL（兼容新旧格式）
                # 获取噪声配置（从 rounds[0].backgroundNoise）
                noise_config = {}
                first_round = config.get('rounds', [{}])[0] if config.get('rounds') else {}
                if isinstance(first_round, dict):
                    noise_config = first_round.get('backgroundNoise') or {}
                noise_name = "无"
                noise_spl = noise_config.get('spl') or noise_config.get('noise_spl', '')
                noise_audio_id = noise_config.get('audio_id')
                
                if noise_audio_id:
                    noise_audio = db.session.get(Audio, noise_audio_id)
                    if noise_audio:
                        noise_name = noise_audio.name

                # 获取标签
                tags = [tag.name for tag in tc.tags]
                tag_items = [{"tag_id": tag.id, "tag_name": tag.name} for tag in tc.tags]

                case_data = {
                    "id": tc.id,
                    "name": tc.name,
                    "description": tc.description,
                    "group": tc.group.name if tc.group else None,
                    "group_id": tc.group_id,
                    "test_type": tc.test_type,
                    "tags": tags,
                    "tag_items": tag_items,
                    "dimensions": dimension_names,
                    "dimension_ids": dimension_ids,
                    "playback_devices": list(playback_device_names),
                    "audios": audios,
                    "audio_details": " ; ".join(audio_details),
                    "noise_name": noise_name,
                    "noise_spl": noise_spl,
                    "noise_audio_id": noise_audio_id,
                    "config": config,
                    "reference_params": tc.reference_params,
                    "raw_config": json.dumps(config, ensure_ascii=False)
                }
                export_data.append(case_data)
            
            if format_type == 'json':
                export_result = {
                    "test_cases": export_data,
                    "exported_at": now_cst().isoformat(),
                    "total_count": len(export_data)
                }
                return success_response(
                    TestCaseExportJsonData(
                        test_cases=[TestCaseExportItem(**item) for item in export_result["test_cases"]],
                        exported_at=export_result["exported_at"],
                        total_count=export_result["total_count"],
                    )
                )
            elif format_type in ['csv', 'xlsx']:
                flattened_data = []
                audio_configs = []
                dimensions_data_list = []
                groups = []
                case_tags = []
                
                for item in export_data:
                    config_data = item.get('config', {})
                    # 优先从独立列读取，兼容旧 config
                    ref_col = item.get('reference_params')
                    if ref_col:
                        asr_ref_text = ReferenceParamsGenerator.get_reference_text(ref_col, 'asr_reference_text')
                        tran_ref_text = ReferenceParamsGenerator.get_reference_text(ref_col, 'translation_reference_text')
                    else:
                        asr_ref_text = ReferenceParamsGenerator.get_reference_text(config_data, 'asr_reference_text')
                        tran_ref_text = ReferenceParamsGenerator.get_reference_text(config_data, 'translation_reference_text')
                    flat_item = {
                        "ID": item['id'],
                        "NAME": item['name'],
                        "DESCRIPTION": item['description'],
                        "GROUP_NAME": item['group'],
                        "GROUP_ID": item.get('group_id') or "",
                        "TEST_TYPE": item.get('test_type') or "",
                        "NOISE_AUDIO_NAME": item['noise_name'],
                        "NOISE_AUDIO_ID": item.get('noise_audio_id') or "",
                        "NOISE_SPL": item['noise_spl'],
                        "ASR_REFERENCE_TEXT": asr_ref_text,
                        "TRANSLATION_REFERENCE_TEXT": tran_ref_text,
                        "TAGS": ", ".join(item['tags']) if item['tags'] else "",
                        "REMARKS": ""
                    }
                    flattened_data.append(flat_item)
                    
                    for audio in item.get('audios', []):
                        audio_configs.append({
                            "CASE_ID": item['id'],
                            "CASE_NAME": item['name'],
                            "AUDIO_ID": audio.get('audio_id') or "",
                            "AUDIO_NAME": audio.get('audio_name', ''),
                            "SPL": audio.get('spl', ''),
                            "PLAYBACK_DEVICE_ID": audio.get('playback_device_id') or "",
                            "PLAYBACK_DEVICE_NAME": audio.get('playback_device_name', ''),
                            "PLAY_ORDER": audio.get('play_order', 0)
                        })
                    
                    for dim_id in item.get('dimension_ids', []) or []:
                        dim_obj = db.session.get(Dimension, dim_id)
                        dim_name = dim_obj.name if dim_obj else str(dim_id)
                        dim_display_name = dim_name
                        weight = dim_obj.weight if dim_obj else 50
                        threshold = 80
                        dimensions_data_list.append({
                            "CASE_ID": item['id'],
                            "CASE_NAME": item['name'],
                            "DIMENSION_ID": dim_id,
                            "DIMENSION_NAME": dim_name,
                            "DIMENSION_DISPLAY_NAME": dim_display_name,
                            "WEIGHT": weight,
                            "THRESHOLD": threshold
                        })
                    
                    if item.get('group_id') or item.get('group'):
                        groups.append({"group_id": item.get('group_id'), "group_name": item.get('group')})

                    for tag_item in item.get('tag_items', []) or []:
                        case_tags.append({
                            "CASE_ID": item['id'],
                            "CASE_NAME": item['name'],
                            "TAG_ID": tag_item.get("tag_id") or "",
                            "TAG_NAME": tag_item.get("tag_name") or ""
                        })
                
                if format_type == 'csv':
                    df = pd.DataFrame(flattened_data)
                    df.to_csv(io.BytesIO(), index=False, encoding='utf-8-sig')
                    output = io.BytesIO()
                    df.to_csv(output, index=False, encoding='utf-8-sig')
                    mimetype = 'text/csv'
                    download_name = f"testcases_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
                    output.seek(0)
                    return send_file(
                        output,
                        mimetype=mimetype,
                        as_attachment=True,
                        download_name=download_name
                    )
                else:
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        testcases_columns = [
                            'ID', 'NAME', 'DESCRIPTION', 'GROUP_NAME', 'GROUP_ID',
                            'TRANSLATION_DIRECTION', 'TEST_TYPE', 'NOISE_AUDIO_NAME', 'NOISE_AUDIO_ID',
                            'NOISE_SPL', 'ASR_REFERENCE_TEXT', 'TRANSLATION_REFERENCE_TEXT',
                            'TAGS', 'REMARKS'
                        ]
                        audio_configs_columns = [
                            'CASE_ID', 'CASE_NAME', 'AUDIO_ID', 'AUDIO_NAME', 'SPL',
                            'PLAYBACK_DEVICE_ID', 'PLAYBACK_DEVICE_NAME', 'PLAY_ORDER'
                        ]
                        dimensions_columns = [
                            'CASE_ID', 'CASE_NAME', 'DIMENSION_ID', 'DIMENSION_NAME', 'DIMENSION_DISPLAY_NAME', 'WEIGHT', 'THRESHOLD'
                        ]
                        tags_columns = ['TAG_ID', 'TAG_NAME', 'TAG_DESCRIPTION', 'TAG_COLOR']
                        groups_columns = ['GROUP_ID', 'GROUP_NAME', 'GROUP_DESCRIPTION', 'PARENT_GROUP_NAME']
                        case_tags_columns = ['CASE_ID', 'CASE_NAME', 'TAG_ID', 'TAG_NAME']

                        testcases_df = pd.DataFrame(flattened_data)
                        if testcases_df.empty:
                            testcases_df = pd.DataFrame(columns=testcases_columns)
                        else:
                            testcases_df = testcases_df.reindex(columns=testcases_columns)
                        testcases_df.to_excel(writer, sheet_name='TestCases', index=False)
                        
                        audio_df = pd.DataFrame(audio_configs)
                        if audio_df.empty:
                            audio_df = pd.DataFrame(columns=audio_configs_columns)
                        else:
                            audio_df = audio_df.reindex(columns=audio_configs_columns)
                        audio_df.to_excel(writer, sheet_name='AudioConfigs', index=False)
                        
                        dims_df = pd.DataFrame(dimensions_data_list)
                        if dims_df.empty:
                            dims_df = pd.DataFrame(columns=dimensions_columns)
                        else:
                            dims_df = dims_df.reindex(columns=dimensions_columns)
                        dims_df.to_excel(writer, sheet_name='Dimensions', index=False)
                        
                        tag_names = set()
                        for item in export_data:
                            for t in item.get('tags', []):
                                if t:
                                    tag_names.add(t)

                        tags_rows = []
                        if tag_names:
                            tag_objects = Tag.query.filter(Tag.name.in_(list(tag_names))).all()
                            tag_by_name = {t.name: t for t in tag_objects}
                            for name in sorted(tag_names):
                                tag_obj = tag_by_name.get(name)
                                tags_rows.append({
                                    "TAG_ID": tag_obj.id if tag_obj else "",
                                    "TAG_NAME": name,
                                    "TAG_DESCRIPTION": tag_obj.description if tag_obj else "",
                                    "TAG_COLOR": tag_obj.color if tag_obj else ""
                                })

                        tags_df = pd.DataFrame(tags_rows)
                        if tags_df.empty:
                            tags_df = pd.DataFrame(columns=tags_columns)
                        else:
                            tags_df = tags_df.reindex(columns=tags_columns)
                        tags_df.to_excel(writer, sheet_name='Tags', index=False)

                        unique_groups = {}
                        for g in groups:
                            g_id = g.get("group_id")
                            g_name = g.get("group_name")
                            if g_id:
                                unique_groups[g_id] = g_name
                            elif g_name and g_name not in unique_groups.values():
                                unique_groups[g_name] = g_name

                        group_rows = []
                        if unique_groups:
                            group_objects = TestCaseGroup.query.filter(
                                TestCaseGroup.id.in_(list(unique_groups.keys())),
                                TestCaseGroup.deleted == False
                            ).all()
                            group_by_id = {g.id: g for g in group_objects}
                            missing_names = [v for k, v in unique_groups.items() if k not in group_by_id]
                            if missing_names:
                                group_objects_by_name = TestCaseGroup.query.filter(
                                    TestCaseGroup.name.in_(missing_names),
                                    TestCaseGroup.deleted == False
                                ).all()
                                for g in group_objects_by_name:
                                    group_by_id[g.id] = g

                            for group_key, group_name in sorted(unique_groups.items(), key=lambda x: str(x[0])):
                                group_obj = group_by_id.get(group_key)
                                if not group_obj and group_name:
                                    group_obj = next((g for g in group_by_id.values() if g.name == group_name), None)
                                resolved_id = group_obj.id if group_obj else (group_key if group_key and group_key != group_name else "")
                                group_rows.append({
                                    "GROUP_ID": resolved_id,
                                    "GROUP_NAME": group_obj.name if group_obj else group_name,
                                    "GROUP_DESCRIPTION": group_obj.description if group_obj else "",
                                    "PARENT_GROUP_NAME": ""
                                })
                        groups_df = pd.DataFrame(group_rows)
                        if groups_df.empty:
                            groups_df = pd.DataFrame(columns=groups_columns)
                        else:
                            groups_df = groups_df.reindex(columns=groups_columns)
                        groups_df.to_excel(writer, sheet_name='Groups', index=False)

                        case_tags_df = pd.DataFrame(case_tags)
                        if case_tags_df.empty:
                            case_tags_df = pd.DataFrame(columns=case_tags_columns)
                        else:
                            case_tags_df = case_tags_df.reindex(columns=case_tags_columns)
                        case_tags_df.to_excel(writer, sheet_name='CaseTags', index=False)
                    
                    output.seek(0)
                    mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    download_name = f"testcases_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
                    return send_file(
                        output,
                        mimetype=mimetype,
                        as_attachment=True,
                        download_name=download_name
                    )
            else:
                return error_response(f"不支持的导出格式: {format_type}")
                
        except Exception as e:
            return error_response(str(e))

    @staticmethod
    def import_cases():
        try:
            if 'file' not in request.files:
                return error_response("未上传文件")
            
            file = request.files['file']
            if file.filename == '':
                return error_response("未选择文件")
            
            import json
            import pandas as pd
            import io
            
            def parse_legacy_format(df):
                column_map = {
                    "ID": "id",
                    "用例名称": "name",
                    "描述": "description",
                    "分组": "group",
                    "分组ID": "group_id",
                    "标签": "tags_str",
                    "raw_config": "raw_config"
                }
                
                test_cases_data = []
                for _, row in df.iterrows():
                    case_item = {}
                    for csv_col, data_key in column_map.items():
                        if csv_col in row:
                            val = row[csv_col]
                            if pd.isna(val):
                                case_item[data_key] = None
                            else:
                                case_item[data_key] = val
                    
                    if 'tags_str' in case_item and case_item['tags_str']:
                        case_item['tags'] = [t.strip() for t in str(case_item['tags_str']).split(',') if t.strip()]
                    else:
                        case_item['tags'] = []
                    
                    if 'raw_config' in case_item and case_item['raw_config']:
                        try:
                            case_item['config'] = json.loads(case_item['raw_config'])
                        except:
                            case_item['config'] = {}
                    
                    test_cases_data.append(case_item)
                
                return test_cases_data
            
            file_extension = file.filename.split('.')[-1].lower()
            test_cases_data = []
            
            if file_extension == 'json':
                file_content = file.read().decode('utf-8')
                data = json.loads(file_content)
                test_cases_data = data.get('test_cases', [])
            elif file_extension in ['csv', 'xlsx', 'xls']:
                if file_extension == 'csv':
                    df = pd.read_csv(io.BytesIO(file.read()), encoding='utf-8-sig')
                    test_cases_data = parse_legacy_format(df)
                else:
                    xl = pd.ExcelFile(io.BytesIO(file.read()))
                    sheet_names = xl.sheet_names
                    
                    if 'TestCases' in sheet_names:
                        test_cases_data = []
                        audio_configs = {}
                        dimensions_by_case = {}
                        
                        testcases_df = pd.read_excel(xl, sheet_name='TestCases')
                        audio_df = pd.read_excel(xl, sheet_name='AudioConfigs') if 'AudioConfigs' in sheet_names else None
                        dims_df = pd.read_excel(xl, sheet_name='Dimensions') if 'Dimensions' in sheet_names else None
                        case_tags_df = pd.read_excel(xl, sheet_name='CaseTags') if 'CaseTags' in sheet_names else None

                        case_tags_by_id = {}
                        case_tags_by_name = {}
                        if case_tags_df is not None and not case_tags_df.empty:
                            for _, ct_row in case_tags_df.iterrows():
                                c_id = str(ct_row.get('CASE_ID', '')).strip() if pd.notna(ct_row.get('CASE_ID')) else ''
                                c_name = str(ct_row.get('CASE_NAME', '')).strip() if pd.notna(ct_row.get('CASE_NAME')) else ''
                                t_id_raw = ct_row.get('TAG_ID')
                                t_name = str(ct_row.get('TAG_NAME', '')).strip() if pd.notna(ct_row.get('TAG_NAME')) else ''
                                t_id = None
                                try:
                                    t_id = int(str(t_id_raw).strip()) if pd.notna(t_id_raw) and str(t_id_raw).strip() else None
                                except Exception:
                                    t_id = None
                                tag_link = {"tag_id": t_id, "tag_name": t_name}
                                if c_id:
                                    case_tags_by_id.setdefault(c_id, []).append(tag_link)
                                if c_name:
                                    case_tags_by_name.setdefault(c_name, []).append(tag_link)

                        def normalize_cell(val):
                            if val is None or (hasattr(pd, "isna") and pd.isna(val)):
                                return None
                            text = str(val).strip()
                            return text if text else None

                        for _, row in testcases_df.iterrows():
                            case_item = {
                                'id': str(row.get('ID', '')).strip() if pd.notna(row.get('ID')) else None,
                                'name': str(row.get('NAME', '')).strip() if pd.notna(row.get('NAME')) else '',
                                'description': str(row.get('DESCRIPTION', '')) if pd.notna(row.get('DESCRIPTION')) else '',
                                'group': str(row.get('GROUP_NAME', '')).strip() if pd.notna(row.get('GROUP_NAME')) else '未分类',
                                'group_id': normalize_cell(row.get('GROUP_ID')),
                                'test_type': str(row.get('TEST_TYPE', '')) if pd.notna(row.get('TEST_TYPE')) else 'api',
                                'noise_audio_name': str(row.get('NOISE_AUDIO_NAME', '')) if pd.notna(row.get('NOISE_AUDIO_NAME')) else '',
                                'noise_audio_id': normalize_cell(row.get('NOISE_AUDIO_ID')),
                                'noise_spl': row.get('NOISE_SPL', 0) if pd.notna(row.get('NOISE_SPL')) else 0,
                                'asr_reference_text': str(row.get('ASR_REFERENCE_TEXT', '')) if pd.notna(row.get('ASR_REFERENCE_TEXT')) else '',
                                'translation_reference_text': str(row.get('TRANSLATION_REFERENCE_TEXT', '')) if pd.notna(row.get('TRANSLATION_REFERENCE_TEXT')) else '',
                                'tags': [t.strip() for t in str(row.get('TAGS', '')).split(',') if t.strip()] if pd.notna(row.get('TAGS')) else [],
                                'remarks': str(row.get('REMARKS', '')) if pd.notna(row.get('REMARKS')) else '',
                                'audios': [],
                                'dimensions': [],
                                'config': {},
                                'tag_links': []
                            }

                            if case_item['id'] and case_item['id'] in case_tags_by_id:
                                case_item['tag_links'] = case_tags_by_id.get(case_item['id'], [])
                            elif case_item['name'] and case_item['name'] in case_tags_by_name:
                                case_item['tag_links'] = case_tags_by_name.get(case_item['name'], [])

                            if case_item['tag_links']:
                                names = []
                                for tl in case_item['tag_links']:
                                    if tl.get("tag_name"):
                                        names.append(tl["tag_name"])
                                case_item['tags'] = names
                            
                            if audio_df is not None and not audio_df.empty:
                                if 'CASE_ID' in audio_df.columns and case_item['id']:
                                    case_audios = audio_df[audio_df['CASE_ID'].astype(str).str.strip() == case_item['id']]
                                else:
                                    case_audios = audio_df[audio_df['CASE_NAME'] == case_item['name']]

                                for _, audio_row in case_audios.iterrows():
                                    audio_id_val = audio_row.get('AUDIO_ID')
                                    playback_device_id_val = audio_row.get('PLAYBACK_DEVICE_ID')
                                    try:
                                        audio_id = int(str(audio_id_val).strip()) if pd.notna(audio_id_val) and str(audio_id_val).strip() else None
                                    except Exception:
                                        audio_id = None
                                    try:
                                        playback_device_id = int(str(playback_device_id_val).strip()) if pd.notna(playback_device_id_val) and str(playback_device_id_val).strip() else None
                                    except Exception:
                                        playback_device_id = None

                                    if audio_id is None:
                                        audio_name = str(audio_row.get('AUDIO_NAME', '')).strip() if pd.notna(audio_row.get('AUDIO_NAME')) else ''
                                        if audio_name:
                                            audio_obj = Audio.query.filter_by(name=audio_name).first()
                                            if audio_obj:
                                                audio_id = audio_obj.id

                                    case_item['audios'].append({
                                        'audio_id': audio_id,
                                        'audio_name': str(audio_row.get('AUDIO_NAME', '')) if pd.notna(audio_row.get('AUDIO_NAME')) else '',
                                        'spl': audio_row.get('SPL', 60) if pd.notna(audio_row.get('SPL')) else 60,
                                        'playback_device_id': playback_device_id,
                                        'playback_device_name': str(audio_row.get('PLAYBACK_DEVICE_NAME', '')) if pd.notna(audio_row.get('PLAYBACK_DEVICE_NAME')) else '',
                                        'play_order': audio_row.get('PLAY_ORDER', 0) if pd.notna(audio_row.get('PLAY_ORDER')) else 0
                                    })
                            
                            if dims_df is not None and not dims_df.empty:
                                if 'CASE_ID' in dims_df.columns and case_item['id']:
                                    case_dims = dims_df[dims_df['CASE_ID'].astype(str).str.strip() == case_item['id']]
                                else:
                                    case_dims = dims_df[dims_df['CASE_NAME'] == case_item['name']]

                                for _, dim_row in case_dims.iterrows():
                                    dim_id_val = dim_row.get('DIMENSION_ID')
                                    dim_id = None
                                    try:
                                        dim_id = int(str(dim_id_val).strip()) if pd.notna(dim_id_val) and str(dim_id_val).strip() else None
                                    except Exception:
                                        dim_id = None
                                    case_item['dimensions'].append({
                                        'id': dim_id,
                                        'name': str(dim_row.get('DIMENSION_NAME', '')) if pd.notna(dim_row.get('DIMENSION_NAME')) else '',
                                        'display_name': str(dim_row.get('DIMENSION_DISPLAY_NAME', '')) if pd.notna(dim_row.get('DIMENSION_DISPLAY_NAME')) else '',
                                        'weight': dim_row.get('WEIGHT', 50) if pd.notna(dim_row.get('WEIGHT')) else 50,
                                        'threshold': dim_row.get('THRESHOLD', 80) if pd.notna(dim_row.get('THRESHOLD')) else 80
                                    })
                            
                            test_cases_data.append(case_item)
                    else:
                        df = pd.read_excel(xl)
                        test_cases_data = parse_legacy_format(df)
            else:
                return error_response("仅支持 JSON, CSV 或 Excel 格式的导入")
            
            if not test_cases_data:
                return error_response("导入数据为空")
            
            imported_count = 0
            updated_count = 0
            errors = []
            
            for idx, case_data in enumerate(test_cases_data):
                try:
                    # 1. 确定分组
                    group = None
                    group_id = case_data.get('group_id')
                    group_name = case_data.get('group', '未分类')
                    
                    if group_id:
                        group = TestCaseGroup.query.filter(
                            TestCaseGroup.id == group_id,
                            TestCaseGroup.deleted == False
                        ).first()
                    
                    if not group:
                        group = TestCaseGroup.query.filter_by(name=group_name, deleted=False).first()
                    
                    if not group:
                        # 如果都没有，则创建（注意：如果 group_id 是 UUID 字符串，建议使用 name 创建）
                        group = TestCaseGroup(id=str(uuid.uuid4()) if not group_id else group_id, name=group_name)
                        db.session.add(group)
                        db.session.flush()
                    
                    # 2. 检查是更新还是创建
                    tc_id = case_data.get('id')
                    existing_tc = None
                    if tc_id:
                        # 导入是"恢复"语义：显式放开全局软删过滤，软删用例按 ID 命中后复活
                        # （下方 existing_tc.deleted = False 由 soft_delete 统一清空 deleted_at）
                        with include_deleted():
                            existing_tc = db.session.get(TestCase, tc_id)
                        if not existing_tc:
                            raise Exception(f"UPDATE失败：未找到ID对应的用例: {tc_id}")
                    
                    # 3. 准备配置
                    config = case_data.get('config', {})
                    merged_config = config.copy() if config else {}

                    noise_audio_name = (case_data.get('noise_audio_name') or '').strip()
                    if noise_audio_name == "无":
                        noise_audio_name = ""
                    noise_spl = case_data.get('noise_spl', 0) or 0
                    noise_audio_id = case_data.get('noise_audio_id')
                    resolved_noise_id = None
                    if noise_audio_id:
                        try:
                            resolved_noise_id = int(str(noise_audio_id).strip())
                        except Exception:
                            resolved_noise_id = None

                    if resolved_noise_id is None and noise_audio_name:
                        noise_audio = Audio.query.filter_by(name=noise_audio_name).first()
                        if noise_audio:
                            resolved_noise_id = noise_audio.id

                    if resolved_noise_id is not None or noise_spl:
                        bg_noise_cfg = {}
                        if resolved_noise_id is not None:
                            bg_noise_cfg['audio_id'] = resolved_noise_id
                        if noise_spl:
                            bg_noise_cfg['spl'] = noise_spl
                        if bg_noise_cfg:
                            merged_config['background_noise'] = bg_noise_cfg
                    
                    # 处理音频数据
                    if 'audios' in case_data and case_data['audios']:
                        audios_data = case_data['audios']
                        standard_audios = []
                        for audio_item in audios_data:
                            standard_audios.append({
                                'audio_id': audio_item.get('audio_id'),
                                'spl': audio_item.get('spl'),
                                'playback_device_id': TestCaseController._normalize_optional_int(audio_item.get('playback_device_id')),
                                'play_order': audio_item.get('play_order', 1)
                            })
                        merged_config['audios'] = standard_audios
                    
                    # 处理维度数据（扁平数组格式）
                    if 'dimensions' in case_data and case_data['dimensions']:
                        dimensions_data = case_data['dimensions']
                        if isinstance(dimensions_data, list):
                            dimension_ids = [d.get('id') if isinstance(d, dict) else d for d in dimensions_data]
                            merged_config['dimensions'] = dimension_ids

                    # 转换为 rounds 格式（已有 rounds 的不做转换）
                    if not TestCaseController._has_rounds(merged_config):
                        merged_config = TestCaseController._convert_flat_config_to_rounds(merged_config)

                    # 4. 执行创建或更新
                    if existing_tc:
                        # 更新
                        if existing_tc.deleted:
                            existing_tc.deleted = False
                        existing_tc.name = case_data['name']
                        existing_tc.description = case_data.get('description')
                        existing_tc.group_id = group.id
                        existing_tc.test_type = case_data.get('test_type', 'api')
                        existing_tc.config = merged_config
                        
                        # 清除并重新添加标签
                        existing_tc.tags = []
                        updated_count += 1
                        current_tc = existing_tc
                    else:
                        # 创建
                        new_id = str(uuid.uuid4())
                        current_tc = TestCase(
                            id=new_id,
                            name=case_data['name'],
                            description=case_data.get('description'),
                            group_id=group.id,
                            test_type=case_data.get('test_type', 'api'),
                            config=merged_config
                        )
                        db.session.add(current_tc)
                        imported_count += 1
                    
                    # 5. 处理标签
                    tag_links = case_data.get('tag_links') or []
                    if tag_links:
                        for tag_link in tag_links:
                            tag_id = tag_link.get('tag_id')
                            tag_name = (tag_link.get('tag_name') or '').strip()
                            tag = None
                            if tag_id:
                                tag = db.session.get(Tag, tag_id)
                            if not tag and tag_name:
                                tag = Tag.query.filter_by(name=tag_name).first()
                            if not tag and tag_name:
                                tag = Tag(name=tag_name)
                                db.session.add(tag)
                            if tag:
                                current_tc.tags.append(tag)
                    else:
                        tags_data = case_data.get('tags', [])
                        for tag_name in tags_data:
                            tag = Tag.query.filter_by(name=tag_name).first()
                            if not tag:
                                tag = Tag(name=tag_name)
                                db.session.add(tag)
                            current_tc.tags.append(tag)
                    
                    # 6. 刷新参考文本
                    TestCaseController.refresh_reference_texts(current_tc)
                    
                except Exception as e:
                    errors.append(f"第{idx+1}行: {str(e)}")
            
            db.session.commit()
            
            message = f"成功导入 {imported_count} 个用例，更新 {updated_count} 个用例"
            if errors:
                message += f"，{len(errors)} 个失败: {'; '.join(errors[:5])}"
                if len(errors) > 5:
                    message += f" ... (共{len(errors)}个错误)"
            
            return success_response(TestCaseImportResult(imported_count=imported_count, errors=errors), message)
            
        except json.JSONDecodeError as e:
            return error_response(f"JSON解析错误: {str(e)}")
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    @staticmethod
    def _read_interruption_package(file):
        if (file.filename or '').lower().endswith('.zip') is False:
            raise ValueError("打断测试包必须是 ZIP 格式")

        archive = zipfile.ZipFile(file.stream, mode='r')
        try:
            names = _safe_interruption_zip_names(archive.namelist())
            zip_root = _find_interruption_zip_root(names)
            report_path = 'report.json' if not zip_root else f'{zip_root}report.json'
            report = json.loads(archive.read(report_path).decode('utf-8-sig'))
            report_cases = report.get('cases') if isinstance(report, dict) else None
            if not isinstance(report_cases, list) or not report_cases:
                raise ValueError("report.json 中没有可导入的 cases")

            path_mapping = {}
            report_case_by_uid = {
                str(report_case.get('case_uid') or report_case.get('id') or ''): report_case
                for report_case in report_cases
            }
            for report_case in report_cases:
                for file_item in report_case.get('files', []):
                    logical_path = _normalize_interruption_path(file_item.get('path'))
                    actual_path = _normalize_interruption_path(file_item.get('key'))
                    if logical_path and actual_path and actual_path in names:
                        path_mapping[logical_path] = actual_path
            for attempt in report.get('attempts', []):
                case_uid = str(
                    attempt.get('case_uid')
                    or (attempt.get('case') or {}).get('case_uid')
                    or ''
                ).strip()
                if not case_uid:
                    continue
                for file_item in (attempt.get('result') or {}).get('artifacts', []):
                    filename = _normalize_interruption_path(file_item.get('path'))
                    actual_path = _normalize_interruption_path(file_item.get('key'))
                    if not actual_path or actual_path not in names:
                        report_case = report_case_by_uid.get(case_uid, {})
                        case_folder = _normalize_interruption_path(
                            report_case.get('relative_path') or ''
                        )
                        if case_folder.endswith('.json'):
                            case_folder = case_folder[:-len('.json')]
                        direct_path = _normalize_interruption_path(
                            f'{zip_root}{case_folder}/result/{filename}'
                        )
                        if direct_path in names:
                            actual_path = direct_path
                    if filename and actual_path and actual_path in names:
                        path_mapping[f'cases/{case_uid}/result/{filename}'] = actual_path

            return {
                'archive': archive,
                'report': report,
                'cases': report_cases,
                'names': names,
                'zip_root': zip_root,
                'path_mapping': path_mapping,
            }
        except Exception:
            archive.close()
            raise

    @staticmethod
    def _read_interruption_file(package, logical_path):
        actual_path = _resolve_interruption_zip_entry(
            logical_path,
            package['names'],
            package['path_mapping'],
        )
        if not actual_path:
            raise ValueError(f"ZIP 包中未找到文件: {logical_path}")
        return package['archive'].read(actual_path)

    @staticmethod
    def _interruption_preview_items(package):
        items = []
        attempt_count = 0
        result_audio_count = 0
        report = package['report']
        dataset_id = str(report.get('id') or '')
        existing_task = TestCaseController._find_interruption_task(dataset_id)

        for attempt in report.get('attempts', []):
            case_info = attempt.get('case') or {}
            case_uid = str(attempt.get('case_uid') or case_info.get('case_uid') or case_info.get('id') or '').strip()
            outcome = ((attempt.get('result') or {}).get('outcome')
                       or attempt.get('state')
                       or 'unknown')
            has_result_audio = any(
                artifact.get('path') in ('input-actual.wav', 'live-output.wav')
                for artifact in (attempt.get('result') or {}).get('artifacts', [])
            )
            attempt_count += 1
            if has_result_audio:
                result_audio_count += 1

            items.append({
                'ID': dataset_id,
                'EXISTING': bool(existing_task),
                'NAME': case_info.get('title') or f"打断执行记录 {case_uid}",
                'DESCRIPTION': f"历史执行结果：{outcome}",
                'GROUP_NAME': case_info.get('group_path') or '未分类',
                'TEST_TYPE': 'e2e',
                'CASE_UID': case_uid,
                'OUTCOME': outcome,
                'HAS_RESULT_AUDIO': has_result_audio,
            })
        return items, attempt_count, result_audio_count

    @staticmethod
    def preview_interruption_package():
        try:
            if 'file' not in request.files:
                return error_response("未上传文件")
            file = request.files['file']
            if not file.filename:
                return error_response("未选择文件")

            package = TestCaseController._read_interruption_package(file)
            report = package['report']
            dataset_label = report.get('id') or 'unknown'
            try:
                items, attempt_count, result_audio_count = TestCaseController._interruption_preview_items(package)
            finally:
                package['archive'].close()

            return success_response({
                'packageType': 'interruption',
                'totalRows': len(items),
                'testCases': items,
                'audioConfigsCount': attempt_count,
                'resultAudioCount': result_audio_count,
                'taskName': f"打断历史任务_{dataset_label}",
                'reportName': f"打断历史报告_{dataset_label}",
                'importTarget': 'task-report',
                'errors': [],
            })
        except Exception as e:
            return error_response(f"打断测试包预览失败: {str(e)}")

    @staticmethod
    def _get_or_create_interruption_group(group_name):
        group = TestCaseGroup.query.filter_by(
            name=group_name,
            algorithm_type='voice_llm',
            deleted=False,
        ).first()
        if group:
            return group
        group = TestCaseGroup(
            id=str(uuid.uuid4()),
            name=group_name,
            description='外部打断测试包自动创建的分组',
            algorithm_type='voice_llm',
        )
        db.session.add(group)
        db.session.flush()
        return group

    @staticmethod
    def _resolve_interruption_device(device_name):
        device = None
        if device_name:
            device = PlaybackDevice.query.filter_by(name=device_name, is_deleted=0).first()
        if not device:
            device = PlaybackDevice.query.filter_by(device_type='dry', is_deleted=0).first()
        if not device:
            raise ValueError("未找到可用于打断用例的信号播放设备，请先配置播放设备")
        return device

    @staticmethod
    def _save_interruption_audio(package, logical_path, relative_path, original_filename):
        content = TestCaseController._read_interruption_file(package, logical_path)
        md5 = _interruption_md5(content)
        existing_audio = Audio.query.filter_by(md5=md5, deleted=False).first()
        if existing_audio:
            return existing_audio

        metadata = AudioController._save_audio(
            _MemoryAudioFile(original_filename, content),
            relative_path=relative_path,
        )
        audio = Audio(
            name=metadata['name'],
            original_filename=original_filename,
            file_path=metadata['file_path'],
            size=metadata['size'],
            duration=metadata['duration'],
            sample_rate=metadata['sample_rate'],
            channels=metadata['channels'],
            bitrate=metadata['bitrate'],
            format=metadata['format'],
            audio_type='dry',
            md5=md5,
            description='外部打断测试包导入的播放音源',
        )
        db.session.add(audio)
        db.session.flush()
        return audio

    @staticmethod
    def _save_interruption_result_audio(package, report_case, result_dir):
        logical_paths = {
            'user_wav': 'result/input-actual.wav',
            'ai_wav': 'result/live-output.wav',
            'record_file': 'result/conversation.wav',
        }
        file_items = {
            _normalize_interruption_path(file_item.get('path', '')): file_item
            for file_item in report_case.get('files', [])
        }
        saved_paths = {}
        for key, logical_name in logical_paths.items():
            logical_path = f"cases/{report_case.get('case_uid')}/{logical_name}"
            if logical_path not in file_items and key != 'record_file':
                raise ValueError(f"用例 {report_case.get('case_uid')} 缺少 {logical_name}")
            if logical_path not in file_items:
                continue

            target_path = os.path.join(result_dir, logical_name.replace('/', os.sep))
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            with open(target_path, 'wb') as output:
                output.write(TestCaseController._read_interruption_file(package, logical_path))
            saved_paths[key] = {
                'source_path': logical_path,
                'file_path': target_path.replace('\\', '/'),
            }
        return saved_paths

    @staticmethod
    def import_interruption_package():
        return TestCaseController.import_interruption_task_report()

        try:
            if 'file' not in request.files:
                return error_response("未上传文件")
            file = request.files['file']
            if not file.filename:
                return error_response("未选择文件")

            package = TestCaseController._read_interruption_package(file)
            imported_count = 0
            updated_count = 0
            errors = []
            try:
                report = package['report']
                dataset_id = str(report.get('id') or uuid.uuid4())
                storage_root = current_app.config.get('AUDIO_STORAGE_PATH')

                for index, report_case in enumerate(package['cases'], 1):
                    try:
                        case_transaction = db.session.begin_nested()
                        case_uid = str(report_case.get('case_uid') or report_case.get('id') or '').strip()
                        if not case_uid:
                            raise ValueError("缺少 case_uid")
                        case_id = f"INT-{case_uid}"
                        source = json.loads(
                            TestCaseController._read_interruption_file(
                                package,
                                report_case.get('source_json') or f"cases/{case_uid}/source.json",
                            ).decode('utf-8-sig')
                        )

                        report_segments = {}
                        for segment in report_case.get('segments', []):
                            segment_id = segment.get('id')
                            if segment_id:
                                report_segments[segment_id] = segment

                        rounds = []
                        for round_item in source.get('rounds', []):
                            round_number = int(round_item.get('round_number') or len(rounds) + 1)
                            audios = []
                            for play_order, segment in enumerate(round_item.get('segments', [])):
                                segment_id = segment.get('id') or f"r{round_number:03d}-s{play_order + 1:03d}"
                                report_segment = report_segments.get(segment_id, {})
                                logical_audio = report_segment.get('pcm_audio') or f"cases/{case_uid}/pcm/{segment_id}.wav"
                                original_filename = os.path.basename(str(segment.get('audio') or f'{segment_id}.wav'))
                                audio = TestCaseController._save_interruption_audio(
                                    package,
                                    logical_audio,
                                    f"interruption_packages/{dataset_id}/{case_uid}/pcm/{segment_id}.wav",
                                    original_filename,
                                )
                                device = TestCaseController._resolve_interruption_device(
                                    segment.get('playback_device_name'),
                                )
                                audios.append({
                                    'audio_id': audio.id,
                                    'audio_name': original_filename,
                                    'spl': segment.get('spl', 65),
                                    'playback_device_id': device.id,
                                    'playback_device_name': device.name,
                                    'play_order': play_order,
                                    'source': {
                                        'query': segment.get('query'),
                                        'input_text': segment.get('input_text'),
                                        'timing': segment.get('timing'),
                                        'trigger': report_segment.get('trigger'),
                                        'is_interruption': segment.get('is_interruption'),
                                    },
                                })
                            rounds.append({
                                'round_number': round_number,
                                'audios': audios,
                            })

                        if not rounds:
                            raise ValueError("source.json 中没有 rounds 配置")

                        result_audio = TestCaseController._save_interruption_result_audio(
                            package,
                            report_case,
                            os.path.join(storage_root, 'interruption_packages', dataset_id, case_uid),
                        )
                        config = {
                            'rounds': rounds,
                            'source_audio': report_case.get('relative_path'),
                            'auto_generated': False,
                            'result_audio': result_audio,
                        }

                        group = TestCaseController._get_or_create_interruption_group(
                            report_case.get('group_path') or '打断测试',
                        )
                        with include_deleted():
                            existing_tc = db.session.get(TestCase, case_id)
                        if existing_tc:
                            if existing_tc.deleted:
                                existing_tc.deleted = False
                            existing_tc.name = report_case.get('title') or case_id
                            existing_tc.description = f"外部打断测试包导入；原ID: {report_case.get('original_id', '')}；数据集: {dataset_id}"
                            existing_tc.group_id = group.id
                            existing_tc.algorithm_type = 'voice_llm'
                            existing_tc.test_type = 'e2e'
                            existing_tc.config = config
                            existing_tc.tags = []
                            current_tc = existing_tc
                            updated_count += 1
                        else:
                            current_tc = TestCase(
                                id=case_id,
                                name=report_case.get('title') or case_id,
                                description=f"外部打断测试包导入；原ID: {report_case.get('original_id', '')}；数据集: {dataset_id}",
                                group_id=group.id,
                                algorithm_type='voice_llm',
                                test_type='e2e',
                                config=config,
                            )
                            db.session.add(current_tc)
                            imported_count += 1

                        for tag_name in ('打断测试', '外部导入'):
                            tag = Tag.query.filter_by(name=tag_name).first()
                            if not tag:
                                tag = Tag(name=tag_name)
                                db.session.add(tag)
                            current_tc.tags.append(tag)

                        TestCaseController.refresh_reference_texts(current_tc)
                        case_transaction.commit()
                    except Exception as case_error:
                        case_transaction.rollback()
                        errors.append(f"第{index}个用例 {report_case.get('case_uid', '')}: {str(case_error)}")

                db.session.commit()
            finally:
                package['archive'].close()

            message = f"成功导入 {imported_count} 个打断用例，更新 {updated_count} 个打断用例"
            if errors:
                message += f"，{len(errors)} 个失败: {'; '.join(errors[:5])}"
                if len(errors) > 5:
                    message += f" ... (共{len(errors)}个错误)"
            return success_response(
                TestCaseImportResult(imported_count=imported_count, errors=errors),
                message,
            )
        except Exception as e:
            db.session.rollback()
            return error_response(f"打断测试包导入失败: {str(e)}")

    @staticmethod
    def _find_interruption_task(dataset_id):
        if not dataset_id:
            return None
        return Task.query.filter(
            Task.config.cast(db.Text).like(f'%{dataset_id}%'),
            Task.deleted == False,
        ).first()

    @staticmethod
    def _find_imported_task(import_source, dataset_id):
        if not dataset_id:
            return None
        candidates = Task.query.filter(
            Task.config.cast(db.Text).like(f'%{dataset_id}%'),
            Task.deleted == False,
        ).all()
        for task in candidates:
            if (task.config or {}).get('import_source') == import_source:
                return task
        return None

    @staticmethod
    def reevaluate_interruption_task(task_id):
        task = Task.query.filter_by(id=task_id, deleted=False).first()
        if not task:
            raise ValueError("未找到导入的打断任务")
        config = task.config or {}
        import_source = config.get('import_source')
        if import_source not in ('interruption_package', 'evaluation_result_package'):
            raise ValueError("该任务不是历史测试包导入任务")
        resource_name = '历史打断执行' if import_source == 'interruption_package' else '历史评分执行'
        resource_tags = (
            ['历史导入', '打断测试']
            if import_source == 'interruption_package'
            else ['历史导入', '评分结果']
        )

        report_record = Report.query.filter_by(task_id=task.id, deleted=False).first()
        if not report_record:
            raise ValueError("未找到导入任务对应的报告")
        report_cases = ReportCase.query.filter_by(report_id=report_record.id).order_by(ReportCase.id).all()
        if not report_cases:
            raise ValueError("报告中没有可重新评估的执行记录")

        def as_json(value, fallback):
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except (TypeError, ValueError):
                    return fallback
            return value if value is not None else fallback

        completed_count = 0
        failed_count = 0
        metric_values = {}
        category_stats = {}
        durations = []
        for report_case in report_cases:
            results = as_json(report_case.results, [])
            outcome = ''
            if results and isinstance(results[0], dict):
                outcome = results[0].get('outcome') or results[0].get('state') or ''
            if outcome == 'completed':
                completed_count += 1
            else:
                failed_count += 1

            case_metrics = {}
            for resource_item in as_json(report_case.metrics, []):
                if not isinstance(resource_item, dict):
                    continue
                for metric_item in resource_item.get('metrics') or []:
                    if not isinstance(metric_item, dict):
                        continue
                    metric_name = metric_item.get('metric')
                    metric_value = metric_item.get('value')
                    if metric_name and isinstance(metric_value, (int, float)):
                        metric_values.setdefault(metric_name, []).append(metric_value)
                        case_metrics[metric_name] = metric_value
            category = report_case.category or '未分类'
            category_stats.setdefault(category, []).append(case_metrics)
            if isinstance(case_metrics.get('duration_ms'), (int, float)):
                durations.append(case_metrics['duration_ms'] / 1000)

        metric_names = [
            metric_code for metric_code, _, _, _ in INTERRUPTION_METRIC_DEFINITIONS
            if metric_values.get(metric_code)
        ]
        averages = {
            metric_name: round(sum(metric_values[metric_name]) / len(metric_values[metric_name]), 2)
            for metric_name in metric_names
            if metric_values.get(metric_name)
        }
        all_metrics = [
            {
                'id': metric_code,
                'name': metric_name,
                'unit': unit,
                'decimal_places': decimal_places,
            }
            for metric_code, metric_name, unit, decimal_places in INTERRUPTION_METRIC_DEFINITIONS
            if metric_values.get(metric_code)
        ]
        dimension_values = [
            {
                'id': metric_code,
                'name': metric_name,
                'average_value': averages.get(metric_code),
            }
            for metric_code, metric_name, _, _ in INTERRUPTION_METRIC_DEFINITIONS
            if metric_values.get(metric_code)
        ]
        case_type_stats = []
        for category, category_items in category_stats.items():
            category_metrics = []
            for metric_code, _, _, _ in INTERRUPTION_METRIC_DEFINITIONS:
                values = [
                    item.get(metric_code)
                    for item in category_items
                    if isinstance(item.get(metric_code), (int, float))
                ]
                if values:
                    category_metrics.append({
                        'metric': metric_code,
                        'value': round(sum(values) / len(values), 2),
                    })
            case_type_stats.append({
                'groupId': category,
                'groupName': category,
                'metrics': category_metrics,
            })

        old_meta = ReportSummaryMeta.query.filter_by(report_id=report_record.id).first()
        raw_devices = as_json(old_meta.devices, []) if old_meta else []
        devices = []
        for index, device in enumerate(raw_devices):
            if isinstance(device, dict):
                devices.append(device)
            elif device:
                devices.append({'id': index + 1, 'name': str(device)})
        apis = as_json(old_meta.apis, []) if old_meta else []

        for model in (ReportSummary, ReportSummaryMeta, ReportRawData, ReportMetricStats):
            model.query.filter_by(report_id=report_record.id).delete(synchronize_session=False)

        task.status = TaskStatus.COMPLETED.value
        task.total_cases = len(report_cases)
        task.completed_cases = completed_count
        task.failed_cases = failed_count
        task.actual_duration = round(sum(durations), 2)
        task.updated_at = now_cst()
        task.completed_at = task.completed_at or task.created_at or now_cst()
        report_record.status = ReportStatus.PUBLISHED.value
        report_record.updated_at = now_cst()

        db.session.add(ReportSummary(
            report_id=report_record.id,
            task_ids=[task.id],
            total_cases=len(report_cases),
            completed_cases=completed_count,
            failed_cases=failed_count,
            pass_rate=round(completed_count / len(report_cases) * 100, 2),
            duration=task.actual_duration,
            started_at=task.started_at,
            completed_at=task.completed_at,
        ))
        db.session.add(ReportSummaryMeta(
            report_id=report_record.id,
            dimension_values=json.dumps(dimension_values, ensure_ascii=False),
            case_categories=json.dumps(sorted(category_stats.keys()), ensure_ascii=False),
            all_case_tags=json.dumps(resource_tags, ensure_ascii=False),
            devices=json.dumps(devices, ensure_ascii=False),
            apis=json.dumps(apis, ensure_ascii=False),
            resources=json.dumps([resource_name], ensure_ascii=False),
            resource_headers=json.dumps([{
                'key': resource_name,
                'label': resource_name,
                'type': 'unknown',
                'id': None,
                'name': resource_name,
                'version': None,
                'result_type': None,
                'editable': False,
            }], ensure_ascii=False),
            all_metrics=json.dumps(all_metrics, ensure_ascii=False),
            field_mappings=json.dumps({}, ensure_ascii=False),
        ))
        db.session.add(ReportRawData(
            report_id=report_record.id,
            raw_data=json.dumps({resource_name: metric_values}, ensure_ascii=False),
        ))
        db.session.add(ReportMetricStats(
            report_id=report_record.id,
            metric_data=json.dumps({resource_name: averages}, ensure_ascii=False),
            tag_metric_data=json.dumps({}, ensure_ascii=False),
            tag_category_metric_data=json.dumps({}, ensure_ascii=False),
            case_type_stats=json.dumps(case_type_stats, ensure_ascii=False),
            device_stats=json.dumps([], ensure_ascii=False),
            api_stats=json.dumps([], ensure_ascii=False),
        ))
        db.session.commit()
        return {
            'task_id': task.id,
            'report_id': report_record.id,
            'total_cases': len(report_cases),
            'completed_cases': completed_count,
            'failed_cases': failed_count,
            'metric_count': len(metric_names),
        }

    @staticmethod
    def _interruption_datetime(value):
        try:
            if isinstance(value, (int, float)):
                return datetime.fromtimestamp(value, timezone(timedelta(hours=8)))
        except (TypeError, ValueError, OSError):
            pass
        return now_cst()

    @staticmethod
    def _read_interruption_result_json(package, case_uid, filename):
        logical_path = f'cases/{case_uid}/result/{filename}'
        try:
            return json.loads(TestCaseController._read_interruption_file(package, logical_path).decode('utf-8-sig'))
        except Exception:
            return {}

    @staticmethod
    def _save_interruption_artifact(package, dataset_id, case_uid, filename):
        logical_path = f'cases/{case_uid}/result/{filename}'
        content = TestCaseController._read_interruption_file(package, logical_path)
        relative_path = f'case_result/interruption_packages/{dataset_id}/{case_uid}/{filename}'
        target_path = os.path.join(
            current_app.config.get('STATIC_BASE_PATH'),
            *relative_path.split('/'),
        )
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, 'wb') as output:
            output.write(content)
        return {
            'filename': filename,
            'url': f'/static/{relative_path}',
            'size': len(content),
        }

    @staticmethod
    def _interruption_case_metrics(status_data, evaluation_data, segments):
        steps = evaluation_data.get('steps') or []
        trigger_errors = [step.get('trigger_error_ms') for step in steps if isinstance(step.get('trigger_error_ms'), (int, float))]
        input_end_outputs = [step.get('input_end_output_ms') for step in steps if isinstance(step.get('input_end_output_ms'), (int, float))]
        detected = sum(1 for step in steps if step.get('audio_output_detected') is True)
        round_count = len(segments or [])
        completed_steps = sum(1 for step in steps if step.get('status') == 'played')
        values = {
            'duration_ms': status_data.get('duration_ms'),
            'turns': status_data.get('turns'),
            'round_count': round_count,
            'completed_step_count': completed_steps,
            'trigger_error_ms': round(sum(trigger_errors) / len(trigger_errors), 2) if trigger_errors else None,
            'input_end_output_ms': round(sum(input_end_outputs) / len(input_end_outputs), 2) if input_end_outputs else None,
            'audio_output_detected_rate': round(detected / len(steps) * 100, 2) if steps else None,
        }
        return {key: value for key, value in values.items() if value is not None}

    @staticmethod
    def _build_interruption_report_case(package, report, dataset_id, attempt):
        case_info = attempt.get('case') or {}
        case_uid = str(attempt.get('case_uid') or case_info.get('case_uid') or case_info.get('id') or '')
        result = attempt.get('result') or {}
        status_data = TestCaseController._read_interruption_result_json(package, case_uid, 'status.json')
        evaluation_data = TestCaseController._read_interruption_result_json(package, case_uid, 'evaluation-result.json')
        metrics = TestCaseController._interruption_case_metrics(
            status_data,
            evaluation_data,
            case_info.get('segments'),
        )

        audio_entries = []
        for filename, label in (
            ('input-actual.wav', '用户实际输入'),
            ('live-output.wav', 'AI实时输出'),
            ('conversation.wav', '完整对话录音'),
        ):
            try:
                audio_entry = TestCaseController._save_interruption_artifact(
                    package, dataset_id, case_uid, filename,
                )
                audio_entry['label'] = label
                audio_entries.append(audio_entry)
            except Exception:
                continue

        algorithm_results = []
        for metric_name, metric_value in metrics.items():
            algorithm_results.append({
                'device': '历史打断执行',
                'param_code': metric_name,
                'param_type': 'number',
                'label': metric_name,
                'value': metric_value,
                'round_number': None,
                'dimension_name': None,
            })
        for audio_entry in audio_entries:
            algorithm_results.append({
                'device': '历史打断执行',
                'param_code': audio_entry['filename'],
                'param_type': 'audio_file',
                'label': audio_entry['label'],
                'value': audio_entry['url'],
                'round_number': None,
                'dimension_name': None,
            })

        reference_params = {}
        for segment in case_info.get('segments', []):
            source_info = segment.get('source') or {}
            reference_params[str(segment.get('round_number'))] = {
                'query': source_info.get('query'),
                'input_text': source_info.get('input_text'),
                'timing': source_info.get('timing'),
                'trigger': segment.get('trigger'),
            }

        return {
            'test_case_id': None,
            'name': case_info.get('title') or case_uid,
            'description': f"历史打断执行记录；原ID: {case_info.get('original_id', '')}",
            'category': case_info.get('group_path') or '未分类',
            'tags': ['历史导入', '打断测试'],
            'metrics': [{
                'resource': '历史打断执行',
                'metrics': [
                    {'metric': metric_name, 'value': metric_value}
                    for metric_name, metric_value in metrics.items()
                ],
            }],
            'results': [{
                'resource': '历史打断执行',
                'outcome': result.get('outcome') or attempt.get('state'),
                'state': result.get('state') or attempt.get('state'),
                'archive': result.get('archive'),
                'scoring': result.get('scoring'),
                'status': status_data,
                'evaluation': {
                    'schema': evaluation_data.get('schema'),
                    'status': evaluation_data.get('status'),
                    'steps': evaluation_data.get('steps', []),
                    'final_reply': evaluation_data.get('final_reply'),
                },
            }],
            'audios': audio_entries,
            'reference_params': reference_params,
            'algorithm_results': algorithm_results,
            'algorithm_type': 'voice_llm',
            'logs': json.dumps({
                'attempt_id': attempt.get('id'),
                'rerun_count': attempt.get('rerun_count'),
                'package_id': report.get('id'),
            }, ensure_ascii=False),
        }

    @staticmethod
    def _create_or_update_interruption_task_report(package):
        report = package['report']
        dataset_id = str(report.get('id') or uuid.uuid4())
        attempts = report.get('attempts') or []
        if not attempts:
            raise ValueError("report.json 中没有 attempts 执行记录")

        completed_count = sum(
            1 for attempt in attempts
            if (attempt.get('result') or {}).get('outcome') == 'completed'
            or attempt.get('state') == 'completed'
        )
        failed_count = len(attempts) - completed_count
        durations = []
        for attempt in attempts:
            case_uid = attempt.get('case_uid') or (attempt.get('case') or {}).get('case_uid')
            status_data = TestCaseController._read_interruption_result_json(package, case_uid, 'status.json')
            if isinstance(status_data.get('duration_ms'), (int, float)):
                durations.append(status_data['duration_ms'] / 1000)

        task_config = {
            'import_source': 'interruption_package',
            'dataset_id': dataset_id,
            'package_id': report.get('id'),
            'revision': report.get('revision'),
            'state': report.get('state'),
            'options': report.get('options', {}),
        }
        task = TestCaseController._find_interruption_task(dataset_id)
        if task:
            if task.deleted:
                task.deleted = False
            task.name = f"打断历史任务_{report.get('id')}"
            task.description = '外部全双工打断测试包导入的历史任务记录'
            task.type = 'e2e'
            task.status = TaskStatus.COMPLETED.value
            task.config = task_config
            task.algorithm_type = 'voice_llm'
            task.total_cases = len(attempts)
            task.completed_cases = completed_count
            task.failed_cases = failed_count
            task.created_at = TestCaseController._interruption_datetime(report.get('created_at'))
            task.updated_at = now_cst()
            task.started_at = task.created_at
            task.completed_at = task.created_at
            task.actual_duration = round(sum(durations), 2)
            created = False
        else:
            task = Task(
                name=f"打断历史任务_{report.get('id')}",
                description='外部全双工打断测试包导入的历史任务记录',
                type='e2e',
                status=TaskStatus.COMPLETED.value,
                config=task_config,
                algorithm_type='voice_llm',
                total_cases=len(attempts),
                completed_cases=completed_count,
                failed_cases=failed_count,
                created_at=TestCaseController._interruption_datetime(report.get('created_at')),
                started_at=TestCaseController._interruption_datetime(report.get('created_at')),
                completed_at=TestCaseController._interruption_datetime(report.get('created_at')),
                actual_duration=round(sum(durations), 2),
                execution_source='manual',
            )
            db.session.add(task)
            db.session.flush()
            created = True

        report_cases = [
            TestCaseController._build_interruption_report_case(package, report, dataset_id, attempt)
            for attempt in attempts
        ]
        metric_names = []
        metric_values = {}
        category_stats = {}
        devices = set()
        for case_item, attempt in zip(report_cases, attempts):
            case_metrics = {}
            for resource_item in case_item['metrics']:
                for metric_item in resource_item['metrics']:
                    metric_name = metric_item['metric']
                    metric_value = metric_item['value']
                    if isinstance(metric_value, (int, float)):
                        metric_names.append(metric_name)
                        metric_values.setdefault(metric_name, []).append(metric_value)
                        case_metrics[metric_name] = metric_value
            category = case_item['category']
            category_stats.setdefault(category, []).append(case_metrics)
            for segment in (attempt.get('case') or {}).get('segments', []):
                device_name = (segment.get('source') or {}).get('playback_device_name')
                if device_name:
                    devices.add(device_name)
        device_infos = []
        for index, device_name in enumerate(sorted(devices)):
            device = PlaybackDevice.query.filter_by(name=device_name, is_deleted=0).first()
            device_infos.append({
                'id': device.id if device else index + 1,
                'name': device_name,
            })

        metric_names = sorted(set(metric_names))
        averages = {
            metric_name: round(sum(metric_values[metric_name]) / len(metric_values[metric_name]), 2)
            for metric_name in metric_names
            if metric_values.get(metric_name)
        }
        all_metrics = [
            {'id': metric_name, 'name': metric_name, 'unit': 'ms' if metric_name.endswith('_ms') else '', 'decimal_places': 2}
            for metric_name in metric_names
        ]
        dimension_values = [
            {'id': metric_name, 'name': metric_name, 'average_value': metric_value}
            for metric_name, metric_value in averages.items()
        ]
        case_type_stats = []
        for category, category_items in category_stats.items():
            category_metrics = []
            for metric_name in metric_names:
                values = [item.get(metric_name) for item in category_items if isinstance(item.get(metric_name), (int, float))]
                if values:
                    category_metrics.append({
                        'metric': metric_name,
                        'value': round(sum(values) / len(values), 2),
                    })
            case_type_stats.append({
                'groupId': category,
                'groupName': category,
                'metrics': category_metrics,
            })

        report_record = Report.query.filter_by(task_id=task.id, deleted=False).first()
        if report_record:
            for model in (ReportSummary, ReportSummaryMeta, ReportRawData, ReportCase, ReportMetricStats):
                model.query.filter_by(report_id=report_record.id).delete(synchronize_session=False)
            report_record.name = f"打断历史报告_{report.get('id')}"
            report_record.description = '外部全双工打断测试包导入的历史任务报告'
            report_record.algorithm_type = 'voice_llm'
            report_record.status = ReportStatus.PUBLISHED.value
            report_record.updated_at = now_cst()
        else:
            report_record = Report(
                name=f"打断历史报告_{report.get('id')}",
                type=ReportType.TASK.value,
                task_id=task.id,
                description='外部全双工打断测试包导入的历史任务报告',
                algorithm_type='voice_llm',
                status=ReportStatus.PUBLISHED.value,
            )
            db.session.add(report_record)
            db.session.flush()

        summary_info = ReportSummary(
            report_id=report_record.id,
            task_ids=[task.id],
            total_cases=len(report_cases),
            completed_cases=completed_count,
            failed_cases=failed_count,
            pass_rate=round(completed_count / len(report_cases) * 100, 2) if report_cases else 0,
            duration=task.actual_duration,
            started_at=task.started_at,
            completed_at=task.completed_at,
        )
        db.session.add(summary_info)
        db.session.add(ReportSummaryMeta(
            report_id=report_record.id,
            dimension_values=json.dumps(dimension_values, ensure_ascii=False),
            case_categories=json.dumps(sorted(category_stats.keys()), ensure_ascii=False),
            all_case_tags=json.dumps(['历史导入', '打断测试'], ensure_ascii=False),
            devices=json.dumps(device_infos, ensure_ascii=False),
            apis=json.dumps([], ensure_ascii=False),
            resources=json.dumps(['历史打断执行'], ensure_ascii=False),
            resource_headers=json.dumps([{
                'key': '历史打断执行',
                'label': '历史打断执行',
                'type': 'unknown',
                'id': None,
                'name': '历史打断执行',
                'version': None,
                'result_type': None,
                'editable': False,
            }], ensure_ascii=False),
            all_metrics=json.dumps(all_metrics, ensure_ascii=False),
            field_mappings=json.dumps({}, ensure_ascii=False),
        ))
        db.session.add(ReportRawData(
            report_id=report_record.id,
            raw_data=json.dumps({'历史打断执行': metric_values}, ensure_ascii=False),
        ))
        for case_item in report_cases:
            db.session.add(ReportCase(report_id=report_record.id, **case_item))
        db.session.add(ReportMetricStats(
            report_id=report_record.id,
            metric_data=json.dumps({'历史打断执行': averages}, ensure_ascii=False),
            tag_metric_data=json.dumps({}, ensure_ascii=False),
            tag_category_metric_data=json.dumps({}, ensure_ascii=False),
            case_type_stats=json.dumps(case_type_stats, ensure_ascii=False),
            device_stats=json.dumps([], ensure_ascii=False),
            api_stats=json.dumps([], ensure_ascii=False),
        ))
        db.session.commit()
        return task, report_record, created

    @staticmethod
    def import_interruption_task_report():
        try:
            if 'file' not in request.files:
                return error_response("未上传文件")
            file = request.files['file']
            if not file.filename:
                return error_response("未选择文件")

            package = TestCaseController._read_interruption_package(file)
            try:
                task, report_record, created = TestCaseController._create_or_update_interruption_task_report(package)
            finally:
                package['archive'].close()

            return success_response({
                'taskId': task.id,
                'reportId': report_record.id,
                'importedCount': 1 if created else 0,
                'updatedCount': 0 if created else 1,
                'errors': [],
            }, '打断历史任务和报告导入成功')
        except Exception as e:
            db.session.rollback()
            return error_response(f"打断历史任务和报告导入失败: {str(e)}")

    @staticmethod
    def _read_evaluation_result_package(file):
        if (file.filename or '').lower().endswith('.json') is False:
            raise ValueError("评分结果包必须是 JSON 格式")
        content = file.stream.read()
        report = json.loads(content.decode('utf-8-sig'))
        cases = report.get('cases') if isinstance(report, dict) else None
        if not isinstance(cases, list) or not cases:
            raise ValueError("评分结果 JSON 中没有可导入的 cases")
        if any(not (case_item.get('case') and case_item.get('title')) for case_item in cases):
            raise ValueError("评分结果中存在缺少 case 或 title 的记录")
        return {
            'content': content,
            'sha256': hashlib.sha256(content).hexdigest(),
            'report': report,
            'cases': cases,
        }

    @staticmethod
    def _evaluation_targets(package):
        targets = {}
        for case_item in package['cases']:
            run_id = str(case_item.get('run') or '').strip()
            if not run_id or run_id in targets:
                continue
            target_list = []
            tasks = Task.query.filter(
                Task.config.cast(db.Text).like(f'%{run_id}%'),
                Task.deleted == False,
            ).order_by(Task.id).all()
            for task in tasks:
                if (task.config or {}).get('dataset_id') != run_id:
                    continue
                report_record = Report.query.filter_by(
                    task_id=task.id, deleted=False,
                ).order_by(Report.id).first()
                if report_record:
                    target_list.append((task, report_record))
            if target_list:
                targets[run_id] = target_list
        return targets

    @staticmethod
    def _split_case_codes(task):
        return {
            str(code).strip().upper()
            for code in ((task.config or {}).get('split_case_codes') or [])
            if str(code).strip()
        }

    @staticmethod
    def _evaluation_target_for_case(run_targets, case_code):
        normalized_code = str(case_code or '').strip().upper()
        for task, report_record in run_targets:
            if normalized_code in TestCaseController._split_case_codes(task):
                return task, report_record
        for task, report_record in run_targets:
            if not TestCaseController._split_case_codes(task):
                return task, report_record
        return None

    @staticmethod
    def _evaluation_case_metrics(case_item):
        raw_result = case_item.get('raw_platform_result') or {}
        interruption = raw_result.get('interruption') or {}
        primary_metrics = case_item.get('primary_metrics') or {}
        metrics = {}
        for metric_name, metric_code in INTERRUPTION_METRIC_FIELDS.items():
            metric_value = interruption.get(metric_code, primary_metrics.get(metric_code))
            if isinstance(metric_value, bool):
                metric_value = int(metric_value)
            metrics[metric_name] = metric_value if isinstance(metric_value, (int, float)) else None
        return metrics

    @staticmethod
    def _evaluation_dimensions():
        dimensions = Dimension.query.filter(
            Dimension.task_type_code == 'interruption_metrics',
            Dimension.deleted == False,
            Dimension.status == True,
        ).order_by(Dimension.sort_order, Dimension.id).all()
        if not dimensions:
            raise ValueError("未找到打断评估维度配置")
        return dimensions

    @staticmethod
    def _evaluation_all_metrics(dimensions):
        dim_id_to_name = {dim.id: dim.name for dim in dimensions}
        return [{
            'id': dim.id,
            'name': dim.name,
            'unit': '%' if (dim.statistic_method or 'average') in ('pass_rate', 'ratio', 'weighted_sum_ratio', 'weighted_wer') else (dim.score_unit or ''),
            'decimal_places': dim.decimal_places if dim.decimal_places is not None else 2,
            'statistic_method': dim.statistic_method or 'average',
            'agg_denominator': dim.agg_denominator or 'case',
            'sort_order': dim.sort_order or 0,
            'dimension_type': dim.dimension_type or 'main',
            'parent_dimension_id': dim.parent_dimension_id,
            'parent_dimension_name': dim_id_to_name.get(dim.parent_dimension_id),
        } for dim in dimensions]

    @staticmethod
    def _aggregate_evaluation_metrics(dimensions, metric_values):
        total_interruption_rounds = sum(
            metric_values.get('打断成功数量', [0])[i]
            + metric_values.get('打断失败数量', [0])[i]
            + metric_values.get('打断询问数量', [0])[i]
            for i in range(len(metric_values.get('打断成功数量', [])))
        ) if metric_values.get('打断成功数量') else 0
        result = {}
        for dim in dimensions:
            values = metric_values.get(dim.name, [])
            if not values:
                result[dim.id] = None
                continue
            method = dim.statistic_method or 'average'
            if method == 'ratio' and (dim.agg_denominator or 'case') == 'round':
                if total_interruption_rounds:
                    result[dim.id] = round(sum(values) / total_interruption_rounds * 100, 2)
                else:
                    result[dim.id] = None
            elif method == 'pass_rate':
                passed_count = sum(1 for value in values if value == 1)
                result[dim.id] = round(passed_count / len(values) * 100, 2)
            else:
                result[dim.id] = round(sum(values) / len(values), 2)
        return result

    @staticmethod
    def _turn_eval_dimensions():
        dimensions = Dimension.query.filter(
            Dimension.id.in_(TURN_EVAL_DIMENSION_IDS),
            Dimension.deleted == False,
            Dimension.status == True,
        ).order_by(Dimension.sort_order, Dimension.id).all()
        if not dimensions:
            raise ValueError("未找到接管评估维度配置")
        return dimensions

    @staticmethod
    def _nested_value(payload, path):
        current = payload
        for key in path.split('.'):
            if not isinstance(current, dict):
                return None
            current = current.get(key)
        return current

    @staticmethod
    def _turn_eval_case_values(case_item):
        raw_result = case_item.get('raw_platform_result') or {}
        primary_metrics = case_item.get('primary_metrics') or {}
        values = {}
        for dimension_id, (_, field_path) in TURN_EVAL_DIMENSION_FIELDS.items():
            value = TestCaseController._nested_value(raw_result, field_path)
            if value is None:
                value = TestCaseController._nested_value({'turn_classification': primary_metrics}, field_path)
            if isinstance(value, bool):
                value = int(value)
            values[dimension_id] = value if isinstance(value, (int, float)) else None
        return values

    @staticmethod
    def _aggregate_turn_eval_metrics(dimensions, cases):
        total_turns = sum(
            int(TestCaseController._nested_value(case.get('raw_platform_result') or {}, 'turn_classification.total_turns') or 0)
            for case in cases
        )
        result = {}
        for dimension in dimensions:
            if dimension.id == 72:
                result[dimension.id] = None
                continue
            if dimension.id in (84, 85, 86):
                count_field = {
                    84: 'normal_takeover_count',
                    85: 'no_takeover_count',
                    86: 'false_takeover_count',
                }[dimension.id]
                numerator = sum(
                    int(TestCaseController._nested_value(
                        case.get('raw_platform_result') or {},
                        f'turn_classification.{count_field}',
                    ) or 0)
                    for case in cases
                )
                result[dimension.id] = round(numerator / total_turns * 100, 4) if total_turns else None
                continue
            values = [
                TestCaseController._turn_eval_case_values(case).get(dimension.id)
                for case in cases
            ]
            values = [value for value in values if isinstance(value, (int, float))]
            result[dimension.id] = round(sum(values) / len(values), 4) if values else None
        return result

    @staticmethod
    def _evaluation_preview_items(package):
        targets = TestCaseController._evaluation_targets(package)
        if not targets:
            raise ValueError("评分结果中未找到已导入的打断任务记录，请先导入对应的打断测试包")

        matched_cases = []
        valid_count = 0
        for case_item in package['cases']:
            run_id = str(case_item.get('run') or '').strip()
            if run_id not in targets:
                continue
            if not TestCaseController._evaluation_target_for_case(
                targets[run_id], case_item.get('case'),
            ):
                continue
            matched_cases.append(case_item)
            if case_item.get('category') == 'valid_metrics':
                valid_count += 1

        items = []
        for case_item in matched_cases:
            task, report_record = TestCaseController._evaluation_target_for_case(
                targets[str(case_item.get('run'))], case_item.get('case'),
            )
            outcome = case_item.get('category') or 'unknown'
            items.append({
                'ID': case_item.get('case'),
                'NAME': case_item.get('title'),
                'DESCRIPTION': f"合并到已有报告：{report_record.name}",
                'GROUP_NAME': task.name,
                'OUTCOME': outcome,
                'REASON': case_item.get('reason') or '',
                'HAS_RESULT_AUDIO': True,
            })
        return items, valid_count, targets, matched_cases

    @staticmethod
    def preview_evaluation_result_package():
        try:
            if 'file' not in request.files:
                return error_response("未上传文件")
            file = request.files['file']
            if not file.filename:
                return error_response("未选择文件")

            package = TestCaseController._read_evaluation_result_package(file)
            items, valid_count, targets, matched_cases = TestCaseController._evaluation_preview_items(package)
            primary_task, primary_report = next(iter(targets.values()))[0]
            return success_response({
                'packageType': 'evaluation-result',
                'totalRows': len(items),
                'validCount': valid_count,
                'matchedTargetCount': sum(len(items) for items in targets.values()),
                'unmatchedSourceCount': len(package['cases']) - len(matched_cases),
                'testCases': items,
                'taskId': primary_task.id,
                'reportId': primary_report.id,
                'taskName': primary_task.name,
                'reportName': primary_report.name,
                'importTarget': 'existing-task-report',
                'errors': [],
            })
        except Exception as e:
            return error_response(f"评分结果包预览失败: {str(e)}")

    @staticmethod
    def _merge_evaluation_results_into_report(task, report_record, cases, package):
        if cases and cases[0].get('task_type') == 'turn_eval':
            return TestCaseController._merge_turn_eval_results_into_report(
                task, report_record, cases, package,
            )
        if cases and cases[0].get('task_type') == 'reject_judge':
            return TestCaseController._merge_reject_results_into_report(
                task, report_record, cases, package,
            )
        if cases and cases[0].get('task_type') == 'env_judge':
            return TestCaseController._merge_env_results_into_report(
                task, report_record, cases, package,
            )

        report_cases = ReportCase.query.filter_by(report_id=report_record.id).order_by(ReportCase.id).all()
        if not report_cases:
            raise ValueError(f"报告 {report_record.id} 中没有可合并评分的执行记录")

        report_case_by_name = {report_case.name: report_case for report_case in report_cases}
        report_case_by_code = {}
        for report_case in report_cases:
            code = str(report_case.name or '').split('_', 1)[0]
            if code:
                report_case_by_code[code] = report_case

        dimensions = TestCaseController._evaluation_dimensions()
        dimension_id_to_name = {dimension.id: dimension.name for dimension in dimensions}

        unmatched_cases = []
        matched_count = 0
        metric_values = {}
        category_stats = {}
        completed_count = 0

        for case_item in cases:
            case_code = str(case_item.get('case') or '').strip()
            report_case = report_case_by_name.get(case_item.get('title')) or report_case_by_code.get(case_code)
            if not report_case:
                unmatched_cases.append(case_item.get('case') or case_item.get('title'))
                continue

            metrics = TestCaseController._evaluation_case_metrics(case_item)
            report_case.metrics = [{
                'resource': '历史打断执行',
                'metrics': [
                    {
                        'id': dimension.id,
                        'metric': dimension.name,
                        'value': metrics.get(dimension.name),
                        'round_number': None,
                        'dimension_type': dimension.dimension_type or 'main',
                        'parent_dimension_id': dimension.parent_dimension_id,
                        'parent_dimension_name': dimension_id_to_name.get(dimension.parent_dimension_id),
                    }
                    for dimension in dimensions
                ],
            }]

            old_algorithm_results = report_case.algorithm_results or []
            if isinstance(old_algorithm_results, str):
                try:
                    old_algorithm_results = json.loads(old_algorithm_results)
                except (TypeError, ValueError):
                    old_algorithm_results = []
            preserved_algorithm_results = [
                algorithm_result for algorithm_result in old_algorithm_results
                if not (
                    isinstance(algorithm_result, dict)
                    and algorithm_result.get('param_type') == 'number'
                    and (
                        algorithm_result.get('param_code') in INTERRUPTION_METRIC_CODES
                        or algorithm_result.get('param_code') in LEGACY_INTERRUPTION_EXECUTION_METRICS
                    )
                )
            ]
            report_case.algorithm_results = preserved_algorithm_results + [
                {
                    'device': '历史打断执行',
                    'param_code': INTERRUPTION_METRIC_FIELDS[dimension.name],
                    'param_type': 'number',
                    'label': dimension.name,
                    'value': metrics.get(dimension.name),
                    'round_number': None,
                    'dimension_name': dimension.name,
                }
                for dimension in dimensions
                if dimension.name in INTERRUPTION_METRIC_FIELDS
            ]

            results = report_case.results or []
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except (TypeError, ValueError):
                    results = []
            if results and isinstance(results[0], dict):
                updated_result = dict(results[0])
                updated_result['evaluation'] = {
                    'schema': package['report'].get('schema'),
                    'status': case_item.get('category'),
                    'imported_at': now_cst().isoformat(),
                    'primary_metrics': metrics,
                }
                updated_result['scoring'] = 'completed' if case_item.get('category') == 'valid_metrics' else 'not_scored'
                report_case.results = [updated_result, *results[1:]]

            old_logs = report_case.logs or {}
            if isinstance(old_logs, str):
                try:
                    old_logs = json.loads(old_logs)
                except (TypeError, ValueError):
                    old_logs = {}
            if not isinstance(old_logs, dict):
                old_logs = {'original_logs': old_logs}
            old_logs['evaluation_result_import'] = {
                'case': case_item.get('case'),
                'run': case_item.get('run'),
                'case_uid': case_item.get('case_uid'),
                'attempt': case_item.get('Live_attempt'),
                'category': case_item.get('category'),
            }
            report_case.logs = json.dumps(old_logs, ensure_ascii=False)

            matched_count += 1
            case_metrics = {}
            for dimension in dimensions:
                metric_value = metrics.get(dimension.name)
                if isinstance(metric_value, (int, float)):
                    metric_values.setdefault(dimension.name, []).append(metric_value)
                    case_metrics[dimension.name] = metric_value
            category_stats.setdefault(report_case.category or '未分类', []).append(metrics)

            result_outcome = ''
            if results and isinstance(results[0], dict):
                result_outcome = results[0].get('outcome') or results[0].get('state') or ''
            if result_outcome == 'completed':
                completed_count += 1

        if unmatched_cases:
            preview = '、'.join(str(item) for item in unmatched_cases[:5])
            raise ValueError(f"有 {len(unmatched_cases)} 条评分结果未匹配到报告执行记录: {preview}")

        metric_averages = TestCaseController._aggregate_evaluation_metrics(dimensions, metric_values)
        all_metrics = TestCaseController._evaluation_all_metrics(dimensions)
        case_type_stats = []
        for category, category_items in category_stats.items():
            category_values = {}
            for item in category_items:
                for dimension in dimensions:
                    value = item.get(dimension.name)
                    if isinstance(value, (int, float)):
                        category_values.setdefault(dimension.name, []).append(value)
            category_averages = TestCaseController._aggregate_evaluation_metrics(dimensions, category_values)
            category_metrics = []
            for dimension in dimensions:
                value = category_averages.get(dimension.id)
                if value is not None:
                    category_metrics.append({
                        'id': dimension.id,
                        'metric': dimension.name,
                        'value': value,
                    })
            case_type_stats.append({
                'groupId': category,
                'groupName': category,
                'metrics': category_metrics,
            })

        old_meta = ReportSummaryMeta.query.filter_by(report_id=report_record.id).first()

        def meta_value(field, fallback):
            if not old_meta:
                return fallback
            value = getattr(old_meta, field, fallback)
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except (TypeError, ValueError):
                    return fallback
            return value if value is not None else fallback

        devices = meta_value('devices', [])
        apis = meta_value('apis', [])
        all_case_tags = meta_value('all_case_tags', ['历史导入', '打断测试'])
        resource_headers = meta_value('resource_headers', [])
        if not resource_headers:
            resource_headers = [{
                'key': '历史打断执行',
                'label': '历史打断执行',
                'type': 'unknown',
                'id': None,
                'name': '历史打断执行',
                'version': None,
                'result_type': None,
                'editable': False,
            }]

        for model in (ReportSummary, ReportSummaryMeta, ReportRawData, ReportMetricStats):
            model.query.filter_by(report_id=report_record.id).delete(synchronize_session=False)

        task_config = task.config or {}
        task_config['evaluation_result_imported'] = True
        task_config['evaluation_result_sha256'] = package['sha256']
        task_config['evaluation_result_as_of'] = package['report'].get('as_of_UTC')
        task.config = task_config
        task.updated_at = now_cst()

        report_record.description = '外部全双工打断测试包导入的历史任务报告；已合并外部评分结果'
        report_record.status = ReportStatus.PUBLISHED.value
        report_record.updated_at = now_cst()

        db.session.add(ReportSummary(
            report_id=report_record.id,
            task_ids=[task.id],
            total_cases=len(report_cases),
            completed_cases=completed_count,
            failed_cases=len(report_cases) - completed_count,
            pass_rate=round(completed_count / len(report_cases) * 100, 2) if report_cases else 0,
            duration=task.actual_duration or 0,
            started_at=task.started_at,
            completed_at=task.completed_at,
        ))
        db.session.add(ReportSummaryMeta(
            report_id=report_record.id,
            dimension_values=[
                {'id': dimension.id, 'name': dimension.name, 'average_value': metric_averages.get(dimension.id)}
                for dimension in dimensions
            ],
            case_categories=sorted(category_stats.keys()),
            all_case_tags=all_case_tags,
            devices=devices,
            apis=apis,
            resources=['历史打断执行'],
            resource_headers=resource_headers,
            all_metrics=all_metrics,
            field_mappings=meta_value('field_mappings', {}),
        ))
        db.session.add(ReportRawData(
            report_id=report_record.id,
            raw_data={'历史打断执行': {
                dimension.name: metric_values.get(dimension.name, [])
                for dimension in dimensions
            }},
        ))
        db.session.add(ReportMetricStats(
            report_id=report_record.id,
            metric_data=[{
                'resource': '历史打断执行',
                'metrics': [
                    {'id': dimension.id, 'metric': dimension.name, 'value': metric_averages.get(dimension.id)}
                    for dimension in dimensions
                ],
            }],
            tag_metric_data={},
            tag_category_metric_data={},
            case_type_stats=case_type_stats,
            device_stats=[],
            api_stats=[],
        ))
        db.session.commit()
        return matched_count, len(dimensions)

    @staticmethod
    def _merge_turn_eval_results_into_report(task, report_record, cases, package):
        report_cases = ReportCase.query.filter_by(report_id=report_record.id).order_by(ReportCase.id).all()
        if not report_cases:
            raise ValueError(f"报告 {report_record.id} 中没有可合并评分的执行记录")

        report_case_by_name = {report_case.name: report_case for report_case in report_cases}
        report_case_by_code = {}
        for report_case in report_cases:
            code = str(report_case.name or '').split('_', 1)[0]
            if code:
                report_case_by_code[code] = report_case

        dimensions = TestCaseController._turn_eval_dimensions()
        dimension_id_to_name = {dimension.id: dimension.name for dimension in dimensions}
        resource = '历史接管执行'
        unmatched_cases = []
        matched_cases = []
        category_cases = {}
        completed_count = 0

        for case_item in cases:
            case_code = str(case_item.get('case') or '').strip()
            report_case = report_case_by_name.get(case_item.get('title')) or report_case_by_code.get(case_code)
            if not report_case:
                unmatched_cases.append(case_code or case_item.get('title'))
                continue

            case_values = TestCaseController._turn_eval_case_values(case_item)
            case_metrics = [{
                'id': dimension.id,
                'metric': dimension.name,
                'value': case_values.get(dimension.id),
                'round_number': None,
                'dimension_type': dimension.dimension_type or 'main',
                'parent_dimension_id': dimension.parent_dimension_id,
                'parent_dimension_name': dimension_id_to_name.get(dimension.parent_dimension_id),
            } for dimension in dimensions]
            report_case.metrics = [{'resource': resource, 'metrics': case_metrics}]
            report_case.description = (
                str(report_case.description or '').replace('历史打断执行记录', '历史接管执行记录')
            )
            report_case.tags = ['历史导入', '话轮接管']

            old_algorithm_results = report_case.algorithm_results or []
            if isinstance(old_algorithm_results, str):
                try:
                    old_algorithm_results = json.loads(old_algorithm_results)
                except (TypeError, ValueError):
                    old_algorithm_results = []
            turn_eval_codes = {code for code, _ in TURN_EVAL_DIMENSION_FIELDS.values()}
            preserved_algorithm_results = [
                algorithm_result for algorithm_result in old_algorithm_results
                if not (
                    isinstance(algorithm_result, dict)
                    and algorithm_result.get('param_type') == 'number'
                    and (
                        algorithm_result.get('param_code') in turn_eval_codes
                        or algorithm_result.get('param_code') in TURN_EVAL_LEGACY_METRICS
                    )
                )
            ]
            report_case.algorithm_results = preserved_algorithm_results + [{
                'device': resource,
                'param_code': TURN_EVAL_DIMENSION_FIELDS[dimension.id][0],
                'param_type': 'number',
                'label': dimension.name,
                'value': case_values.get(dimension.id),
                'round_number': None,
                'dimension_name': dimension.name,
            } for dimension in dimensions if dimension.id in TURN_EVAL_DIMENSION_FIELDS]

            results = report_case.results or []
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except (TypeError, ValueError):
                    results = []
            if results and isinstance(results[0], dict):
                updated_result = dict(results[0])
                updated_result['evaluation'] = {
                    'schema': package['report'].get('schema'),
                    'status': case_item.get('category'),
                    'imported_at': now_cst().isoformat(),
                    'primary_metrics': {
                        dimensions_by_id.id: case_values.get(dimensions_by_id.id)
                        for dimensions_by_id in dimensions
                    },
                }
                updated_result['scoring'] = 'completed' if case_item.get('category') == 'valid_metrics' else 'not_scored'
                report_case.results = [updated_result, *results[1:]]

            old_logs = report_case.logs or {}
            if isinstance(old_logs, str):
                try:
                    old_logs = json.loads(old_logs)
                except (TypeError, ValueError):
                    old_logs = {}
            if not isinstance(old_logs, dict):
                old_logs = {'original_logs': old_logs}
            old_logs['evaluation_result_import'] = {
                'case': case_item.get('case'),
                'run': case_item.get('run'),
                'case_uid': case_item.get('case_uid'),
                'attempt': case_item.get('Live_attempt'),
                'category': case_item.get('category'),
            }
            report_case.logs = json.dumps(old_logs, ensure_ascii=False)

            matched_cases.append(case_item)
            category_cases.setdefault(report_case.category or '未分类', []).append(case_item)
            if (results and isinstance(results[0], dict)
                    and (results[0].get('outcome') or results[0].get('state')) == 'completed'):
                completed_count += 1

        if unmatched_cases:
            preview = '、'.join(str(item) for item in unmatched_cases[:5])
            raise ValueError(f"有 {len(unmatched_cases)} 条评分结果未匹配到报告执行记录: {preview}")

        metric_averages = TestCaseController._aggregate_turn_eval_metrics(dimensions, matched_cases)
        all_metrics = TestCaseController._evaluation_all_metrics(dimensions)
        case_type_stats = []
        for category, category_items in category_cases.items():
            category_averages = TestCaseController._aggregate_turn_eval_metrics(dimensions, category_items)
            case_type_stats.append({
                'groupId': category,
                'groupName': category,
                'metrics': [
                    {'id': dimension.id, 'metric': dimension.name, 'value': category_averages.get(dimension.id)}
                    for dimension in dimensions
                    if category_averages.get(dimension.id) is not None
                ],
            })

        old_meta = ReportSummaryMeta.query.filter_by(report_id=report_record.id).first()

        def meta_value(field, fallback):
            if not old_meta:
                return fallback
            value = getattr(old_meta, field, fallback)
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except (TypeError, ValueError):
                    return fallback
            return value if value is not None else fallback

        for model in (ReportSummary, ReportSummaryMeta, ReportRawData, ReportMetricStats):
            model.query.filter_by(report_id=report_record.id).delete(synchronize_session=False)

        task_config = task.config or {}
        task_config['evaluation_result_imported'] = True
        task_config['evaluation_result_sha256'] = package['sha256']
        task_config['evaluation_result_as_of'] = package['report'].get('as_of_UTC')
        task.config = task_config
        task.updated_at = now_cst()

        dataset_id = (
            (task.config or {}).get('dataset_id')
            or (task.config or {}).get('package_id')
            or report_record.name.rsplit('_', 1)[-1]
        )
        report_record.name = f"接管历史报告_{dataset_id}"
        report_record.description = '外部全双工接管测试包导入的历史任务报告；已合并外部评分结果'
        report_record.status = ReportStatus.PUBLISHED.value
        report_record.updated_at = now_cst()

        db.session.add(ReportSummary(
            report_id=report_record.id,
            task_ids=[task.id],
            total_cases=len(report_cases),
            completed_cases=completed_count,
            failed_cases=len(report_cases) - completed_count,
            pass_rate=round(completed_count / len(report_cases) * 100, 2) if report_cases else 0,
            duration=task.actual_duration or 0,
            started_at=task.started_at,
            completed_at=task.completed_at,
        ))
        db.session.add(ReportSummaryMeta(
            report_id=report_record.id,
            dimension_values=[
                {'id': dimension.id, 'name': dimension.name, 'average_value': metric_averages.get(dimension.id)}
                for dimension in dimensions
            ],
            case_categories=sorted(category_cases.keys()),
            all_case_tags=['历史导入', '话轮接管'],
            devices=meta_value('devices', []),
            apis=meta_value('apis', []),
            resources=[resource],
            resource_headers=[{
                'key': resource,
                'label': resource,
                'type': 'unknown',
                'id': None,
                'name': resource,
                'version': None,
                'result_type': None,
                'editable': False,
            }],
            all_metrics=all_metrics,
            field_mappings=meta_value('field_mappings', {}),
        ))
        db.session.add(ReportRawData(
            report_id=report_record.id,
            raw_data={resource: {
                dimension.name: [
                    TestCaseController._turn_eval_case_values(case_item).get(dimension.id)
                    for case_item in matched_cases
                    if TestCaseController._turn_eval_case_values(case_item).get(dimension.id) is not None
                ]
                for dimension in dimensions
            }},
        ))
        db.session.add(ReportMetricStats(
            report_id=report_record.id,
            metric_data=[{
                'resource': resource,
                'metrics': [
                    {'id': dimension.id, 'metric': dimension.name, 'value': metric_averages.get(dimension.id)}
                    for dimension in dimensions
                ],
            }],
            tag_metric_data={},
            tag_category_metric_data={},
            case_type_stats=case_type_stats,
            device_stats=[],
            api_stats=[],
        ))
        db.session.commit()
        return len(matched_cases), len(dimensions)

    @staticmethod
    def _reject_dimensions():
        dimensions = Dimension.query.filter(
            Dimension.id.in_(REJECT_DIMENSION_IDS),
            Dimension.deleted == False,
            Dimension.status == True,
        ).order_by(Dimension.sort_order, Dimension.id).all()
        if not dimensions:
            raise ValueError("未找到拒识评估维度配置")
        return dimensions

    @staticmethod
    def _reject_case_values(case_item):
        raw_result = case_item.get('raw_platform_result') or {}
        primary_metrics = case_item.get('primary_metrics') or {}
        values = {}
        for dimension_id, (metric_code, _) in REJECT_DIMENSION_FIELDS.items():
            value = raw_result.get(metric_code)
            if value is None:
                value = primary_metrics.get(metric_code)
            if isinstance(value, bool):
                value = int(value)
            values[dimension_id] = value if isinstance(value, (int, float)) else None
        return values

    @staticmethod
    def _reject_numeric_value(payload, field_name):
        value = (payload or {}).get(field_name)
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, (int, float)):
            return float(value)
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _aggregate_reject_metrics(dimensions, cases):
        result = {}
        for dimension in dimensions:
            numerator_field, denominator_field = REJECT_DIMENSION_FIELDS[dimension.id]
            total_numerator = 0.0
            total_denominator = 0.0
            for case_item in cases:
                raw_result = case_item.get('raw_platform_result') or {}
                primary_metrics = case_item.get('primary_metrics') or {}
                message = raw_result.get('message') or primary_metrics.get('message')
                if 'LLM 调用失败' in str(message or ''):
                    continue

                numerator = TestCaseController._reject_numeric_value(raw_result, numerator_field)
                if numerator is None:
                    numerator = TestCaseController._reject_numeric_value(primary_metrics, numerator_field)
                denominator = TestCaseController._reject_numeric_value(raw_result, denominator_field)
                if denominator is None:
                    denominator = TestCaseController._reject_numeric_value(primary_metrics, denominator_field)
                if numerator is None or denominator is None or denominator <= 0:
                    continue
                total_numerator += numerator
                total_denominator += denominator

            result[dimension.id] = (
                round(total_numerator / total_denominator * 100, 4)
                if total_denominator else None
            )
        return result

    @staticmethod
    def _merge_reject_results_into_report(task, report_record, cases, package, commit=True):
        report_cases = ReportCase.query.filter_by(report_id=report_record.id).order_by(ReportCase.id).all()
        if not report_cases:
            raise ValueError(f"报告 {report_record.id} 中没有可合并评分的执行记录")

        report_case_by_name = {report_case.name: report_case for report_case in report_cases}
        report_case_by_code = {}
        for report_case in report_cases:
            code = str(report_case.name or '').split('_', 1)[0]
            if code:
                report_case_by_code[code] = report_case

        dimensions = TestCaseController._reject_dimensions()
        dimension_id_to_name = {dimension.id: dimension.name for dimension in dimensions}
        resource = '历史拒识执行'
        unmatched_cases = []
        matched_cases = []
        category_cases = {}

        for case_item in cases:
            case_code = str(case_item.get('case') or '').strip()
            report_case = report_case_by_name.get(case_item.get('title')) or report_case_by_code.get(case_code)
            if not report_case:
                unmatched_cases.append(case_code or case_item.get('title'))
                continue

            case_values = TestCaseController._reject_case_values(case_item)
            case_metrics = [{
                'id': dimension.id,
                'metric': dimension.name,
                'value': case_values.get(dimension.id),
                'round_number': None,
                'dimension_type': dimension.dimension_type or 'main',
                'parent_dimension_id': dimension.parent_dimension_id,
                'parent_dimension_name': dimension_id_to_name.get(dimension.parent_dimension_id),
            } for dimension in dimensions]
            report_case.metrics = [{'resource': resource, 'metrics': case_metrics}]
            report_case.description = (
                str(report_case.description or '').replace('历史打断执行记录', '历史拒识执行记录')
            )
            report_case.tags = ['历史导入', '拒识测试']

            old_algorithm_results = report_case.algorithm_results or []
            if isinstance(old_algorithm_results, str):
                try:
                    old_algorithm_results = json.loads(old_algorithm_results)
                except (TypeError, ValueError):
                    old_algorithm_results = []
            reject_codes = {
                code for fields in REJECT_DIMENSION_FIELDS.values() for code in fields
            }
            preserved_algorithm_results = [
                algorithm_result for algorithm_result in old_algorithm_results
                if not (
                    isinstance(algorithm_result, dict)
                    and algorithm_result.get('param_type') == 'number'
                    and (
                        algorithm_result.get('param_code') in reject_codes
                        or algorithm_result.get('param_code') in REJECT_LEGACY_METRICS
                    )
                )
            ]
            report_case.algorithm_results = preserved_algorithm_results + [{
                'device': resource,
                'param_code': REJECT_DIMENSION_FIELDS[dimension.id][0],
                'param_type': 'number',
                'label': dimension.name,
                'value': case_values.get(dimension.id),
                'round_number': None,
                'dimension_name': dimension.name,
            } for dimension in dimensions]

            results = report_case.results or []
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except (TypeError, ValueError):
                    results = []
            if results and isinstance(results[0], dict):
                updated_result = dict(results[0])
                updated_result['evaluation'] = {
                    'schema': package['report'].get('schema'),
                    'status': case_item.get('category'),
                    'imported_at': now_cst().isoformat(),
                    'primary_metrics': case_values,
                }
                updated_result['scoring'] = (
                    'completed' if case_item.get('category') == 'valid_metrics' else 'not_scored'
                )
                report_case.results = [updated_result, *results[1:]]

            old_logs = report_case.logs or {}
            if isinstance(old_logs, str):
                try:
                    old_logs = json.loads(old_logs)
                except (TypeError, ValueError):
                    old_logs = {}
            if not isinstance(old_logs, dict):
                old_logs = {'original_logs': old_logs}
            old_logs['evaluation_result_import'] = {
                'case': case_item.get('case'),
                'run': case_item.get('run'),
                'case_uid': case_item.get('case_uid'),
                'attempt': case_item.get('Live_attempt'),
                'category': case_item.get('category'),
            }
            report_case.logs = json.dumps(old_logs, ensure_ascii=False)

            matched_cases.append(case_item)
            category_cases.setdefault(report_case.category or '未分类', []).append(case_item)

        if unmatched_cases:
            preview = '、'.join(str(item) for item in unmatched_cases[:5])
            raise ValueError(f"有 {len(unmatched_cases)} 条评分结果未匹配到报告执行记录: {preview}")

        metric_averages = TestCaseController._aggregate_reject_metrics(dimensions, matched_cases)
        all_metrics = TestCaseController._evaluation_all_metrics(dimensions)
        case_type_stats = []
        for category, category_items in category_cases.items():
            category_averages = TestCaseController._aggregate_reject_metrics(dimensions, category_items)
            case_type_stats.append({
                'groupId': category,
                'groupName': category,
                'metrics': [
                    {'id': dimension.id, 'metric': dimension.name, 'value': category_averages.get(dimension.id)}
                    for dimension in dimensions
                    if category_averages.get(dimension.id) is not None
                ],
            })

        old_meta = ReportSummaryMeta.query.filter_by(report_id=report_record.id).first()

        def meta_value(field, fallback):
            if not old_meta:
                return fallback
            value = getattr(old_meta, field, fallback)
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except (TypeError, ValueError):
                    return fallback
            return value if value is not None else fallback

        for model in (ReportSummary, ReportSummaryMeta, ReportRawData, ReportMetricStats):
            model.query.filter_by(report_id=report_record.id).delete(synchronize_session=False)

        dataset_id = (
            (task.config or {}).get('dataset_id')
            or (task.config or {}).get('package_id')
            or report_record.name.rsplit('_', 1)[-1]
        )
        split_suffix = str((task.config or {}).get('split_suffix') or '')
        task.name = f"拒识历史任务_{dataset_id}{split_suffix}"
        task.description = '外部全双工拒识测试包导入的历史任务记录'
        task_config = task.config or {}
        task_config['evaluation_result_imported'] = True
        task_config['evaluation_result_sha256'] = package['sha256']
        task_config['evaluation_result_as_of'] = package['report'].get('as_of_UTC')
        task.config = task_config
        task.updated_at = now_cst()

        report_record.name = f"拒识历史报告_{dataset_id}{split_suffix}"
        report_record.description = '外部全双工拒识测试包导入的历史任务报告；已合并外部评分结果'
        report_record.status = ReportStatus.PUBLISHED.value
        report_record.updated_at = now_cst()

        completed_count = int(task.completed_cases or 0)
        db.session.add(ReportSummary(
            report_id=report_record.id,
            task_ids=[task.id],
            total_cases=len(report_cases),
            completed_cases=completed_count,
            failed_cases=max(len(report_cases) - completed_count, 0),
            pass_rate=round(completed_count / len(report_cases) * 100, 2) if report_cases else 0,
            duration=task.actual_duration or 0,
            started_at=task.started_at,
            completed_at=task.completed_at,
        ))
        db.session.add(ReportSummaryMeta(
            report_id=report_record.id,
            dimension_values=[
                {'id': dimension.id, 'name': dimension.name, 'average_value': metric_averages.get(dimension.id)}
                for dimension in dimensions
            ],
            case_categories=sorted(category_cases.keys()),
            all_case_tags=['历史导入', '拒识测试'],
            devices=meta_value('devices', []),
            apis=meta_value('apis', []),
            resources=[resource],
            resource_headers=[{
                'key': resource,
                'label': resource,
                'type': 'unknown',
                'id': None,
                'name': resource,
                'version': None,
                'result_type': None,
                'editable': False,
            }],
            all_metrics=all_metrics,
            field_mappings=meta_value('field_mappings', {}),
        ))
        db.session.add(ReportRawData(
            report_id=report_record.id,
            raw_data={resource: {
                dimension.name: [
                    TestCaseController._reject_case_values(case_item).get(dimension.id)
                    for case_item in matched_cases
                    if TestCaseController._reject_case_values(case_item).get(dimension.id) is not None
                ]
                for dimension in dimensions
            }},
        ))
        db.session.add(ReportMetricStats(
            report_id=report_record.id,
            metric_data=[{
                'resource': resource,
                'metrics': [
                    {'id': dimension.id, 'metric': dimension.name, 'value': metric_averages.get(dimension.id)}
                    for dimension in dimensions
                ],
            }],
            tag_metric_data={},
            tag_category_metric_data={},
            case_type_stats=case_type_stats,
            device_stats=[],
            api_stats=[],
        ))
        if commit:
            db.session.commit()
        return len(matched_cases), len(dimensions)

    @staticmethod
    def _env_dimensions():
        dimensions = Dimension.query.filter(
            Dimension.id.in_(ENV_DIMENSION_IDS),
            Dimension.deleted == False,
            Dimension.status == True,
        ).order_by(Dimension.sort_order, Dimension.id).all()
        if not dimensions:
            raise ValueError("未找到环境理解评估维度配置")
        return dimensions

    @staticmethod
    def _env_case_values(case_item):
        raw_result = case_item.get('raw_platform_result') or {}
        primary_metrics = case_item.get('primary_metrics') or {}
        values = {}
        for dimension_id, metric_code in ENV_DIMENSION_FIELDS.items():
            value = raw_result.get(metric_code)
            if value is None:
                value = primary_metrics.get(metric_code)
            if isinstance(value, bool):
                value = int(value)
            values[dimension_id] = value if isinstance(value, (int, float)) else None
        return values

    @staticmethod
    def _aggregate_env_metrics(dimensions, cases):
        result = {}
        for dimension in dimensions:
            values = [
                TestCaseController._env_case_values(case_item).get(dimension.id)
                for case_item in cases
            ]
            values = [value for value in values if isinstance(value, (int, float))]
            if not values:
                result[dimension.id] = None
            elif dimension.id == 133:
                result[dimension.id] = round(
                    sum(1 for value in values if value == 1) / len(values) * 100,
                    2,
                )
            else:
                result[dimension.id] = round(sum(values) / len(values), 2)
        return result

    @staticmethod
    def _merge_env_results_into_report(task, report_record, cases, package):
        report_cases = ReportCase.query.filter_by(report_id=report_record.id).order_by(ReportCase.id).all()
        if not report_cases:
            raise ValueError(f"报告 {report_record.id} 中没有可合并评分的执行记录")

        report_case_by_name = {report_case.name: report_case for report_case in report_cases}
        report_case_by_code = {}
        for report_case in report_cases:
            code = str(report_case.name or '').split('_', 1)[0]
            if code:
                report_case_by_code[code] = report_case

        dimensions = TestCaseController._env_dimensions()
        resource = '历史环境理解执行'
        unmatched_cases = []
        matched_cases = []
        category_cases = {}

        for case_item in cases:
            case_code = str(case_item.get('case') or '').strip()
            report_case = report_case_by_name.get(case_item.get('title')) or report_case_by_code.get(case_code)
            if not report_case:
                unmatched_cases.append(case_code or case_item.get('title'))
                continue

            case_values = TestCaseController._env_case_values(case_item)
            case_metrics = [{
                'id': dimension.id,
                'metric': dimension.name,
                'value': case_values.get(dimension.id),
                'round_number': None,
                'dimension_type': dimension.dimension_type or 'main',
                'parent_dimension_id': dimension.parent_dimension_id,
                'parent_dimension_name': None,
            } for dimension in dimensions]
            report_case.metrics = [{'resource': resource, 'metrics': case_metrics}]
            report_case.description = (
                str(report_case.description or '').replace('历史打断执行记录', '历史环境理解执行记录')
            )
            report_case.tags = ['历史导入', '环境理解']

            old_algorithm_results = report_case.algorithm_results or []
            if isinstance(old_algorithm_results, str):
                try:
                    old_algorithm_results = json.loads(old_algorithm_results)
                except (TypeError, ValueError):
                    old_algorithm_results = []
            env_codes = set(ENV_DIMENSION_FIELDS.values())
            preserved_algorithm_results = [
                algorithm_result for algorithm_result in old_algorithm_results
                if not (
                    isinstance(algorithm_result, dict)
                    and algorithm_result.get('param_type') == 'number'
                    and (
                        algorithm_result.get('param_code') in env_codes
                        or algorithm_result.get('param_code') in ENV_LEGACY_METRICS
                    )
                )
            ]
            report_case.algorithm_results = preserved_algorithm_results + [{
                'device': resource,
                'param_code': ENV_DIMENSION_FIELDS[dimension.id],
                'param_type': 'number',
                'label': dimension.name,
                'value': case_values.get(dimension.id),
                'round_number': None,
                'dimension_name': dimension.name,
            } for dimension in dimensions]

            results = report_case.results or []
            if isinstance(results, str):
                try:
                    results = json.loads(results)
                except (TypeError, ValueError):
                    results = []
            if results and isinstance(results[0], dict):
                updated_result = dict(results[0])
                updated_result['evaluation'] = {
                    'schema': package['report'].get('schema'),
                    'status': case_item.get('category'),
                    'imported_at': now_cst().isoformat(),
                    'primary_metrics': case_values,
                }
                updated_result['scoring'] = (
                    'completed' if case_item.get('category') == 'valid_metrics' else 'not_scored'
                )
                report_case.results = [updated_result, *results[1:]]

            old_logs = report_case.logs or {}
            if isinstance(old_logs, str):
                try:
                    old_logs = json.loads(old_logs)
                except (TypeError, ValueError):
                    old_logs = {}
            if not isinstance(old_logs, dict):
                old_logs = {'original_logs': old_logs}
            old_logs['evaluation_result_import'] = {
                'case': case_item.get('case'),
                'run': case_item.get('run'),
                'case_uid': case_item.get('case_uid'),
                'attempt': case_item.get('Live_attempt'),
                'category': case_item.get('category'),
            }
            report_case.logs = json.dumps(old_logs, ensure_ascii=False)

            matched_cases.append(case_item)
            category_cases.setdefault(report_case.category or '未分类', []).append(case_item)

        if unmatched_cases:
            preview = '、'.join(str(item) for item in unmatched_cases[:5])
            raise ValueError(f"有 {len(unmatched_cases)} 条评分结果未匹配到报告执行记录: {preview}")

        metric_averages = TestCaseController._aggregate_env_metrics(dimensions, matched_cases)
        all_metrics = TestCaseController._evaluation_all_metrics(dimensions)
        case_type_stats = []
        for category, category_items in category_cases.items():
            category_averages = TestCaseController._aggregate_env_metrics(dimensions, category_items)
            case_type_stats.append({
                'groupId': category,
                'groupName': category,
                'metrics': [
                    {'id': dimension.id, 'metric': dimension.name, 'value': category_averages.get(dimension.id)}
                    for dimension in dimensions
                    if category_averages.get(dimension.id) is not None
                ],
            })

        old_meta = ReportSummaryMeta.query.filter_by(report_id=report_record.id).first()

        def meta_value(field, fallback):
            if not old_meta:
                return fallback
            value = getattr(old_meta, field, fallback)
            if isinstance(value, str):
                try:
                    return json.loads(value)
                except (TypeError, ValueError):
                    return fallback
            return value if value is not None else fallback

        for model in (ReportSummary, ReportSummaryMeta, ReportRawData, ReportMetricStats):
            model.query.filter_by(report_id=report_record.id).delete(synchronize_session=False)

        dataset_id = (
            (task.config or {}).get('dataset_id')
            or (task.config or {}).get('package_id')
            or report_record.name.rsplit('_', 1)[-1]
        )
        task.name = f"环境理解历史任务_{dataset_id}"
        task.description = '外部全双工环境理解测试包导入的历史任务记录'
        task_config = task.config or {}
        task_config['evaluation_result_imported'] = True
        task_config['evaluation_result_sha256'] = package['sha256']
        task_config['evaluation_result_as_of'] = package['report'].get('as_of_UTC')
        task.config = task_config
        task.updated_at = now_cst()

        report_record.name = f"环境理解历史报告_{dataset_id}"
        report_record.description = '外部全双工环境理解测试包导入的历史任务报告；已合并外部评分结果'
        report_record.status = ReportStatus.PUBLISHED.value
        report_record.updated_at = now_cst()

        completed_count = int(task.completed_cases or 0)
        db.session.add(ReportSummary(
            report_id=report_record.id,
            task_ids=[task.id],
            total_cases=len(report_cases),
            completed_cases=completed_count,
            failed_cases=max(len(report_cases) - completed_count, 0),
            pass_rate=round(completed_count / len(report_cases) * 100, 2) if report_cases else 0,
            duration=task.actual_duration or 0,
            started_at=task.started_at,
            completed_at=task.completed_at,
        ))
        db.session.add(ReportSummaryMeta(
            report_id=report_record.id,
            dimension_values=[
                {'id': dimension.id, 'name': dimension.name, 'average_value': metric_averages.get(dimension.id)}
                for dimension in dimensions
            ],
            case_categories=sorted(category_cases.keys()),
            all_case_tags=['历史导入', '环境理解'],
            devices=meta_value('devices', []),
            apis=meta_value('apis', []),
            resources=[resource],
            resource_headers=[{
                'key': resource,
                'label': resource,
                'type': 'unknown',
                'id': None,
                'name': resource,
                'version': None,
                'result_type': None,
                'editable': False,
            }],
            all_metrics=all_metrics,
            field_mappings=meta_value('field_mappings', {}),
        ))
        db.session.add(ReportRawData(
            report_id=report_record.id,
            raw_data={resource: {
                dimension.name: [
                    TestCaseController._env_case_values(case_item).get(dimension.id)
                    for case_item in matched_cases
                    if TestCaseController._env_case_values(case_item).get(dimension.id) is not None
                ]
                for dimension in dimensions
            }},
        ))
        db.session.add(ReportMetricStats(
            report_id=report_record.id,
            metric_data=[{
                'resource': resource,
                'metrics': [
                    {'id': dimension.id, 'metric': dimension.name, 'value': metric_averages.get(dimension.id)}
                    for dimension in dimensions
                ],
            }],
            tag_metric_data={},
            tag_category_metric_data={},
            case_type_stats=case_type_stats,
            device_stats=[],
            api_stats=[],
        ))
        db.session.commit()
        return len(matched_cases), len(dimensions)

    @staticmethod
    def _create_or_update_evaluation_task_report(package):
        targets = TestCaseController._evaluation_targets(package)
        if not targets:
            raise ValueError("评分结果中未找到已导入的打断任务记录，请先导入对应的打断测试包")

        results = []
        for run_id, run_targets in targets.items():
            run_cases = [
                case_item for case_item in package['cases']
                if str(case_item.get('run') or '').strip() == run_id
            ]
            split_codes = set().union(*[
                TestCaseController._split_case_codes(task)
                for task, _ in run_targets
            ] or [set()])
            for task, report_record in run_targets:
                target_codes = TestCaseController._split_case_codes(task)
                cases = [
                    case_item for case_item in run_cases
                    if (
                        str(case_item.get('case') or '').strip().upper() in target_codes
                        if target_codes
                        else str(case_item.get('case') or '').strip().upper() not in split_codes
                    )
                ]
                matched_count, metric_count = TestCaseController._merge_evaluation_results_into_report(
                    task, report_record, cases, package,
                )
                results.append({
                    'run': run_id,
                    'task_id': task.id,
                    'report_id': report_record.id,
                    'matched_count': matched_count,
                    'metric_count': metric_count,
                })
        return results


    @staticmethod
    def import_evaluation_result_package():
        try:
            if 'file' not in request.files:
                return error_response("未上传文件")
            file = request.files['file']
            if not file.filename:
                return error_response("未选择文件")

            package = TestCaseController._read_evaluation_result_package(file)
            results = TestCaseController._create_or_update_evaluation_task_report(package)
            primary_result = results[0]
            return success_response({
                'taskId': primary_result['task_id'],
                'reportId': primary_result['report_id'],
                'importedCount': 0,
                'updatedCount': primary_result['matched_count'],
                'targetCount': len(results),
                'results': results,
                'errors': [],
            }, '评分结果已合并到已有任务报告')
        except Exception as e:
            db.session.rollback()
            return error_response(f"评分结果合并到已有任务报告失败: {str(e)}")

    @staticmethod
    def download_template():
        try:
            output = io.BytesIO()
            
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                testcases_df = pd.DataFrame(columns=[
                    'ID', 'NAME', 'DESCRIPTION', 'GROUP_NAME', 'GROUP_ID',
                    'TRANSLATION_DIRECTION', 'TEST_TYPE', 'NOISE_AUDIO_NAME', 'NOISE_AUDIO_ID',
                    'NOISE_SPL', 'ASR_REFERENCE_TEXT', 'TRANSLATION_REFERENCE_TEXT',
                    'TAGS', 'REMARKS'
                ])
                testcases_df.loc[0] = [
                    '', '示例用例名称', '用例详细描述', '示例分组', '',
                    '中文->英文', 'api', '', '', '', 'ASR参考文本', '翻译参考文本',
                    '标签1,标签2', '备注信息'
                ]
                testcases_df.to_excel(writer, sheet_name='TestCases', index=False)
                
                audio_configs_df = pd.DataFrame(columns=[
                    'CASE_ID', 'CASE_NAME', 'AUDIO_ID', 'AUDIO_NAME', 'SPL',
                    'PLAYBACK_DEVICE_ID', 'PLAYBACK_DEVICE_NAME', 'PLAY_ORDER'
                ])
                audio_configs_df.loc[0] = ['', '示例用例名称', '', '示例音频.wav', 65, '', '', 1]
                audio_configs_df.loc[1] = ['', '示例用例名称', '', '示例音频2.wav', 70, '', '扬声器', 2]
                audio_configs_df.to_excel(writer, sheet_name='AudioConfigs', index=False)
                
                dims_df = pd.DataFrame(columns=[
                    'CASE_ID', 'CASE_NAME', 'DIMENSION_ID', 'DIMENSION_NAME', 'DIMENSION_DISPLAY_NAME', 'WEIGHT', 'THRESHOLD'
                ])
                dims_df.loc[0] = ['', '示例用例名称', '', 'BLEU', 'BLEU分数', 60, 85]
                dims_df.loc[1] = ['', '示例用例名称', '', 'METEOR', 'METEOR分数', 40, 75]
                dims_df.loc[2] = ['', '示例用例名称', '', 'WER', '字错误率', 70, 90]
                dims_df.to_excel(writer, sheet_name='Dimensions', index=False)
                
                tags_df = pd.DataFrame(columns=[
                    'TAG_ID', 'TAG_NAME', 'TAG_DESCRIPTION', 'TAG_COLOR'
                ])
                tags_df.loc[0] = ['', '语音测试', '语音相关测试用例', '#1677FF']
                tags_df.to_excel(writer, sheet_name='Tags', index=False)
                
                groups_df = pd.DataFrame(columns=[
                    'GROUP_ID', 'GROUP_NAME', 'GROUP_DESCRIPTION', 'PARENT_GROUP_NAME'
                ])
                groups_df.loc[0] = ['', '新分组名称', '分组描述', '']
                groups_df.to_excel(writer, sheet_name='Groups', index=False)

                case_tags_df = pd.DataFrame(columns=[
                    'CASE_ID', 'CASE_NAME', 'TAG_ID', 'TAG_NAME'
                ])
                case_tags_df.loc[0] = ['', '示例用例名称', '', '语音测试']
                case_tags_df.to_excel(writer, sheet_name='CaseTags', index=False)
            
            output.seek(0)
            return send_file(
                output,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=f'testcase_template_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
            )
        except Exception as e:
            return error_response(f"生成模板失败: {str(e)}")

    @staticmethod
    def preview_import():
        try:
            if 'file' not in request.files:
                return error_response("未上传文件")
            
            file = request.files['file']
            if file.filename == '':
                return error_response("未选择文件")
            
            file_extension = file.filename.split('.')[-1].lower()
            preview_result = {
                'totalRows': 0,
                'testCases': [],
                'audioConfigs': [],
                'dimensions': [],
                'tags': [],
                'groups': [],
                'errors': []
            }
            
            if file_extension in ['xlsx', 'xls']:
                xl = pd.ExcelFile(io.BytesIO(file.read()))
                sheet_names = xl.sheet_names
                
                if 'TestCases' in sheet_names:
                    df = pd.read_excel(xl, sheet_name='TestCases')
                    preview_result['totalRows'] = len(df)
                    df = df.astype(object).where(pd.notna(df), None)
                    preview_result['testCases'] = df.to_dict('records')
                
                if 'AudioConfigs' in sheet_names:
                    df = pd.read_excel(xl, sheet_name='AudioConfigs')
                    df = df.astype(object).where(pd.notna(df), None)
                    preview_result['audioConfigs'] = df.to_dict('records')
                
                if 'Dimensions' in sheet_names:
                    df = pd.read_excel(xl, sheet_name='Dimensions')
                    df = df.astype(object).where(pd.notna(df), None)
                    preview_result['dimensions'] = df.to_dict('records')
                
                if 'Tags' in sheet_names:
                    df = pd.read_excel(xl, sheet_name='Tags')
                    df = df.astype(object).where(pd.notna(df), None)
                    preview_result['tags'] = df.to_dict('records')
                
                if 'Groups' in sheet_names:
                    df = pd.read_excel(xl, sheet_name='Groups')
                    df = df.astype(object).where(pd.notna(df), None)
                    preview_result['groups'] = df.to_dict('records')
            elif file_extension == 'json':
                file_content = file.read().decode('utf-8')
                data = json.loads(file_content)
                preview_result['testCases'] = data.get('test_cases', [])
                preview_result['totalRows'] = len(preview_result['testCases'])
            elif file_extension == 'csv':
                df = pd.read_csv(io.BytesIO(file.read()), encoding='utf-8-sig')
                preview_result['totalRows'] = len(df)
                df = df.astype(object).where(pd.notna(df), None)
                preview_result['testCases'] = df.to_dict('records')
            else:
                return error_response("仅支持 JSON, CSV 或 Excel 格式")
            
            return success_response(data=preview_result)
        except Exception as e:
            return error_response(f"预览失败: {str(e)}")

    # ---- reference_params 文件读写 ----

    @staticmethod
    def get_ref_params(tc_id, round_number):
        """获取指定用例指定轮的参考参数文件内容"""
        tc = TestCase.query.filter_by(id=tc_id, deleted=False).first()
        if not tc:
            return error_response("未找到测试用例", 404)
        
        # 新架构：参考参数路径存于 test_cases.reference_params 独立列（[{round_number, reference_params_path}]）
        # 兼容旧架构：config.rounds[].referenceParamsPath
        ref_path = None
        ref_params_col = tc.reference_params or []
        if isinstance(ref_params_col, list):
            for item in ref_params_col:
                if isinstance(item, dict) and item.get('round_number') == round_number:
                    ref_path = item.get('reference_params_path') or item.get('referenceParamsPath')
                    break
        
        if not ref_path:
            config = tc.config or {}
            for r in config.get('rounds', []):
                if isinstance(r, dict) and (r.get('roundNumber') or r.get('round_number')) == round_number:
                    ref_path = r.get('referenceParamsPath') or r.get('reference_params_path')
                    break
        
        if not ref_path:
            return error_response(f"第 {round_number} 轮未配置参考参数路径", 404)
        
        ref_data = ReferenceParamsGenerator.load_from_file(ref_path)
        if ref_data is None:
            return error_response(f"参考参数文件不存在或读取失败: {ref_path}", 404)
        
        return success_response({
            'roundNumber': round_number,
            'referenceParamsPath': ref_path,
            'referenceParams': ref_data
        })

    @staticmethod
    def update_ref_params(tc_id, round_number):
        """更新指定用例指定轮的参考参数文件"""
        tc = TestCase.query.filter_by(id=tc_id, deleted=False).first()
        if not tc:
            return error_response("未找到测试用例", 404)
        
        data = request.get_json()
        if not data:
            return error_response("请求体不能为空")
        
        new_ref_params = data.get('referenceParams')
        if new_ref_params is None:
            return error_response("缺少 referenceParams 字段")
        
        from backend.utils.algorithm.reference_params_generator import normalize_reference_params
        new_ref_params = normalize_reference_params(new_ref_params)
        
        config = tc.config or {}
        rounds = config.get('rounds', [])
        
        target_round = None
        for r in rounds:
            if isinstance(r, dict) and r.get('roundNumber') == round_number:
                target_round = r
                break
        
        if not target_round:
            return error_response(f"未找到第 {round_number} 轮", 404)
        
        ref_path = target_round.get('referenceParamsPath')
        if not ref_path:
            return error_response(f"第 {round_number} 轮未配置参考参数路径", 404)
        
        import os
        if not os.path.exists(ref_path):
            return error_response(f"参考参数文件不存在: {ref_path}", 404)
        
        try:
            with open(ref_path, 'w', encoding='utf-8') as f:
                json.dump(new_ref_params, f, ensure_ascii=False, indent=2)
        except Exception as e:
            return error_response(f"写入参考参数文件失败: {str(e)}")
        
        return success_response({
            'roundNumber': round_number,
            'referenceParamsPath': ref_path,
            'referenceParams': new_ref_params
        }, "参考参数更新成功")

