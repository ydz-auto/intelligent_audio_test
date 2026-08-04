"""测试用例写操作 Service。

从 TestCaseController 抽取的 CRUD、批量操作及参考参数维护方法。
"""
import uuid
import json
import logging

from api_gateway.infrastructure.request_adapter import request
from shared.models.models import TestCase, TestCaseGroup, Tag
from shared.models.database import db
from shared.utils.response import success_response, error_response
from shared.utils.query_utils import now_cst
from shared.algorithm.reference_params_generator import ReferenceParamsGenerator

from api_gateway.schemas.common import StringIdData
from api_gateway.schemas.testcase import (
    TestCaseStopPreviewData,
    TestCaseCreateSchema,
    TestCaseUpdateSchema,
    TestCaseBatchActionRequest,
)
from api_gateway.application.services import testcase_common as common

logger = logging.getLogger(__name__)


class TestCaseCommandService:
    # 公共方法：刷新测试用例的ASR和翻译参考文本
    @staticmethod
    def refresh_reference_texts(test_case):
        """
        刷新测试用例的参考参数
        根据算法类型和测试用例配置，自动生成并更新config中的参考参数
        使用 ReferenceParamsGenerator 组件生成不同算法类型的参考字段
        """
        ReferenceParamsGenerator.apply_to_config(test_case)

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
        if common.has_rounds(config):
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
                    pdid = common.normalize_optional_int(audio_item.playback_device_id)
                    if aid is None or spl is None or porder is None:
                        return error_response(f"第 {i+1} 个音频配置缺少必要字段: audio_id, spl, play_order")
                    if test_type_val == 'e2e' and not pdid:
                        return error_response(f"第 {i+1} 个音频配置为 E2E 类型用例，必须指定 playback_device_id")
                standard_audios = []
                for audio_item in audios_data:
                    standard_audios.append({
                        'audio_id': audio_item.audio_id,
                        'spl': audio_item.spl,
                        'playback_device_id': common.normalize_optional_int(audio_item.playback_device_id),
                        'play_order': audio_item.play_order
                    })
                merged_config['audios'] = standard_audios

            dimensions_data = data.dimensions
            if dimensions_data:
                merged_config['dimensions'] = dimensions_data

            # 转换为 rounds 格式
            merged_config = common.convert_flat_config_to_rounds(merged_config)

        # 多轮用例校验：不支持需要传递音频文件的维度
        audio_dim_error = common.validate_multi_round_audio_dimensions(merged_config)
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
            TestCaseCommandService.refresh_reference_texts(new_tc)

            db.session.commit()

            from shared.utils.report.stats_cache import refresh_stats_cache
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
                if common.has_rounds(data.config):
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
                    merged_config = common.convert_flat_config_to_rounds(data.config.copy())
            elif common.has_rounds(current_config):
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
                merged_config = common.convert_flat_config_to_rounds(current_config.copy())

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
                    pdid = common.normalize_optional_int(audio_item.playback_device_id)
                    if aid is None or spl is None or porder is None:
                        return error_response(f"第 {i+1} 个音频配置缺少必要字段: audio_id, spl, play_order")
                    if tc_test_type == 'e2e' and not pdid:
                        return error_response(f"第 {i+1} 个音频配置为 E2E 类型用例，必须指定 playback_device_id")
                standard_audios = []
                for audio_item in audios_data:
                    standard_audios.append({
                        'audio_id': audio_item.audio_id,
                        'spl': audio_item.spl,
                        'playback_device_id': common.normalize_optional_int(audio_item.playback_device_id),
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
            audio_dim_error = common.validate_multi_round_audio_dimensions(merged_config)
            if audio_dim_error:
                return error_response(audio_dim_error)

            tc.config = merged_config

            algorithm_type = data.algorithm_type
            need_refresh_reference = False

            if common.audios_changed(current_config, merged_config):
                need_refresh_reference = True

            if algorithm_type is not None and algorithm_type != tc.algorithm_type:
                need_refresh_reference = True
                tc.algorithm_type = algorithm_type

            if algo_params_col:
                # 优先从独立列读旧参数，兼容旧数据从 config 读
                old_params = common.get_algo_params_list_from_columns(tc.algorithm_params, 1)
                if not old_params:
                    old_params = common.get_algo_params_list_from_config(current_config)
                # 新参数从按轮分组格式提取 round_number=1
                new_params = common.get_algo_params_list_from_columns(algo_params_col, 1)
                if common.has_overlap_param_changed(old_params, new_params):
                    need_refresh_reference = True

            tc.updated_at = now_cst()

            if need_refresh_reference:
                TestCaseCommandService.refresh_reference_texts(tc)

            db.session.commit()

            from shared.utils.report.stats_cache import refresh_stats_cache
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
            now = now_cst()
            tc.deleted = True
            tc.deleted_at = now
            tc.updated_at = now
            db.session.commit()

            from shared.utils.report.stats_cache import refresh_stats_cache
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
            TestCaseCommandService.refresh_reference_texts(new_tc)

            db.session.commit()
            return success_response(StringIdData(id=new_id), "测试用例复制成功", 0, 201)
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    # 停止预览测试用例
    @staticmethod
    def stop_preview(tc_id):
        """停止预览测试用例：向音频引擎发送停止信号"""
        # 跨服务调用：通过 gRPC AudioService 调用音频引擎
        from api_gateway.infrastructure.grpc_proxies import audio_service
        preview_task_id = f"PREVIEW_{tc_id}"

        # 设置停止标志，通知播放线程停止（共享于 common 模块）
        common.preview_stop_flags[tc_id] = True

        # 停止音频播放 - 停止所有 PREVIEW_ 开头的任务
        try:
            audio_service.stop_task_audio_by_pattern("PREVIEW_")
        except AttributeError:
            # gRPC 服务不可用时忽略，本地预览已通过 preview_stop_flags 停止
            pass

        return success_response(TestCaseStopPreviewData(test_case_id=tc_id, status="preview_stopped", message="预览已停止"))

    # 批量操作
    @staticmethod
    def batch_action():
        """批量操作入口：验证请求并分发到对应处理函数"""
        req_data = TestCaseBatchActionRequest.model_validate(request.get_json())
        action = req_data.action

        # action → handler 映射
        handlers = {
            'delete': TestCaseCommandService._batch_delete,
            'move_to_group': TestCaseCommandService._batch_move_to_group,
            'copy_to_group': TestCaseCommandService._batch_copy_to_group,
            'copy': TestCaseCommandService._batch_copy,
            'copy_by_group': TestCaseCommandService._batch_copy_by_group,
            'update_algorithm_params': TestCaseCommandService._batch_update_algorithm_params,
            'update_playback_devices': TestCaseCommandService._batch_update_playback_devices,
            'update_spl': TestCaseCommandService._batch_update_spl,
            'update_dimensions': TestCaseCommandService._batch_update_dimensions,
            'update_noise': TestCaseCommandService._batch_update_noise,
            'auto_generate_name': TestCaseCommandService._batch_auto_generate_name,
            'add_tags': TestCaseCommandService._batch_add_tags,
            'remove_tags': TestCaseCommandService._batch_remove_tags,
            'rename_tag': TestCaseCommandService._batch_rename_tag,
            'refresh_reference': TestCaseCommandService._batch_refresh_reference,
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
            from shared.utils.report.stats_cache import refresh_stats_cache
            refresh_stats_cache()
            return success_response(None, message)
        except Exception as e:
            db.session.rollback()
            return error_response(str(e))

    @staticmethod
    def _batch_delete(req_data):
        """批量删除用例"""
        ids = req_data.ids
        now = now_cst()
        TestCase.query.filter(TestCase.id.in_(ids)).update(
            {"deleted": True, "deleted_at": now, "updated_at": now},
            synchronize_session=False
        )
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
                TestCaseCommandService.refresh_reference_texts(new_tc)
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
                TestCaseCommandService.refresh_reference_texts(new_tc)
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
            TestCaseCommandService.refresh_reference_texts(new_tc)
            copied_count += 1
        return f"已成功复制分组 '{new_group_name}' 的 {copied_count} 个用例"

    @staticmethod
    def _batch_update_algorithm_params(req_data):
        """批量更新用例专属参数"""
        ids = req_data.ids
        algorithm_params = req_data.algorithm_params
        if algorithm_params is None:
            return error_response("更新用例专属参数需要 'algorithm_params'")
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
            tc.algorithm_params = [{'round_number': 1, 'params': [{'field_code': k, 'field_value': v} for k, v in ap_dict.items()]}]
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

        test_cases = TestCase.query.filter(TestCase.id.in_(ids), TestCase.deleted == False).all()
        logger.info(f"[update_playback_devices] 查询到 {len(test_cases)} 个用例")

        updated_count = 0
        for tc in test_cases:
            if (tc.test_type or 'api') != 'e2e':
                continue
            logger.debug(f"[update_playback_devices] 处理用例 {tc.id}, config: {tc.config}")
            if tc.config:
                config = tc.config.copy()
                device_id = playback_devices.get('deviceId') or playback_devices.get('device_id')
                for round_item in config.get('rounds', []):
                    if isinstance(round_item, dict):
                        for idx, audio_config in enumerate(round_item.get('audios', [])):
                            logger.debug(f"[update_playback_devices] 更新用例 {tc.id} round audio[{idx}] 的 playback_device_id 为 {device_id}")
                            if device_id is not None:
                                audio_config['playback_device_id'] = device_id
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

        test_cases = TestCase.query.filter(TestCase.id.in_(ids), TestCase.deleted == False).all()
        logger.info(f"[update_spl] 查询到 {len(test_cases)} 个用例")

        updated_count = 0
        for tc in test_cases:
            if (tc.test_type or 'api') != 'e2e':
                continue
            logger.debug(f"[update_spl] 处理用例 {tc.id}, config: {tc.config}")
            if tc.config:
                config = tc.config.copy()
                for round_item in config.get('rounds', []):
                    if isinstance(round_item, dict):
                        for audio_config in round_item.get('audios', []):
                            if spl_data.get('value') is not None:
                                audio_config['spl'] = spl_data['value']
                                logger.debug(f"[update_spl] 更新用例 {tc.id} 的 spl 为 {spl_data['value']}")
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
                    if isinstance(round_item, dict):
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

        logger.info(f"[update_noise] audio_id: {audio_id}, spl: {spl}, device_ids: {device_ids}")

        test_cases = TestCase.query.filter(TestCase.id.in_(ids), TestCase.deleted == False).all()
        logger.info(f"[update_noise] 查询到 {len(test_cases)} 个用例")

        updated_count = 0
        for tc in test_cases:
            if (tc.test_type or 'api') != 'e2e':
                continue
            logger.info(f"[update_noise] 处理用例 {tc.id}, 当前 config: {tc.config}")
            if tc.config is None:
                config = {}
            else:
                config = tc.config.copy()

            for round_item in config.get('rounds', []):
                if isinstance(round_item, dict):
                    if 'backgroundNoise' not in round_item:
                        round_item['backgroundNoise'] = {'audio_id': '', 'spl': 0, 'device_ids': []}
                    if audio_id is not None:
                        round_item['backgroundNoise']['audio_id'] = audio_id
                    if spl is not None:
                        round_item['backgroundNoise']['spl'] = spl
                    if device_ids is not None:
                        round_item['backgroundNoise']['device_ids'] = device_ids

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
        logger.info(f"[refresh_reference] 开始处理, ids: {ids}")

        test_cases = TestCase.query.filter(
            TestCase.id.in_(ids),
            TestCase.deleted == False
        ).all()
        logger.info(f"[refresh_reference] 查询到 {len(test_cases)} 个用例")

        if len(ids) > 50:
            from shared.utils.reference_refresh_task import submit_reference_refresh_task
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
                    TestCaseCommandService.refresh_reference_texts(tc)
                    tc.updated_at = now_cst()
                    db.session.add(tc)
                    updated_count += 1
                except Exception as e:
                    logger.error(f"[refresh_reference] 处理用例 {tc.id} 失败: {e}")

            db.session.commit()
            logger.info(f"[refresh_reference] 更新完成，共更新 {updated_count} 个用例")
            return f"已成功刷新 {updated_count} 个用例的参考参数"

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

        from shared.algorithm.reference_params_generator import normalize_reference_params
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
