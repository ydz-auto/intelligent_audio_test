# -*- coding: utf-8 -*-
"""音频轮次配置与上传参数服务

从 audio_upload_service.py 中提取的合并参数/轮次配置相关逻辑：
- 从 data 中提取合并参数（_extract_merge_params）
- 算法参数归一化（list/dict 互转、ACL 规范化）
- 秒传场景下的轮次配置匹配（按 name/original_filename/md5 匹配已存在音频）
"""
import logging

logger = logging.getLogger(__name__)


class AudioRoundConfigService:
    """音频轮次配置与上传参数服务"""

    def extract_merge_params(self, data):
        """从 data 中提取合并参数

        :param data: 上传请求 data
        :return: dict，包含 create_test_case/test_types/dimensions_data 等键
        """
        tc_config = data.get('test_case_config') or data.get('testCaseConfig')
        rounds_config, tc_group_name, tc_inherit_tags, tc_case_background_noise = (
            self._extract_tc_config(tc_config)
        )
        test_case_group_name = self._resolve_group_name(data, tc_group_name)
        algorithm_params, algorithm_params_dict = self._resolve_algorithm_params(data, tc_config)
        dimensions_data = self._resolve_dimensions(data, tc_config)

        return {
            'create_test_case': data.get('create_test_case', data.get('createTestCase', False)),
            'test_types': data.get('test_types', data.get('testTypes', ['api'])),
            'dimensions_data': dimensions_data,
            'default_playback_device_id': data.get('default_playback_device_id') or data.get('defaultPlaybackDeviceId'),
            'default_spl': data.get('default_spl', data.get('defaultSpl', 65.0)),
            'noise_spl': data.get('noise_spl', data.get('noiseSpl', 60.0)),
            'noise_audio_id': data.get('noise_audio_id') or data.get('noiseAudioId'),
            'noise_device_ids': data.get('noise_device_ids') or data.get('noiseDeviceIds') or [],
            'test_case_group_name': test_case_group_name,
            'algorithm_type': data.get('algorithm_type') or data.get('algorithmType'),
            'algorithm_params': algorithm_params,
            'algorithm_params_dict': algorithm_params_dict,
            'description': data.get('description', ''),
            'user_tags': data.get('tags', []),
            'rounds_config': rounds_config,
            'tc_inherit_tags': tc_inherit_tags,
            'case_background_noise': tc_case_background_noise,
        }

    def _extract_tc_config(self, tc_config):
        """从 test_case_config 提取轮次配置/分组名/继承标签/case级背景噪声"""
        rounds_config = None
        if tc_config and isinstance(tc_config, dict):
            rounds_config = tc_config.get('rounds')
        tc_group_name = tc_config.get('group_name') if tc_config else None
        tc_inherit_tags = tc_config.get('inherit_tags', True) if tc_config else True
        # case 级背景噪声（rounds 外层），优先级高于轮次级
        tc_case_background_noise = tc_config.get('background_noise') if tc_config else None
        return rounds_config, tc_group_name, tc_inherit_tags, tc_case_background_noise

    def _resolve_group_name(self, data, tc_group_name):
        """解析测试用例分组名：tc_config 优先，其次 data"""
        test_case_group_name = data.get('test_case_group_name') or data.get('testCaseGroupName')
        if tc_group_name:
            test_case_group_name = tc_group_name
        return test_case_group_name

    def _resolve_algorithm_params(self, data, tc_config):
        """解析算法参数：返回 (原始值, 归一化list)"""
        algorithm_params = data.get('algorithm_params') or data.get('algorithmParams')
        algorithm_params_dict = self._normalize_algorithm_params(algorithm_params)
        if tc_config and tc_config.get('algorithm_params') and not algorithm_params_dict:
            # 通过 ACL 仓储规范化算法参数
            from audio_service.infrastructure.acl.algorithm_acl_repository import (
                AlgorithmACLRepositoryImpl,
            )
            algorithm_params_dict = AlgorithmACLRepositoryImpl().normalize_algorithm_params_to_list(
                tc_config.get('algorithm_params')
            )
        return algorithm_params, algorithm_params_dict

    def _resolve_dimensions(self, data, tc_config):
        """解析维度数据：data 优先，其次 tc_config"""
        dimensions_data = data.get('dimensions')
        if tc_config and tc_config.get('dimensions') and not dimensions_data:
            dimensions_data = tc_config.get('dimensions')
        return dimensions_data

    def _normalize_algorithm_params(self, algorithm_params):
        """将算法参数归一化为 list 形式

        :param algorithm_params: list 或 dict
        :return: list 形式参数，或 None
        """
        if isinstance(algorithm_params, list):
            return algorithm_params
        if isinstance(algorithm_params, dict):
            return [{'field_code': k, 'field_value': v} for k, v in algorithm_params.items()]
        return None

    def match_existing_audio_in_rounds(self, rounds_config, existing_audio):
        """秒传场景：将已存在的音频匹配到 rounds_config 中的音频项

        :param rounds_config: 轮次配置列表
        :param existing_audio: 已存在的 Audio 记录
        :return: int，匹配数量
        """
        if not rounds_config:
            return 0
        unmatched_items = self._collect_unmatched_audio_items(rounds_config)
        matched_count = self._match_by_name(unmatched_items, existing_audio)
        # 兜底：若按名称都匹配不上，且仅剩1个未匹配项，直接赋值（秒传的音频就是它）
        if matched_count == 0 and len(unmatched_items) == 1:
            unmatched_items[0]['audio_id'] = existing_audio.id
        return matched_count

    def _collect_unmatched_audio_items(self, rounds_config):
        """收集 rounds_config 中所有未匹配的音频项"""
        unmatched_items = []
        for r in rounds_config:
            if not isinstance(r, dict):
                continue
            for a in r.get('audios', []):
                if not isinstance(a, dict) or a.get('audio_id'):
                    continue
                unmatched_items.append(a)
        return unmatched_items

    def _match_by_name(self, unmatched_items, existing_audio):
        """按 name/original_filename/md5 匹配未匹配项"""
        matched_count = 0
        for a in unmatched_items:
            item_name = a.get('audio_name') or ''
            if (item_name == existing_audio.name
                    or item_name == (existing_audio.original_filename or '')
                    or item_name == (existing_audio.md5 or '')
                    or not item_name):
                a['audio_id'] = existing_audio.id
                matched_count += 1
        return matched_count


# 模块级实例
audio_round_config_service = AudioRoundConfigService()
