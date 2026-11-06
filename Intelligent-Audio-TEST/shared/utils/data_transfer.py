# -*- coding: utf-8 -*-
"""任务数据导入导出 —— 跨服务共享的纯函数工具（无 DB / 网络 / 存储依赖）

task_service / evaluation_service / report_service 的导入器共用：
- 主键冲突检测与 id 剥离（冲突行去 id 交由 DB 自增）
- 外键映射改写（统一表达式 mapping.get(old_id, old_id)）
- ZIP 条目名 / 存储 key 安全校验（防 zip-slip 与路径逃逸）
- result 文件 key 的 task_id 段重映射

可单测（tests/unit/test_data_transfer_*.py）。
"""
import posixpath
import re
from typing import Dict, Iterable, List, Sequence, Set, Tuple


def strip_conflicting_ids(rows: List[dict], existing_ids: Set[int]) -> List[dict]:
    """按目标库存在性集合处理主键：无冲突保留原 id，冲突行去掉 id（DB 自增分配）。

    返回重写后的新行列表（不改入参）。原 id 保留还是自增由数据决定，全自动无用户选项。
    """
    result = []
    for row in rows:
        new_row = dict(row)
        old_id = new_row.get('id')
        if old_id is not None and old_id in existing_ids:
            new_row.pop('id', None)
        result.append(new_row)
    return result


def conflicted_ids(rows: Sequence[dict], existing_ids: Set[int]) -> List[int]:
    """列出与目标库冲突的主键（预检 / 日志用）"""
    return [row['id'] for row in rows if row.get('id') in existing_ids]


def apply_fk_mapping(rows: Iterable[dict], column: str, mapping: Dict[int, int]) -> List[dict]:
    """对行列表应用一条外键转换规则：row[column] = mapping.get(old, old)。

    None 值跳过（可空外键）。返回重写后的新行列表（不改入参）。
    """
    result = []
    for row in rows:
        new_row = dict(row)
        old_value = new_row.get(column)
        if old_value is not None:
            new_row[column] = mapping.get(old_value, old_value)
        result.append(new_row)
    return result


def build_id_mapping(rows_with_old_ids: Sequence[int], inserted_new_ids: Sequence[int]) -> Dict[int, int]:
    """flush 后由「原 id 序列 + DB 分配的新 id 序列」构建 old→new 映射。

    长度不一致时抛错（调用方保证两序列一一对应）。
    """
    if len(rows_with_old_ids) != len(inserted_new_ids):
        raise ValueError(
            f'ID 映射构建失败：原 id {len(rows_with_old_ids)} 个 vs 新 id {len(inserted_new_ids)} 个')
    return {old: new for old, new in zip(rows_with_old_ids, inserted_new_ids)}


_ZIP_NAME_RE = re.compile(r'^[\w./\- ]+$')

# ZIP 包内允许出现条目的顶层目录（manifest.json 位于根目录，由读取侧单独处理）
ZIP_ENTRY_PREFIXES = ('db/', 'files/', 'meta/')


def _normalize_zip_entry_name(name: str) -> str:
    """校验 ZIP 条目名无路径逃逸（防 zip-slip），返回规范化 posix 相对路径。"""
    if not name or name.startswith('/') or '\\' in name:
        raise ValueError(f'非法 ZIP 条目名: {name!r}')
    if not _ZIP_NAME_RE.match(name):
        raise ValueError(f'ZIP 条目名含非法字符: {name!r}')
    # 任何字面 '..' 段一律拒绝（normpath 会吞掉中间上跳段，必须在规范化前判定）
    if any(seg == '..' for seg in name.split('/')):
        raise ValueError(f'ZIP 条目名越界: {name!r}')
    normalized = posixpath.normpath(name)
    if normalized.startswith('..') or '/..' in normalized:
        raise ValueError(f'ZIP 条目名越界: {name!r}')
    return normalized


def safe_zip_entry_name(name: str, allowed_prefixes: Iterable[str]) -> str:
    """校验 ZIP 条目名合法且位于允许的前缀目录内（写入侧严格模式）。

    - 拒绝绝对路径、反斜杠、`..` 上跳段
    - 必须以 allowed_prefixes 之一开头（如 'db/'、'files/case_results/'）
    返回规范化的 posix 相对路径，非法时抛 ValueError。
    """
    normalized = _normalize_zip_entry_name(name)
    for prefix in allowed_prefixes:
        prefix_norm = posixpath.normpath(prefix)
        if normalized == prefix_norm or normalized.startswith(prefix_norm + '/'):
            return normalized
    raise ValueError(f'ZIP 条目不在允许目录内: {name!r}')


def match_zip_entry_name(name: str, allowed_prefixes: Iterable[str]) -> 'str | None':
    """读取侧条目匹配：先做防 zip-slip 校验（非法即抛），再匹配前缀目录。

    不属于任何前缀的合法条目（如根目录 manifest.json）返回 None，由调用方跳过。
    """
    normalized = _normalize_zip_entry_name(name)
    for prefix in allowed_prefixes:
        prefix_norm = posixpath.normpath(prefix)
        if normalized == prefix_norm or normalized.startswith(prefix_norm + '/'):
            return normalized
    return None


def safe_storage_key(key: str) -> str:
    """校验存储对象 key（相对路径，单段不含 ..）。非法时抛 ValueError。"""
    if not key or key.startswith('/') or '\\' in key:
        raise ValueError(f'非法存储 key: {key!r}')
    segments = key.split('/')
    if any(seg in ('', '.', '..') for seg in segments):
        raise ValueError(f'非法存储 key: {key!r}')
    return key


def remap_task_id_in_key(key: str, new_task_id: int) -> str:
    """把存储 key 的首段（task_id）替换为新 id。

    result 文件 key 形如 {task_id}/{case_id}/{device_sn}/{filename}（result_data_store 约定）。
    """
    safe_storage_key(key)
    segments = key.split('/')
    segments[0] = str(new_task_id)
    return '/'.join(segments)


def parse_storage_path(path: str) -> Tuple[str, str]:
    """解析 storage 路径为 (category, key)。

    支持 oss://{category}/{key}、local://{category}/{key} 与无前缀历史格式
    （与 shared/infrastructure/storage.Storage._parse_path 语义一致，独立实现避免依赖单例）。
    """
    if not path:
        return '', ''
    for scheme in ('oss://', 'local://'):
        if path.startswith(scheme):
            rest = path[len(scheme):]
            parts = rest.split('/', 1)
            return (parts[0] if parts else '', parts[1] if len(parts) > 1 else '')
    parts = path.split('/', 1)
    return (parts[0] if parts else '', parts[1] if len(parts) > 1 else '')
