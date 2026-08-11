# -*- coding: utf-8 -*-
"""音频查询处理器（CQRS 读侧）。

接收 Query 对象，委托仓储返回领域实体/DTO。
依赖 domain/repositories ABC 接口，不直接 import ORM。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from shared.infrastructure.storage import storage

from audio_service.domain.repositories import AudioRepositoryInterface
from audio_service.application.queries.audio_queries import (
    ListAudiosQuery,
    GetAudioQuery,
    GetAudiosByIdsQuery,
    GetAudioByMD5Query,
    GetAllAudioIdsQuery,
    GetAllAudioTagsQuery,
    StreamAudioQuery,
    StreamAudioByPathQuery,
    GetAudioAlgorithmsQuery,
    GetAudioFolderTreeQuery,
)

logger = logging.getLogger(__name__)


def _ok(data: Any = None, message: str = 'Success', code: int = 200) -> Dict[str, Any]:
    return {'success': True, 'message': message, 'data': data, 'code': code}


def _fail(message: str, code: int = 400, data: Any = None) -> Dict[str, Any]:
    return {'success': False, 'message': message, 'data': data, 'code': code}


def _audio_to_dict(audio, tags=None, annotations=None) -> dict:
    """将 AudioAggregate 序列化为 dict（用于接口层响应）。"""
    return {
        'id': audio.id,
        'name': audio.filename,
        'original_filename': audio.original_filename,
        'file_path': audio.file_path,
        'duration': audio.duration,
        'size': audio.file_size,
        'sample_rate': audio.sample_rate,
        'channels': audio.channels,
        'bitrate': audio.bitrate,
        'format': audio.audio_format,
        'audio_type': audio.audio_type,
        'asr_text': audio.asr_text,
        'description': audio.description,
        'source_language': audio.source_language,
        'md5': audio.md5,
        'tags': tags or [],
        'annotations': annotations or [],
        'created_at': audio.created_at.isoformat() if audio.created_at else None,
        'updated_at': audio.updated_at.isoformat() if audio.updated_at else None,
    }


class AudioQueryHandler:
    """音频读查询处理器。

    依赖注入 AudioRepositoryInterface（ABC），不直接 import 具体仓储类。
    """

    def __init__(self, repository: AudioRepositoryInterface = None) -> None:
        if repository is None:
            from audio_service.infrastructure.persistence.audio_repository import audio_repository
            repository = audio_repository
        self.repo = repository
        # ACL 仓储（跨域只读查询）
        from audio_service.infrastructure.acl.task_acl_repository import (
            TaskACLRepositoryImpl,
        )
        self._task_acl = TaskACLRepositoryImpl()

    def handle_get_all_tags(self, query: GetAllAudioTagsQuery) -> Dict[str, Any]:
        tag_names = self.repo.get_all_tag_names()
        return _ok(data={'items': tag_names, 'total': len(tag_names)})

    def handle_list_audios(self, query: ListAudiosQuery) -> Dict[str, Any]:
        try:
            pagination = self.repo.list_audios(query.params)
            audios = pagination.items

            audio_ids = [a.id for a in audios]
            tags_map = self.repo.get_audio_tags_map(audio_ids) if audio_ids else {}
            ann_map = self.repo.get_annotations_map(audio_ids) if audio_ids else {}

            items = []
            for audio in audios:
                items.append(_audio_to_dict(
                    audio,
                    tags_map.get(audio.id, []),
                    ann_map.get(audio.id, []),
                ))

            stats = self.repo.get_audio_stats()
            total_size = stats.get('total_size', 0)
            total_duration = stats.get('total_duration', 0)
            today_uploads = stats.get('today_uploads', 0)

            if total_size < 1024:
                size_str = f"{total_size} B"
            elif total_size < 1024 * 1024:
                size_str = f"{total_size/1024:.2f} KB"
            else:
                size_str = f"{total_size/(1024*1024):.2f} MB"

            mins, secs = divmod(int(total_duration), 60)
            duration_str = f"{mins}:{secs:02d}"

            return _ok(data={
                'items': items,
                'total': pagination.total,
                'page': pagination.page,
                'per_page': pagination.per_page,
                'pages': pagination.pages,
                'stats': {
                    'total_files': pagination.total,
                    'total_size': size_str,
                    'total_duration': duration_str,
                    'today_uploads': today_uploads,
                },
            })
        except Exception as e:
            return _fail(str(e))

    def handle_get_audio(self, query: GetAudioQuery) -> Dict[str, Any]:
        audio = self.repo.get_audio(query.audio_id)
        if not audio:
            return _fail('音频文件不存在', 404)

        tags = self.repo.get_audio_tag_names(audio.id)
        annotations = [
            {
                'format': ann.format,
                'code': ann.code,
                'data': ann.data,
                'source_language': ann.source_language,
                'target_language': ann.target_language,
            }
            for ann in self.repo.get_annotations_by_audio(audio.id)
        ]

        return _ok(data=_audio_to_dict(audio, tags, annotations))

    def handle_get_by_ids(self, query: GetAudiosByIdsQuery) -> Dict[str, Any]:
        if not query.ids:
            return _ok(data=[])

        audio_ids = [int(aid) if str(aid).isdigit() else aid for aid in query.ids]
        audios = self.repo.get_audios_by_ids(audio_ids)

        results = []
        for audio in audios:
            tags = self.repo.get_audio_tag_names(audio.id)
            annotations = [
                {
                    'format': ann.format,
                    'code': ann.code,
                    'data': ann.data,
                    'source_language': ann.source_language,
                    'target_language': ann.target_language,
                }
                for ann in self.repo.get_annotations_by_audio(audio.id)
            ]
            results.append(_audio_to_dict(audio, tags, annotations))

        return _ok(data=results)

    def handle_get_by_md5(self, query: GetAudioByMD5Query) -> Dict[str, Any]:
        if not query.md5_list:
            return _ok(data={})

        audios = self.repo.get_audios_by_md5_list(query.md5_list)
        result = {}
        for audio in audios:
            result[audio.md5] = {
                'id': audio.id,
                'name': audio.filename,
            }
        return _ok(data=result)

    def handle_get_all_ids(self, query: GetAllAudioIdsQuery) -> Dict[str, Any]:
        ids = self.repo.get_all_audio_ids(query.params)
        return _ok(data={'ids': ids, 'total': len(ids)})

    def handle_stream_audio(self, query: StreamAudioQuery) -> Dict[str, Any]:
        audio = self.repo.get_audio_with_deleted(query.audio_id)

        if not audio or audio.deleted:
            audios_config = self._task_acl.get_testcase_config_audios(query.audio_id)
            task_type = (query.data or {}).get('task_type', 'api')
            tc_test_type = self._task_acl.get_testcase_test_type(query.audio_id)
            if tc_test_type == task_type:
                target_audio_config = next((c for c in audios_config if c.get('audio_id')), None)
                if target_audio_config:
                    target_audio_id = target_audio_config.get('audio_id')
                    if target_audio_id:
                        audio = self.repo.get_audio_with_deleted(target_audio_id)

        if not audio or audio.deleted:
            return _fail('音频不存在', 404)

        file_path = audio.file_path
        if not file_path:
            return _fail('音频文件路径缺失', 404)

        presigned_url = storage.get_url(
            file_path if file_path.startswith(('oss://', 'local://'))
            else storage.build_path('audios', file_path),
            expires=3600,
        )
        if presigned_url:
            return _ok(data={'url': presigned_url})
        return _ok(data={'url': f'/api/audio/download?path={file_path}'})

    def handle_stream_audio_by_path(self, query: StreamAudioByPathQuery) -> Dict[str, Any]:
        oss_key = query.data.get('path')
        if not oss_key:
            return _fail('未提供路径')

        try:
            presigned_url = storage.get_url(oss_key, expires=3600)
            return _ok(data={'url': presigned_url})
        except Exception as e:
            logger.error(f"stream_by_path 获取存储 URL 失败: {e}, key={oss_key}")
            return _fail(f'获取音频失败: {e}', 404)

    def handle_get_audio_algorithms(self, query: GetAudioAlgorithmsQuery) -> Dict[str, Any]:
        audio = self.repo.get_audio(query.audio_id)
        if not audio:
            return _fail('音频不存在', 404)

        relations = self.repo.get_audio_algorithm_relations(query.audio_id)
        result = []
        for r in relations:
            result.append({
                'algorithm_type': r.algorithm_type,
                'is_primary': r.is_primary,
                'weight': r.weight,
                'params': r.params,
            })
        return _ok(data=result)

    def handle_get_folder_tree(self, query: GetAudioFolderTreeQuery) -> Dict[str, Any]:
        from audio_service.config.config import Config

        audios = self.repo.collect_folder_files(query.data)
        audio_storage_path = getattr(Config, 'AUDIO_STORAGE_PATH', '')
        base_normalized = (audio_storage_path or '').replace(chr(92), '/').rstrip('/')
        parent_path = query.data.get('parent_path', '')
        depth = query.data.get('depth', 1)

        result = self._build_folder_structure(audios, base_normalized, parent_path, depth)
        return _ok(data=result)

    @staticmethod
    def _build_folder_structure(audios, base_normalized, parent_path, depth):
        def get_folder_key(file_path):
            normalized = file_path.replace(chr(92), '/') if file_path else ''
            parts = [p for p in normalized.split('/') if p]
            if base_normalized and normalized.startswith(base_normalized + '/'):
                relative = normalized[len(base_normalized) + 1:]
                rel_parts = [p for p in relative.split('/') if p]
                return rel_parts[:-1] if len(rel_parts) > 1 else []
            last_audio_idx = -1
            for idx, p in enumerate(parts):
                if p in ('audios', 'audio'):
                    last_audio_idx = idx
            if last_audio_idx >= 0:
                parts = parts[last_audio_idx + 1:]
                return parts[:-1] if len(parts) > 1 else []
            if parts and len(parts[0]) == 2 and parts[0][1] == ':':
                parts = parts[1:]
            skip_segments = {'static', 'S2TT', 'auto_test', 'ver8', '202604231600', 'Intelligent-Audio-TEST'}
            while parts and parts[0] in skip_segments:
                parts = parts[1:]
            return parts[:-1] if len(parts) > 1 else []

        def make_file_item(audio):
            return {
                'id': audio.id,
                'name': audio.name,
                'filename': audio.original_filename or audio.name,
                'format': audio.format,
                'duration': audio.duration,
                'size': audio.size,
                'audio_type': audio.audio_type,
                'created_at': audio.created_at.isoformat() if audio.created_at else None,
            }

        folder_map = {}
        root_files = []
        subfolder_parents = set()

        for audio in audios:
            folder_parts = get_folder_key(audio.file_path)
            if not folder_parts:
                root_files.append(make_file_item(audio))
                continue
            current_path = ''
            for i, part in enumerate(folder_parts):
                parent = current_path
                current_path = f'{current_path}/{part}' if current_path else part
                if current_path not in folder_map:
                    folder_map[current_path] = {
                        'name': part, 'path': current_path, 'parent': parent,
                        'depth': i + 1, 'count': 0, 'file_count': 0, 'files': []
                    }
                folder_map[current_path]['count'] += 1
                if parent:
                    subfolder_parents.add(parent)
                if i == len(folder_parts) - 1:
                    folder_map[current_path]['file_count'] += 1
                    if parent_path or depth > i + 1:
                        folder_map[current_path]['files'].append(make_file_item(audio))

        from collections import defaultdict
        children_map = defaultdict(list)
        for path_key, folder in folder_map.items():
            children_map[folder['parent']].append(path_key)

        def build_tree(parent_key=''):
            result = []
            for path_key in children_map.get(parent_key, []):
                folder = folder_map[path_key]
                children = build_tree(path_key)
                result.append({
                    'name': folder['name'], 'path': folder['path'],
                    'count': folder['count'], 'file_count': folder['file_count'],
                    'has_children': len(children) > 0 or folder['file_count'] > 0,
                    'files': folder['files'] if parent_path or depth > folder['depth'] else [],
                    'folders': children,
                })
            return sorted(result, key=lambda x: x['name'])

        tree = {
            'name': '音频文件', 'path': '', 'count': len(audios),
            'file_count': len(root_files),
            'has_children': len(folder_map) > 0 or len(root_files) > 0,
            'files': root_files if depth >= 1 else [],
            'folders': build_tree(),
        }

        folder_list = []
        for path_key in children_map.get('', []):
            folder = folder_map[path_key]
            folder_list.append({
                'name': folder['name'], 'path': folder['path'],
                'count': folder['count'], 'file_count': folder['file_count'],
                'has_children': path_key in subfolder_parents,
            })

        return {
            'tree': tree,
            'folders': sorted(folder_list, key=lambda x: x['name']),
            'total': len(audios),
            'folder_count': len(folder_map),
        }
