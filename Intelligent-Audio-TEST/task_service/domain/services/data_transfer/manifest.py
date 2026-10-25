# -*- coding: utf-8 -*-
"""manifest.json 构建与校验（纯函数）"""
import socket
from datetime import datetime
from typing import Dict, List, Optional

# ManifestVersion 供合入 V9.7.31 后的报告包 manifest（INT-1764/D6）使用，解冲突时勿删。
from shared.constants.data_transfer import (
    DEFAULT_INCLUDE_AUDIOS,
    DEFAULT_INCLUDE_REF_PARAMS,
    SUPPORTED_MANIFEST_VERSIONS,
    ManifestVersion,
    FULL_MANIFEST_VERSION,
    RAW_OBJECTS_MANIFEST_KEY,
)


class ManifestError(ValueError):
    """manifest 非法（版本不符 / 结构缺失）——导入直接拒绝"""


def _raw_objects_section(raw_objects: Optional[dict]) -> dict:
    """manifest.rawObjects 段：包内原始报文对象清单（与 files/raw/ 条目一一对应）

    INT-1811：内容寻址 → 同对象只出现一次；files 列出 (key, sha256, bytes)，
    导入侧据此核对包完整性（1.2 包缺对象按坏包拒绝）。
    """
    from shared.utils.raw_payload import RAW_CATEGORY, RAW_CONTENT_TYPE

    section = {'contentType': RAW_CONTENT_TYPE, 'category': RAW_CATEGORY}
    section.update(raw_objects or {})
    section.setdefault('count', 0)
    section.setdefault('totalBytes', 0)
    section.setdefault('files', [])
    return section


def build_manifest(task_rows: List[dict],
                   result_rows: List[dict],
                   dimension_count: int,
                   report_count: int,
                   file_count: int,
                   total_file_size: int,
                   include_ref_params: bool = DEFAULT_INCLUDE_REF_PARAMS,
                   include_audios: bool = DEFAULT_INCLUDE_AUDIOS,
                   source: Optional[str] = None,
                   raw_objects: Optional[dict] = None) -> dict:
    """构建导出清单（字段名按设计文档用 camelCase——ZIP 包文件格式，非 HTTP 契约）

    INT-1811 起整包产出 1.2（带原始报文对象清单 `rawObjects`）；1.1 的增量包由
    `build_incremental_manifest` 构建，不复用本函数的 stats 口径。
    """
    stats = {
        'taskCount': len(task_rows),
        'resultCount': len(result_rows),
        'dimensionCount': dimension_count,
        'reportCount': report_count,
        'fileCount': file_count,
        'totalFileSize': total_file_size,
    }
    return {
        'version': FULL_MANIFEST_VERSION,
        'exportedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
        'serverInfo': {'source': source or socket.gethostname()},
        'tasks': [
            {
                'id': row.get('id'),
                'name': row.get('name'),
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
        RAW_OBJECTS_MANIFEST_KEY: _raw_objects_section(raw_objects),
    }


def build_incremental_manifest(source_task: dict,
                               task_rows: List[dict],
                               dimension_count: int = 0,
                               report_count: int = 0,
                               entities: Optional[List[str]] = None,
                               source: Optional[str] = None,
                               options: Optional[dict] = None,
                               raw_objects: Optional[dict] = None) -> dict:
    """构建增量包 manifest（版本 1.2，D0 A1-3 + INT-1811）

    Args:
        source_task: {id, name, caseCount, caseSetHash}——id / caseSetHash 是
            A 原始 id 与 A 侧指纹（A7），A 侧据此定位原任务并防错配
        task_rows: 包内 tasks[]（增量包写 [{id: A 原始 id, name, status, resultCount}]）
        entities: 包内实体段清单（['dimensions', 'reports'] 的子集）
        source: 稳定服务标识（DATA_TRANSFER_SERVER_ID），写入 serverInfo.source
        options: 追加的 options 字段（如 include）
        raw_objects: manifest.rawObjects 段（INT-1811：增量包同样携带原始报文对象）
    """
    from shared.constants.data_transfer import INCREMENTAL_MANIFEST_VERSION

    stats = {
        'taskCount': len(task_rows),
        'resultCount': 0,          # 增量包不搬结果本体（A2-1）
        'dimensionCount': dimension_count,
        'reportCount': report_count,
        'fileCount': 0,            # 增量包不搬结果 / 音频文件
        'totalFileSize': 0,
    }
    manifest = {
        'version': INCREMENTAL_MANIFEST_VERSION,
        'exportedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
        'serverInfo': {'source': source or socket.gethostname()},
        'sourceTask': {
            'id': source_task.get('id'),
            'name': source_task.get('name'),
            'caseCount': source_task.get('caseCount', 0),
            'caseSetHash': source_task.get('caseSetHash', ''),
        },
        'entities': list(entities or []),
        'tasks': [
            {
                'id': row.get('id'),
                'name': row.get('name'),
                'status': row.get('status'),
                'resultCount': row.get('resultCount', 0),
            }
            for row in task_rows
        ],
        'stats': stats,
        'options': dict(options or {}),
        RAW_OBJECTS_MANIFEST_KEY: _raw_objects_section(raw_objects),
    }
    return manifest


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
