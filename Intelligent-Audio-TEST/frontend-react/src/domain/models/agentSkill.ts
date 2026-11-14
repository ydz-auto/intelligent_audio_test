/**
 * 自定义 Skill 领域模型（domain 层；doc/agent化/07_单Agent_Skills落地方案.md
 * §4.4 / §11；INT-2549 后端契约、INT-2550 前端落地）。
 *
 * 架构红线：domain 只见 camelCase 领域对象；snake_case ↔ camelCase 只发生在
 * infrastructure/dto/agentSkill.dto.ts。枚举一律常量化，禁止魔法字符串。
 *
 * 来源三层（§4.4「来源与优先级」）：PLATFORM 只读、TENANT 租户共享（M3）、
 * USER 个人私有；同名时 USER > TENANT > PLATFORM，被遮蔽项带 maskedBy。
 */

/** Skill 来源（后端原值即大写字符串） */
export const SKILL_SCOPE = {
  PLATFORM: 'PLATFORM',
  TENANT: 'TENANT',
  USER: 'USER',
} as const

export type SkillScope = (typeof SKILL_SCOPE)[keyof typeof SKILL_SCOPE]

export const SKILL_SCOPE_LABELS: Record<SkillScope, string> = {
  PLATFORM: '平台内置',
  TENANT: '租户共享',
  USER: '我的',
}

/** 来源页签（全部 + 三层来源） */
export const SKILL_SCOPE_FILTER = {
  ALL: 'ALL',
  PLATFORM: SKILL_SCOPE.PLATFORM,
  USER: SKILL_SCOPE.USER,
} as const

export type SkillScopeFilter =
  (typeof SKILL_SCOPE_FILTER)[keyof typeof SKILL_SCOPE_FILTER]

export function isSkillScope(value: unknown): value is SkillScope {
  return typeof value === 'string' && value in SKILL_SCOPE
}

export function normalizeSkillScope(value: unknown): SkillScope {
  return isSkillScope(value) ? value : SKILL_SCOPE.PLATFORM
}

/** Skill 生命周期状态（§4.4「安全与生命周期」） */
export const SKILL_STATUS = {
  DRAFT: 'DRAFT',
  ACTIVE: 'ACTIVE',
  DISABLED: 'DISABLED',
} as const

export type SkillStatus = (typeof SKILL_STATUS)[keyof typeof SKILL_STATUS]

export const SKILL_STATUS_LABELS: Record<SkillStatus, string> = {
  DRAFT: '草稿',
  ACTIVE: '已发布',
  DISABLED: '已停用',
}

/** 状态页签（全部 + 三种状态） */
export const SKILL_STATUS_FILTER = {
  ALL: 'ALL',
  DRAFT: SKILL_STATUS.DRAFT,
  ACTIVE: SKILL_STATUS.ACTIVE,
  DISABLED: SKILL_STATUS.DISABLED,
} as const

export type SkillStatusFilter =
  (typeof SKILL_STATUS_FILTER)[keyof typeof SKILL_STATUS_FILTER]

export function isSkillStatus(value: unknown): value is SkillStatus {
  return typeof value === 'string' && value in SKILL_STATUS
}

export function normalizeSkillStatus(value: unknown): SkillStatus {
  return isSkillStatus(value) ? value : SKILL_STATUS.DRAFT
}

/** 校验问题严重度：ERROR 拒绝落库 / 发布，WARNING 只提示 */
export const SKILL_ISSUE_SEVERITY = {
  ERROR: 'ERROR',
  WARNING: 'WARNING',
} as const

export type SkillIssueSeverity =
  (typeof SKILL_ISSUE_SEVERITY)[keyof typeof SKILL_ISSUE_SEVERITY]

export function isSkillIssueSeverity(
  value: unknown
): value is SkillIssueSeverity {
  return typeof value === 'string' && value in SKILL_ISSUE_SEVERITY
}

/** 未知严重度按 ERROR 处理（宁严不漏，不允许静默降级告警） */
export function normalizeSkillIssueSeverity(
  value: unknown
): SkillIssueSeverity {
  return isSkillIssueSeverity(value)
    ? value
    : SKILL_ISSUE_SEVERITY.ERROR
}

/** 一条逐项校验问题（`field` 为服务端给出的定位字段，可能为空） */
export interface SkillIssue {
  code: string
  severity: SkillIssueSeverity
  field: string
  message: string
}

/** 表单可定位字段（服务端 issues[].field 的已知取值） */
export const SKILL_ISSUE_FIELD = {
  NAME: 'name',
  DESCRIPTION: 'description',
  BODY: 'body',
  ALLOWED_TOOLS: 'allowed-tools',
  PERMISSIONS: 'permissions',
  FRONTMATTER: 'frontmatter',
  PACKAGE: 'package',
} as const

export type SkillIssueField =
  (typeof SKILL_ISSUE_FIELD)[keyof typeof SKILL_ISSUE_FIELD]

/** 已注册意图工具（GET /agent/skills 同响应附带；allowed-tools 只能引用它们） */
export interface SkillTool {
  name: string
  description: string
  risk: string
  permissions: string[]
  /** M0 是否已实现（未实现仍可写进 allowed-tools，但运行期返回「未启用」） */
  enabled: boolean
}

/** 一个可见 Skill（列表项 / 详情，camelCase 领域对象） */
export interface AgentSkill {
  id: string
  scope: SkillScope
  name: string
  description: string
  /** 行版本号（每次保存 +1，字符串形态） */
  version: string
  status: SkillStatus
  contentHash: string
  /** 被同名的更高优先级来源遮蔽时，值为遮蔽它的来源 */
  maskedBy: SkillScope | null
  owner: string
  ownerId: number | null
  allowedTools: string[]
  permissions: string[]
  budgets: Record<string, number>
  updatedAt: string | null
  issues: SkillIssue[]
}

/** 列表响应（技能 + 意图工具清单 + 装载摘要） */
export interface AgentSkillList {
  items: AgentSkill[]
  tools: SkillTool[]
  /** 平台层装载的 Skill 数（看板 / 审计判「Skill 层是否整体消失」） */
  skillsCount: number
  toolsCount: number
  l1Tokens: number
  l1BudgetTokens: number
}

/** 新建 / 保存草稿请求（服务端身份字段由服务端填写） */
export interface AgentSkillDraftInput {
  name: string
  description: string
  /** 除 name / description 外的 frontmatter 契约字段（allowed-tools / permissions / budgets / owner） */
  frontmatter?: Record<string, unknown>
  body: string
}

/** fork 请求（name 缺省时服务端用 `<name>-copy`） */
export interface AgentSkillForkInput {
  name?: string
  description?: string
}

/** 版本历史项（GET /agent/skills/{id}/versions） */
export interface SkillVersion {
  version: string
  contentHash: string
  createdAt: string | null
  createdBy: number | null
}

/** 发布门槛结果（POST /agent/skills/{id}/publish） */
export interface SkillGate {
  goldenTasks: number
  passed: boolean
  failures: string[]
  note: string
}

/** 发布结果（门槛未达标时 skill 仍为 DRAFT，不抛错） */
export interface SkillPublishResult {
  skill: AgentSkill
  gate: SkillGate
  participatesInTrigger: boolean
}

/** 导出产物（filename 由页面按 `<name>-v<version>.zip` 生成，字节来自服务端） */
export interface SkillPackageDownload {
  filename: string
  blob: Blob
}

/** 编辑器载入的 SKILL.md 文档（正文来自导出包的根级 SKILL.md） */
export interface SkillDocument {
  /** frontmatter 原文（仅供预览，不参与编辑） */
  frontmatterText: string
  body: string
}

/** 名称口径（§4.4 落库前校验；前端只做即时提示，规则仍以服务端为准） */
export const SKILL_NAME_PATTERN = /^[a-z0-9][a-z0-9-]{1,63}$/

/** 正文必须包含的两节（§4.2 规则 3） */
export const SKILL_REQUIRED_SECTIONS = ['Gotchas', '验收'] as const

/** 新建草稿的正文骨架（含两节必需标题，用户在其中补内容） */
export const SKILL_BODY_TEMPLATE = `## 适用场景

描述这个 Skill 解决什么问题、在什么情况下触发。

## 步骤

1.

## Gotchas

-

## 验收

-
`

/** 名称是否合法（前端即时提示；服务端仍会逐项校验） */
export function isValidSkillName(name: string): boolean {
  return SKILL_NAME_PATTERN.test(name.trim())
}

/** 正文是否缺少必需小节（前端即时提示） */
export function missingRequiredSections(body: string): string[] {
  return SKILL_REQUIRED_SECTIONS.filter(
    (section) => !new RegExp(`^##\\s*${section}\\s*$`, 'm').test(body)
  )
}

/** 是否本人可写（PLATFORM 只读，仅 fork / 导出） */
export function isWritableSkill(skill: AgentSkill): boolean {
  return skill.scope === SKILL_SCOPE.USER
}

/** 是否可发布（只有 DRAFT 能发布） */
export function isPublishableSkill(skill: AgentSkill): boolean {
  return isWritableSkill(skill) && skill.status === SKILL_STATUS.DRAFT
}

/** 是否可停用（只有非 DISABLED 的本人 Skill） */
export function isDisableableSkill(skill: AgentSkill): boolean {
  return isWritableSkill(skill) && skill.status !== SKILL_STATUS.DISABLED
}

/** contentHash 前 8 位（列表只展示短哈希） */
export function shortContentHash(hash: string): string {
  return hash ? hash.slice(0, 8) : '—'
}

/** 导出文件名口径：`<name>-v<version>.zip` */
export function skillPackageFilename(skill: {
  name: string
  version: string
}): string {
  const version = (skill.version || '0').trim()
  return `${skill.name}-v${version}.zip`
}

/** 空草稿（新建入口的初始值） */
export function emptySkillDraft(): AgentSkillDraftInput {
  return {
    name: '',
    description: '',
    frontmatter: { 'allowed-tools': [], permissions: [] },
    body: SKILL_BODY_TEMPLATE,
  }
}
