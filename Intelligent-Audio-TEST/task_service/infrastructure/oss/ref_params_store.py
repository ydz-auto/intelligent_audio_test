# -*- coding: utf-8 -*-
"""用例参考参数（ref_params）存储适配 — INT-1645。

用例参考参数内容存文件、路径存 `test_cases.reference_params` 独立列
（`[{round_number, reference_params_path}]`）。历史数据里的路径来自 V9.7.10
单机部署，是宿主绝对路径（`D:\\00_static\\static\\ref_params\\<case_id>\\round_1.json`），
既不能直接 `open()`，`Storage._parse_path` 也会把它解析成
category=整串 / key=''。

本模块把读写端点共用的三件事集中到一处：
1. 路径归一化：历史 Windows 绝对路径 / 裸 key / 带 scheme 路径统一成
   `oss://ref_params/<key>`；
2. 轮次定位：`reference_params` 列优先、`config.rounds[]` 兜底，轮次键
   `round_number` / `roundNumber` 都认；
3. 读写统一走 `shared.infrastructure.storage`（docker 内不依赖宿主磁盘），
   并把「读取失败」与「内容为空数组」区分开——失败必须抛错，不能伪装成空列表。
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 参考参数存储类别（与 _apply_reference_params_to_config 的写入口径一致）
REF_PARAMS_BUCKET = 'ref_params'

_SCHEME_OSS = 'oss://'
_SCHEME_LOCAL = 'local://'

# 轮次键：snake_case 为库/前端落库口径，camelCase 为历史 config 口径
_ROUND_NUMBER_KEYS = ('round_number', 'roundNumber')
# 路径键：同上，独立列 snake_case，历史 config 两种都有
_REF_PATH_KEYS = ('reference_params_path', 'referenceParamsPath')


class RefParamsReadError(Exception):
    """参考参数对象读取失败（不存在 / 非法 JSON / 非数组）。"""


def to_round_number(value: Any) -> Optional[int]:
    """把轮次键值归一成 int；无法识别返回 None（数值字符串按 int 比较）。"""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    try:
        text = str(value).strip()
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return int(float(text))
    except (TypeError, ValueError):
        return None


def _round_number_of(mapping: Dict[str, Any]) -> Optional[int]:
    """取映射里的轮次号，snake_case 优先，camelCase 兜底。"""
    for key in _ROUND_NUMBER_KEYS:
        number = to_round_number(mapping.get(key))
        if number is not None:
            return number
    return None


def build_ref_params_path(case_id: str, round_number: int) -> str:
    """构建参考参数规范路径：oss://ref_params/<case_id>/round_<n>.json。"""
    return f'{_SCHEME_OSS}{REF_PARAMS_BUCKET}/{case_id}/round_{int(round_number)}.json'


def _looks_like_bare_key(path: str) -> bool:
    """无 scheme、无 bucket 的裸 key（<case_id>/round_N.json）。"""
    if not path or path.startswith('/') or ':' in path or '..' in path:
        return False
    return '/' in path


def normalize_ref_params_path(path: Any) -> str:
    """把参考参数路径归一成存储抽象可读的形态。

    规则（卡面 §四）：
    1. `oss://` / `local://` 前缀 → 原样；
    2. 含 `ref_params` 目录段（正反斜杠均可）→ `oss://ref_params/<该段之后的部分>`；
    3. 形如 `<case_id>/round_N.json`（无 scheme、无 bucket）→ `oss://ref_params/<path>`；
    4. 其它 → 原样返回（读失败时错误信息带原始路径）。

    空值返回空串，由调用方按「未生成参考参数」处理。
    """
    if not path or not isinstance(path, str):
        return ''
    raw = path.strip()
    if not raw:
        return ''
    if raw.startswith(_SCHEME_OSS) or raw.startswith(_SCHEME_LOCAL):
        return raw

    normalized = raw.replace('\\', '/')
    marker = f'/{REF_PARAMS_BUCKET}/'
    index = normalized.find(marker)
    if index >= 0:
        return f'{_SCHEME_OSS}{normalized[index + 1:]}'
    if normalized.startswith(f'{REF_PARAMS_BUCKET}/'):
        return f'{_SCHEME_OSS}{normalized}'
    if _looks_like_bare_key(normalized):
        return f'{_SCHEME_OSS}{REF_PARAMS_BUCKET}/{normalized}'
    return raw


def resolve_round_ref_path(test_case, round_number: int) -> Tuple[bool, Optional[str]]:
    """定位用例指定轮的参考参数路径。

    轮次存在性：`reference_params` 列或 `config.rounds[]` 任一登记即算存在。
    路径取值：独立列为准（真实落点），config.rounds[] 兜底。

    :return: (轮次是否存在, 路径或 None)
    """
    round_number = to_round_number(round_number)
    if round_number is None:
        return False, None

    exists = False
    column_path = ''
    entries = getattr(test_case, 'reference_params', None)
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict) or _round_number_of(entry) != round_number:
                continue
            exists = True
            if not column_path:
                column_path = _first_non_empty(entry, _REF_PATH_KEYS)

    config = getattr(test_case, 'config', None) or {}
    rounds = config.get('rounds', []) if isinstance(config, dict) else []
    config_path = ''
    for round_item in rounds or []:
        if not isinstance(round_item, dict) or _round_number_of(round_item) != round_number:
            continue
        exists = True
        if not config_path:
            config_path = _first_non_empty(round_item, _REF_PATH_KEYS)

    return exists, (column_path or config_path or None)


def _first_non_empty(mapping: Dict[str, Any], keys: Tuple[str, ...]) -> str:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ''


def upsert_round_ref_path(entries: Any, round_number: int,
                          stored_path: str) -> List[Dict[str, Any]]:
    """把该轮条目 upsert 进 reference_params 列（保留其它轮、按轮次升序）。

    只改独立列，不把路径写回 config.rounds（卡面 §六.4）。
    """
    round_number = to_round_number(round_number)
    result: List[Dict[str, Any]] = []
    replaced = False
    source = entries if isinstance(entries, list) else []
    for entry in source:
        if not isinstance(entry, dict):
            continue
        if _round_number_of(entry) == round_number:
            if replaced:
                # 历史重复条目：收敛成一条
                continue
            merged = dict(entry)
            merged['round_number'] = round_number
            merged['reference_params_path'] = stored_path
            result.append(merged)
            replaced = True
            continue
        result.append(dict(entry))
    if not replaced:
        result.append({
            'round_number': round_number,
            'reference_params_path': stored_path,
        })
    result.sort(key=lambda item: to_round_number(item.get('round_number')) or 0)
    return result


def _split_storage_path(path: str) -> Tuple[str, str, str]:
    """拆出 (scheme, category, key)，path 需已归一化。"""
    scheme = 'oss'
    rest = path
    if path.startswith(_SCHEME_OSS):
        rest = path[len(_SCHEME_OSS):]
    elif path.startswith(_SCHEME_LOCAL):
        scheme = 'local'
        rest = path[len(_SCHEME_LOCAL):]
    category, _, key = rest.partition('/')
    return scheme, category, key


def read_ref_params(path: str) -> List[Dict[str, Any]]:
    """读取参考参数内容。

    读取失败（对象不存在 / 非法 JSON / 非数组）抛 RefParamsReadError，
    由调用方回报 404 带路径——不得退化成「空列表」让前端误判为未生成。
    文件存在但内容为空数组时返回 `[]`。
    """
    from shared.infrastructure.storage import storage_load_bytes

    try:
        raw = storage_load_bytes(path)
    except Exception as exc:  # FileNotFoundError / OSS 异常 / 权限
        raise RefParamsReadError(f'{path}: {exc}') from exc

    if not raw:
        raise RefParamsReadError(f'{path}: 空文件')

    try:
        data = json.loads(raw.decode('utf-8'))
    except Exception as exc:
        raise RefParamsReadError(f'{path}: 内容不是合法 JSON ({exc})') from exc

    if not isinstance(data, list):
        raise RefParamsReadError(f'{path}: 内容不是参考参数数组')
    return data


def write_ref_params(path: str, params: List[Dict[str, Any]]) -> str:
    """写参考参数内容，返回实际写入的存储路径（oss:// 或本地降级 local://）。"""
    from shared.infrastructure.storage import storage

    _, category, key = _split_storage_path(path)
    payload = json.dumps(params, ensure_ascii=False, indent=2).encode('utf-8')
    return storage.save_bytes(payload, category, key,
                              content_type='application/json')
