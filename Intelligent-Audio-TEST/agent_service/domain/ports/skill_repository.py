# -*- coding: utf-8 -*-
"""Skill 仓储端口（domain 定义，infrastructure/skill 实现）。

只负责「把 ``skills/`` 下的文档装载成领域对象」，不做校验取舍、不做权限
过滤——那是 application/skill_registry 的职责。
"""
from abc import ABC, abstractmethod

from agent_service.domain.model.skill_scan import SkillScanResult


class SkillRepository(ABC):
    @abstractmethod
    def load_all(self) -> SkillScanResult:
        """扫描 Skill 根目录，返回装载结果与目录级问题。

        目录不存在 / 不可读 / 为空、``skills/<name>/`` 缺 ``SKILL.md`` 都不抛
        异常：分别以 ``SKILLS_ROOT_MISSING`` / ``SKILLS_ROOT_UNREADABLE`` /
        ``SKILLS_ROOT_EMPTY`` / ``SKILL_FILE_MISSING`` 原因码回报（INT-2506），
        由 application 层统一判定严重度、是否让启动失败。单个 Skill 的格式
        问题仍通过 ``Skill.load_error`` 上报。
        """


class SkillResourceStore(ABC):
    """自定义 Skill 资源存储端口（INT-2549 §4.4）。

    资源只走对象存储，表内仅存 key；``put`` 返回 key，``get`` 按 key 取回
    字节（导出 / run 回放用）。实现复用仓库唯一 OSS 客户端，不新起存储栈。
    """

    @abstractmethod
    def put(self, key: str, data: bytes,
            content_type: str = 'application/octet-stream') -> str:
        """写入资源，返回实际 key。"""

    @abstractmethod
    def get(self, key: str) -> bytes:
        """按 key 取回资源字节；不存在时抛 ``KeyError``。"""

    def delete(self, key: str) -> None:  # pragma: no cover - 默认无操作
        """可选清理钩子；对象存储实现可覆盖（保留期策略不在本卡）。"""


class NullSkillResourceStore(SkillResourceStore):
    """未配置对象存储时的兜底：写入即失败，绝不静默丢资源。"""

    def put(self, key: str, data: bytes,
            content_type: str = 'application/octet-stream') -> str:
        raise RuntimeError('未配置对象存储，无法保存 Skill 资源')

    def get(self, key: str) -> bytes:
        raise RuntimeError('未配置对象存储，无法读取 Skill 资源')


__all__ = ['NullSkillResourceStore', 'SkillRepository', 'SkillResourceStore']
