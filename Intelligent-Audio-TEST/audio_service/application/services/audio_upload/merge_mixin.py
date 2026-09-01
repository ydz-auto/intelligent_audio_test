# -*- coding: utf-8 -*-
"""分片合并 Mixin（原 audio_upload_service.py 拆分产物，P4-5；P4-6 重组入 audio_upload 子包）。

职责：分片合并、秒传处理、音频记录创建、标签/算法关联、测试用例创建。
依赖 self.repo / self._annotation_service / self._testcase_creation_service /
self._transcoding_service / self._round_config_service。
"""
import os
import logging

from audio_service.domain.entities import UploadStatus
from audio_service.application.services.audio_convert_service import (
    _get_source_language_from_algorithm_params,
)

logger = logging.getLogger(__name__)


class AudioMergeMixin:
    """分片合并（依赖 self.repo 与各协作服务）"""

    def merge_chunks(self, data: dict) -> dict:
        """合并分片"""
        try:
            file_id = data.get('file_id') or data.get('fileId')
            task_id = data.get('task_id') or data.get('taskId')
            if not file_id or not task_id:
                return {'success': False, 'message': '缺少文件或任务ID', 'data': None, 'code': 400}

            upload_file = self.repo.get_upload_file(file_id)
            if not upload_file:
                return {'success': False, 'message': '文件不存在', 'data': None, 'code': 404}
            task = self.repo.get_upload_task(task_id)
            if not task:
                return {'success': False, 'message': '任务不存在', 'data': None, 'code': 404}

            params = self._round_config_service.extract_merge_params(data)

            # 检查秒传
            instant_result = self._check_instant_upload(upload_file, data, params)
            if instant_result is not None:
                return instant_result

            # 合并分片
            final_path = self._merge_file_parts(upload_file, data)

            # 转码并提取元数据
            audio_meta = self._transcoding_service.transcode_and_extract_metadata(
                final_path, upload_file
            )

            # 创建音频记录
            new_audio, audio_tags, raw_annotations_data = self._create_audio_record(
                audio_meta, upload_file, data, params
            )

            # 创建测试用例（如果需要）
            tc_result = self._create_test_case_if_needed(
                new_audio, params, audio_tags, raw_annotations_data
            )

            self.repo.commit()
            return self._build_merge_response(file_id, new_audio, tc_result)
        except Exception as e:
            self.repo.rollback()
            logger.error(f"合并分片失败: {str(e)}", exc_info=True)
            return {'success': False, 'message': f'合并分片失败: {str(e)}', 'data': None, 'code': 400}

    def _build_merge_response(self, file_id, new_audio, tc_result):
        """构建合并完成响应"""
        response_data = {
            'file_id': file_id,
            'audio_id': new_audio.id,
            'name': new_audio.name,
            'status': 'completed',
        }
        if tc_result:
            response_data['test_case_id'] = tc_result.get('tc_id')
            response_data['test_case_count'] = tc_result.get('tc_count')
        return {'success': True, 'message': '合并完成', 'data': response_data, 'code': 200}

    def _check_instant_upload(self, upload_file, data, params):
        """检查秒传场景：返回响应 dict 表示已处理，返回 None 表示继续合并流程"""
        is_instant_upload = upload_file.total_chunks == 0 and upload_file.status == UploadStatus.completed

        if not is_instant_upload and upload_file.md5:
            existing_audio = self.repo.get_audio_by_md5(upload_file.md5)
            if existing_audio:
                is_instant_upload = True

        if not is_instant_upload:
            if upload_file.completed_chunks < upload_file.total_chunks:
                return {'success': False, 'message': '还有分片未上传完成', 'data': None, 'code': 400}
            return None

        return self._handle_instant_upload(upload_file, data, params)

    def _handle_instant_upload(self, upload_file, data, params):
        """处理秒传：查找已有音频并按是否创建测试用例分支"""
        if not upload_file.md5:
            return None

        existing_audio = self.repo.get_audio_by_md5(upload_file.md5)
        if not existing_audio:
            return None

        audio_tags = self.repo.get_audio_tag_names(existing_audio.id)

        if params['create_test_case']:
            return self._instant_upload_with_testcase(existing_audio, data, params, audio_tags)
        return self._instant_upload_without_testcase(existing_audio, data, params)

    def _instant_upload_with_testcase(self, existing_audio, data, params, audio_tags):
        """秒传 + 创建测试用例：匹配轮次、创建用例、返回响应"""
        self._round_config_service.match_existing_audio_in_rounds(
            params['rounds_config'], existing_audio
        )
        raw_annotations_data = self._annotation_service.persist_annotations_and_raw(
            existing_audio.id,
            data.get('annotations', []),
            params['algorithm_type'],
        )
        tc_ids = self._testcase_creation_service.create_test_case_from_audio(
            existing_audio.id,
            params['test_types'],
            audio_tags,
            params['default_playback_device_id'],
            params['default_spl'],
            params['noise_spl'],
            params['noise_audio_id'],
            params['test_case_group_name'],
            params['dimensions_data'],
            params['algorithm_type'],
            params['algorithm_params_dict'],
            rounds_config=params['rounds_config'],
            inherit_tags=params['tc_inherit_tags'],
            raw_annotations=raw_annotations_data,
            noise_device_ids=params.get('noise_device_ids'),
            case_background_noise=params.get('case_background_noise'),
        )
        self.repo.commit()
        return {
            'success': True, 'message': '秒传成功，测试用例已创建',
            'data': {
                'file_id': data.get('file_id') or data.get('fileId'),
                'audio_id': existing_audio.id,
                'name': existing_audio.name,
                'status': 'completed',
                'test_case_id': tc_ids[0] if tc_ids else None,
                'test_case_count': len(tc_ids) if isinstance(tc_ids, list) else (1 if tc_ids else 0),
                'instant_upload': True,
            },
            'code': 200,
        }

    def _instant_upload_without_testcase(self, existing_audio, data, params):
        """秒传不创建测试用例：仅持久化标注并返回响应"""
        self._annotation_service.persist_annotations_and_raw(
            existing_audio.id,
            data.get('annotations', []),
            params['algorithm_type'],
        )
        self.repo.commit()
        return {
            'success': True, 'message': '秒传成功',
            'data': {
                'file_id': data.get('file_id') or data.get('fileId'),
                'audio_id': existing_audio.id,
                'name': existing_audio.name,
                'status': 'completed',
                'instant_upload': True,
            },
            'code': 200,
        }

    def _merge_file_parts(self, upload_file, data):
        """合并分片，返回 final_path（委托转码服务）"""
        base_upload_dir = self._get_base_upload_dir()
        chunk_base = os.path.join(base_upload_dir, 'chunks')

        is_direct_oss = data.get('is_direct_oss', data.get('isDirectOss', False))
        oss_key = data.get('oss_key', data.get('ossKey'))
        oss_upload_id = data.get('oss_upload_id', data.get('ossUploadId'))
        oss_parts = data.get('oss_parts', data.get('ossParts'))

        if is_direct_oss and oss_key and oss_upload_id:
            return self._transcoding_service.merge_direct_oss_parts(
                oss_key, oss_upload_id, oss_parts
            )
        return self._transcoding_service.merge_local_chunks(
            upload_file, base_upload_dir, chunk_base
        )

    def _create_audio_record(self, audio_meta, upload_file, data, params):
        """创建音频数据库记录，处理标签和算法关联"""
        source_language = _get_source_language_from_algorithm_params(
            params['algorithm_params']
        )

        audio_record = self.repo.create_audio({
            'name': upload_file.filename,
            'original_filename': upload_file.original_filename,
            'file_path': audio_meta['final_path'],
            'size': audio_meta['file_size'],
            'duration': audio_meta['duration'],
            'sample_rate': audio_meta['sample_rate'],
            'channels': audio_meta['channels'],
            'bitrate': audio_meta['bitrate'],
            'format': 'wav',
            'audio_type': data.get('audio_type', data.get('audioType', 'dry')),
            'md5': upload_file.md5,
            'source_language': source_language,
            'asr_text': data.get('asr_text', data.get('asrText', '')),
            'description': params['description'],
        })

        audio_tags = self._process_audio_tags(audio_record, params['user_tags'], upload_file)

        raw_annotations_data = self._annotation_service.persist_annotations_and_raw(
            audio_record.id,
            data.get('annotations', []),
            params['algorithm_type'],
        )

        self._process_algorithm_relations(audio_record, data, params['algorithm_type'])
        self.repo.flush()

        return audio_record, audio_tags, raw_annotations_data

    def _process_audio_tags(self, audio_record, user_tags, upload_file):
        """处理音频标签关联"""
        audio_tags = []
        all_tag_names = list(user_tags)

        relative_path = upload_file.relative_path
        if relative_path:
            path_parts = relative_path.split('/')
            directory_parts = path_parts[:-1]
            for part in directory_parts:
                if part and part not in all_tag_names:
                    all_tag_names.append(part)

        for tag_name in all_tag_names:
            if not tag_name:
                continue
            tag = self.repo.get_or_create_tag(tag_name)
            self.repo.add_audio_tag(audio_record.id, tag.id)
            audio_tags.append(tag.name)

        return audio_tags

    def _process_algorithm_relations(self, audio_record, data, algorithm_type):
        """处理音频算法关联"""
        algorithm_relations = data.get('algorithm_relations', data.get('algorithmRelations'))
        if algorithm_relations:
            for item in algorithm_relations:
                if isinstance(item, dict):
                    self.repo.create_audio_algorithm_relation(audio_record.id, item)
        elif algorithm_type:
            self.repo.create_audio_algorithm_relation(audio_record.id, {
                'algorithm_type': algorithm_type,
                'is_primary': True,
                'weight': 1.0,
                'params': None,
            })

    def _create_test_case_if_needed(self, new_audio, params, audio_tags, raw_annotations_data):
        """如果需要，创建测试用例"""
        if not params['create_test_case']:
            return None

        tc_ids = self._testcase_creation_service.create_test_case_from_audio(
            new_audio.id,
            params['test_types'],
            audio_tags,
            params['default_playback_device_id'],
            params['default_spl'],
            params['noise_spl'],
            params['noise_audio_id'],
            params['test_case_group_name'],
            params['dimensions_data'],
            params['algorithm_type'],
            params['algorithm_params_dict'],
            rounds_config=params['rounds_config'],
            inherit_tags=params['tc_inherit_tags'],
            raw_annotations=raw_annotations_data or None,
            noise_device_ids=params.get('noise_device_ids'),
            case_background_noise=params.get('case_background_noise'),
        )

        if isinstance(tc_ids, list):
            tc_id = tc_ids[0] if tc_ids else None
            tc_count = len(tc_ids)
        else:
            tc_id = tc_ids
            tc_count = 1 if tc_ids else 0

        return {'tc_id': tc_id, 'tc_count': tc_count}
