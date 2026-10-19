# -*- coding: utf-8 -*-
"""TestCaseCrudService — 测试用例核心 CRUD 应用服务。

将网关 TestCaseCommandService / TestCaseQueryService 的
业务逻辑下沉到 task_service，通过 gRPC TestCaseConfigService 暴露。

整改说明：
- 引入 Repository 模式，消除所有 session 直连 DB（参见 testcase_repository.py）
- 批量操作委托 testcase_batch_service.TestCaseBatchService
- 查询操作委托 testcase_query_service.TestCaseQueryService
- 模块级单例 testcase_crud_service 保持可用，方法签名与返回格式不变

约定：
- 所有方法返回 dict: {success, message, data, code?}
- 复杂参数通过 JSON dict 传递
- 网关侧负责 Pydantic 校验，此处仅处理业务逻辑
- 保留软删除模式（deleted=True + deleted_at）
- 跨域查询（Audio / Dimension）通过 repo 访问并加注释标记后续 gRPC 改造
"""
from __future__ import annotations

import copy
import json
import logging
import os
import uuid
from datetime import datetime, timezone, timedelta

from shared.utils.query_utils import now_cst
from shared.utils.testcase_helpers import derive_case_test_type as common_derive_case_test_type
from task_service.infrastructure.persistence.testcase_repository import testcase_repository
from task_service.application.testcase.testcase_batch_service import TestCaseBatchService
from task_service.application.testcase.testcase_query_service import TestCaseQueryService

logger = logging.getLogger(__name__)

_UTC_PLUS_8 = timezone(timedelta(hours=8))

# reference_params 文件存储到 OSS（ref_params bucket）
_REF_PARAMS_BUCKET = 'ref_params'


def _build_ref_params_key(case_id, round_number, filename=None):
    """构建参考参数 OSS key：{case_id}/{filename} 或 {case_id}/round_{round_number}.json"""
    if filename is None:
        filename = f"round_{round_number}.json"
    return f"{case_id}/{filename}"


def _resolve_strategy_config(data, config, current_strategy_id=None, current_overrides=None):
    """INT-590：评估策略引用 + 覆盖（写时物化）。

    保存用例时合并策略 config 与用例级 strategy_overrides，解析结果写回
    config.dimensions / config.background_noise（下游 e2e/评估/报告零改动，
    任务创建快照天然含解析后配置）。strategy_id + overrides 另列落库由调用方完成。

    Returns:
        (error_message_or_None, strategy_id_or_None, overrides_or_None)
    """
    from task_service.domain.services.evaluation_strategy_merge import (
        evaluation_strategy_merge_service,
    )

    strategy_id = data.get('strategy_id')
    overrides = data.get('strategy_overrides')

    # 显式清空引用（空字符串）：保留当前 config 快照（P1 不回灌）
    if strategy_id is not None and str(strategy_id) == '':
        return None, None, None

    if not strategy_id:
        # 未传 strategy_id：沿用既有引用（用例编辑抽屉仅改音频/参数时不动策略）
        strategy_id = current_strategy_id
        if overrides is None:
            overrides = current_overrides

    if not strategy_id:
        return None, None, None

    if overrides is not None:
        err = evaluation_strategy_merge_service.validate_overrides(overrides)
        if err:
            return err, None, None

    from task_service.infrastructure.persistence.testcase_repository import testcase_repository
    strategy = testcase_repository.get_evaluation_strategy(strategy_id)
    if not strategy:
        return f"评估策略不存在或已删除: {strategy_id}", None, None

    resolved = evaluation_strategy_merge_service.resolve(strategy.config, overrides)
    if resolved.get('dimensions'):
        config['dimensions'] = resolved['dimensions']
    if resolved.get('background_noise'):
        config['background_noise'] = resolved['background_noise']
    return None, strategy_id, overrides


def _apply_reference_params_to_config(test_case) -> None:
    """为 test_case 逐轮生成参考参数并写入 OSS，路径存入 reference_params 独立列。

    替代 ReferenceParamsGenerator.apply_to_config，改为通过 gRPC 调用
    algorithm_service 生成每轮参考参数，存储逻辑仍在 task_service 本地完成。
    """
    if not test_case:
        return

    config = test_case.config or {}
    rounds = config.get('rounds', [])

    if not rounds:
        return

    from task_service.infrastructure.acl.algorithm_acl_repository import AlgorithmRepository
    _algo_repo = AlgorithmRepository()

    case_id = getattr(test_case, 'id', '') or str(id(test_case))

    # 构建传入 gRPC 的 test_case_config（algorithm_type / config / test_type，
    # test_type 为算法服务参考值口径契约值，由配置形态派生）
    test_case_config = {
        'algorithm_type': getattr(test_case, 'algorithm_type', None),
        'config': config,
        'test_type': common_derive_case_test_type(config),
    }

    ref_params_list = []
    total_params = 0
    for round_item in rounds:
        if not isinstance(round_item, dict):
            continue

        round_number = round_item.get('round_number') or round_item.get('roundNumber') or 1

        round_params = _algo_repo.algo_generate_reference_params(test_case_config, round_item)
        if not round_params:
            continue

        round_params = _algo_repo.algo_get_all_reference_params(round_params)

        oss_key = _build_ref_params_key(case_id, round_number)

        try:
            from shared.infrastructure.storage import storage_save_bytes
            data = json.dumps(round_params, ensure_ascii=False, indent=2).encode('utf-8')
            stored_path = storage_save_bytes(data, _REF_PARAMS_BUCKET, oss_key,
                                             content_type='application/json')
            ref_params_list.append({
                'round_number': round_number,
                'reference_params_path': stored_path
            })
            total_params += len(round_params)
        except Exception as e:
            logger.warning(f"round {round_number}: failed to upload {_REF_PARAMS_BUCKET}/{oss_key}: {e}")

    test_case.reference_params = ref_params_list



class TestCaseCrudService:
    """测试用例核心 CRUD 应用服务。"""

    def __init__(self):
        self.repo = testcase_repository
        self._batch_service = TestCaseBatchService(self.repo)
        self._query_service = TestCaseQueryService(self.repo)

    # ==================== 写操作 ====================

    def create(self, data: dict) -> dict:
        """创建测试用例。

        Args:
            data: 已通过网关 Pydantic 校验的请求体 dict，包含：
                name, description, group_id/group, config, algorithm_type,
                tags, audios, dimensions, background_noise_*,
                algorithm_params 等

        Returns:
            {success, message, data, code?}
        """
        from shared.utils import testcase_helpers as common

        try:
            name = data.get('name')
            if not name:
                return {'success': False, 'message': '缺少必要字段: name', 'data': None, 'code': 400}

            group_id = data.get('group_id')
            resolved_group = None
            if group_id is None and data.get('group'):
                group_name = data['group']
                group = self.repo.get_group_by_name(group_name)
                if group:
                    group_id = group.id if hasattr(group, 'id') else (group.get('id') if isinstance(group, dict) else None)
                    resolved_group = group
                else:
                    group_id = str(uuid.uuid4())
                    self.repo.create_group(
                        group_id, group_name, f"自动创建的分组: {group_name}"
                    )

            # INT-423：私有分组非 owner 不允许在其下建用例（越权写入 → 403）。
            # 按分组名解析（resolved_group）与 group_id 直传两条路径均先取分组
            # 对象校验可见性；分组不存在沿用现状（不额外拦截）。
            # getattr 防御：既有测试替身 repo 未实现 get_group_by_id 时跳过校验
            #（生产 testcase_repository 恒有该方法，校验必达）。
            from task_service.infrastructure.visibility_context import (
                check_object_visible, visibility_identity,
            )
            group_to_check = resolved_group
            if group_to_check is None and group_id is not None:
                get_group_by_id = getattr(self.repo, 'get_group_by_id', None)
                if get_group_by_id is not None:
                    group_to_check = get_group_by_id(group_id)
            if group_to_check is not None:
                _uid, _is_admin = visibility_identity()
                try:
                    check_object_visible(group_to_check, _uid, _is_admin)
                except PermissionError as e:
                    return {'success': False, 'message': str(e), 'data': None, 'code': 403}

            if group_id is None:
                return {'success': False, 'message': '缺少必要字段: group_id 或 group', 'data': None, 'code': 400}

            # 差异#2 收尾：用例是纯数据载体，不再接收/校验/存储 test_type；
            # 执行方式由任务侧被测设备类型（device_type）决定
            data.pop('test_type', None)

            # 构建 config
            config = data.get('config') or {}
            if common.has_rounds(config):
                merged_config = config.copy()
                for round_item in merged_config.get('rounds', []):
                    if isinstance(round_item, dict):
                        round_item.pop('algorithmParams', None)
                        round_item.pop('algorithm_params', None)
                        round_item.pop('referenceParamsPath', None)
                        round_item.pop('reference_params_path', None)
                        round_item.pop('interferers', None)
                device_error = self._process_case_devices(merged_config, from_rounds=True, common=common)
                if device_error is not None:
                    return {'success': False, 'message': device_error, 'data': None, 'code': 400}
            else:
                merged_config = config.copy() if config else {}
                if 'background_noise' not in merged_config:
                    bg_noise_audio_id = data.get('background_noise_id')
                    bg_noise_spl = data.get('background_noise_spl')
                    bg_noise_device_ids = data.get('background_noise_device_ids')
                    if bg_noise_audio_id is not None:
                        merged_config['background_noise'] = {
                            'audio_id': bg_noise_audio_id,
                            'spl': bg_noise_spl
                        }
                        if bg_noise_device_ids:
                            merged_config['background_noise']['device_ids'] = bg_noise_device_ids

                audios_result = self._process_case_audios(data, common)
                if audios_result is not None and isinstance(audios_result, str):
                    return {'success': False, 'message': audios_result, 'data': None, 'code': 400}
                if audios_result is not None:
                    merged_config['audios'] = audios_result

                dimensions_data = data.get('dimensions')
                if dimensions_data:
                    merged_config['dimensions'] = dimensions_data

                merged_config = common.convert_flat_config_to_rounds(merged_config)

            # INT-590：评估策略引用 + 覆盖（写时物化，解析结果并入 config.dimensions /
            # config.background_noise；strategy_id + overrides 另列落库）
            strategy_error, strategy_id_val, strategy_overrides_val = _resolve_strategy_config(
                data, merged_config)
            if strategy_error is not None:
                return {'success': False, 'message': strategy_error, 'data': None, 'code': 400}

            algo_params_col = data.get('algorithm_params')
            if algo_params_col:
                first = algo_params_col[0] if isinstance(algo_params_col[0], dict) else {}
                if 'round_number' not in first and 'params' not in first:
                    algo_params_col = [{'round_number': 1, 'params': algo_params_col}]

            try:
                tc_id = str(uuid.uuid4())
                new_tc = self.repo.create_testcase({
                    'id': tc_id,
                    'name': name,
                    'description': data.get('description'),
                    'group_id': group_id,
                    'config': merged_config,
                    'algorithm_params': algo_params_col,
                    'algorithm_type': data.get('algorithm_type'),
                    'strategy_id': strategy_id_val,
                    'strategy_overrides': strategy_overrides_val,
                })

                # 处理标签
                tags_data = data.get('tags')
                if tags_data:
                    self.repo.set_testcase_tags(new_tc, tags_data)

                # 刷新参考文本
                try:
                    _apply_reference_params_to_config(new_tc)
                except Exception as e:
                    logger.warning(f"刷新参考文本失败: {e}")

                self.repo.commit()

                # INT-464 数据可见性：用例建后把引用音频 visibility 经 gRPC 同步过来
                try:
                    from task_service.application.testcase.audio_visibility_sync import (
                        sync_case_audio_visibility,
                    )
                    sync_case_audio_visibility(
                        tc_id,
                        data.get('visibility'),
                        merged_config,
                    )
                except Exception:
                    logger.warning("创建测试用例后同步音频可见性失败", exc_info=True)

                try:
                    from api_gateway.application.services.stats_cache import refresh_stats_cache
                    refresh_stats_cache()
                except Exception:
                    logger.warning("创建测试用例后刷新统计缓存失败", exc_info=True)

                return {'success': True, 'message': '测试用例创建成功', 'data': {'id': tc_id}, 'code': 201}
            except Exception:
                self.repo.rollback()
                raise
        except Exception as e:
            logger.error(f"创建测试用例失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def update(self, tc_id: str, data: dict) -> dict:
        """更新测试用例。

        Args:
            tc_id: 测试用例 ID
            data: 已通过网关 Pydantic 校验的请求体 dict

        Returns:
            {success, message, data, code?}
        """
        from shared.utils import testcase_helpers as common

        try:
            tc = self.repo.get_testcase(tc_id)
            if not tc:
                return {'success': False, 'message': '未找到测试用例', 'data': None, 'code': 404}

            # INT-423：私有用例非 owner 更新返回 403
            from task_service.infrastructure.visibility_context import (
                check_object_visible, visibility_identity,
            )
            _uid, _is_admin = visibility_identity()
            try:
                check_object_visible(tc, _uid, _is_admin)
            except PermissionError as e:
                return {'success': False, 'message': str(e), 'data': None, 'code': 403}

            current_config = tc.config or {}

            # 更新基本字段
            group_id = data.get('group_id')
            if group_id is None and data.get('group'):
                group_name = data['group']
                group = self.repo.get_group_by_name(group_name)
                if group:
                    group_id = group.id
                else:
                    group_id = str(uuid.uuid4())
                    self.repo.create_group(
                        group_id, group_name, f"自动创建的分组: {group_name}"
                    )

            if group_id is not None:
                tc.group_id = group_id

            if data.get('name') is not None:
                tc.name = data['name']

            if data.get('description') is not None:
                tc.description = data['description']

            # 更新 config
            incoming_config = data.get('config')
            if incoming_config is not None:
                if common.has_rounds(incoming_config):
                    merged_config = incoming_config.copy()
                    for round_item in merged_config.get('rounds', []):
                        if isinstance(round_item, dict):
                            round_item.pop('algorithmParams', None)
                            round_item.pop('algorithm_params', None)
                            round_item.pop('referenceParamsPath', None)
                            round_item.pop('reference_params_path', None)
                            round_item.pop('interferers', None)
                else:
                    merged_config = common.convert_flat_config_to_rounds(incoming_config.copy())
            elif common.has_rounds(current_config):
                merged_config = current_config.copy()
                for round_item in merged_config.get('rounds', []):
                    if isinstance(round_item, dict):
                        round_item.pop('algorithmParams', None)
                        round_item.pop('algorithm_params', None)
                        round_item.pop('referenceParamsPath', None)
                        round_item.pop('reference_params_path', None)
                        round_item.pop('interferers', None)
            else:
                merged_config = common.convert_flat_config_to_rounds(current_config.copy())

            algo_params_col = data.get('algorithm_params')
            if algo_params_col:
                first = algo_params_col[0] if isinstance(algo_params_col[0], dict) else {}
                if 'round_number' not in first and 'params' not in first:
                    algo_params_col = [{'round_number': 1, 'params': algo_params_col}]
            if algo_params_col is not None:
                tc.algorithm_params = algo_params_col

            # 更新设备关联（背景噪声）
            bg_noise_audio_id = data.get('background_noise_id')
            bg_noise_spl = data.get('background_noise_spl')
            bg_noise_device_ids = data.get('background_noise_device_ids')
            if bg_noise_audio_id is not None:
                first_round = merged_config.get('rounds', [{}])[0]
                if isinstance(first_round, dict):
                    noise_cfg = {'audio_id': bg_noise_audio_id, 'spl': bg_noise_spl}
                    if bg_noise_device_ids:
                        noise_cfg['device_ids'] = bg_noise_device_ids
                    first_round['backgroundNoise'] = noise_cfg

            # INT-105 rounds 注入完整性：客户端携带 rounds 结构的 config 时，rounds
            # 即为唯一权威。GET 详情响应会把全部轮次音频拍平（附合成 id）、全部轮次
            # 维度去重后放在顶层 audios/dimensions 供展示；若原样回传详情，这两份
            # 聚合数据会被注入 round1，造成 round1 音频逐次累积膨胀并覆盖 round1
            # 单轮维度。故仅旧平面格式请求（未携带 rounds 结构）才把顶层字段注入 round1。
            legacy_flat_input = not (incoming_config is not None and common.has_rounds(incoming_config))

            # 更新音频关联
            audios_data = data.get('audios')
            if legacy_flat_input and audios_data is not None:
                for i, audio_item in enumerate(audios_data):
                    aid = audio_item.get('audio_id')
                    spl = audio_item.get('spl')
                    porder = audio_item.get('play_order')
                    pdid = common.normalize_optional_int(audio_item.get('playback_device_id'))
                    if aid is None or spl is None or porder is None:
                        return {'success': False, 'message': f"第 {i+1} 个音频配置缺少必要字段: audio_id, spl, play_order", 'data': None, 'code': 400}

                standard_audios = []
                for audio_item in audios_data:
                    standard_audios.append({
                        'audio_id': audio_item.get('audio_id'),
                        'spl': audio_item.get('spl'),
                        'playback_device_id': common.normalize_optional_int(audio_item.get('playback_device_id')),
                        'play_order': audio_item.get('play_order')
                    })
                first_round = merged_config.get('rounds', [{}])[0]
                if isinstance(first_round, dict):
                    first_round['audios'] = standard_audios

            # 处理 dimensions
            dimensions_data = data.get('dimensions')
            if legacy_flat_input and dimensions_data is not None:
                first_round = merged_config.get('rounds', [{}])[0]
                if isinstance(first_round, dict):
                    if 'evaluation' not in first_round:
                        first_round['evaluation'] = {}
                    first_round['evaluation']['dimensions'] = dimensions_data

            # 更新标签
            tags_data = data.get('tags')
            if tags_data is not None:
                self.repo.set_testcase_tags(tc, tags_data)

            # INT-590：评估策略引用 + 覆盖（写时物化，解析结果并入 config.dimensions /
            # config.background_noise；strategy_id + overrides 另列落库）。
            # 未传 strategy_id 时沿用既有引用（仅改音频/参数不动策略），
            # 显式传空字符串则清空引用（保留当前 config 快照，P1 不回灌）。
            strategy_error, strategy_id_val, strategy_overrides_val = _resolve_strategy_config(
                data, merged_config,
                current_strategy_id=getattr(tc, 'strategy_id', None),
                current_overrides=getattr(tc, 'strategy_overrides', None),
            )
            if strategy_error is not None:
                return {'success': False, 'message': strategy_error, 'data': None, 'code': 400}

            tc.strategy_id = strategy_id_val
            tc.strategy_overrides = strategy_overrides_val

            tc.config = merged_config

            # INT-464 跟随用例同步最小列：改用例时同步落可见性（供其他用例取最宽松聚合）
            if data.get('visibility') is not None:
                tc.visibility = data['visibility']

            algorithm_type = data.get('algorithm_type')
            need_refresh_reference = False

            if common.audios_changed(current_config, merged_config):
                need_refresh_reference = True

            if algorithm_type is not None and algorithm_type != tc.algorithm_type:
                need_refresh_reference = True
                tc.algorithm_type = algorithm_type

            if algo_params_col:
                old_params = common.get_algo_params_list_from_columns(tc.algorithm_params, 1)
                if not old_params:
                    old_params = common.get_algo_params_list_from_config(current_config)
                new_params = common.get_algo_params_list_from_columns(algo_params_col, 1)
                if common.has_overlap_param_changed(old_params, new_params):
                    need_refresh_reference = True

            tc.updated_at = now_cst()
            from shared.infrastructure.user_context import get_current_user_id
            tc.updated_by_user_id = get_current_user_id()

            if need_refresh_reference:
                try:
                    _apply_reference_params_to_config(tc)
                except Exception as e:
                    logger.warning(f"刷新参考文本失败: {e}")

            try:
                self.repo.commit()

                # INT-464 数据可见性：用例改后把引用音频 visibility 经 gRPC 同步过来。
                # 用例可见性优先取请求载荷（前端新建/编辑选择器），PO 列补齐
                # （INT-463）后回落读取，列缺失时按迁移默认 shared 聚合。
                try:
                    from task_service.application.testcase.audio_visibility_sync import (
                        sync_case_audio_visibility,
                    )
                    case_visibility = data.get('visibility')
                    if case_visibility is None:
                        case_visibility = getattr(tc, 'visibility', None)
                    sync_case_audio_visibility(
                        tc_id,
                        case_visibility,
                        merged_config,
                    )
                except Exception:
                    logger.warning("更新测试用例后同步音频可见性失败", exc_info=True)

                try:
                    from api_gateway.application.services.stats_cache import refresh_stats_cache
                    refresh_stats_cache()
                except Exception:
                    logger.warning("更新测试用例后刷新统计缓存失败", exc_info=True)

                return {'success': True, 'message': '测试用例更新成功', 'data': None}
            except Exception:
                self.repo.rollback()
                raise
        except Exception as e:
            logger.error(f"更新测试用例失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def delete(self, tc_id: str) -> dict:
        """软删除测试用例。

        INT-423：私有用例非 owner 删除返回 403。
        """
        try:
            tc = self.repo.get_testcase(tc_id)
            if not tc:
                return {'success': False, 'message': '未找到测试用例', 'data': None, 'code': 404}
            from task_service.infrastructure.visibility_context import (
                check_object_visible, visibility_identity,
            )
            _uid, _is_admin = visibility_identity()
            try:
                check_object_visible(tc, _uid, _is_admin)
            except PermissionError as e:
                return {'success': False, 'message': str(e), 'data': None, 'code': 403}

            if not self.repo.soft_delete_testcase(tc_id):
                return {'success': False, 'message': '未找到测试用例', 'data': None, 'code': 404}

            try:
                self.repo.commit()

                try:
                    from api_gateway.application.services.stats_cache import refresh_stats_cache
                    refresh_stats_cache()
                except Exception:
                    logger.warning("删除测试用例后刷新统计缓存失败", exc_info=True)

                return {'success': True, 'message': '测试用例已删除', 'data': None}
            except Exception:
                self.repo.rollback()
                raise
        except Exception as e:
            logger.error(f"删除测试用例失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def copy(self, tc_id: str) -> dict:
        """复制测试用例。

        INT-423：私有用例非 owner 不允许复制（越权读取源数据 → 403）。
        """
        try:
            tc = self.repo.get_testcase(tc_id)
            if not tc:
                return {'success': False, 'message': '未找到原始测试用例', 'data': None, 'code': 404}
            from task_service.infrastructure.visibility_context import (
                check_object_visible, visibility_identity,
            )
            _uid, _is_admin = visibility_identity()
            try:
                check_object_visible(tc, _uid, _is_admin)
            except PermissionError as e:
                return {'success': False, 'message': str(e), 'data': None, 'code': 403}

            try:
                new_id = str(uuid.uuid4())
                new_tc = self.repo.create_testcase({
                    'id': new_id,
                    'name': f"{tc.name}_copy",
                    'description': tc.description,
                    'group_id': tc.group_id,
                    'config': tc.config.copy() if tc.config else {},
                    'algorithm_params': copy.deepcopy(tc.algorithm_params) if tc.algorithm_params else None,
                    'reference_params': copy.deepcopy(tc.reference_params) if tc.reference_params else None,
                    'algorithm_type': tc.algorithm_type,
                    # INT-590：复制用例保留策略引用（config 已含解析后快照，引用列随拷贝）
                    'strategy_id': getattr(tc, 'strategy_id', None),
                    'strategy_overrides': copy.deepcopy(getattr(tc, 'strategy_overrides', None)),
                })

                for tag in tc.tags:
                    new_tc.tags.append(tag)

                try:
                    _apply_reference_params_to_config(new_tc)
                except Exception as e:
                    logger.warning(f"刷新参考文本失败: {e}")

                self.repo.commit()

                # INT-464 数据可见性：复制用例同样触发引用音频可见性跟随同步
                try:
                    from task_service.application.testcase.audio_visibility_sync import (
                        sync_case_audio_visibility,
                    )
                    sync_case_audio_visibility(
                        new_id,
                        getattr(tc, 'visibility', None),
                        new_tc.config,
                    )
                except Exception:
                    logger.warning("复制测试用例后同步音频可见性失败", exc_info=True)

                return {'success': True, 'message': '测试用例复制成功', 'data': {'id': new_id}, 'code': 201}
            except Exception:
                self.repo.rollback()
                raise
        except Exception as e:
            logger.error(f"复制测试用例失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def update_ref_params(self, tc_id: str, round_number: int, data: dict) -> dict:
        """更新指定用例指定轮的参考参数文件。"""
        from task_service.infrastructure.acl.algorithm_acl_repository import AlgorithmRepository
        _algo_repo = AlgorithmRepository()

        try:
            tc = self.repo.get_testcase(tc_id)
            if not tc:
                return {'success': False, 'message': '未找到测试用例', 'data': None, 'code': 404}

            # INT-423：私有用例非 owner 更新参考参数返回 403
            from task_service.infrastructure.visibility_context import (
                check_object_visible, visibility_identity,
            )
            _uid, _is_admin = visibility_identity()
            try:
                check_object_visible(tc, _uid, _is_admin)
            except PermissionError as e:
                return {'success': False, 'message': str(e), 'data': None, 'code': 403}

            new_ref_params = data.get('referenceParams')
            if new_ref_params is None:
                return {'success': False, 'message': '缺少 referenceParams 字段', 'data': None, 'code': 400}

            new_ref_params = _algo_repo.algo_get_all_reference_params(new_ref_params)

            config = tc.config or {}
            rounds = config.get('rounds', [])

            target_round = None
            for r in rounds:
                if isinstance(r, dict) and r.get('roundNumber') == round_number:
                    target_round = r
                    break

            if not target_round:
                return {'success': False, 'message': f"未找到第 {round_number} 轮", 'data': None, 'code': 404}

            ref_path = target_round.get('referenceParamsPath')
            if not ref_path:
                return {'success': False, 'message': f"第 {round_number} 轮未配置参考参数路径", 'data': None, 'code': 404}

            if not os.path.exists(ref_path):
                return {'success': False, 'message': f"参考参数文件不存在: {ref_path}", 'data': None, 'code': 404}

            try:
                with open(ref_path, 'w', encoding='utf-8') as f:
                    json.dump(new_ref_params, f, ensure_ascii=False, indent=2)
            except Exception as e:
                return {'success': False, 'message': f"写入参考参数文件失败: {str(e)}", 'data': None, 'code': 500}

            return {
                'success': True,
                'message': '参考参数更新成功',
                'data': {
                    'roundNumber': round_number,
                    'referenceParamsPath': ref_path,
                    'referenceParams': new_ref_params
                }
            }
        except Exception as e:
            logger.error(f"更新参考参数失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    # ==================== 委托：批量操作 ====================

    def batch_action(self, data: dict) -> dict:
        """批量操作（委托 TestCaseBatchService）。"""
        return self._batch_service.batch_action(data)

    # ==================== 委托：读操作 ====================

    def list_testcases(self, page=1, per_page=10, keyword=None, tag=None,
                       group_id=None, algorithm_type=None, test_type=None,
                       view=None, include_deleted=False, dimension_id=None,
                       favorite=False, only_deleted=False, user_id=None,
                       lab_ids=None, visibility=None) -> dict:
        """查询测试用例列表（委托 TestCaseQueryService）。

        favorite/only_deleted/user_id（INT-141）：收藏/回收站过滤，
        user_id 为当前操作人（x-user-id metadata），必须透传给查询服务。
        test_type/dimension_id（INT-193）：执行口径与评估维度过滤。
        lab_ids（INT-539）：按实验室过滤（含通用用例；None/空 = 不过滤）。
        visibility（INT-466）：可见性筛选（shared/private；None=全部）。
        """
        return self._query_service.list_testcases(
            page=page, per_page=per_page, keyword=keyword, tag=tag,
            group_id=group_id,
            algorithm_type=algorithm_type, test_type=test_type, view=view,
            include_deleted=include_deleted, dimension_id=dimension_id,
            favorite=favorite, only_deleted=only_deleted, user_id=user_id,
            lab_ids=lab_ids,
            visibility=visibility,
        )

    def get_testcase_detail(self, tc_id: str) -> dict:
        """获取单个测试用例详情（委托 TestCaseQueryService）。"""
        return self._query_service.get_testcase_detail(tc_id)

    def get_testcase_stats(self) -> dict:
        """获取测试用例统计信息（委托 TestCaseQueryService）。"""
        return self._query_service.get_testcase_stats()

    def get_testcase_tags(self) -> dict:
        """获取所有标签名列表（委托 TestCaseQueryService）。"""
        return self._query_service.get_testcase_tags()

    def fetch_case_ids(self, data: dict) -> dict:
        """按筛选条件返回全量用例ID（不分页，委托 TestCaseQueryService）。"""
        return self._query_service.fetch_case_ids(data)

    def get_testcase_ref_params(self, tc_id: str, round_number: int) -> dict:
        """获取指定用例指定轮的参考参数文件内容（委托 TestCaseQueryService）。"""
        return self._query_service.get_testcase_ref_params(tc_id, round_number)

    # ==================== 内部辅助 ====================

    @staticmethod
    def _process_case_audios(data, common):
        """处理音频关联，返回标准音频列表或 error message string 或 None

        差异#2 收尾：E2E 一致性校验由配置形态承载 —— 任一音频指定了
        playback_device_id（物理执行形态）时，全部音频必须指定。
        """
        audios_data = data.get('audios')
        if not audios_data:
            return None
        normalized = [
            (item, common.normalize_optional_int(item.get('playback_device_id')))
            for item in audios_data
        ]
        has_playback = any(pdid for _, pdid in normalized)
        for i, (audio_item, pdid) in enumerate(normalized):
            aid = audio_item.get('audio_id')
            spl = audio_item.get('spl')
            porder = audio_item.get('play_order')
            if aid is None or spl is None or porder is None:
                return f"第 {i+1} 个音频配置缺少必要字段: audio_id, spl, play_order"
            if has_playback and not pdid:
                return f"第 {i+1} 个音频配置为 E2E（物理执行）形态用例，必须指定 playback_device_id"
        standard_audios = []
        for audio_item in audios_data:
            standard_audios.append({
                'audio_id': audio_item.get('audio_id'),
                'spl': audio_item.get('spl'),
                'playback_device_id': common.normalize_optional_int(audio_item.get('playback_device_id')),
                'play_order': audio_item.get('play_order')
            })
        return standard_audios

    @staticmethod
    def _process_case_devices(merged_config, from_rounds=False, common=None):
        """处理设备关联验证，返回 error message 或 None

        差异#2 收尾：由配置形态承载 —— rounds 中任一音频携带
        playback_device_id（物理执行形态）时，全部音频必须指定。
        """
        if not from_rounds:
            return None
        all_audios = [
            (rn, ai, audio_item)
            for rn, round_item in enumerate(merged_config.get('rounds', []), 1)
            if isinstance(round_item, dict)
            for ai, audio_item in enumerate(round_item.get('audios', []), 1)
            if isinstance(audio_item, dict)
        ]
        if any(audio_item.get('playback_device_id') for _, _, audio_item in all_audios):
            for rn, ai, audio_item in all_audios:
                if not audio_item.get('playback_device_id'):
                    return f"第{rn}轮第{ai}个音频配置为 E2E（物理执行）形态用例，必须指定 playback_device_id"
        return None


# 模块级单例
testcase_crud_service = TestCaseCrudService()
