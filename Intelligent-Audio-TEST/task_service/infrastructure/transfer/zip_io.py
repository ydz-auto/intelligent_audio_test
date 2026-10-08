# -*- coding: utf-8 -*-
"""导出包 ZIP 读写（基础设施层：zipfile + 路径安全校验）

- 导出：逐条目流式写入磁盘 ZIP（大任务不整包驻留内存）
- 导入/预检：解包读取 db/*.json 与 manifest，文件条目经 safe_zip_entry_name 校验
"""
import json
import os
import zipfile
from typing import Dict, Iterator, List, Tuple

from shared.constants.data_transfer import (
    DB_DIR,
    DIMENSIONS_SNAPSHOT_PATH,
    FILES_AUDIOS_DIR,
    FILES_CASE_RESULTS_DIR,
    FILES_REF_PARAMS_DIR,
    MANIFEST_NAME,
)
from shared.utils.data_transfer import match_zip_entry_name, safe_zip_entry_name

_ALLOWED_PREFIXES = (DB_DIR, 'files/', 'meta/')


def build_zip(zip_path: str,
              db_tables: Dict[str, List[dict]],
              manifest,
              file_entries: Iterator[Tuple[str, bytes]],
              dimensions_snapshot: List[dict] = None) -> int:
    """流式构建导出 ZIP，返回打包的文件条目数。

    Args:
        zip_path: 目标 ZIP 路径（DATA_TRANSFER_TMP_DIR/export/ 下）
        db_tables: 表名 → 行列表（每个 <table>.json 一个数组）
        manifest: 清单 dict，或返回 dict 的延迟回调（文件条目边写边统计，
            fileCount/totalFileSize 在写 manifest 前才最终可知，须传回调）
        file_entries: (zip 内相对名如 case_results/12/c_1/dev/result_data.json, 内容) 迭代器
        dimensions_snapshot: 评估维度定义快照（meta/dimensions.json，仅展示参考）
    """
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    file_count = 0
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED) as zf:
        for table, rows in db_tables.items():
            arcname = safe_zip_entry_name(f'{DB_DIR}/{table}.json', _ALLOWED_PREFIXES)
            zf.writestr(arcname, json.dumps(rows, ensure_ascii=False, default=str))
        for name, data in file_entries:
            arcname = safe_zip_entry_name(f'files/{name}', _ALLOWED_PREFIXES)
            zf.writestr(arcname, data)
            file_count += 1
        if dimensions_snapshot:
            arcname = safe_zip_entry_name(DIMENSIONS_SNAPSHOT_PATH, _ALLOWED_PREFIXES)
            zf.writestr(arcname, json.dumps(dimensions_snapshot, ensure_ascii=False, default=str))
        manifest_dict = manifest() if callable(manifest) else manifest
        zf.writestr(MANIFEST_NAME, json.dumps(manifest_dict, ensure_ascii=False, default=str))
    return file_count


def read_manifest(zip_path: str) -> dict:
    """读取并解析 manifest.json（缺失/坏 JSON 抛 ValueError）"""
    with zipfile.ZipFile(zip_path, 'r') as zf:
        names = set(zf.namelist())
        if MANIFEST_NAME not in names:
            raise ValueError('导出包缺少 manifest.json')
        raw = zf.read(MANIFEST_NAME)
    try:
        return json.loads(raw.decode('utf-8'))
    except Exception as e:
        raise ValueError(f'manifest.json 解析失败: {e}')


def read_db_tables(zip_path: str) -> Dict[str, List[dict]]:
    """读取 db/ 目录下全部 <table>.json → {表名: 行列表}（缺文件视为空表）"""
    tables: Dict[str, List[dict]] = {}
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for name in zf.namelist():
            normalized = match_zip_entry_name(name, _ALLOWED_PREFIXES)
            if normalized is None or not normalized.endswith('.json'):
                continue  # manifest.json 等非 db 条目跳过；路径逃逸条目已抛错
            if not normalized.startswith(f'{DB_DIR}/'):
                continue
            table = normalized[len(DB_DIR) + 1:-len('.json')]
            rows = json.loads(zf.read(name).decode('utf-8'))
            if not isinstance(rows, list):
                raise ValueError(f'db/{table}.json 不是 JSON 数组')
            tables[table] = rows
    return tables


def read_dimensions_snapshot(zip_path: str) -> List[dict]:
    """读取维度定义快照（不存在返回空列表）"""
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            if DIMENSIONS_SNAPSHOT_PATH not in zf.namelist():
                return []
            return json.loads(zf.read(DIMENSIONS_SNAPSHOT_PATH).decode('utf-8'))
    except ValueError:
        raise
    except Exception:
        return []


def iter_file_entries(zip_path: str, subdir: str) -> Iterator[Tuple[str, bytes]]:
    """迭代 files/<subdir>/ 下的文件条目，产出 (条目内相对 key, 内容 bytes)。

    Args:
        subdir: files/ 下的子目录，兼容传入带 'files/' 前缀的完整目录
            （如 'files/case_results' 或 'case_results' 均可）。
    相对 key 保留包内目录结构（如 case_results/12/c_1/dev/result_data.json
    产出 ('12/c_1/dev/result_data.json', ...)）。
    """
    subdir = subdir.strip('/')
    if subdir.startswith('files/'):
        subdir = subdir[len('files/'):]
    prefix = f'files/{subdir}/'
    with zipfile.ZipFile(zip_path, 'r') as zf:
        for name in zf.namelist():
            normalized = match_zip_entry_name(name, _ALLOWED_PREFIXES)
            if normalized is None or not normalized.startswith(prefix):
                continue
            key = normalized[len(prefix):]
            if not key:
                continue
            yield key, zf.read(name)


def case_results_entries(zip_path: str) -> Iterator[Tuple[str, bytes]]:
    return iter_file_entries(zip_path, FILES_CASE_RESULTS_DIR)


def ref_params_entries(zip_path: str) -> Iterator[Tuple[str, bytes]]:
    return iter_file_entries(zip_path, FILES_REF_PARAMS_DIR)


def audios_entries(zip_path: str) -> Iterator[Tuple[str, bytes]]:
    return iter_file_entries(zip_path, FILES_AUDIOS_DIR)
