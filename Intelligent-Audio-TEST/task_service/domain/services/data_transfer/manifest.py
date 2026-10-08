# -*- coding: utf-8 -*-
"""manifest.json 构建与校验（纯函数）"""
import socket
from datetime import datetime
from typing import Dict, List, Optional

from shared.constants.data_transfer import (
    DEFAULT_INCLUDE_AUDIOS,
    DEFAULT_INCLUDE_REF_PARAMS,
    SUPPORTED_MANIFEST_VERSIONS,
    ManifestVersion,
)


class ManifestError(ValueError):
    """manifest 非法（版本不符 / 结构缺失）——导入直接拒绝"""


def build_manifest(task_rows: List[dict],
                   result_rows: List[dict],
                   dimension_count: int,
                   report_count: int,
                   file_count: int,
                   total_file_size: int,
                   include_ref_params: bool = DEFAULT_INCLUDE_REF_PARAMS,
                   include_audios: bool = DEFAULT_INCLUDE_AUDIOS,
                   source: Optional[str] = None) -> dict:
    """构建导出清单（字段名按设计文档用 camelCase——ZIP 包文件格式，非 HTTP 契约）"""
    stats = {
        'taskCount': len(task_rows),
        'resultCount': len(result_rows),
        'dimensionCount': dimension_count,
        'reportCount': report_count,
        'fileCount': file_count,
        'totalFileSize': total_file_size,
    }
    return {
        'version': ManifestVersion.V1_0.value,
        'exportedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
        'serverInfo': {'source': source or socket.gethostname()},
        'tasks': [
            {
                'id': row.get('id'),
                'name': row.get('name'),
                'type': row.get('type'),
                'status': row.get('status'),
                'resultCount': sum(1 for r in result_rows if r.get('task_id') == row.get('id')),
            }
            for row in task_rows
        ],
        'stats': stats,
        'options': {
            'includeRefParams': bool(include_ref_params),
            'includeAudios': bool(include_audios),
        },
    }


def validate_manifest(manifest: Optional[dict]) -> dict:
    """校验 manifest：版本不符直接拒绝导入（不做跨版本迁移），结构缺失视为坏包。"""
    if not isinstance(manifest, dict):
        raise ManifestError('manifest.json 缺失或不是 JSON 对象')
    version = manifest.get('version')
    if version not in SUPPORTED_MANIFEST_VERSIONS:
        raise ManifestError(
            f'导出包版本 {version!r} 不受支持（支持: {sorted(SUPPORTED_MANIFEST_VERSIONS)}），拒绝导入')
    tasks = manifest.get('tasks')
    if not isinstance(tasks, list):
        raise ManifestError('manifest.tasks 缺失或格式错误')
    options = manifest.get('options')
    if not isinstance(options, dict):
        options = {'includeRefParams': DEFAULT_INCLUDE_REF_PARAMS,
                   'includeAudios': DEFAULT_INCLUDE_AUDIOS}
    return {**manifest, 'options': options}
