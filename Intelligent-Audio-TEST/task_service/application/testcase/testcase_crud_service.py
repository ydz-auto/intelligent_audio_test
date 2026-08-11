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

    from shared.clients.grpc_clients import (
        algo_generate_reference_params,
        algo_get_all_reference_params,
    )

    case_id = getattr(test_case, 'id', '') or str(id(test_case))

    # 构建传入 gRPC 的 test_case_config（algorithm_type / config / test_type）
    test_case_config = {
        'algorithm_type': getattr(test_case, 'algorithm_type', None),
        'config': config,
        'test_type': getattr(test_case, 'test_type', 'api') or 'api',
    }

    ref_params_list = []
    total_params = 0
    for round_item in rounds:
        if not isinstance(round_item, dict):
            continue

        round_number = round_item.get('round_number') or round_item.get('roundNumber') or 1

        round_params = algo_generate_reference_params(test_case_config, round_item)
        if not round_params:
            continue

        round_params = algo_get_all_reference_params(round_params)

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
                test_type, tags, audios, dimensions, background_noise_*,
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

            if group_id is None:
                return {'success': False, 'message': '缺少必要字段: group_id 或 group', 'data': None, 'code': 400}

            test_type_val = data.get('test_type', 'api')
            if test_type_val not in ['api', 'e2e']:
                return {'success': False, 'message': f"test_type 无效: {test_type_val}，必须为 api 或 e2e", 'data': None, 'code': 400}

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
                device_error = self._process_case_devices(merged_config, test_type_val, from_rounds=True, common=common)
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

                audios_result = self._process_case_audios(data, test_type_val, common)
                if audios_result is not None and isinstance(audios_result, str):
                    return {'success': False, 'message': audios_result, 'data': None, 'code': 400}
                if audios_result is not None:
                    merged_config['audios'] = audios_result

                dimensions_data = data.get('dimensions')
                if dimensions_data:
                    merged_config['dimensions'] = dimensions_data

                merged_config = common.convert_flat_config_to_rounds(merged_config)

            audio_dim_error = common.validate_multi_round_audio_dimensions(merged_config)
            if audio_dim_error:
                return {'success': False, 'message': audio_dim_error, 'data': None, 'code': 400}

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
                    'test_type': test_type_val,
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

                try:
                    from api_gateway.application.services.stats_cache import refresh_stats_cache
                    refresh_stats_cache()
                except Exception:
                    pass

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

            current_config = tc.config or {}
            tc_test_type = tc.test_type or 'api'

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

            # 更新音频关联
            audios_data = data.get('audios')
            if audios_data is not None:
                for i, audio_item in enumerate(audios_data):
                    aid = audio_item.get('audio_id')
                    spl = audio_item.get('spl')
                    porder = audio_item.get('play_order')
                    pdid = common.normalize_optional_int(audio_item.get('playback_device_id'))
                    if aid is None or spl is None or porder is None:
                        return {'success': False, 'message': f"第 {i+1} 个音频配置缺少必要字段: audio_id, spl, play_order", 'data': None, 'code': 400}
                    if tc_test_type == 'e2e' and not pdid:
                        return {'success': False, 'message': f"第 {i+1} 个音频配置为 E2E 类型用例，必须指定 playback_device_id", 'data': None, 'code': 400}
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
            if dimensions_data is not None:
                first_round = merged_config.get('rounds', [{}])[0]
                if isinstance(first_round, dict):
                    if 'evaluation' not in first_round:
                        first_round['evaluation'] = {}
                    first_round['evaluation']['dimensions'] = dimensions_data

            # 更新标签
            tags_data = data.get('tags')
            if tags_data is not None:
                self.repo.set_testcase_tags(tc, tags_data)

            audio_dim_error = common.validate_multi_round_audio_dimensions(merged_config)
            if audio_dim_error:
                return {'success': False, 'message': audio_dim_error, 'data': None, 'code': 400}

            tc.config = merged_config

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

            if need_refresh_reference:
                try:
                    _apply_reference_params_to_config(tc)
                except Exception as e:
                    logger.warning(f"刷新参考文本失败: {e}")

            try:
                self.repo.commit()

                try:
                    from api_gateway.application.services.stats_cache import refresh_stats_cache
                    refresh_stats_cache()
                except Exception:
                    pass

                return {'success': True, 'message': '测试用例更新成功', 'data': None}
            except Exception:
                self.repo.rollback()
                raise
        except Exception as e:
            logger.error(f"更新测试用例失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def delete(self, tc_id: str) -> dict:
        """软删除测试用例。"""
        try:
            if not self.repo.soft_delete_testcase(tc_id):
                return {'success': False, 'message': '未找到测试用例', 'data': None, 'code': 404}

            try:
                self.repo.commit()

                try:
                    from api_gateway.application.services.stats_cache import refresh_stats_cache
                    refresh_stats_cache()
                except Exception:
                    pass

                return {'success': True, 'message': '测试用例已删除', 'data': None}
            except Exception:
                self.repo.rollback()
                raise
        except Exception as e:
            logger.error(f"删除测试用例失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def copy(self, tc_id: str) -> dict:
        """复制测试用例。"""
        try:
            tc = self.repo.get_testcase(tc_id)
            if not tc:
                return {'success': False, 'message': '未找到原始测试用例', 'data': None, 'code': 404}

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
                    'test_type': tc.test_type or 'api',
                })

                for tag in tc.tags:
                    new_tc.tags.append(tag)

                try:
                    _apply_reference_params_to_config(new_tc)
                except Exception as e:
                    logger.warning(f"刷新参考文本失败: {e}")

                self.repo.commit()
                return {'success': True, 'message': '测试用例复制成功', 'data': {'id': new_id}, 'code': 201}
            except Exception:
                self.repo.rollback()
                raise
        except Exception as e:
            logger.error(f"复制测试用例失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    def update_ref_params(self, tc_id: str, round_number: int, data: dict) -> dict:
        """更新指定用例指定轮的参考参数文件。"""
        from shared.clients.grpc_clients import algo_get_all_reference_params

        try:
            tc = self.repo.get_testcase(tc_id)
            if not tc:
                return {'success': False, 'message': '未找到测试用例', 'data': None, 'code': 404}

            new_ref_params = data.get('referenceParams')
            if new_ref_params is None:
                return {'success': False, 'message': '缺少 referenceParams 字段', 'data': None, 'code': 400}

            new_ref_params = algo_get_all_reference_params(new_ref_params)

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
                       group_id=None, test_type=None, algorithm_type=None,
                       view=None, include_deleted=False) -> dict:
        """查询测试用例列表（委托 TestCaseQueryService）。"""
        return self._query_service.list_testcases(
            page=page, per_page=per_page, keyword=keyword, tag=tag,
            group_id=group_id, test_type=test_type,
            algorithm_type=algorithm_type, view=view,
            include_deleted=include_deleted,
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

    def get_testcase_ref_params(self, tc_id: str, round_number: int) -> dict:
        """获取指定用例指定轮的参考参数文件内容（委托 TestCaseQueryService）。"""
        return self._query_service.get_testcase_ref_params(tc_id, round_number)

    # ==================== 内部辅助 ====================

    @staticmethod
    def _process_case_audios(data, test_type_val, common):
        """处理音频关联，返回标准音频列表或 error message string 或 None"""
        audios_data = data.get('audios')
        if not audios_data:
            return None
        for i, audio_item in enumerate(audios_data):
            aid = audio_item.get('audio_id')
            spl = audio_item.get('spl')
            porder = audio_item.get('play_order')
            pdid = common.normalize_optional_int(audio_item.get('playback_device_id'))
            if aid is None or spl is None or porder is None:
                return f"第 {i+1} 个音频配置缺少必要字段: audio_id, spl, play_order"
            if test_type_val == 'e2e' and not pdid:
                return f"第 {i+1} 个音频配置为 E2E 类型用例，必须指定 playback_device_id"
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
    def _process_case_devices(merged_config, test_type_val, from_rounds=False, common=None):
        """处理设备关联验证，返回 error message 或 None"""
        if test_type_val != 'e2e':
            return None
        if from_rounds:
            for rn, round_item in enumerate(merged_config.get('rounds', []), 1):
                for ai, audio_item in enumerate(round_item.get('audios', []), 1):
                    if not audio_item.get('playback_device_id'):
                        return f"第{rn}轮第{ai}个音频配置为 E2E 类型用例，必须指定 playback_device_id"
        return None


# 模块级单例
testcase_crud_service = TestCaseCrudService()
