# -*- coding: utf-8 -*-
"""记忆文件树路径构造与守卫（INT-2490，§8.6.1）。

所有路径都由 **服务端身份** 构造：``tenants/<tenant_id>/users/<owner_id>/``。
模型输入里没有任何路径字段；唯一可能进路径的用户输入是 ``project_id`` 与
``approval_id``，二者都过 ``safe_component``：

- 拒绝 ``..`` / ``.`` / 绝对路径 / ``~`` / 盘符 / 分隔符 / 空白；
- 拒绝任何已存在的软链 / 符号链接组件（写入与读取都查）；
- 最终路径 ``resolve()`` 后必须仍在根目录内（兜底 junction / 挂载点逃逸）。
"""
import os
import re
from pathlib import Path
from typing import Iterable, Optional

from agent_service.domain.exceptions import MemoryPathRejected
from agent_service.domain.model.memory import (
    USER_PROFILE_FILE, USER_PROFILE_HEADER,
)

# 组件白名单：字母数字开头，其后允许字母数字与 . _ -，总长 ≤ 64
_SAFE_COMPONENT = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')

TENANTS_DIR = 'tenants'
USERS_DIR = 'users'
PROJECTS_DIR = 'projects'
SESSIONS_DIR = 'sessions'
PROPOSALS_DIR = '.proposals'
AUDIT_DIR = '.audit'


def safe_component(value: object, label: str) -> str:
    """校验并返回一个安全路径组件；非法即抛 ``MemoryPathRejected``。"""
    if value is None:
        raise MemoryPathRejected(f'{label} 不能为空')
    text = value if isinstance(value, str) else str(value)
    if text != text.strip():
        raise MemoryPathRejected(f'{label} 不能包含首尾空白')
    if not text:
        raise MemoryPathRejected(f'{label} 不能为空')
    if text in ('.', '..'):
        raise MemoryPathRejected(f'{label} 不能是 {text}')
    if text.startswith(('~', '/', '\\')):
        raise MemoryPathRejected(f'{label} 不能是绝对路径或 ~ 开头')
    if len(text) > 1 and text[1] == ':':
        raise MemoryPathRejected(f'{label} 不能包含盘符')
    if not _SAFE_COMPONENT.match(text):
        raise MemoryPathRejected(
            f'{label} 含非法字符（只允许字母数字 . _ -，且不得含路径分隔符）')
    return text


def _is_link(path: Path) -> bool:
    """软链 / Windows junction / 其它 reparse point 统一判定。

    ``Path.is_symlink()`` 对 Windows junction 返回 False（目录联接不是符号
    链接），只查它会让 ``mklink /J`` 穿越漏网；因此补 ``os.path.isjunction``
    （Python 3.12+）与 reparse 标记（3.11 可用）。
    """
    try:
        if path.is_symlink():
            return True
    except OSError:  # pragma: no cover
        return False
    isjunction = getattr(os.path, 'isjunction', None)
    if isjunction is not None:
        try:
            if isjunction(path):
                return True
        except OSError:  # pragma: no cover
            return False
    try:
        info = os.lstat(path)
    except OSError:
        return False
    return bool(getattr(info, 'st_reparse_tag', 0))


def safe_owner_id(value: object) -> int:
    if isinstance(value, bool):
        raise MemoryPathRejected('owner_id 必须是整数')
    try:
        owner = int(value)
    except (TypeError, ValueError):
        raise MemoryPathRejected('owner_id 必须是整数')
    if owner < 0:
        raise MemoryPathRejected('owner_id 不能为负数')
    return owner


class MemoryPaths:
    """按根目录构造 tenant / owner 隔离路径。"""

    def __init__(self, root: Path, *, skills_root: Optional[Path] = None):
        self.root = Path(root)
        self.skills_root = Path(skills_root) if skills_root else None

    # ------------------------------------------------------------ 基本路径

    def tenant_dir(self, tenant_id: str) -> Path:
        tenant = safe_component(tenant_id, 'tenant_id')
        return self.root / TENANTS_DIR / tenant

    def user_root(self, tenant_id: str, owner_id: int) -> Path:
        owner = safe_owner_id(owner_id)
        path = self.tenant_dir(tenant_id) / USERS_DIR / str(owner)
        # 每次取用户根都做一次软链 / junction 链检查：租户目录被替换成链接时
        # 后面所有读写都会逃逸到根目录外。
        self._assert_chain_from_root(path)
        self._reject_symlink(path)
        return path

    def proposal_root(self, tenant_id: str, owner_id: int) -> Path:
        owner = safe_owner_id(owner_id)
        tenant = safe_component(tenant_id, 'tenant_id')
        path = self.root / PROPOSALS_DIR / tenant / str(owner)
        self._assert_chain_from_root(path)
        return path

    def audit_file(self, tenant_id: str) -> Path:
        tenant = safe_component(tenant_id, 'tenant_id')
        return self.root / AUDIT_DIR / f'{tenant}.jsonl'

    # ------------------------------------------------------------ 目录初始化

    def ensure_user_tree(self, tenant_id: str, owner_id: int) -> Path:
        """初始化用户目录：``user_profile.md`` / ``projects/`` / ``sessions/``。

        ``projects/<project>/project_memory.md`` 与 ``<date>/topics.md`` 在
        首次写入时创建；``sessions/`` 只建目录（会话正文属 INT-2454 的
        context snapshot，本卡不与它双写）。
        """
        user_root = self.user_root(tenant_id, owner_id)
        for path in (user_root, user_root / PROJECTS_DIR,
                     user_root / SESSIONS_DIR):
            self._mkdir_guarded(path)
        profile = user_root / USER_PROFILE_FILE
        if not profile.exists():
            self._write_guarded(
                profile, f'{USER_PROFILE_HEADER}\n', append=False)
        return user_root

    # ------------------------------------------------------------ 守卫

    def resolve_under(self, base: Path, *components: str,
                      allow_missing: bool = True) -> Path:
        """在 ``base`` 下解析组件路径：拒绝穿越、软链与越界。"""
        base_path = Path(base)
        for component in components:
            safe_component(component, 'path')
        target = base_path.joinpath(*components)
        self._assert_no_symlink(base_path, components)
        resolved_base = self._resolve(base_path)
        resolved_target = self._resolve(target)
        if resolved_target != resolved_base:
            try:
                resolved_target.relative_to(resolved_base)
            except ValueError:
                raise MemoryPathRejected('路径越界：目标不在记忆根目录内')
        if not allow_missing and not resolved_target.exists():
            raise MemoryPathRejected('目标文件不存在')
        return target

    def _assert_no_symlink(self, base: Path, components: Iterable[str]) -> None:
        # 从记忆根逐级检查到 base：租户 / owner 目录被替换成软链或 junction
        # 时，单查 base 自身（is_symlink 对 junction 为 False）会漏掉逃逸。
        self._assert_chain_from_root(base)
        current = base
        self._reject_symlink(current)
        for component in components:
            current = current / component
            self._reject_symlink(current)

    def _assert_chain_from_root(self, path: Path) -> None:
        try:
            relative = Path(path).relative_to(self.root)
        except ValueError:
            # 不在记忆根下（如 skills 根）：只查自身，由根目录部署保证
            return
        current = self.root
        for part in relative.parts:
            current = current / part
            self._reject_symlink(current)

    @staticmethod
    def _reject_symlink(path: Path) -> None:
        try:
            if _is_link(path):
                raise MemoryPathRejected(f'拒绝软链路径：{path.name}')
        except OSError as exc:  # pragma: no cover - 文件系统异常按拒绝处理
            raise MemoryPathRejected(f'路径不可信：{exc}')

    @staticmethod
    def _resolve(path: Path) -> Path:
        try:
            return path.resolve()
        except OSError as exc:  # pragma: no cover
            raise MemoryPathRejected(f'路径不可解析：{exc}')

    # ------------------------------------------------------------ 读写（守卫后）

    def _mkdir_guarded(self, path: Path) -> None:
        self._reject_symlink(path)
        path.mkdir(parents=True, exist_ok=True)

    def read_text_guarded(self, base: Path, *components: str) -> Optional[str]:
        target = self.resolve_under(base, *components, allow_missing=True)
        if not target.exists():
            return None
        if not target.is_file():
            raise MemoryPathRejected('目标不是普通文件')
        return target.read_text(encoding='utf-8', errors='replace')

    def _write_guarded(self, target: Path, content: str, *,
                       append: bool) -> None:
        self._reject_symlink(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        if append:
            with open(target, 'a', encoding='utf-8', newline='\n') as handle:
                handle.write(content)
        else:
            # 原子替换：避免半截文件被下一次读取当成合法记忆
            tmp = target.with_name(f'.{target.name}.tmp')
            tmp.write_text(content, encoding='utf-8', newline='\n')
            os.replace(str(tmp), str(target))

    def write_text_guarded(self, base: Path, components: Iterable[str],
                           content: str) -> Path:
        parts = list(components)
        target = self.resolve_under(base, *parts)
        self._write_guarded(target, content, append=False)
        return target

    def append_text_guarded(self, base: Path, components: Iterable[str],
                            content: str) -> Path:
        parts = list(components)
        target = self.resolve_under(base, *parts)
        self._write_guarded(target, content, append=True)
        return target


__all__ = [
    'AUDIT_DIR', 'MemoryPaths', 'PROJECTS_DIR', 'PROPOSALS_DIR',
    'SESSIONS_DIR', 'TENANTS_DIR', 'USERS_DIR', 'safe_component',
    'safe_owner_id',
]
