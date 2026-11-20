# -*- coding: utf-8 -*-
"""读取平台 Skill 目录里的资源文本（INT-2549 fork 用）。

平台 ``skills/`` 是只读挂载，资源没有进对象存储；fork 出本人草稿时要把
``references/`` / ``scripts/`` / ``assets/`` 的文本一起带过去，否则正文里
引用的资料在草稿里断裂。二进制 / 超大文件跳过（自定义 Skill 的资源口径本就
只允许文本与体积上限）。
"""
import logging
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

MAX_RESOURCE_BYTES = 512 * 1024


def load_platform_resources(skill) -> Dict[str, str]:
    root = Path(getattr(skill, 'path', '') or '')
    if not root.is_dir():
        return {}
    resources: Dict[str, str] = {}
    for rel in (*skill.references, *skill.scripts, *skill.assets):
        path = root / rel
        try:
            if not path.is_file() or path.stat().st_size > MAX_RESOURCE_BYTES:
                continue
            data = path.read_bytes()
        except OSError:
            logger.warning('读取平台 Skill 资源失败：%s', path)
            continue
        if b'\x00' in data:
            continue
        try:
            resources[rel.replace('\\', '/')] = data.decode('utf-8')
        except UnicodeDecodeError:
            continue
    return resources


__all__ = ['load_platform_resources']
