# -*- coding: utf-8 -*-
"""manifest.json 构建与校验（纯函数）"""
import socket
from datetime import datetime
from typing import Dict, List, Optional

from shared.constants.data_transfer import (
    DEFAULT_DOC_VERSION_SCOPE,
    DEFAULT_INCLUDE_AUDIOS,
    DEFAULT_INCLUDE_REF_PARAMS,
    REPORT_PACKAGE_ENTITIES,
    REPORT_PACKAGE_MANIFEST_KIND,
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
    """构建导出清单（字段名按设计文档用 camelCase——ZIP 包文件格式，非 HTTP 契约）

    整包导出继续产出 1.0（D0 A1-2）；1.1 的增量包由
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
        'version': ManifestVersion.V1_0.value,
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
    }


def build_incremental_manifest(source_task: dict,
                               task_rows: List[dict],
                               dimension_count: int = 0,
                               report_count: int = 0,
                               entities: Optional[List[str]] = None,
                               source: Optional[str] = None,
                               options: Optional[dict] = None) -> dict:
    """构建增量包 manifest（版本 1.1，D0 A1-3）。

    Args:
        source_task: {id, name, caseCount, caseSetHash}——id / caseSetHash 是
            A 原始 id 与 A 侧指纹（A7），A 侧据此定位原任务并防错配
        task_rows: 包内 tasks[]（增量包写 [{id: A 原始 id, name, status, resultCount}]）
        entities: 包内实体段清单（['dimensions', 'reports'] 的子集）
        source: 稳定服务标识（DATA_TRANSFER_SERVER_ID），写入 serverInfo.source
        options: 追加的 options 字段（如 include）
    """
    from shared.constants.data_transfer import INCREMENTAL_MANIFEST_VERSION

    stats = {
        'taskCount': len(task_rows),
        'resultCount': 0,          # 增量包不搬结果本体（A2-1）
        'dimensionCount': dimension_count,
        'reportCount': report_count,
        'fileCount': 0,            # 增量包不搬文件
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


def build_report_package_manifest(source_task_id: int,
                                  local_task_id: Optional[int],
                                  task_name: str,
                                  report_ids: List[int],
                                  doc_version_scope: str = DEFAULT_DOC_VERSION_SCOPE,
                                  entities: Optional[List[str]] = None,
                                  counts: Optional[Dict[str, int]] = None,
                                  source: Optional[str] = None) -> dict:
    """构建报告包清单（INT-1764 D6，链路 3a + 3b/3c）。

    `sourceTask.id` 是 A 侧原任务 id（B 导出时经 source_map 反查），导入方据此
    定位并原地替换报告；`localTaskId` 是导出端本地 id，仅供回溯排查。
    """
    return {
        'version': ManifestVersion.V1_0.value,
        'kind': REPORT_PACKAGE_MANIFEST_KIND,
        'exportedAt': datetime.now().astimezone().isoformat(timespec='seconds'),
        'serverInfo': {'source': source or socket.gethostname()},
        'sourceTask': {
            'id': source_task_id,
            'localTaskId': local_task_id,
            'name': task_name,
        },
        'reports': [{'id': rid} for rid in (report_ids or [])],
        'entities': list(entities or []),
        'options': {'docVersionScope': doc_version_scope or DEFAULT_DOC_VERSION_SCOPE},
        'stats': dict(counts or {}),
    }


def validate_report_package_manifest(manifest: Optional[dict]) -> dict:
    """校验报告包 manifest：kind / 版本 / sourceTask.id 与 entities 必须齐备。"""
    if not isinstance(manifest, dict):
        raise ManifestError('manifest.json 缺失或不是 JSON 对象')
    if manifest.get('kind') != REPORT_PACKAGE_MANIFEST_KIND:
        raise ManifestError('上报的不是报告包（manifest.kind 不符）')
    version = manifest.get('version')
    if version not in SUPPORTED_MANIFEST_VERSIONS:
        raise ManifestError(
            f'导出包版本 {version!r} 不受支持（支持: {sorted(SUPPORTED_MANIFEST_VERSIONS)}），拒绝导入')
    source_task = manifest.get('sourceTask')
    if not isinstance(source_task, dict) or source_task.get('id') in (None, ''):
        raise ManifestError('manifest.sourceTask.id 缺失，无法定位原任务')
    entities = manifest.get('entities')
    if not isinstance(entities, list):
        raise ManifestError('manifest.entities 缺失或格式错误')
    unknown = [e for e in entities if e not in REPORT_PACKAGE_ENTITIES]
    if unknown:
        raise ManifestError(f'manifest.entities 含未知实体: {unknown}')
    options = manifest.get('options')
    if not isinstance(options, dict):
        options = {'docVersionScope': DEFAULT_DOC_VERSION_SCOPE}
    return {**manifest, 'options': options}
