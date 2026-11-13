# -*- coding: utf-8 -*-
"""Skill zip 包的共享读写实现（INT-2549 §4.4「zip 单一口径」）。

唯一口径（与既有 ``GET /api/v1/agent/skill`` 一致，不出现双口径）：

- 包**根级**直接是 ``SKILL.md``（+ ``references/`` / ``scripts/`` /
  ``assets/``），不套外层目录、不改文件名，外部 Agent 可直接识别；
- 导入接受同一结构（agentskills.io 兼容）。

**平台下载包的例外（当前不支持导入，归 INT-2476）**：``GET /api/v1/agent/skill``
的产物额外带 ``mcp.json``（网关 MCP 配置模板），且其 ``SKILL.md`` 没有
frontmatter，不是可落库的用户 Skill。因此平台包虽然复用本模块的同一打包
实现与根级口径，但**当前不能**经 ``POST /api/v1/agent/skills/import`` 导入
（``mcp.json`` 会以 ``INVALID_PATH`` 拒绝）。平台包生成对齐导入结构由
INT-2476 负责；在那之前不要按「同一结构」推论平台包可导入。

安全边界（zip 导入是攻击面）：解压前先按目录条目累加体积、限制条目数与
压缩比（防 zip bomb），解压后再次校验路径与类型；禁止绝对路径、``..``、
反斜杠路径、软链。本模块不落盘，调用方只拿到内存里的字节 —— 绝不按包内
路径写任意磁盘位置。

分层：本模块是**共享层**（api_gateway / agent_service 都可用），不依赖任何
服务包。``code`` 用共享词表（``PackageIssueCode``），agent_service 侧以
``SkillIssueCode`` 承接，二者的取值一致性由单测钉死（不各写一套）。
"""
from __future__ import annotations

import io
import stat
import zipfile
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Mapping, Optional, Tuple

# 包结构常量（与 ``agent_service.domain.model.skill`` 的目录契约一致，
# 一致性由 tests/agent_skill 断言；两处都指向同一个物理文件名）
SKILL_FILE_NAME = 'SKILL.md'
RESOURCE_DIRS: Tuple[str, ...] = ('references', 'scripts', 'assets')
RESOURCE_PREFIXES: Tuple[str, ...] = tuple(f'{name}/' for name in RESOURCE_DIRS)
FRONTMATTER_DELIMITER = '---'

# 上传（压缩前）体积上限：网关与 agent_service 接口层在读入内存前按同一
# 口径拒绝（默认 10 MB；可用 ``AGENT_SKILL_MAX_UPLOAD_BYTES`` 调整）。
DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024

# 导入接口对外错误码（网关不依赖 agent_service 包，值必须与
# ``agent_service.domain.enums.SkillErrorCode.SKILL_IMPORT_INVALID`` 一致，
# 由单测钉死；网关超限 413 与接口层同码）。
SKILL_IMPORT_INVALID_CODE = 'SKILL_IMPORT_INVALID'


class PackageIssueCode(str, Enum):
    """包级问题码（共享词表；agent_service 的 ``SkillIssueCode`` 同名承接）。"""

    INVALID_PATH = 'INVALID_PATH'
    SYMLINK_REJECTED = 'SYMLINK_REJECTED'
    TOO_MANY_ENTRIES = 'TOO_MANY_ENTRIES'
    PACKAGE_TOO_LARGE = 'PACKAGE_TOO_LARGE'
    RESOURCE_TOO_LARGE = 'RESOURCE_TOO_LARGE'
    BODY_TOO_LARGE = 'BODY_TOO_LARGE'
    BINARY_CONTENT = 'BINARY_CONTENT'
    SKILL_FILE_MISSING = 'SKILL_FILE_MISSING'


class SkillPackageError(ValueError):
    """包结构 / 安全校验失败（``code`` 为 ``PackageIssueCode``）。"""

    def __init__(self, code: PackageIssueCode, message: str):
        self.code = code
        self.message = message
        super().__init__(message)


@dataclass(frozen=True)
class SkillPackageLimits:
    """包体限制（配置化；默认值与卡面 §4.4 逐项校验一致）。"""

    max_entries: int = 200
    max_skill_bytes: int = 64 * 1024
    max_resource_bytes: int = 512 * 1024
    max_total_bytes: int = 5 * 1024 * 1024
    max_compression_ratio: int = 100
    # 压缩前（上传原始字节）上限：在读入内存 / 解析 multipart 之前判定
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES


def ensure_upload_size(size: int, *,
                       limits: Optional[SkillPackageLimits] = None) -> None:
    """上传体积校验（网关与接口层共用；读入内存前调用）。

    超过 ``max_upload_bytes`` 抛 ``PACKAGE_TOO_LARGE``：网关侧据此回 413、
    服务层据此回 413，不把整包先读进内存再判定。
    """
    limits = limits or SkillPackageLimits()
    if size > limits.max_upload_bytes:
        raise SkillPackageError(
            PackageIssueCode.PACKAGE_TOO_LARGE,
            f'上传包 {size} 字节，超过上限 {limits.max_upload_bytes} 字节')


@dataclass(frozen=True)
class SkillPackage:
    """解包结果：``SKILL.md`` 原文 + 资源（相对路径 → 字节）。"""

    skill_md: str
    resources: Mapping[str, bytes]

    @property
    def frontmatter_text(self) -> str:
        return split_frontmatter(self.skill_md)[0] or ''

    @property
    def body(self) -> str:
        return split_frontmatter(self.skill_md)[1]


def split_frontmatter(raw: str) -> Tuple[Optional[str], str]:
    """``---`` 分隔的 frontmatter 与正文（扫描与导入共用唯一实现）。"""
    lines = (raw or '').splitlines()
    if not lines or lines[0].strip() != FRONTMATTER_DELIMITER:
        return None, raw or ''
    for index in range(1, len(lines)):
        if lines[index].strip() == FRONTMATTER_DELIMITER:
            frontmatter = '\n'.join(lines[1:index])
            body = '\n'.join(lines[index + 1:]).lstrip('\n')
            return frontmatter, body
    return None, raw or ''


def normalize_entry_path(name: str) -> str:
    """包内条目路径归一 + 安全校验（返回 posix 相对路径）。"""
    raw = (name or '').replace('\\', '/').strip()
    if not raw or raw.endswith('/'):
        raise SkillPackageError(PackageIssueCode.INVALID_PATH,
                                f'包内条目路径为空或以 / 结尾：{name!r}')
    if raw.startswith('/') or ':' in raw.split('/')[0]:
        raise SkillPackageError(PackageIssueCode.INVALID_PATH,
                                f'禁止绝对路径：{name}')
    if any(part == '..' for part in raw.split('/')):
        raise SkillPackageError(PackageIssueCode.INVALID_PATH,
                                f'禁止 .. 路径：{name}')
    parts = [part for part in raw.split('/') if part not in ('', '.')]
    if not parts:
        raise SkillPackageError(PackageIssueCode.INVALID_PATH,
                                f'包内条目路径非法：{name!r}')
    return '/'.join(parts)


def _entry_is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return bool(mode) and stat.S_ISLNK(mode)


def build_zip(entries: Mapping[str, bytes],
              *, limits: Optional[SkillPackageLimits] = None) -> bytes:
    """按条目字典打 zip（路径统一校验，根级不套外层目录）。"""
    limits = limits or SkillPackageLimits()
    payloads: Dict[str, bytes] = {}
    total = 0
    for name, data in entries.items():
        path = normalize_entry_path(name)
        if path in payloads:
            raise SkillPackageError(PackageIssueCode.INVALID_PATH,
                                    f'包内条目重复：{path}')
        payload = data if isinstance(data, bytes) else str(data).encode('utf-8')
        payloads[path] = payload
        total += len(payload)
    if len(payloads) > limits.max_entries:
        raise SkillPackageError(
            PackageIssueCode.TOO_MANY_ENTRIES,
            f'包内条目 {len(payloads)} 个，超过上限 {limits.max_entries}')
    if total > limits.max_total_bytes:
        raise SkillPackageError(
            PackageIssueCode.PACKAGE_TOO_LARGE,
            f'整包 {total} 字节，超过上限 {limits.max_total_bytes}')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(payloads):
            archive.writestr(path, payloads[path])
    return buf.getvalue()


def build_skill_package(skill_md: str,
                        resources: Optional[Mapping[str, bytes]] = None,
                        *, limits: Optional[SkillPackageLimits] = None) -> bytes:
    """生成 Skill 包：根级 ``SKILL.md`` + 资源子目录。"""
    limits = limits or SkillPackageLimits()
    entries: Dict[str, bytes] = {
        SKILL_FILE_NAME: (skill_md or '').encode('utf-8')}
    entries.update(dict(resources or {}))
    return build_zip(entries, limits=limits)


def read_skill_package(data: bytes,
                       *, limits: Optional[SkillPackageLimits] = None
                       ) -> SkillPackage:
    """解析 Skill 包（不落盘），逐项做安全与体积校验。"""
    limits = limits or SkillPackageLimits()
    if not data:
        raise SkillPackageError(PackageIssueCode.INVALID_PATH, '包内容为空')
    ensure_upload_size(len(data), limits=limits)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise SkillPackageError(
            PackageIssueCode.INVALID_PATH, f'不是合法 zip 包：{exc}') from exc

    with archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if not infos:
            raise SkillPackageError(PackageIssueCode.INVALID_PATH,
                                    '包内没有任何文件')
        if len(infos) > limits.max_entries:
            raise SkillPackageError(
                PackageIssueCode.TOO_MANY_ENTRIES,
                f'包内条目 {len(infos)} 个，超过上限 {limits.max_entries}')
        total = sum(info.file_size for info in infos)
        if total > limits.max_total_bytes:
            raise SkillPackageError(
                PackageIssueCode.PACKAGE_TOO_LARGE,
                f'解压后合计 {total} 字节，超过上限 {limits.max_total_bytes}')
        ratio = total / max(len(data), 1)
        if ratio > limits.max_compression_ratio and total > 1024:
            raise SkillPackageError(
                PackageIssueCode.PACKAGE_TOO_LARGE,
                f'压缩比 {ratio:.0f}:1 超过上限 '
                f'{limits.max_compression_ratio}:1（疑似 zip bomb）')

        resources: Dict[str, bytes] = {}
        skill_md: Optional[str] = None
        for info in infos:
            if _entry_is_symlink(info):
                raise SkillPackageError(
                    PackageIssueCode.SYMLINK_REJECTED,
                    f'禁止软链条目：{info.filename}')
            path = normalize_entry_path(info.filename)
            if path == SKILL_FILE_NAME:
                if info.file_size > limits.max_skill_bytes:
                    raise SkillPackageError(
                        PackageIssueCode.BODY_TOO_LARGE,
                        f'{SKILL_FILE_NAME} {info.file_size} 字节，'
                        f'超过上限 {limits.max_skill_bytes}')
                raw = archive.read(info)
                try:
                    skill_md = raw.decode('utf-8-sig')
                except UnicodeDecodeError as exc:
                    raise SkillPackageError(
                        PackageIssueCode.BINARY_CONTENT,
                        f'{SKILL_FILE_NAME} 不是 UTF-8 文本') from exc
                continue
            if not path.startswith(RESOURCE_PREFIXES):
                raise SkillPackageError(
                    PackageIssueCode.INVALID_PATH,
                    f'根级只允许 {SKILL_FILE_NAME} 与 '
                    f'{" / ".join(RESOURCE_PREFIXES)}：{path}')
            if info.file_size > limits.max_resource_bytes:
                raise SkillPackageError(
                    PackageIssueCode.RESOURCE_TOO_LARGE,
                    f'资源 {path} {info.file_size} 字节，'
                    f'超过单资源上限 {limits.max_resource_bytes}')
            payload = archive.read(info)
            if b'\x00' in payload:
                raise SkillPackageError(
                    PackageIssueCode.BINARY_CONTENT,
                    f'资源 {path} 含可执行二进制内容')
            try:
                payload.decode('utf-8')
            except UnicodeDecodeError as exc:
                # 非 UTF-8 资源同样按二进制拒绝（不允许静默丢弃）
                raise SkillPackageError(
                    PackageIssueCode.BINARY_CONTENT,
                    f'资源 {path} 不是 UTF-8 文本') from exc
            resources[path] = payload
    if skill_md is None:
        raise SkillPackageError(
            PackageIssueCode.SKILL_FILE_MISSING,
            f'包根级缺少 {SKILL_FILE_NAME}')
    return SkillPackage(skill_md=skill_md, resources=resources)


__all__ = [
    'DEFAULT_MAX_UPLOAD_BYTES', 'FRONTMATTER_DELIMITER', 'PackageIssueCode',
    'RESOURCE_DIRS', 'RESOURCE_PREFIXES', 'SKILL_FILE_NAME',
    'SKILL_IMPORT_INVALID_CODE', 'SkillPackage', 'SkillPackageError',
    'SkillPackageLimits', 'build_skill_package', 'build_zip',
    'ensure_upload_size', 'normalize_entry_path', 'read_skill_package',
    'split_frontmatter',
]
