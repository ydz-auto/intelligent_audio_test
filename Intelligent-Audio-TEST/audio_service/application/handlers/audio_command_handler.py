# -*- coding: utf-8 -*-
"""音频命令处理器（CQRS 写侧）。

接收 Command 对象，编排领域服务/仓储/跨域 ACL 完成写操作。
依赖 domain/repositories ABC 接口，不直接 import ORM。
复杂子服务（annotation/testcase_creation）通过 application/services 委托。
"""
from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, List, Optional, Tuple

from shared.utils.log_handler import log_and_emit
from shared.infrastructure.storage import storage

from audio_service.domain.repositories import AudioRepositoryInterface
from audio_service.application.commands.audio_commands import (
    UpdateAudioMetadataCommand,
    BatchUpdateAnnotationsCommand,
    BatchActionAudiosCommand,
    DeleteAudioCommand,
    UpdateAudioAlgorithmsCommand,
    BatchUpdateAudioAlgorithmsCommand,
    ConvertAudioCommand,
    PreviewAudioCommand,
    StopPreviewAudioCommand,
    PersistAnnotationsCommand,
    CreateTestCaseFromAudioCommand,
)

logger = logging.getLogger(__name__)


def _ok(data: Any = None, message: str = 'Success', code: int = 200) -> Dict[str, Any]:
    return {'success': True, 'message': message, 'data': data, 'code': code}


def _fail(message: str, code: int = 400, data: Any = None) -> Dict[str, Any]:
    return {'success': False, 'message': message, 'data': data, 'code': code}


class AudioCommandHandler:
    """音频写命令处理器。

    依赖注入 AudioRepositoryInterface（ABC），不直接 import 具体仓储类。
    """

    def __init__(self, repository: AudioRepositoryInterface = None) -> None:
        if repository is None:
            from audio_service.infrastructure.persistence.audio_repository import audio_repository
            repository = audio_repository
        self.repo = repository
        self._annotation_service = None
        self._testcase_creation_service = None
        # ACL 仓储（跨域只读查询）
        from audio_service.infrastructure.acl.task_acl_repository import (
            TaskACLRepositoryImpl,
        )
        from audio_service.infrastructure.acl.device_acl_repository import (
            DeviceACLRepositoryImpl,
        )
        self._task_acl = TaskACLRepositoryImpl()
        self._device_acl = DeviceACLRepositoryImpl()

    @property
    def annotation_service(self):
        if self._annotation_service is None:
            from audio_service.application.services.audio_annotation_service import audio_annotation_service
            self._annotation_service = audio_annotation_service
        return self._annotation_service

    @property
    def testcase_creation_service(self):
        if self._testcase_creation_service is None:
            from audio_service.application.services.audio_testcase_creation_service import audio_testcase_creation_service
            self._testcase_creation_service = audio_testcase_creation_service
        return self._testcase_creation_service

    # ========== 音频元数据写操作 ==========

    def handle_update_metadata(self, cmd: UpdateAudioMetadataCommand) -> Dict[str, Any]:
        audio = self.repo.get_audio(cmd.audio_id)
        if not audio:
            return _fail('未找到音频文件', 404)

        try:
            data = cmd.data
            name = data.get('name')
            audio_type = data.get('audio_type') or data.get('audioType')
            asr_text = data.get('asr_text') or data.get('asrText')
            description = data.get('description')
            source_language = data.get('source_language') or data.get('sourceLanguage')
            tags_str = data.get('tags')
            annotations = data.get('annotations', [])

            update_fields = {}
            if name is not None:
                update_fields['name'] = name
            if audio_type is not None:
                update_fields['audio_type'] = audio_type
            if asr_text is not None:
                update_fields['asr_text'] = asr_text
            if description is not None:
                update_fields['description'] = description
            if source_language is not None:
                update_fields['source_language'] = source_language

            if update_fields:
                self.repo.update_audio(cmd.audio_id, update_fields)

            if tags_str is not None:
                self.repo.delete_audio_tags(cmd.audio_id)
                if tags_str:
                    for tag_name in tags_str.split(','):
                        tag_name = tag_name.strip()
                        if tag_name:
                            tag = self.repo.get_or_create_tag(tag_name)
                            self.repo.add_audio_tag(cmd.audio_id, tag.id)

            if annotations is not None:
                self.repo.delete_audio_annotations(cmd.audio_id)
                for ann in annotations:
                    self.repo.create_audio_annotation(cmd.audio_id, ann)

            self.repo.commit()
            return _ok(message='元数据更新成功')
        except Exception as e:
            self.repo.rollback()
            return _fail(str(e))

    def handle_batch_update_annotations(self, cmd: BatchUpdateAnnotationsCommand) -> Dict[str, Any]:
        if not cmd.data:
            return _fail('请求体不能为空')

        items = cmd.data.get('items', [])
        algorithm_type = cmd.data.get('algorithm_type') or cmd.data.get('algorithmType')
        refresh_test_cases = cmd.data.get('refresh_test_cases', cmd.data.get('refreshTestCases', True))

        if not items:
            return _fail('标注列表不能为空')

        updated_audio_ids = []
        updated_count = 0
        failed_count = 0
        refreshed_tc_ids = []

        try:
            for item in items:
                audio_id = item.get('audio_id') or item.get('audioId')
                annotations = item.get('annotations', [])
                if not annotations:
                    continue

                audio = self.repo.get_audio(audio_id)
                if not audio:
                    failed_count += 1
                    continue

                self.annotation_service.persist_annotations_and_raw(audio_id, annotations, algorithm_type)
                updated_audio_ids.append(audio_id)
                updated_count += 1

            self.repo.flush()

            if refresh_test_cases and updated_audio_ids:
                refreshed_tc_ids = self.testcase_creation_service.refresh_test_cases_for_audios(
                    updated_audio_ids, algorithm_type
                )

            self.repo.commit()
            return _ok(
                data={
                    'updated_count': updated_count,
                    'failed_count': failed_count,
                    'refreshed_test_case_ids': refreshed_tc_ids,
                },
                message=f'批量更新标注成功，更新 {updated_count} 个音频，刷新 {len(refreshed_tc_ids)} 个用例',
            )
        except Exception as e:
            self.repo.rollback()
            log_and_emit(
                level='error', module='audio_controller',
                content=f'批量更新标注失败: {str(e)}\n{traceback.format_exc()}',
                category='audio',
            )
            return _fail(str(e))

    def handle_batch_action(self, cmd: BatchActionAudiosCommand) -> Dict[str, Any]:
        if not cmd.data:
            return _fail('请求体不能为空')

        audio_ids = cmd.data.get('audio_ids') or cmd.data.get('audioIds', [])
        action = cmd.data.get('action')
        tags = cmd.data.get('tags', [])

        try:
            if action == 'delete':
                deletable_audio_ids = []
                skipped_audio_ids = []

                for audio_id in audio_ids:
                    if self._task_acl.check_audio_in_testcases(audio_id) > 0:
                        skipped_audio_ids.append(audio_id)
                        continue
                    if self._task_acl.check_audio_in_testcase_noise(audio_id) > 0:
                        skipped_audio_ids.append(audio_id)
                        continue
                    if self._device_acl.check_audio_in_devices(audio_id) > 0:
                        skipped_audio_ids.append(audio_id)
                        continue
                    if self._task_acl.check_audio_in_tasks(audio_id) > 0:
                        skipped_audio_ids.append(audio_id)
                        continue
                    deletable_audio_ids.append(audio_id)

                if not deletable_audio_ids:
                    return _ok(message='没有可删除的音频文件，所有音频都被其他资源引用')

                audios = self.repo.get_audios_by_ids(deletable_audio_ids)
                for audio in audios:
                    try:
                        storage.delete(audio.file_path)
                    except Exception:
                        pass
                    self.repo.delete_audio_annotations(audio.id)
                    self.repo.delete_audio_tags(audio.id)

                self.repo.batch_soft_delete_audios(deletable_audio_ids)

                message = f'成功删除 {len(deletable_audio_ids)} 个音频文件'
                if skipped_audio_ids:
                    message += f'，跳过了 {len(skipped_audio_ids)} 个被引用的音频文件'

                self.repo.commit()
                return _ok(message=message)

            elif action == 'export':
                import zipfile
                from io import BytesIO
                audios = self.repo.get_audios_by_ids(audio_ids)
                memory_file = BytesIO()
                with zipfile.ZipFile(memory_file, 'w') as zf:
                    for audio in audios:
                        try:
                            local_path = storage.load_file(audio.file_path)
                            zf.write(local_path, audio.original_filename)
                        except Exception:
                            pass
                memory_file.seek(0)
                import base64
                zip_b64 = base64.b64encode(memory_file.getvalue()).decode('ascii')
                from shared.utils.query_utils import now_cst
                return _ok(data={
                    'zip_base64': zip_b64,
                    'filename': f'audios_export_{now_cst().strftime("%Y%m%d%H%M%S")}.zip',
                }, message='批量导出成功')

            elif action == 'tags':
                for audio_id in audio_ids:
                    audio = self.repo.get_audio(audio_id)
                    if audio:
                        self.repo.delete_audio_tags(audio_id)
                        for tag_name in tags:
                            tag = self.repo.get_or_create_tag(tag_name)
                            self.repo.add_audio_tag(audio_id, tag.id)

                self.repo.commit()
                return _ok(message=f'批量操作 {action} 执行成功')

            else:
                return _fail(f'不支持的操作: {action}')

        except Exception as e:
            self.repo.rollback()
            return _fail(str(e))

    def handle_delete(self, cmd: DeleteAudioCommand) -> Dict[str, Any]:
        audio = self.repo.get_audio(cmd.audio_id)
        if not audio:
            return _fail('未找到音频文件', 404)

        try:
            if self._task_acl.check_audio_in_testcases(cmd.audio_id) > 0:
                return _fail('该音频文件已被测试用例使用，禁止删除')
            if self._task_acl.check_audio_in_testcase_noise(cmd.audio_id) > 0:
                return _fail('该音频文件已被测试用例作为背景噪音使用，禁止删除')
            if self._device_acl.check_audio_in_devices(cmd.audio_id) > 0:
                return _fail('该音频文件已被设备作为提示词使用，禁止删除')
            if self._task_acl.check_audio_in_tasks(cmd.audio_id) > 0:
                return _fail('该音频文件已被任务使用，禁止删除')

            try:
                storage.delete(audio.file_path)
            except Exception:
                pass

            self.repo.delete_audio_annotations(cmd.audio_id)
            self.repo.delete_audio_tags(cmd.audio_id)
            self.repo.delete_audio(cmd.audio_id)
            self.repo.commit()

            try:
                from api_gateway.application.services.stats_cache import refresh_stats_cache
                refresh_stats_cache()
            except Exception:
                pass

            return _ok(message='音频文件已删除')
        except Exception as e:
            self.repo.rollback()
            return _fail(str(e))

    def handle_update_audio_algorithms(self, cmd: UpdateAudioAlgorithmsCommand) -> Dict[str, Any]:
        audio = self.repo.get_audio(cmd.audio_id)
        if not audio:
            return _fail('音频不存在', 404)

        algorithms = cmd.data.get('algorithms', [])
        try:
            self.repo.soft_delete_audio_algorithm_relations(cmd.audio_id)
            for item in algorithms:
                self.repo.create_audio_algorithm_relation(cmd.audio_id, item)
            self.repo.commit()
            return _ok(message='算法关联更新成功')
        except Exception as e:
            self.repo.rollback()
            return _fail(str(e))

    def handle_batch_update_audio_algorithms(self, cmd: BatchUpdateAudioAlgorithmsCommand) -> Dict[str, Any]:
        audio_ids = cmd.data.get('audio_ids') or cmd.data.get('audioIds', [])
        algorithms = cmd.data.get('algorithms', [])

        try:
            updated_count = 0
            for audio_id in audio_ids:
                audio = self.repo.get_audio(audio_id)
                if not audio:
                    continue
                self.repo.soft_delete_audio_algorithm_relations(audio_id)
                for item in algorithms:
                    self.repo.create_audio_algorithm_relation(audio_id, item)
                updated_count += 1

            self.repo.commit()
            return _ok(
                data={'updated_count': updated_count},
                message=f'成功更新 {updated_count} 个音频的算法关联',
            )
        except Exception as e:
            self.repo.rollback()
            return _fail(str(e))

    # ========== 转换/预览（委托子服务） ==========

    def handle_convert_audio(self, cmd: ConvertAudioCommand) -> Dict[str, Any]:
        from audio_service.application.services.audio_convert_service import audio_convert_service
        return audio_convert_service.convert_audio(cmd.audio_id, cmd.data)

    def handle_preview_audio(self, cmd: PreviewAudioCommand) -> Dict[str, Any]:
        from audio_service.application.services.audio_preview_service import audio_preview_service
        return audio_preview_service.preview_audio(cmd.audio_id, cmd.data)

    def handle_stop_preview_audio(self, cmd: StopPreviewAudioCommand) -> Dict[str, Any]:
        from audio_service.application.services.audio_preview_service import audio_preview_service
        return audio_preview_service.stop_preview_audio(cmd.audio_id)

    # ========== 标注/测试用例创建（委托子服务） ==========

    def handle_persist_annotations(self, cmd: PersistAnnotationsCommand) -> Dict[str, Any]:
        try:
            self.annotation_service.persist_annotations_and_raw(
                cmd.audio_id, cmd.annotations, cmd.algorithm_type
            )
            self.repo.commit()
            return _ok(message='标注持久化成功')
        except Exception as e:
            self.repo.rollback()
            return _fail(str(e))

    def handle_create_test_case_from_audio(self, cmd: CreateTestCaseFromAudioCommand) -> Dict[str, Any]:
        try:
            tc_ids = self.testcase_creation_service.create_test_case_from_audio(
                cmd.audio_id,
                cmd.test_types,
                cmd.tags,
                cmd.default_playback_device_id,
                cmd.default_spl,
                cmd.noise_spl,
                cmd.noise_audio_id,
                cmd.group_name,
                cmd.dimensions_data,
                cmd.algorithm_type,
                cmd.algorithm_params_dict,
                rounds_config=cmd.rounds_config,
                inherit_tags=cmd.inherit_tags,
                raw_annotations=cmd.raw_annotations,
                noise_device_ids=cmd.noise_device_ids,
            )
            self.repo.commit()
            return _ok(data={
                'test_case_id': tc_ids[0] if isinstance(tc_ids, list) and tc_ids else tc_ids,
                'test_case_count': len(tc_ids) if isinstance(tc_ids, list) else (1 if tc_ids else 0),
            }, message='测试用例创建成功')
        except Exception as e:
            self.repo.rollback()
            return _fail(str(e))
