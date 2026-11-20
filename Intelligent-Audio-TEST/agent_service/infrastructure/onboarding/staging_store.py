# -*- coding: utf-8 -*-
"""onboarding 交付包的 staging 落盘（INT-2491）。

边界（卡面「不直接写生产目录、不自动注册」）：

- 只写 ``AGENT_ONBOARDING_STAGING_DIR`` 下的 ``onboarding-<hash>/`` 目录，
  不碰生产驱动 / 适配器注册表；
- 路径只接受包内相对路径，拒绝绝对路径 / ``..`` / 反斜杠，防止逃逸；
- 文件数与总字节有上限，超出即拒绝，不落半包；
- 同一 ``driver_ref`` 重复写入是幂等的（先写临时目录再整体替换）。

``task_run(mode=SMOKE)`` 按 ``driver_ref`` 从本存储读取包，不依赖进程内存，
因此跨 turn / 重启后仍可复验（只要 staging 目录还在）。
"""
from __future__ import annotations

import os
import re
import shutil
import tempfile
from typing import Dict, Mapping, Optional

from agent_service.domain.ports.onboarding_staging import (
    OnboardingStagingPort, StagingPackageNotFound,
)

_REF_PATTERN = re.compile(r'^onboarding-[0-9a-f]{16,64}$')
_MAX_FILES = 64
_MAX_BYTES = 2 * 1024 * 1024


def default_staging_dir() -> str:
    return os.path.join(tempfile.gettempdir(), 'agent-onboarding-staging')


def _safe_relative(path: str) -> str:
    normalized = path.replace('\\', '/').strip()
    if not normalized or normalized.startswith('/'):
        raise ValueError(f'交付包路径不合法：{path!r}')
    parts = normalized.split('/')
    if any(part in ('', '.', '..') for part in parts):
        raise ValueError(f'交付包路径不合法：{path!r}')
    if ':' in parts[0]:
        raise ValueError(f'交付包路径不合法：{path!r}')
    return '/'.join(parts)


class OnboardingStagingStore(OnboardingStagingPort):
    def __init__(self, root: Optional[str] = None, *,
                 max_files: int = _MAX_FILES,
                 max_bytes: int = _MAX_BYTES):
        self._root = os.path.abspath(root or default_staging_dir())
        self._max_files = int(max_files)
        self._max_bytes = int(max_bytes)

    @property
    def root(self) -> str:
        return self._root

    def path_for(self, driver_ref: str) -> str:
        ref = str(driver_ref or '').strip()
        if not _REF_PATTERN.match(ref):
            raise ValueError(f'driver_ref 不合法：{driver_ref!r}')
        return os.path.join(self._root, ref)

    def save(self, driver_ref: str, files: Mapping[str, str]) -> str:
        """原子写入交付包，返回 staging 目录绝对路径。"""
        ref = str(driver_ref or '').strip()
        target = self.path_for(ref)
        if not files:
            raise ValueError('交付包为空，拒绝写入 staging')
        if len(files) > self._max_files:
            raise ValueError(f'交付包文件数超过上限 {self._max_files}')
        total = sum(len(str(content).encode('utf-8'))
                    for content in files.values())
        if total > self._max_bytes:
            raise ValueError(f'交付包超过 staging 大小上限 {self._max_bytes} 字节')
        os.makedirs(self._root, exist_ok=True)
        staging = tempfile.mkdtemp(prefix=f'.{ref}.', dir=self._root)
        try:
            for path, content in files.items():
                relative = _safe_relative(path)
                destination = os.path.join(staging, *relative.split('/'))
                parent = os.path.dirname(destination)
                if parent:
                    os.makedirs(parent, exist_ok=True)
                with open(destination, 'w', encoding='utf-8', newline='\n') as fh:
                    fh.write(str(content))
            if os.path.isdir(target):
                shutil.rmtree(target, ignore_errors=True)
            os.replace(staging, target)
        except Exception:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return target

    def load(self, driver_ref: str) -> Dict[str, str]:
        """读取交付包；不存在时抛 ``StagingPackageNotFound``。"""
        target = self.path_for(driver_ref)
        if not os.path.isdir(target):
            raise StagingPackageNotFound(
                f'staging 中不存在接入包 {driver_ref}；请先经审批执行 '
                'driver_propose 生成，或确认 staging 目录未被清理。')
        files: Dict[str, str] = {}
        total = 0
        for root, _dirs, names in os.walk(target):
            for name in names:
                absolute = os.path.join(root, name)
                relative = os.path.relpath(absolute, target).replace('\\', '/')
                relative = _safe_relative(relative)
                with open(absolute, encoding='utf-8') as fh:
                    content = fh.read()
                total += len(content.encode('utf-8'))
                if total > self._max_bytes:
                    raise ValueError(
                        f'staging 接入包超过读取上限 {self._max_bytes} 字节')
                files[relative] = content
        if not files:
            raise StagingPackageNotFound(f'staging 接入包为空：{driver_ref}')
        return files

    def exists(self, driver_ref: str) -> bool:
        try:
            return os.path.isdir(self.path_for(driver_ref))
        except ValueError:
            return False


__all__ = [
    'OnboardingStagingStore', 'StagingPackageNotFound', 'default_staging_dir',
]
