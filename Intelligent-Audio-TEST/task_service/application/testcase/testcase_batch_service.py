# -*- coding: utf-8 -*-
"""TestCaseBatchService — 测试用例批量操作应用服务。

从 testcase_crud_service 拆分，承担所有批量动作（删除/移动/复制/参数更新/
播放设备/声压/维度/噪声/自动命名/标签增删改/参考参数刷新）。

约定：
- 所有方法返回 dict: {success, message, data, code?}
- 通过 self.repo 调用 Repository，不直连 DB
- 保留软删除模式（deleted=True + deleted_at）
"""
from __future__ import annotations

import json
import logging
import uuid
from typing import Tuple

from shared.utils.query_utils import now_cst
from task_service.domain.repositories.testcase_group_repository import TestCaseGroupRepositoryABC
from task_service.infrastructure.persistence.testcase_repository import testcase_repository

logger = logging.getLogger(__name__)

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

    from task_service.infrastructure.acl.algorithm_acl_repository import AlgorithmRepository
    _algo_repo = AlgorithmRepository()

    case_id = getattr(test_case, 'id', '') or str(id(test_case))

    # 构建传入 gRPC 的 test_case_config（algorithm_type / config / test_type）
    test_case_config = {
        'algorithm_type': getattr(test_case, 'algorithm_type', None),
        'config': config,
        'test_type': getattr(test_case, 'test_type', 'api') or 'api',
    }

    ref_params_list = []
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
        except Exception as e:
            logger.warning(f"round {round_number}: failed to upload {_REF_PARAMS_BUCKET}/{oss_key}: {e}")

    test_case.reference_params = ref_params_list


class TestCaseBatchService:
    """测试用例批量操作应用服务。"""

    def __init__(self, repo: TestCaseGroupRepositoryABC = None):
        self.repo = repo or testcase_repository

    def batch_action(self, data: dict) -> dict:
        """批量操作。

        Args:
            data: {action, ids, ...} — 已通过网关 Pydantic 校验

        Returns:
            {success, message, data, code?}
        """
        from shared.utils import testcase_helpers as common

        action = data.get('action')
        ids = data.get('ids', [])

        handlers = {
            'delete': self._batch_delete,
            'move_to_group': self._batch_move_to_group,
            'copy_to_group': self._batch_copy_to_group,
            'copy': self._batch_copy,
            'copy_by_group': self._batch_copy_by_group,
            'update_algorithm_params': self._batch_update_algorithm_params,
            'update_playback_devices': self._batch_update_playback_devices,
            'update_spl': self._batch_update_spl,
            'update_dimensions': self._batch_update_dimensions,
            'update_noise': self._batch_update_noise,
            'auto_generate_name': self._batch_auto_generate_name,
            'add_tags': self._batch_add_tags,
            'remove_tags': self._batch_remove_tags,
            'rename_tag': self._batch_rename_tag,
            'refresh_reference': self._batch_refresh_reference,
        }

        handler = handlers.get(action)
        if not handler:
            return {'success': False, 'message': f"不支持的操作类型: {action}", 'data': None, 'code': 400}

        try:
            result = handler(data, common=common)
            # handler 返回 dict 表示提前返回（如异步任务提交）
            if isinstance(result, dict):
                return {'success': True, 'message': result.get('message', ''), 'data': result, 'code': 0}
            # handler 返回 (message, is_error) tuple
            if isinstance(result, tuple) and len(result) == 2:
                message, is_error = result
                if is_error:
                    return {'success': False, 'message': message, 'data': None, 'code': 400}
                # 正常 message，继续 commit
                message = result[0]
            else:
                message = result

            self.repo.commit()

            try:
                from api_gateway.application.services.stats_cache import refresh_stats_cache
                refresh_stats_cache()
            except Exception:
                logger.warning("批量操作后刷新统计缓存失败", exc_info=True)

            return {'success': True, 'message': message, 'data': None}
        except Exception as e:
            logger.error(f"批量操作失败: {e}", exc_info=True)
            return {'success': False, 'message': str(e), 'data': None, 'code': 500}

    # ==================== 各批量动作 ====================

    def _batch_delete(self, data, common=None):
        ids = data.get('ids', [])
        self.repo.soft_delete_testcases_by_ids(ids)
        return f"已成功批量删除 {len(ids)} 个用例"

    def _batch_move_to_group(self, data, common=None):
        ids = data.get('ids', [])
        target_group_id = data.get('target_group_id')
        if not target_group_id:
            return ("移动操作需要 'target_group_id'", True)
        self.repo.update_testcase_group_id_by_ids(ids, target_group_id)
        return f"已成功将 {len(ids)} 个用例移动至目标分组"

    def _batch_copy_to_group(self, data, common=None):
        ids = data.get('ids', [])
        target_group_id = data.get('target_group_id')
        if not target_group_id:
            return ("复制到分组操作需要 'target_group_id'", True)

        target_group = self.repo.get_group_by_id(target_group_id)
        if not target_group:
            return (f"未找到目标分组: {target_group_id}", True)

        copied_count = 0
        for tc_id in ids:
            tc = self.repo.get_testcase(tc_id)
            if tc:
                new_id = str(uuid.uuid4())
                new_tc = self.repo.create_testcase({
                    'id': new_id,
                    'name': tc.name,
                    'description': tc.description,
                    'group_id': target_group_id,
                    'config': tc.config.copy() if tc.config else {},
                    'algorithm_type': tc.algorithm_type,
                    'test_type': tc.test_type or 'api',
                })
                # 复制标签关联
                for tag in tc.tags:
                    new_tc.tags.append(tag)
                try:
                    _apply_reference_params_to_config(new_tc)
                except Exception:
                    logger.warning("复制到目标分组时刷新参考文本失败 tc_id=%s", tc_id, exc_info=True)
                copied_count += 1
        return f"已成功复制 {copied_count} 个用例到分组 '{target_group.name}'"

    def _batch_copy(self, data, common=None):
        ids = data.get('ids', [])
        copied_count = 0
        for tc_id in ids:
            tc = self.repo.get_testcase(tc_id)
            if tc:
                new_id = str(uuid.uuid4())
                new_tc_data = {
                    'id': new_id,
                    'name': f"{tc.name}_copy",
                    'description': tc.description,
                    'group_id': tc.group_id,
                    'config': tc.config.copy() if tc.config else {},
                    'algorithm_type': tc.algorithm_type,
                    'test_type': tc.test_type or 'api',
                }
                new_tc = self.repo.create_testcase(new_tc_data)
                for tag in tc.tags:
                    new_tc.tags.append(tag)
                try:
                    _apply_reference_params_to_config(new_tc)
                except Exception:
                    logger.warning("批量复制时刷新参考文本失败 tc_id=%s", tc_id, exc_info=True)
                copied_count += 1
        return f"已成功批量复制 {copied_count} 个用例"

    def _batch_copy_by_group(self, data, common=None):
        group_name = data.get('group_name')
        if not group_name:
            return ("复制分组操作需要 'group_name'", True)

        source_group = self.repo.get_group_by_name(group_name)
        if not source_group:
            return (f"未找到分组: {group_name}", True)

        new_group_name = f"{group_name}_copy"
        existing_group = self.repo.get_group_by_name(new_group_name)
        if existing_group:
            new_group = existing_group
        else:
            new_group = self.repo.create_group(
                str(uuid.uuid4()), new_group_name, source_group.description
            )

        test_cases = self.repo.list_testcases_by_group(source_group.id)
        copied_count = 0
        for tc in test_cases:
            new_id = str(uuid.uuid4())
            new_tc = self.repo.create_testcase({
                'id': new_id,
                'name': tc.name,
                'description': tc.description,
                'group_id': new_group.id,
                'config': tc.config.copy() if tc.config else {},
                'algorithm_type': tc.algorithm_type,
                'test_type': tc.test_type or 'api',
            })
            for tag in tc.tags:
                new_tc.tags.append(tag)
            try:
                _apply_reference_params_to_config(new_tc)
            except Exception:
                logger.warning("按分组复制时刷新参考文本失败 tc_id=%s", tc_id, exc_info=True)
            copied_count += 1
        return f"已成功复制分组 '{new_group_name}' 的 {copied_count} 个用例"

    def _batch_update_algorithm_params(self, data, common=None):
        ids = data.get('ids', [])
        algorithm_params = data.get('algorithm_params')
        if algorithm_params is None:
            return ("更新用例专属参数需要 'algorithm_params'", True)

        test_cases = self.repo.list_testcases_by_ids(ids)
        updated_count = 0
        for tc in test_cases:
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
            tc.algorithm_params = [{'round_number': 1, 'params': [{'field_code': k, 'field_value': v} for k, v in ap_dict.items()]}]
            tc.updated_at = now_cst()
            updated_count += 1
        self.repo.flush()
        return f"已成功更新 {updated_count} 个用例的专属参数"

    def _batch_update_playback_devices(self, data, common=None):
        import sqlalchemy.orm.attributes

        ids = data.get('ids', [])
        playback_devices = data.get('playback_devices')
        if playback_devices is None:
            return ("更新播放设备需要 'playback_devices'", True)

        test_cases = self.repo.list_testcases_by_ids(ids)
        updated_count = 0
        for tc in test_cases:
            if (tc.test_type or 'api') != 'e2e':
                continue
            if tc.config:
                config = tc.config.copy()
                device_id = playback_devices.get('deviceId') or playback_devices.get('device_id')
                for round_item in config.get('rounds', []):
                    if isinstance(round_item, dict):
                        for audio_config in round_item.get('audios', []):
                            if device_id is not None:
                                audio_config['playback_device_id'] = device_id
                tc.config = config
                sqlalchemy.orm.attributes.flag_modified(tc, 'config')
            tc.updated_at = now_cst()
            updated_count += 1
        self.repo.flush()
        return f"已成功更新 {updated_count} 个用例的播放设备"

    def _batch_update_spl(self, data, common=None):
        import sqlalchemy.orm.attributes

        ids = data.get('ids', [])
        spl_data = data.get('spl')
        if spl_data is None:
            return ("更新声压需要 'spl'", True)

        test_cases = self.repo.list_testcases_by_ids(ids)
        updated_count = 0
        for tc in test_cases:
            if (tc.test_type or 'api') != 'e2e':
                continue
            if tc.config:
                config = tc.config.copy()
                for round_item in config.get('rounds', []):
                    if isinstance(round_item, dict):
                        for audio_config in round_item.get('audios', []):
                            if spl_data.get('value') is not None:
                                audio_config['spl'] = spl_data['value']
                tc.config = config
                sqlalchemy.orm.attributes.flag_modified(tc, 'config')
            tc.updated_at = now_cst()
            updated_count += 1
        self.repo.flush()
        return f"已成功更新 {updated_count} 个用例的声压"

    def _batch_update_dimensions(self, data, common=None):
        import sqlalchemy.orm.attributes

        ids = data.get('ids', [])
        dimensions_data = data.get('dimensions')
        if dimensions_data is None:
            return ("更新评价维度需要 'dimensions'", True)

        test_cases = self.repo.list_testcases_by_ids(ids)
        updated_count = 0
        for tc in test_cases:
            if tc.config:
                config = tc.config.copy()
                new_dim_list = []
                for dim in dimensions_data:
                    new_dim_list.append({
                        'id': dim.get('id'),
                        'name': dim.get('name', ''),
                        'weight': dim.get('weight', 50),
                        'threshold': dim.get('threshold', 60)
                    })
                for round_item in config.get('rounds', []):
                    if isinstance(round_item, dict):
                        if 'evaluation' not in round_item:
                            round_item['evaluation'] = {}
                        round_item['evaluation']['dimensions'] = new_dim_list
                tc.config = config
                sqlalchemy.orm.attributes.flag_modified(tc, 'config')
            tc.updated_at = now_cst()
            updated_count += 1
        self.repo.flush()
        return f"已成功更新 {updated_count} 个用例的评价维度"

    def _batch_update_noise(self, data, common=None):
        import sqlalchemy.orm.attributes

        ids = data.get('ids', [])
        audio_id = data.get('noise_audio_id')
        spl = data.get('noise_spl')
        device_ids = data.get('noise_device_ids') or []

        test_cases = self.repo.list_testcases_by_ids(ids)
        updated_count = 0
        for tc in test_cases:
            if (tc.test_type or 'api') != 'e2e':
                continue
            config = (tc.config or {}).copy()
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
            tc.updated_at = now_cst()
            updated_count += 1
        self.repo.flush()
        return f"已成功更新 {updated_count} 个用例的噪声配置"

    def _batch_auto_generate_name(self, data, common=None):
        ids = data.get('ids', [])
        self.repo.auto_generate_names_by_tag_order(ids)
        return f"已成功为 {len(ids)} 个用例自动生成名称"

    def _batch_add_tags(self, data, common=None):
        ids = data.get('ids', [])
        tags_to_add = data.get('tags') or []
        if not tags_to_add:
            return ("添加标签需要 'tags' 参数", True)
        self.repo.add_tags_to_testcases(ids, tags_to_add)
        return f"已成功为 {len(ids)} 个用例添加标签"

    def _batch_remove_tags(self, data, common=None):
        ids = data.get('ids', [])
        tags_to_remove = data.get('tags') or []
        if not tags_to_remove:
            return ("移除标签需要 'tags' 参数", True)
        self.repo.remove_tags_from_testcases(ids, tags_to_remove)
        return f"已成功为 {len(ids)} 个用例移除标签"

    def _batch_rename_tag(self, data, common=None):
        old_tag_name = data.get('old_tag_name')
        new_tag_name = data.get('new_tag_name')
        if not old_tag_name or not new_tag_name:
            return ("重命名标签需要 'old_tag_name' 和 'new_tag_name' 参数", True)
        if old_tag_name == new_tag_name:
            return ("新标签名不能与原标签名相同", True)

        result = self.repo.rename_tag(old_tag_name, new_tag_name)
        if result is None:
            return (f"未找到标签: {old_tag_name}", True)
        old_tag, new_tag_exists = result
        if new_tag_exists:
            return (f"标签名 {new_tag_name} 已存在", True)
        self.repo.update_tag_name(old_tag, new_tag_name)
        return f"已成功将标签 {old_tag_name} 重命名为 {new_tag_name}"

    def _batch_refresh_reference(self, data, common=None):
        ids = data.get('ids', [])
        test_cases = self.repo.list_testcases_by_ids(ids)

        if len(ids) > 50:
            from task_service.application.testcase.reference_refresh_task import submit_reference_refresh_task
            task_id = submit_reference_refresh_task(
                ids,
                refresher=lambda tc: _apply_reference_params_to_config(tc),
            )
            return {
                'task_id': task_id,
                'message': f'已提交异步刷新任务，预计处理 {len(test_cases)} 个用例'
            }
        else:
            updated_count = 0
            for tc in test_cases:
                try:
                    _apply_reference_params_to_config(tc)
                    tc.updated_at = now_cst()
                    updated_count += 1
                except Exception as e:
                    logger.error(f"[refresh_reference] 处理用例 {tc.id} 失败: {e}")
            self.repo.commit()
            return f"已成功刷新 {updated_count} 个用例的参考参数"
