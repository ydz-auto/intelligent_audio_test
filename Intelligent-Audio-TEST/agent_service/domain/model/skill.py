# -*- coding: utf-8 -*-
"""Skill 领域模型（落地方案 §4.1 / §4.2）。

一个 Skill = 目录 ``skills/<name>/``：

    SKILL.md          YAML frontmatter + 正文（L2）
    references/       按需加载的详细资料（L3）
    scripts/          平台受控脚本（T1 沙箱执行，仅登记不执行）
    assets/           输出模板等，不进上下文

本模块只描述「一个 Skill 是什么」，不负责扫描目录（infrastructure）也不
负责校验取舍（application/skill_registry）。
"""
import re
from dataclasses import dataclass, field
from typing import Dict, Mapping, Optional, Tuple

from agent_service.domain.enums import SkillScope, SkillStatus
from shared.constants.permissions import WILDCARD_PERMISSION

# Skill 目录内的正文文件名（唯一事实源；扫描与部署校验共用，INT-2529）
SKILL_FILE_NAME = 'SKILL.md'

# 自定义 Skill 名称口径（INT-2549 §4.4 逐项校验）：小写字母/数字开头，
# 后接小写字母/数字/连字符，总长 2~64。
SKILL_NAME_PATTERN = re.compile(r'^[a-z0-9][a-z0-9-]{1,63}$')

# 资源子目录（zip 包与对象存储路径同一口径，§4.1）
RESOURCE_DIRS: Tuple[str, ...] = ('references', 'scripts', 'assets')

# frontmatter 契约字段（§4.2）。缺 name / description 视为无效 Skill。
FIELD_NAME = 'name'
FIELD_DESCRIPTION = 'description'
FIELD_VERSION = 'version'
FIELD_OWNER = 'owner'
FIELD_ALLOWED_TOOLS = 'allowed-tools'
FIELD_PERMISSIONS = 'permissions'
FIELD_BUDGETS = 'budgets'

# budgets 子字段（§4.2 示例，camelCase 与 frontmatter 一致）
BUDGET_MAX_TOOL_CALLS = 'maxToolCalls'
BUDGET_MAX_TOKENS = 'maxTokens'

# 正文必须包含的两节（§4.2 规则 3）
SECTION_GOTCHAS = 'Gotchas'
SECTION_ACCEPTANCE = '验收'
REQUIRED_SECTIONS: Tuple[str, ...] = (SECTION_GOTCHAS, SECTION_ACCEPTANCE)

# 权限通配符来自 ``shared.constants.permissions``（与 api_gateway /
# auth_service 的 RBAC 口径同一字面值；本模块只做再导出，不再自写一份）

# 三级渐进披露层级（§4.1）
SKILL_DISCLOSURE_L1 = 'L1'
SKILL_DISCLOSURE_L2 = 'L2'
SKILL_DISCLOSURE_L3 = 'L3'


@dataclass(frozen=True)
class SkillMeta:
    """frontmatter 解析结果。"""

    name: str = ''
    description: str = ''
    version: str = ''
    owner: str = ''
    allowed_tools: Tuple[str, ...] = ()
    permissions: Tuple[str, ...] = ()
    budgets: Mapping[str, int] = field(default_factory=dict)

    @property
    def max_tool_calls(self) -> Optional[int]:
        return self.budgets.get(BUDGET_MAX_TOOL_CALLS)

    @property
    def max_tokens(self) -> Optional[int]:
        return self.budgets.get(BUDGET_MAX_TOKENS)


@dataclass(frozen=True)
class Skill:
    """一个已装载的 Skill。``load_error`` 非空表示 frontmatter 不可解析。

    INT-2549 起同一领域对象也承载自定义（TENANT / USER）层：
    ``skill_id`` 非空 = 库内行（PLATFORM 为 ``platform:<name>`` 合成 ID），
    ``scope`` / ``status`` / ``masked_by`` / ``content_hash`` 供列表标注与
    run 快照回放；``resources`` 是「相对路径 → 对象存储 key」映射。
    """

    meta: SkillMeta
    body: str
    path: str
    references: Tuple[str, ...] = ()
    scripts: Tuple[str, ...] = ()
    assets: Tuple[str, ...] = ()
    load_error: Optional[str] = None
    skill_id: str = ''
    scope: SkillScope = SkillScope.PLATFORM
    status: SkillStatus = SkillStatus.ACTIVE
    masked_by: Optional[str] = None
    content_hash: str = ''
    resources: Mapping[str, str] = field(default_factory=dict)
    owner_id: Optional[int] = None
    tenant_id: Optional[str] = None

    @property
    def name(self) -> str:
        return self.meta.name

    @property
    def description(self) -> str:
        return self.meta.description

    @property
    def body_line_count(self) -> int:
        return len(self.body.splitlines())

    @property
    def is_custom(self) -> bool:
        """是否库内自定义层（可写、有版本指针）。"""
        return self.scope is not SkillScope.PLATFORM

    def has_section(self, title: str) -> bool:
        """正文是否有 ``## <title>`` 二级标题。"""
        wanted = f'## {title}'.strip().lower()
        for line in self.body.splitlines():
            if line.strip().lower() == wanted:
                return True
        return False


__all__ = [
    'BUDGET_MAX_TOKENS', 'BUDGET_MAX_TOOL_CALLS', 'FIELD_ALLOWED_TOOLS',
    'FIELD_BUDGETS', 'FIELD_DESCRIPTION', 'FIELD_NAME', 'FIELD_OWNER',
    'FIELD_PERMISSIONS', 'FIELD_VERSION', 'REQUIRED_SECTIONS',
    'RESOURCE_DIRS', 'SECTION_ACCEPTANCE', 'SECTION_GOTCHAS',
    'SKILL_DISCLOSURE_L1', 'SKILL_DISCLOSURE_L2', 'SKILL_DISCLOSURE_L3',
    'SKILL_FILE_NAME', 'SKILL_NAME_PATTERN', 'Skill', 'SkillMeta',
    'WILDCARD_PERMISSION',
]
