# -*- coding: utf-8 -*-
"""原始报文对象（raw payload）在离线搬运包里的规划（纯函数，不连库 / 不碰存储）

包内路径 = 存储 key：`raw/{resp|req}/{sha[:2]}/{sha}.json.gz`（INT-1807 / C1 口径，
实现在 shared/utils/raw_payload.py）。内容寻址意味着：

- 同一份报文在许多维度行上重复出现（实测 51,857 行 → 12,656 个对象），
  包内**同对象只打一次**，行上仍各自带同一个 uri；
- key 与 test_result_id 无关 → 导入侧**免 id_remapper 改写**，这正是选内容寻址
  而不是「路径寻址」的主因（换库 / 换 id 也不会让对象身份漂移）。

本模块只做「行 → 对象引用集合」与「行指针写回」的纯计算，读写存储在
`task_service/infrastructure/transfer/raw_payload_store.py`。
"""
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from shared.utils.raw_payload import (
    RAW_CONTENT_TYPE,
    RAW_PAYLOAD_SPECS,
    RawPayloadSpec,
    object_key,
    sha_from_uri,
)


@dataclass(frozen=True)
class RawObjectRef:
    """包内应携带的一个原始报文对象（按内容寻址去重后）"""
    kind: str
    sha256: str
    key: str          # 存储 key = 包内相对路径（相对 files/raw/）
    uri: str          # 源端存储路径（导出时按它读对象）


def row_object_key(row: dict, spec: RawPayloadSpec) -> Tuple[Optional[str], Optional[str]]:
    """取行上引用对象的 (key, sha256)。

    sha256 优先用摘要列；缺失时从 uri 反推（C1 之前的行可能只有 uri），
    两者都没有但 uri 存在 → 返回 (None, None) 由调用方决定是硬错误还是降级。
    """
    uri = row.get(spec.uri_column)
    sha = str(row.get(spec.sha256_column) or '').strip().lower() or None
    if not sha and uri:
        sha = sha_from_uri(str(uri))
    if not sha:
        return None, None
    try:
        return object_key(spec.kind, sha), sha
    except ValueError:
        return None, None


def collect_raw_object_refs(rows: Iterable[dict]) -> Tuple[List[RawObjectRef], List[str]]:
    """收集包内应携带的对象引用，按 (kind, sha) 去重（内容寻址天然去重）。

    Returns:
        (refs, errors)：errors 非空表示有行引用了无法定位的对象（导出侧硬错误，
        否则搬过去的行会指向包内不存在的对象 = 对端一库悬空指针）。
    """
    refs: Dict[str, RawObjectRef] = {}
    errors: List[str] = []
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        for spec in RAW_PAYLOAD_SPECS:
            uri = row.get(spec.uri_column)
            if not uri:
                continue
            key, sha = row_object_key(row, spec)
            if not key:
                errors.append(
                    f'维度行 id={row.get("id")!r} 的 {spec.uri_column} 无法解析出内容寻址 key: {uri!r}')
                continue
            if key not in refs:
                refs[key] = RawObjectRef(kind=spec.kind, sha256=sha, key=key, uri=str(uri))
    return list(refs.values()), errors


def raw_pointer_columns(spec: RawPayloadSpec, uri: str, sha256: str,
                        size: int, created_at: str) -> Dict[str, object]:
    """回写行的五个指针列（uri-only：内联 JSON 列由调用方置空）。"""
    return {
        spec.uri_column: uri,
        spec.sha256_column: sha256,
        spec.bytes_column: int(size),
        spec.content_type_column: RAW_CONTENT_TYPE,
        spec.created_at_column: created_at,
    }


def strip_raw_pointer_columns(spec: RawPayloadSpec) -> Dict[str, object]:
    """把五个指针列清空（对象不可达时不让行留下悬空指针）。"""
    return {
        spec.uri_column: None,
        spec.sha256_column: None,
        spec.bytes_column: None,
        spec.content_type_column: None,
        spec.created_at_column: None,
    }
