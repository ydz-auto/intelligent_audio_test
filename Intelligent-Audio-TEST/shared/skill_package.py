# -*- coding: utf-8 -*-
"""Skill zip 包的共享读写实现（INT-2549 §4.4「zip 单一口径」）。

唯一口径（与既有 ``GET /api/v1/agent/skill`` 一致，不出现双口径）：

- 包**根级**直接是 ``SKILL.md``（+ ``references/`` / ``scripts/`` /
  ``assets/``），不套外层目录、不改文件名，外部 Agent 可直接识别；
- 导入接受同一结构（agentskills.io 兼容）。

INT-2476 起 ``GET /api/v1/agent/skill`` 的平台下载包也按本口径生成：根级
``SKILL.md``（带 frontmatter）+ 资源子目录，MCP 配置模板落在
``assets/mcp.json``，与 ``GET /api/v1/agent/skills/{id}/export`` 的产物
**同结构**（成员集合一致、根级 ``SKILL.md``、资源只放
``references/ scripts/ assets/``），但**不承诺回导**（INT-2612 收窄）：
下载包预填的是下载时的服务地址（入口页默认取浏览器地址栏，常见内网 /
回环地址），导入侧按自定义包规则校验时会判 ``INTERNAL_ADDRESS`` 拒绝。
平台包 frontmatter 面向外部宿主（``allowed-tools`` / ``permissions``
为空），导入后是文档型 Skill、不参与内部工具收敛；内部复用平台 Skill 请走
「从内置 fork」（``POST /api/v1/agent/skills/{skill_id}/fork``）。
平台包的正文由 ``skills/platform-reference/``
生成（``build_skill_md`` + ``read_skill_directory`` 均在本模块，跨服务唯一
实现），不是第二套 zip 逻辑。

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
import os
import stat
import zipfile
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Tuple

import yaml

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


def build_skill_md(frontmatter: Mapping[str, Any], body: str) -> str:
    """frontmatter 字典 + 正文 → ``SKILL.md`` 原文（导入 / 导出 / 平台包同一口径）。

    INT-2476：从 ``agent_service.application.skill_service`` 抽到共享层 ——
    网关生成平台下载包与 agent_service 导出用户 Skill 必须用同一份写法，
    否则 frontmatter 缩进 / 字段顺序漂移会让「同一结构」变成两张皮。
    """
    data = dict(frontmatter or {})
    dumped = yaml.safe_dump(
        data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return f'---\n{dumped}---\n\n{body or ""}'


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


def _real_within(root_real: str, path: str) -> bool:
    """``path`` 解析（realpath）后是否仍在 ``root_real`` 之内。"""
    root_key = os.path.normcase(root_real).rstrip(os.sep)
    target_key = os.path.normcase(os.path.realpath(path))
    return target_key == root_key or target_key.startswith(root_key + os.sep)


def _ensure_real_within(root_real: str, path: str) -> None:
    """目录解析后越出 Skill 根目录即拒绝（软链 / Windows junction 同判）。"""
    if not _real_within(root_real, path):
        raise SkillPackageError(
            PackageIssueCode.SYMLINK_REJECTED,
            f'禁止链接目录（解析后越出 Skill 目录）：{path} -> '
            f'{os.path.realpath(path)}')


def read_skill_directory(directory: str,
                         *, limits: Optional[SkillPackageLimits] = None
                         ) -> SkillPackage:
    """读取 ``skills/<name>/`` 目录为 Skill 包内容（不落盘、不打包）。

    与 ``read_skill_package`` 互补：一个从目录读、一个从 zip 字节读，产出
    同一个 ``SkillPackage``。平台下载包（api_gateway）据此按 ``skills/``
    生成，避免在网关里再写一份目录遍历 / 路径校验。

    目录约定与导入同一口径：``SKILL.md`` 必需且位于根级；资源只允许在
    ``references/`` / ``scripts/`` / ``assets/`` 下。软链、越界路径、超限
    体积一律 ``SkillPackageError``（不静默跳过）。目录自身是软链 /
    Windows junction 的情形同样拒绝：按 realpath 包含性判定（顶层资源目录
    与递归子目录都查），不依赖 ``os.walk(followlinks=False)``。
    """
    limits = limits or SkillPackageLimits()
    root = os.path.abspath(str(directory or ''))
    if not directory or not os.path.isdir(root):
        raise SkillPackageError(
            PackageIssueCode.INVALID_PATH, f'Skill 目录不存在：{directory}')
    skill_path = os.path.join(root, SKILL_FILE_NAME)
    if not os.path.isfile(skill_path) or os.path.islink(skill_path):
        raise SkillPackageError(
            PackageIssueCode.SKILL_FILE_MISSING,
            f'Skill 目录缺少 {SKILL_FILE_NAME}：{root}')
    try:
        with open(skill_path, 'rb') as handle:
            raw_bytes = handle.read()
    except OSError as exc:
        raise SkillPackageError(
            PackageIssueCode.INVALID_PATH, f'读取 {SKILL_FILE_NAME} 失败：{exc}') from exc
    if len(raw_bytes) > limits.max_skill_bytes:
        raise SkillPackageError(
            PackageIssueCode.BODY_TOO_LARGE,
            f'{SKILL_FILE_NAME} {len(raw_bytes)} 字节，'
            f'超过上限 {limits.max_skill_bytes}')
    try:
        skill_md = raw_bytes.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise SkillPackageError(
            PackageIssueCode.BINARY_CONTENT,
            f'{SKILL_FILE_NAME} 不是 UTF-8 文本') from exc

    resources: Dict[str, bytes] = {}
    total = len(raw_bytes)
    real_root = os.path.realpath(root)
    for name in RESOURCE_DIRS:
        base = os.path.join(root, name)
        if not os.path.isdir(base):
            continue
        # 顶层资源目录自身是链接（软链 / Windows junction）时会被一路跟随：
        # ``os.walk(followlinks=False)`` 只约束递归子目录，不约束遍历起点，
        # 因此这里按 realpath 包含性显式拒绝（INT-2612 P2）。
        _ensure_real_within(real_root, base)
        for current, dirs, filenames in os.walk(base):
            dirs.sort()
            _ensure_real_within(real_root, current)
            for sub in dirs:
                _ensure_real_within(real_root, os.path.join(current, sub))
            for filename in sorted(filenames):
                full = os.path.join(current, filename)
                if os.path.islink(full):
                    raise SkillPackageError(
                        PackageIssueCode.SYMLINK_REJECTED,
                        f'禁止软链资源：{full}')
                rel = os.path.relpath(full, root).replace(os.sep, '/')
                path = normalize_entry_path(rel)
                if not path.startswith(RESOURCE_PREFIXES):
                    raise SkillPackageError(
                        PackageIssueCode.INVALID_PATH,
                        f'资源只允许放在 {" / ".join(RESOURCE_PREFIXES)} 下：{path}')
                size = os.path.getsize(full)
                if size > limits.max_resource_bytes:
                    raise SkillPackageError(
                        PackageIssueCode.RESOURCE_TOO_LARGE,
                        f'资源 {path} {size} 字节，'
                        f'超过单资源上限 {limits.max_resource_bytes}')
                with open(full, 'rb') as handle:
                    resources[path] = handle.read()
                total += size
    if len(resources) + 1 > limits.max_entries:
        raise SkillPackageError(
            PackageIssueCode.TOO_MANY_ENTRIES,
            f'Skill 目录条目 {len(resources) + 1} 个，'
            f'超过上限 {limits.max_entries}')
    if total > limits.max_total_bytes:
        raise SkillPackageError(
            PackageIssueCode.PACKAGE_TOO_LARGE,
            f'Skill 目录合计 {total} 字节，超过上限 {limits.max_total_bytes}')
    return SkillPackage(skill_md=skill_md, resources=resources)


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
    'SkillPackageLimits', 'build_skill_md', 'build_skill_package', 'build_zip',
    'ensure_upload_size', 'normalize_entry_path', 'read_skill_directory',
    'read_skill_package', 'split_frontmatter',
]
