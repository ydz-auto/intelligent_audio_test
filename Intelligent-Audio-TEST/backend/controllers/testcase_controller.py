import os
from flask import request, send_file, current_app
from backend.models.models import TestCase, TestCaseGroup, Tag, Dimension, Audio, PlaybackDevice
from backend.models.database import db
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
import logging
import pandas as pd
from datetime import datetime, timezone, timedelta
from backend.utils.common.query_utils import now_cst

logger = logging.getLogger(__name__)

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
    def _validate_multi_round_audio_dimensions(config: dict):
        """校验整体评估(config.dimensions)不能配置需要音频文件的维度
        
        整体评估在所有轮次执行完成后触发，无法传递音频文件。
        只检查 config.dimensions（整体评估维度），不检查 rounds[].evaluation.dimensions（单轮维度）。
        多轮时，rounds[].evaluation.dimensions（单轮评估）允许配置音频维度。
        """
        if not config:
            return None
        rounds = config.get('rounds', [])
        if not isinstance(rounds, list) or len(rounds) <= 1:
            return None  # 单轮不限制

        # 只收集 config.dimensions（整体评估维度），不收集 rounds[].evaluation.dimensions
        overall_dims = config.get('dimensions', [])
        dim_ids = set()
        for d in overall_dims:
            dim_id = d.get('id') if isinstance(d, dict) else d
            if dim_id:
                dim_ids.add(dim_id)
        if not dim_ids:
            return None

        # 查询这些维度是否有 field_type='audio' 的输入参数
        from backend.models.algorithm_models import EvaluationDimensionParam
        audio_dims = db.session.query(
            EvaluationDimensionParam.dimension_id,
            EvaluationDimensionParam.param_code
        ).filter(
            EvaluationDimensionParam.dimension_id.in_(dim_ids),
            EvaluationDimensionParam.field_type == 'audio',
            EvaluationDimensionParam.param_direction == 'input',
            EvaluationDimensionParam.deleted == False
        ).all()

        if audio_dims:
            # 查维度名
            dim_map = {d.id: d.name for d in Dimension.query.filter(Dimension.id.in_([ad[0] for ad in audio_dims])).all()}
            dim_names = [dim_map.get(ad[0], f"ID:{ad[0]}") for ad in audio_dims]
            param_codes = [ad[1] for ad in audio_dims]
            return (f"整体评估维度不支持需要传递音频文件的维度。"
                    f"维度 {', '.join(dim_names)} 包含音频参数({', '.join(param_codes)})，"
                    f"请在单轮评估中配置该维度，或从整体评估中移除。")
        return None

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
        view = request.args.get('view')
        include_deleted_raw = request.args.get('include_deleted', 'false')
        include_deleted = str(include_deleted_raw).lower() in ('true', '1', 'yes')

        # ===== 标签视图：按标签聚合返回 =====
        if view == 'tag':
            return TestCaseController._get_tag_view(
                page=page, per_page=per_page, keyword=keyword,
                test_type=test_type, algorithm_type=algorithm_type,
                include_deleted=include_deleted,
            )

        query = TestCase.query.options(
            joinedload(TestCase.group),
            joinedload(TestCase.tags)
        ).order_by(TestCase.created_at.desc())
        if not include_deleted:
            query = query.filter(TestCase.deleted == False)

        if keyword:
            query = query.filter(
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
    def _get_tag_view(page=1, per_page=10, keyword=None, test_type=None, algorithm_type=None, include_deleted=False):
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

        if not include_deleted:
            tc_query = tc_query.filter(TestCase.deleted == False)
        if keyword:
            tc_query = tc_query.filter(
                (TestCase.name.like(f'%{keyword}%')) |
                (TestCase.description.like(f'%{keyword}%'))
            )
        if test_type and test_type in ['api', 'e2e']:
            tc_query = tc_query.filter(TestCase.test_type == test_type)
        if algorithm_type:
            tc_query = tc_query.filter(TestCase.algorithm_type == algorithm_type)

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
            group = TestCaseGroup.query.filter_by(name=group_name).first()
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
        
        # 多轮用例校验：不支持需要传递音频文件的维度
        audio_dim_error = TestCaseController._validate_multi_round_audio_dimensions(merged_config)
        if audio_dim_error:
            return error_response(audio_dim_error)

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
                group = TestCaseGroup.query.filter_by(name=group_name).first()
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
            
            # 多轮用例校验：不支持需要传递音频文件的维度
            audio_dim_error = TestCaseController._validate_multi_round_audio_dimensions(merged_config)
            if audio_dim_error:
                return error_response(audio_dim_error)

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
        TestCase.query.filter(TestCase.id.in_(ids)).update({"deleted": True}, synchronize_session=False)
        return f"已成功批量删除 {len(ids)} 个用例"

    @staticmethod
    def _batch_move_to_group(req_data):
        """批量移动到分组"""
        ids = req_data.ids
        target_group_id = req_data.target_group_id
        if not target_group_id:
            return error_response("移动操作需要 'target_group_id'")
        TestCase.query.filter(TestCase.id.in_(ids)).update({"group_id": target_group_id}, synchronize_session=False)
        return f"已成功将 {len(ids)} 个用例移动至目标分组"

    @staticmethod
    def _batch_copy_to_group(req_data):
        """复制到指定分组"""
        ids = req_data.ids
        target_group_id = req_data.target_group_id
        if not target_group_id:
            return error_response("复制到分组操作需要 'target_group_id'")
        target_group = TestCaseGroup.query.filter_by(id=target_group_id).first()
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
        source_group = TestCaseGroup.query.filter_by(name=group_name).first()
        if not source_group:
            return error_response(f"未找到分组: {group_name}")

        new_group_name = f"{group_name}_copy"
        existing_group = TestCaseGroup.query.filter_by(name=new_group_name).first()
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

        if dimensions_data is None:
            logger.error("[update_dimensions] 缺少 dimensions 参数")
            return error_response("更新评价维度需要 'dimensions'")

        # 获取轮次范围
        round_mode = getattr(req_data, 'round_mode', None) or 'all'
        round_numbers = getattr(req_data, 'round_numbers', None) or []

        test_cases = TestCase.query.filter(TestCase.id.in_(ids), TestCase.deleted == False).all()
        logger.info(f"[update_dimensions] 查询到 {len(test_cases)} 个用例")

        updated_count = 0
        for tc in test_cases:
            if tc.config:
                config = tc.config.copy()
                new_dim_list = []
                for dim in dimensions_data:
                    dim_id = dim.get('id')
                    dim_name = dim.get('name', '')
                    dim_weight = dim.get('weight', 50)
                    dim_threshold = dim.get('threshold', 60)
                    new_dim_list.append({
                        'id': dim_id,
                        'name': dim_name,
                        'weight': dim_weight,
                        'threshold': dim_threshold
                    })
                    logger.debug(f"[update_dimensions] 用例 {tc.id} 设置维度 {dim_id}")

                for round_item in config.get('rounds', []):
                    if not isinstance(round_item, dict):
                        continue
                    # 轮次过滤
                    rn = round_item.get('round_number') or round_item.get('roundNumber')
                    if round_mode == 'specific' and rn not in round_numbers:
                        continue
                    if 'evaluation' not in round_item:
                        round_item['evaluation'] = {}
                    round_item['evaluation']['dimensions'] = new_dim_list
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
                group = TestCaseGroup.query.filter_by(name=data['group']).first()
                if group:
                    query = query.filter(TestCase.group_id == group.id)
                else:
                    # 未找到分组则返回空
                    return jsonify({'ids': []})

            if data.get('test_type'):
                query = query.filter(TestCase.test_type == data['test_type'])

            if data.get('search'):
                keyword = f"%{data['search']}%"
                query = query.filter(TestCase.name.like(keyword))

            if data.get('tag'):
                # 按标签筛选
                query = query.join(TestCase.tags).filter(Tag.name == data['tag'])

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
             .filter(TestCase.deleted == False)\
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
            
            # 查询指定的测试用例
            query = TestCase.query.filter(TestCase.id.in_(ids))
            if not include_deleted:
                query = query.filter(TestCase.deleted == False)
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
                            group_objects = TestCaseGroup.query.filter(TestCaseGroup.id.in_(list(unique_groups.keys()))).all()
                            group_by_id = {g.id: g for g in group_objects}
                            missing_names = [v for k, v in unique_groups.items() if k not in group_by_id]
                            if missing_names:
                                group_objects_by_name = TestCaseGroup.query.filter(TestCaseGroup.name.in_(missing_names)).all()
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
                        group = db.session.get(TestCaseGroup, group_id)
                    
                    if not group:
                        group = TestCaseGroup.query.filter_by(name=group_name).first()
                    
                    if not group:
                        # 如果都没有，则创建（注意：如果 group_id 是 UUID 字符串，建议使用 name 创建）
                        group = TestCaseGroup(id=str(uuid.uuid4()) if not group_id else group_id, name=group_name)
                        db.session.add(group)
                        db.session.flush()
                    
                    # 2. 检查是更新还是创建
                    tc_id = case_data.get('id')
                    existing_tc = None
                    if tc_id:
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

