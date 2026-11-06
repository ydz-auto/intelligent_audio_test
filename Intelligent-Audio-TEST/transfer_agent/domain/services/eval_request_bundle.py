# -*- coding: utf-8 -*-
"""EVAL_REQUEST 传输包协议读取（transfer_agent 出站投递腿，设计文档 §4.2.1/§4.2.2 步骤⑤）。

EVAL_REQUEST zip 包格式由发起侧（evaluation_service ACL）按跨服务契约打包：
  request.json  — 清单（transfer_id / form_fields / eval_params / src_zone / dst_zone / files 元数据）
  files/{name}  — 文件部件原始字节
本模块为接收侧（T-B 出站投递）的协议读取器，仅依赖 zip/json 标准库，
不 import 发起侧代码（跨服务契约，无跨服务 import）。
"""
from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field
from typing import Dict

from transfer_agent.domain.errors import InvalidPackageFieldError

_MANIFEST_NAME = 'request.json'
_FILES_PREFIX = 'files/'


@dataclass
class EvalRequestFile:
    """EVAL_REQUEST 包内文件部件。"""
    name: str
    filename: str
    content: bytes
    content_type: str = 'application/octet-stream'


@dataclass
class EvalRequestBundle:
    """EVAL_REQUEST 包读取结果（出站投递按第三方契约组装请求的输入）。"""
    transfer_id: str
    form_fields: Dict = field(default_factory=dict)
    eval_params: Dict = field(default_factory=dict)
    files: Dict[str, EvalRequestFile] = field(default_factory=dict)


def parse_eval_request_bundle(data: bytes) -> EvalRequestBundle:
    """解析 EVAL_REQUEST zip 包字节（损坏包/缺清单 fail-closed 拒绝）。"""
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise InvalidPackageFieldError(f'EVAL_REQUEST 包不是合法 zip: {e}') from e
    with zf:
        try:
            manifest = json.loads(zf.read(_MANIFEST_NAME).decode('utf-8'))
        except KeyError as e:
            raise InvalidPackageFieldError(f'EVAL_REQUEST 包缺少 {_MANIFEST_NAME} 清单') from e
        except (ValueError, UnicodeDecodeError) as e:
            raise InvalidPackageFieldError(f'EVAL_REQUEST 清单解析失败: {e}') from e
        if not isinstance(manifest, dict):
            raise InvalidPackageFieldError('EVAL_REQUEST 清单须为 JSON 对象')
        files: Dict[str, EvalRequestFile] = {}
        for name, meta in (manifest.get('files') or {}).items():
            try:
                content = zf.read(f'{_FILES_PREFIX}{name}')
            except KeyError as e:
                raise InvalidPackageFieldError(f'EVAL_REQUEST 包缺少文件部件: {name}') from e
            files[name] = EvalRequestFile(
                name=str(name),
                filename=str(meta.get('filename') or name),
                content=content,
                content_type=str(meta.get('content_type') or 'application/octet-stream'),
            )
    transfer_id = str(manifest.get('transfer_id') or '')
    if not transfer_id:
        raise InvalidPackageFieldError('EVAL_REQUEST 清单缺少 transfer_id')
    return EvalRequestBundle(
        transfer_id=transfer_id,
        form_fields=dict(manifest.get('form_fields') or {}),
        eval_params=dict(manifest.get('eval_params') or {}),
        files=files,
    )
