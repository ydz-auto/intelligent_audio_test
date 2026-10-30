# -*- coding: utf-8 -*-
"""音频测试用例创建应用服务（跨域协调）

从 audio_crud_service.py 中提取的测试用例创建相关逻辑。

职责拆分（Mixin 组合模式）：
- _creation_round_config_mixin.CreationRoundConfigMixin：轮次配置解析与 config 构建
- _creation_annotation_mixin.CreationAnnotationMixin：标注数据注入与用例参数提取
- _creation_id_resolution_mixin.CreationIdResolutionMixin：文件名/设备名 → ID 解析
- _creation_refresh_mixin.CreationRefreshMixin：音频变更后关联用例刷新

本文件仅保留创建编排（create_test_case_from_audio）与组合类定义。
"""
import json as _json
import logging

from shared.models.common_enums import DeviceType
from shared.utils.query_utils import now_cst
from shared.utils.log_handler import log_not_emit
from audio_service.domain.repositories.audio_repository_abc import AudioRepositoryInterface
from audio_service.infrastructure.persistence.audio_repository import audio_repository
from audio_service.application.services.audio_annotation_service import audio_annotation_service

from audio_service.application.services._creation_round_config_mixin import CreationRoundConfigMixin
from audio_service.application.services._creation_annotation_mixin import CreationAnnotationMixin
from audio_service.application.services._creation_id_resolution_mixin import CreationIdResolutionMixin
from audio_service.application.services._creation_refresh_mixin import CreationRefreshMixin

logger = logging.getLogger(__name__)


class AudioTestCaseCreationService(CreationRoundConfigMixin,
                                   CreationAnnotationMixin,
                                   CreationIdResolutionMixin,
                                   CreationRefreshMixin):
    """音频测试用例创建应用服务（跨域协调）"""

    def __init__(self, repo: AudioRepositoryInterface = None):
        self.repo = repo or audio_repository
        self._annotation_service = audio_annotation_service
        # ACL 仓储（跨域只读/读写查询）
        from audio_service.infrastructure.acl.algorithm_acl_repository import (
            AlgorithmACLRepositoryImpl,
        )
        from audio_service.infrastructure.acl.playback_acl_repository import (
            PlaybackConfigACLRepositoryImpl,
        )
        from audio_service.infrastructure.acl.testcase_acl_repository import (
            TestCaseConfigACLRepositoryImpl,
        )
        self._algorithm_acl = AlgorithmACLRepositoryImpl()
        self._playback_acl = PlaybackConfigACLRepositoryImpl()
        self._testcase_acl = TestCaseConfigACLRepositoryImpl()

    def create_test_case_from_audio(self, audio_id, device_type, audio_tags,
                                    playback_device_id=None, spl=65.0, noise_spl=60.0,
                                    noise_audio_id=None, group_name=None,
                                    dimensions_data=None, algorithm_type=None,
                                    algorithm_params=None, rounds_config=None,
                                    inherit_tags=True, raw_annotations=None,
                                    noise_device_ids=None, case_background_noise=None,
                                    upload_task_id=None, playback_speaker_group_id=None):
        """从音频创建测试用例

        通过 ACL 仓储调用 gRPC TestCaseConfigService 创建测试用例（含分组/标签/参考参数），
        避免直接 import task_service PO。

        :param device_type: 用例目标设备类型（DeviceType 值）。用例本身不承载执行口径，
            仅用于按维度/参数的作用域（common 或该 device_type）做导入期筛选与物理设备回填；
            缺省按 HTTP_API。
        :param upload_task_id: 本次上传任务 ID（合并/秒传流程传入）。用于把轮次音频名
            优先解析到本任务内的音频记录，避免同名素材绑到库中陈旧同名记录。
        """
        device_type = str(device_type).strip() if device_type else DeviceType.HTTP_API.value

        audio = self.repo.get_audio(audio_id)
        if not audio:
            return None

        effective_group_name = group_name if group_name else '音频上传生成'

        effective_playback_device_id = playback_device_id
        if (device_type == DeviceType.PHYSICAL.value and not effective_playback_device_id
                and not playback_speaker_group_id):
            # 通过 ACL 仓储查找第一个 device_type='dry' 的播放设备
            devices = self._playback_acl.list_playback_devices()
            for dev in devices:
                if dev.get('device_type') == 'dry' and not dev.get('is_deleted'):
                    effective_playback_device_id = dev.get('id')
                    break

            if not effective_playback_device_id:
                raise ValueError(
                    "物理设备（physical）用例需要一个 device_type='dry' 的播放设备，"
                    "但未找到可用设备。请先在设备管理中配置播放设备。"
                )

        # 秒传场景下 audio.name 可能是旧的改名（如 "1.wav"），
        # 优先用 rounds_config 里前端传的 audio_name 作为用例名
        tc_audio_name = audio.name
        if rounds_config:
            for r in rounds_config:
                if not isinstance(r, dict):
                    continue
                for a in r.get('audios', []):
                    if isinstance(a, dict) and a.get('audio_name'):
                        tc_audio_name = a['audio_name']
                        break
                if tc_audio_name != audio.name:
                    break
        test_case_name = f"测试用例_{tc_audio_name}"

        # 名称冲突检查：通过 ACL 仓储 ListTestCases 搜索同名用例
        list_data = self._testcase_acl.list_testcases(
            page=1, per_page=50, keyword=test_case_name,
        )
        if list_data:
            for item in list_data.get('items', []):
                if item.get('name') == test_case_name:
                    test_case_name = f"{test_case_name}_{now_cst().strftime('%H%M%S')}"
                    break

        rounds_resolved, algo_params_col = self._resolve_rounds_and_strip_params(
            device_type, audio_id, audio, spl, effective_playback_device_id,
            rounds_config, algorithm_params,
            upload_task_id=upload_task_id,
        )

        self._inject_spl_and_device_from_annotations(
            rounds_resolved, raw_annotations, device_type, effective_playback_device_id, spl
        )

        self._extract_case_params_from_annotations(
            rounds_resolved, raw_annotations, algorithm_type, device_type, algo_params_col
        )

        # 解析 segment 级背景噪声和干扰人：文件名→audio_id，设备名→device_ids/playback_device_id
        self._resolve_bg_noise_and_interferers_ids(rounds_resolved)

        # 用例只关联逻辑音箱：上传选项选了逻辑音箱时，把各播放目标统一改写为组引用
        if playback_speaker_group_id:
            self._apply_speaker_group_to_rounds(rounds_resolved, playback_speaker_group_id)

        # case 级背景噪声（rounds 外层）ID 解析
        if case_background_noise and isinstance(case_background_noise, dict):
            self._resolve_audio_field(case_background_noise)
            self._resolve_device_fields(case_background_noise)

        config = self._build_config_and_apply_dimensions(
            audio, rounds_resolved, dimensions_data, device_type, noise_spl, noise_audio_id,
            noise_device_ids, case_background_noise
        )

        # 通过 ACL 仓储创建测试用例
        # （task_service 侧自动处理分组创建/标签关联/参考参数生成）
        create_data = {
            'name': test_case_name,
            'description': f"自动从音频 '{audio.name}' 创建的测试用例",
            'group': effective_group_name,
            'algorithm_type': algorithm_type,
            'config': config,
            'algorithm_params': algo_params_col if algo_params_col else None,
        }
        if inherit_tags and audio_tags:
            create_data['tags'] = list(audio_tags)

        log_not_emit('DEBUG', 'audio_controller',
                     f'tc.algorithm_params={_json.dumps(algo_params_col, ensure_ascii=False)[:300]}',
                     category='audio')

        resp_data = self._testcase_acl.create_testcase_config(create_data)
        tc_id = resp_data.get('id') if resp_data else None
        return [tc_id] if tc_id else []


    @staticmethod
    def _apply_speaker_group_to_rounds(rounds, group_id):
        """把轮次内所有实体设备引用改写为逻辑音箱组引用（用例只关联逻辑音箱）。

        - audios[].playback_device_id → playback_speaker_group_id
        - segment/轮次背景噪声 device_ids / playback_device_ids → playback_speaker_group_ids
        - 干扰人 / 声纹 playback_device_id → playback_speaker_group_id
        """
        for round_item in rounds or []:
            if not isinstance(round_item, dict):
                continue
            for audio_config in round_item.get('audios', []) or []:
                if not isinstance(audio_config, dict):
                    continue
                # 逐轮选择可能不同逻辑音箱：轮内值优先，否则用顶层默认组
                round_group_id = audio_config.get('playback_device_id') or group_id
                audio_config['playback_speaker_group_id'] = round_group_id
                audio_config.pop('playback_device_id', None)
                audio_config.pop('playback_device_name', None)
                bn = audio_config.get('background_noise') or audio_config.get('backgroundNoise')
                if isinstance(bn, dict):
                    bn_group_ids = bn.get('device_ids') or [round_group_id]
                    bn['playback_speaker_group_ids'] = list(bn_group_ids)
                    bn.pop('device_ids', None)
                    bn.pop('playback_device_ids', None)
                for inf in audio_config.get('interferers', []) or []:
                    if isinstance(inf, dict):
                        inf['playback_speaker_group_id'] = (
                            inf.get('playback_device_id') or round_group_id)
                        inf.pop('playback_device_id', None)
                vp = audio_config.get('voiceprint')
                if isinstance(vp, dict):
                    vp['playback_speaker_group_id'] = (
                        vp.get('playback_device_id') or round_group_id)
                    vp.pop('playback_device_id', None)
            rbn = round_item.get('background_noise') or round_item.get('backgroundNoise')
            if isinstance(rbn, dict):
                rbn['playback_speaker_group_ids'] = (
                    rbn.get('device_ids') or [group_id])
                rbn.pop('device_ids', None)
                rbn.pop('playback_device_ids', None)


# 模块级实例
audio_testcase_creation_service = AudioTestCaseCreationService()
