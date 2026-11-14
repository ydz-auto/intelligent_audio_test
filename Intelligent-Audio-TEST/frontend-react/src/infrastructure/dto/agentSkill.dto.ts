/**
 * 自定义 Skill DTO（infrastructure/dto 层；snake_case ↔ camelCase 唯一转换层）。
 * 契约来源：agent_service/interfaces/api/routes.py + schemas.py + api_gateway/
 * routes/agent_skill_bp.py（INT-2549，已合入 V10.11.2）。网关透明转发，
 * 响应不带 {success,data} 信封。
 *
 * - GET    /api/v1/agent/skills                    → { items, tools, skills_count, ... }
 * - POST   /api/v1/agent/skills                    → SkillView（201）
 * - PUT    /api/v1/agent/skills/{id}               → SkillView（未出现字段不变，version +1）
 * - DELETE /api/v1/agent/skills/{id}               → 204
 * - POST   /api/v1/agent/skills/{id}/publish       → { skill, gate, participates_in_trigger }
 * - POST   /api/v1/agent/skills/{id}/disable       → SkillView
 * - POST   /api/v1/agent/skills/{id}/fork          → SkillView（201）
 * - POST   /api/v1/agent/skills/import             → SkillView（201，multipart）
 * - GET    /api/v1/agent/skills/{id}/export        → application/zip（根级 SKILL.md）
 * - GET    /api/v1/agent/skills/{id}/versions      → { items: SkillVersion[] }
 *
 * 注意：列表/详情视图不返回 SKILL.md 正文（§11 无单条详情接口），编辑器正文经
 * 导出包读取——与导入 / 导出同一格式口径，前端不改写包结构。
 */
import {
  isSkillScope,
  normalizeSkillIssueSeverity,
  normalizeSkillScope,
  normalizeSkillStatus,
  type AgentSkill,
  type AgentSkillDraftInput,
  type SkillGate,
  type SkillIssue,
  type SkillPublishResult,
  type SkillTool,
  type SkillVersion,
} from '@/domain/models/agentSkill'

/** 一条逐项校验问题（SkillIssueSchema） */
export interface SkillIssueDto {
  code?: string
  severity?: string
  field?: string
  message?: string
}

/** SkillViewSchema（列表 / 详情项） */
export interface AgentSkillViewDto {
  id?: string
  scope?: string
  name?: string
  description?: string
  version?: string
  status?: string
  content_hash?: string
  masked_by?: string | null
  owner?: string
  owner_id?: number | null
  tenant_id?: string | null
  created_by?: number | null
  updated_at?: string | null
  allowed_tools?: string[]
  permissions?: string[]
  budgets?: Record<string, unknown>
  issues?: SkillIssueDto[]
}

/** 意图工具（GET /agent/skills 的 tools[]） */
export interface SkillToolDto {
  name?: string
  description?: string
  risk?: string
  permissions?: string[]
  enabled?: boolean
}

/** GET /agent/skills 响应 */
export interface AgentSkillListDto {
  items?: AgentSkillViewDto[]
  tools?: SkillToolDto[]
  skills_count?: number
  tools_count?: number
  l1_tokens?: number
  l1_budget_tokens?: number
}

/** 发布结果（SkillPublishResponse） */
export interface SkillPublishDto {
  skill?: AgentSkillViewDto
  gate?: {
    golden_tasks?: number
    passed?: boolean
    failures?: string[]
    note?: string
  }
  participates_in_trigger?: boolean
}

/** 版本历史项（SkillVersionSchema） */
export interface SkillVersionDto {
  version?: string
  content_hash?: string
  created_at?: string | null
  created_by?: number | null
}

/** GET /agent/skills/{id}/versions 响应 */
export interface SkillVersionListDto {
  items?: SkillVersionDto[]
}

/** 请求体（SkillDraftRequest；身份字段一律不发送） */
export interface SkillDraftRequestDto {
  name?: string
  description?: string
  frontmatter?: Record<string, unknown>
  body?: string
}

/** fork 请求体（SkillForkRequest） */
export interface SkillForkRequestDto {
  name?: string
  description?: string
}

/**
 * 时间戳归一（agent_service 存 naive UTC，序列化不带时区）。
 * 直接 `new Date()` 会按本地时区解析、在 UTC+8 下差 8 小时，补 `Z` 再交给页面。
 */
export function normalizeUtcTimestamp(value?: string | null): string | null {
  if (!value) return null
  const text = value.trim()
  if (!text) return null
  if (/([zZ]|[+-]\d{2}:?\d{2})$/.test(text)) return text
  return `${text}Z`
}

/** SkillViewDto → camelCase 领域对象 */
export function toAgentSkill(dto: AgentSkillViewDto): AgentSkill {
  const budgets: Record<string, number> = {}
  for (const [key, value] of Object.entries(dto.budgets ?? {})) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      budgets[key] = value
    }
  }
  return {
    id: dto.id ?? '',
    scope: normalizeSkillScope(dto.scope),
    name: dto.name ?? '',
    description: dto.description ?? '',
    version: dto.version ?? '',
    status: normalizeSkillStatus(dto.status),
    contentHash: dto.content_hash ?? '',
    maskedBy: isSkillScope(dto.masked_by) ? dto.masked_by : null,
    owner: dto.owner ?? '',
    ownerId: dto.owner_id ?? null,
    allowedTools: Array.isArray(dto.allowed_tools) ? [...dto.allowed_tools] : [],
    permissions: Array.isArray(dto.permissions) ? [...dto.permissions] : [],
    budgets,
    updatedAt: normalizeUtcTimestamp(dto.updated_at),
    issues: toSkillIssues(dto.issues),
  }
}

/** 问题列表 → 领域对象（未知严重度按 ERROR，宁严不漏） */
export function toSkillIssues(issues?: SkillIssueDto[]): SkillIssue[] {
  return (issues ?? []).map((issue) => ({
    code: issue.code ?? '',
    severity: normalizeSkillIssueSeverity(issue.severity),
    field: issue.field ?? '',
    message: issue.message ?? '',
  }))
}

export function toSkillTools(tools?: SkillToolDto[]): SkillTool[] {
  return (tools ?? []).map((tool) => ({
    name: tool.name ?? '',
    description: tool.description ?? '',
    risk: tool.risk ?? 'READ',
    permissions: Array.isArray(tool.permissions) ? [...tool.permissions] : [],
    enabled: tool.enabled ?? false,
  }))
}

/** 草稿输入 → 请求体（frontmatter 只带契约字段；name / description 另列） */
export function toSkillDraftRequest(
  input: AgentSkillDraftInput
): SkillDraftRequestDto {
  const request: SkillDraftRequestDto = {
    name: input.name,
    description: input.description,
    body: input.body,
  }
  if (input.frontmatter) {
    request.frontmatter = { ...input.frontmatter }
  }
  return request
}

export function toSkillVersion(dto: SkillVersionDto): SkillVersion {
  return {
    version: dto.version ?? '',
    contentHash: dto.content_hash ?? '',
    createdAt: normalizeUtcTimestamp(dto.created_at),
    createdBy: dto.created_by ?? null,
  }
}

export function toSkillVersions(dto: SkillVersionListDto): SkillVersion[] {
  return (dto.items ?? []).map(toSkillVersion)
}

export function toSkillGate(dto?: SkillPublishDto['gate']): SkillGate {
  return {
    goldenTasks: dto?.golden_tasks ?? 0,
    passed: dto?.passed ?? false,
    failures: Array.isArray(dto?.failures) ? [...dto.failures] : [],
    note: dto?.note ?? '',
  }
}

export function toSkillPublishResult(
  dto: SkillPublishDto
): SkillPublishResult {
  return {
    skill: toAgentSkill(dto.skill ?? {}),
    gate: toSkillGate(dto.gate),
    participatesInTrigger: dto.participates_in_trigger ?? false,
  }
}
