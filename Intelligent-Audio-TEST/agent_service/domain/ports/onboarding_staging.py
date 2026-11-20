# -*- coding: utf-8 -*-
"""onboarding staging 存储端口（INT-2491，domain 层零依赖）。

应用层只依赖本抽象；具体落盘在
``agent_service.infrastructure.onboarding.staging_store``。
"""
from __future__ import annotations

from typing import Dict, Mapping, Protocol, runtime_checkable


class StagingPackageNotFound(FileNotFoundError):
    """staging 中没有该 driver_ref。"""


@runtime_checkable
class OnboardingStagingPort(Protocol):
    @property
    def root(self) -> str:  # pragma: no cover - 端口声明
        ...

    def save(self, driver_ref: str, files: Mapping[str, str]) -> str:
        ...

    def load(self, driver_ref: str) -> Dict[str, str]:
        ...

    def exists(self, driver_ref: str) -> bool:
        ...


__all__ = ['OnboardingStagingPort', 'StagingPackageNotFound']
