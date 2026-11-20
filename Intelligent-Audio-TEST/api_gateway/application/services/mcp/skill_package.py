# -*- coding: utf-8 -*-
"""skill 包下载生成（INT-1150 / INT-2549 / INT-2476）。

``GET /api/v1/agent/skill`` 动态拼装 zip。INT-2476 起从「单静态模板」升级为
**按 ``skills/`` 生成**：

- 正文与 ``references/`` 取自 ``skills/platform-reference/``（与平台内置
  Agent 共用同一批 Skill 资产，「一套 Skill，两种宿主」）；
- 追加「外部 Agent 接入」与「只读能力」两节（后者按 ``shared/agent_tools``
  的工具注册表渲染，单一事实源，不手写、不出现暗能力）；
- ``assets/mcp.json`` 是 MCP 配置模板（base_url 注入）；
- 与 ``GET /api/v1/agent/skills/{id}/export`` **同结构**（成员集合一致、
  根级 ``SKILL.md`` + ``references/ scripts/ assets/``，不套外层目录），但
  **不承诺回导**（INT-2612 收窄）：包里预填的是下载时的服务地址（入口页
  默认取浏览器地址栏，常见内网 / 回环地址），回导时导入侧按自定义包规则
  校验，正文与 ``assets/mcp.json`` 会被 ``INTERNAL_ADDRESS`` 拒绝 —— 这是
  预期行为，不是缺陷。平台包 frontmatter 面向外部宿主（``allowed-tools`` /
  ``permissions`` 为空），导入后只是文档型 Skill、不参与内部工具收敛。
  内部复用平台 Skill 请走「从内置 fork」（``POST /api/v1/agent/skills/
  {skill_id}/fork``）。打包走 ``shared.skill_package.build_zip``，不在这里
  另写 zipfile 逻辑。

``api_gateway/skill_templates/`` 降级为**兜底模板**：skills 目录缺失 / 不可
读时仍能下载一个结构合法的包（不 500）。兜底包**不保证可导入**：静态模板
自带 ``Bearer 在此填入你的 Access Token`` 占位（命中 ``EMBEDDED_SECRET``），
且补齐两节后正文超过 500 行上限（``BODY_TOO_LONG``）；回退只保证下载可用、
结构合法。

``?base_url=`` 注入服务地址；无 base_url 时后端从 Origin / Host 头兜底。
下载需登录。
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Mapping, Optional, Tuple

import yaml

from shared.agent_tools import coverage, mcp_registry
from shared.skill_package import (
    SKILL_FILE_NAME, PackageIssueCode, SkillPackageError, build_skill_md,
    build_zip, read_skill_directory, split_frontmatter,
)

logger = logging.getLogger(__name__)

MCP_FILE_NAME = 'mcp.json'
# MCP 配置模板放在资源目录下：根级只允许 SKILL.md，mcp.json 放根级会被
# 导入按 INVALID_PATH 拒绝（与 INT-2549 的同一结构冲突）。
MCP_ASSET_PATH = f'assets/{MCP_FILE_NAME}'
TOOLS_REFERENCE_PATH = 'references/mcp-tools.md'

_TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              '..', '..', '..', 'skill_templates')

# 平台包正文来源（平台只读 Skill 目录）
PLATFORM_SKILL_NAME = 'platform-reference'
# 外部包自身的 Skill 名（不占用平台内置名，下载后可经导入落库）
PACKAGE_SKILL_NAME = 'intelligent-audio-test'
PACKAGE_OWNER = 'agent-platform'
PACKAGE_VERSION_FALLBACK = '1.0.0'
# Access Token 明文前缀（与 auth_service 的口径一致；文档里只写前缀）
ACCESS_TOKEN_PREFIX = 'at_'
MCP_ENDPOINT_PATH = '/api/v1/mcp'
BASE_URL_PLACEHOLDER = '{{BASE_URL}}'

_PACKAGE_DESCRIPTION = (
    '智能音频测试平台（Intelligent Audio Test）外部接入与只读能力速查：'
    'MCP 工具目录、REST 接口前缀、字段与枚举口径、权限码与 Access Token 鉴权。'
    '触发词：接入平台、MCP 怎么配、平台有哪些接口、字段叫什么、枚举取值、'
    '权限码是什么。不适用：具体业务执行流程（导入音频、创建任务、生成报告等）'
    '由对应业务 Skill 负责。')

ZIP_FILENAME = 'intelligent_audio_test_skill.zip'


# ========================================================================
# 目录 / 模板
# ========================================================================

def _skills_root() -> str:
    """平台 skills 根目录（部署由 ``AGENT_SKILLS_ROOT`` 指向只读挂载）。"""
    from api_gateway.config.config import Config
    return str(getattr(Config, 'SKILLS_ROOT', '') or '')


def _load_template(filename: str) -> Optional[str]:
    """读兜底模板；缺失返回 None（不阻断下载）。"""
    path = os.path.normpath(os.path.join(_TEMPLATES_DIR, filename))
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            return handle.read()
    except OSError:
        logger.warning('skill 兜底模板缺失：%s', path)
        return None


def _inject_base_url(template: str, base_url: str) -> str:
    """模板 {{BASE_URL}} 占位符注入。"""
    return template.replace(BASE_URL_PLACEHOLDER, base_url)


def resolve_base_url(request) -> str:
    """base_url 解析：?base_url= → Origin 头 → Host 头（X-Forwarded-Proto 兜底协议）。"""
    query = getattr(request, 'query_params', None)
    base_url = ''
    if query is not None:
        base_url = (query.get('base_url') or '').strip()
    if not base_url:
        origin = request.headers.get('Origin', '') if hasattr(request, 'headers') else ''
        if origin:
            base_url = origin.strip()
    if not base_url:
        host = request.headers.get('Host', '') if hasattr(request, 'headers') else ''
        if host:
            scheme = ('https' if request.headers.get('X-Forwarded-Proto', 'http')
                      == 'https' else 'http') if hasattr(request, 'headers') else 'http'
            base_url = f'{scheme}://{host.strip()}'
    return base_url.rstrip('/') if base_url else ''


# ========================================================================
# 按 shared/agent_tools 渲染能力说明（单一事实源）
# ========================================================================

def _readonly_tools() -> List[dict]:
    return [tool for tool in mcp_registry.TOOLS if coverage.is_read_only(tool)]


def _render_access_section(base_url: str, tool_total: int) -> str:
    """外部 Agent 接入说明（MCP / REST / Access Token）。"""
    return '\n'.join([
        '## 外部 Agent 接入（MCP / REST）',
        '',
        f'- **服务地址**：`{base_url}`',
        f'- **MCP 端点**：`{base_url}{MCP_ENDPOINT_PATH}`（JSON-RPC 2.0：'
        '`initialize` / `tools/list` / `tools/call`）；对外共 '
        f'{tool_total} 个工具，逐项见 `{TOOLS_REFERENCE_PATH}`。',
        f'- **REST 前缀**：`{base_url}/api/v1`（字段 snake_case）。',
        '- **鉴权**：`Authorization: Bearer <ACCESS_TOKEN>`。Access Token 明文'
        f'以 `{ACCESS_TOKEN_PREFIX}` 开头，仅创建时显示一次；空 scopes = 继承'
        '用户全部权限。',
        '- **生效权限 = 用户当前权限 ∩ token scopes**：scope 未覆盖某工具所需'
        '权限时，`tools/call` 返回越权错误（403 语义），不是静默降级。',
        f'- **MCP 配置模板**：`{MCP_ASSET_PATH}`（已预填本服务地址与鉴权头占位）。',
    ])


def _render_readonly_section() -> str:
    """只读能力说明（按域聚合；工具明细在 references/mcp-tools.md）。"""
    readonly = _readonly_tools()
    by_domain: Dict[str, List[dict]] = {}
    for tool in readonly:
        by_domain.setdefault(coverage.domain_of(tool['name']), []).append(tool)
    lines = [
        '## 只读能力（对外 MCP）',
        '',
        f'对外 MCP {len(mcp_registry.TOOLS)} 个工具中，只读 {len(readonly)} 个'
        '（HTTP `GET`；写动作即使声明读权限也不计入）。按域分布：',
        '',
        '| 域 | 只读工具数 | 权限码 |',
        '|---|---|---|',
    ]
    for domain in sorted(by_domain):
        tools = by_domain[domain]
        permissions = sorted({p for tool in tools for p in tool['permissions']})
        lines.append(
            f'| {domain} | {len(tools)} | '
            f'{", ".join(f"`{p}`" for p in permissions) or "（仅需登录）"} |')
    lines += [
        '',
        '写 / 破坏性工具同样在 `tools/list` 中可见，执行受目标接口的权限码'
        '（以及内部 Agent 的提案 + 审批链）约束；外部 MCP 不做意图收敛。',
    ]
    return '\n'.join(lines)


def _cell(text: Any) -> str:
    return str(text or '').replace('|', '\\|').replace('\n', ' ')


def _render_tools_reference() -> str:
    """完整对外工具目录（references/mcp-tools.md，生成物）。"""
    lines = [
        '# 对外 MCP 工具目录',
        '',
        f'> 由 `shared/agent_tools/mcp_registry.py` 渲染（{len(mcp_registry.TOOLS)}'
        ' 个工具，单一事实源）；与 `POST /api/v1/mcp` 的 `tools/list` 逐项一致，'
        '请勿手改。',
        '',
        '| 工具 | 方法 | 风险 | 权限 | 说明 |',
        '|---|---|---|---|---|',
    ]
    for tool in mcp_registry.TOOLS:
        risk = 'READ' if coverage.is_read_only(tool) else 'WRITE'
        permissions = ', '.join(f'`{p}`' for p in tool['permissions']) or '—'
        lines.append(
            f'| `{tool["name"]}` | {tool["method"]} | {risk} | {permissions} | '
            f'{_cell(tool["description"])} |')
    lines.append('')
    return '\n'.join(lines)


# ========================================================================
# 平台包拼装
# ========================================================================

def _load_platform_skill(skills_root: str) -> Tuple[Mapping[str, Any], str,
                                                    Dict[str, bytes]]:
    """读取 ``skills/platform-reference`` 的 frontmatter / 正文 / 资源。"""
    directory = os.path.join(skills_root, PLATFORM_SKILL_NAME)
    package = read_skill_directory(directory)
    frontmatter_text, body = split_frontmatter(package.skill_md)
    if frontmatter_text is None:
        raise SkillPackageError(
            PackageIssueCode.INVALID_PATH,
            f'{PLATFORM_SKILL_NAME}/{SKILL_FILE_NAME} 缺少 frontmatter')
    data = yaml.safe_load(frontmatter_text) or {}
    if not isinstance(data, Mapping):
        raise ValueError(f'{PLATFORM_SKILL_NAME} frontmatter 不是映射')
    return data, body, dict(package.resources)


def _package_frontmatter(source: Mapping[str, Any]) -> Dict[str, Any]:
    """平台包 frontmatter：agentskills.io 最小契约（name + description）。"""
    version = str(source.get('version') or '').strip()
    owner = str(source.get('owner') or '').strip()
    return {
        'name': PACKAGE_SKILL_NAME,
        'description': _PACKAGE_DESCRIPTION,
        'version': version or PACKAGE_VERSION_FALLBACK,
        'owner': owner or PACKAGE_OWNER,
        # 外部宿主按 MCP 工具办事，不声明内部意图工具；导入校验据此不误判。
        'allowed-tools': [],
        'permissions': [],
    }


def _fallback_body(base_url: str) -> str:
    """兜底正文：skills 不可用时用内置模板（仍注入 base_url）。"""
    template = _load_template(SKILL_FILE_NAME)
    if template:
        return _inject_base_url(template, base_url)
    return '# 智能音频测试（Intelligent Audio Test）平台能力\n'


def _ensure_required_sections(body: str) -> str:
    """保证包正文含 `## Gotchas` / `## 验收`（导入校验的结构两节）。

    ``skills/`` 生成的正文已带两节；兜底模板（静态 SKILL.md）按手册组织章节，
    这里补齐两节，避免回退模式下产出一个「缺必需章节」的包。**兜底包不保证
    可导入**（INT-2612）：模板自带 ``Bearer 在此填入你的 Access Token``
    占位命中 ``EMBEDDED_SECRET``，补齐两节后正文也超过 500 行上限
    （``BODY_TOO_LONG``）；兜底只保证下载可用、结构合法。
    """
    text = body.rstrip()
    extras = []
    if not re.search(r'^##\s+Gotchas\s*$', text, re.MULTILINE):
        extras.append('## Gotchas\n\n- 兜底模式下无额外踩坑说明。')
    if not re.search(r'^##\s+验收\s*$', text, re.MULTILINE):
        extras.append('## 验收\n\n- [ ] 按上文示例完成一次 MCP `tools/list` 与'
                      ' `tools/call`，确认 `Authorization` 与 base_url 正确。')
    if extras:
        text = '\n\n'.join([text, *extras])
    return text


def _compose_body(body: str, base_url: str) -> str:
    sections = [
        _ensure_required_sections(body),
        _render_access_section(base_url, len(mcp_registry.TOOLS)),
        _render_readonly_section(),
        '## 完整工具目录\n\n'
        f'见 `{TOOLS_REFERENCE_PATH}`（方法 / 风险 / 权限 / 说明逐项对照）。',
    ]
    return '\n\n'.join(section for section in sections if section)


def _render_mcp_json(base_url: str) -> str:
    """MCP 配置模板（base_url 注入；鉴权头用占位符，避免被判为凭证）。"""
    template = _load_template('mcp.json.tpl')
    if template is not None:
        return _inject_base_url(template, base_url)
    return json.dumps({
        'name': PACKAGE_SKILL_NAME,
        'description': '智能音频测试平台 MCP（任务/用例/音频/设备/评估/报告等）',
        'type': 'http',
        'url': f'{base_url}{MCP_ENDPOINT_PATH}',
        'headers': {'Authorization': 'Bearer <ACCESS_TOKEN>'},
    }, ensure_ascii=False, indent=2)


def _package_entries(base_url: str,
                     skills_root: Optional[str] = None) -> Dict[str, bytes]:
    """平台包条目（根级 SKILL.md + 资源目录）。"""
    effective = base_url.rstrip('/') if base_url else BASE_URL_PLACEHOLDER
    source: Mapping[str, Any] = {}
    resources: Dict[str, bytes] = {}
    try:
        source, body, resources = _load_platform_skill(
            skills_root or _skills_root())
    except (SkillPackageError, OSError, ValueError) as exc:
        logger.warning('skills/ 平台 Skill 不可用，skill 下载回退内置模板：%s',
                       exc)
        body = _fallback_body(effective)
    skill_md = build_skill_md(_package_frontmatter(source),
                              _compose_body(body, effective))
    entries: Dict[str, bytes] = {SKILL_FILE_NAME: skill_md.encode('utf-8')}
    entries.update(resources)
    entries[MCP_ASSET_PATH] = _render_mcp_json(effective).encode('utf-8')
    entries[TOOLS_REFERENCE_PATH] = _render_tools_reference().encode('utf-8')
    return entries


def build_skill_zip(base_url: str, *, skills_root: Optional[str] = None) -> bytes:
    """拼装平台 skill zip（按 skills/ 生成；缺目录时回退内置模板）。

    INT-2549 / INT-2476：打包走 ``shared.skill_package.build_zip`` —— 与用户
    自定义 Skill 导入导出同一套路径校验与「根级直接是 SKILL.md、不套外层
    目录」口径，不在这里另写一份 zipfile 逻辑。
    """
    return build_zip(_package_entries(base_url, skills_root))


__all__ = [
    'MCP_ASSET_PATH', 'MCP_FILE_NAME', 'PACKAGE_SKILL_NAME',
    'PLATFORM_SKILL_NAME', 'TOOLS_REFERENCE_PATH', 'ZIP_FILENAME',
    'build_skill_zip', 'resolve_base_url',
]
