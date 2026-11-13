/**
 * 模型供应商领域模型（domain 层；doc/agent化/07_单Agent_Skills落地方案.md
 * §6.4 / §6.4-9 / §11 provider API）。
 *
 * 架构红线：domain 只见 camelCase 领域对象；后端 snake_case 契约的转换只发生在
 * infrastructure/dto/agentProvider.dto.ts。枚举一律常量化（禁止魔法字符串）。
 *
 * Key 安全：本模块不承载任何明文 Key；列表只保留掩码 `sk-****abcd`。
 */

/** 供应商协议（§6.4-5；后端原值即大写字符串） */
export const AGENT_PROVIDER_PROTOCOL = {
  OPENAI_COMPATIBLE: 'OPENAI_COMPATIBLE',
  ANTHROPIC: 'ANTHROPIC',
} as const

export type AgentProviderProtocol =
  (typeof AGENT_PROVIDER_PROTOCOL)[keyof typeof AGENT_PROVIDER_PROTOCOL]

export const AGENT_PROVIDER_PROTOCOL_OPTIONS: ReadonlyArray<{
  value: AgentProviderProtocol
  label: string
}> = [
  { value: AGENT_PROVIDER_PROTOCOL.OPENAI_COMPATIBLE, label: 'OpenAI 兼容' },
  { value: AGENT_PROVIDER_PROTOCOL.ANTHROPIC, label: 'Anthropic' },
]

export function isAgentProviderProtocol(
  value: unknown
): value is AgentProviderProtocol {
  return (
    typeof value === 'string' &&
    value in AGENT_PROVIDER_PROTOCOL
  )
}

export function normalizeAgentProviderProtocol(
  value: unknown
): AgentProviderProtocol {
  return isAgentProviderProtocol(value)
    ? value
    : AGENT_PROVIDER_PROTOCOL.OPENAI_COMPATIBLE
}

export function agentProviderProtocolLabel(
  protocol: AgentProviderProtocol
): string {
  return (
    AGENT_PROVIDER_PROTOCOL_OPTIONS.find((item) => item.value === protocol)
      ?.label ?? protocol
  )
}

/** 供应商状态（§10 agent_llm_provider.status） */
export const AGENT_PROVIDER_STATUS = {
  ACTIVE: 'ACTIVE',
  INVALID: 'INVALID',
  DELETED: 'DELETED',
} as const

export type AgentProviderStatus =
  (typeof AGENT_PROVIDER_STATUS)[keyof typeof AGENT_PROVIDER_STATUS]

export const AGENT_PROVIDER_STATUS_LABELS: Record<AgentProviderStatus, string> = {
  ACTIVE: '可用',
  INVALID: '验证失败',
  DELETED: '已删除',
}

export function normalizeAgentProviderStatus(
  value: unknown
): AgentProviderStatus {
  return typeof value === 'string' && value in AGENT_PROVIDER_STATUS
    ? (value as AgentProviderStatus)
    : AGENT_PROVIDER_STATUS.ACTIVE
}

/** 有效上下文窗口来源（§6.4-9：用户覆盖 → 目录默认 → 兜底） */
export const CONTEXT_WINDOW_SOURCE = {
  USER_OVERRIDE: 'USER_OVERRIDE',
  MODEL_DEFAULT: 'MODEL_DEFAULT',
  FALLBACK: 'FALLBACK',
} as const

export type ContextWindowSource =
  (typeof CONTEXT_WINDOW_SOURCE)[keyof typeof CONTEXT_WINDOW_SOURCE]

export const CONTEXT_WINDOW_SOURCE_LABELS: Record<ContextWindowSource, string> = {
  USER_OVERRIDE: '手动覆盖',
  MODEL_DEFAULT: '目录默认',
  FALLBACK: '默认兜底',
}

export function normalizeContextWindowSource(
  value: unknown
): ContextWindowSource {
  return typeof value === 'string' && value in CONTEXT_WINDOW_SOURCE
    ? (value as ContextWindowSource)
    : CONTEXT_WINDOW_SOURCE.FALLBACK
}

/** 覆盖值高于目录默认时的告警码（仍允许保存，预算按覆盖值计算） */
export const CONTEXT_WINDOW_WARNING_ABOVE_CATALOG =
  'CONTEXT_WINDOW_ABOVE_CATALOG'

/** 目录未命中时的兜底窗口（对齐后端 config/model_catalog.json） */
export const DEFAULT_CONTEXT_WINDOW_FALLBACK = 131_072

/** 覆盖值边界（后端 bounds 缺省值；实际以 GET /model-catalog 返回为准） */
export const DEFAULT_CONTEXT_WINDOW_BOUNDS = {
  min: 8_192,
  max: 2_097_152,
  alignment: 1_024,
} as const

/** 供应商（GET /agent/providers 条目；无密文、无明文） */
export interface AgentProvider {
  id: string
  name: string
  protocol: AgentProviderProtocol
  baseUrl: string
  model: string
  /** 掩码（sk-****abcd）；编辑时永远不回显明文 */
  apiKeyMask: string
  /** 用户覆盖值；null = 使用目录默认 / 兜底 */
  contextWindow: number | null
  contextWindowSource: ContextWindowSource
  effectiveContextWindow: number
  catalogContextWindow: number | null
  catalogMaxOutputTokens: number | null
  /** 覆盖值高于目录默认时的告警码 / 文案（仅告警，不阻断保存） */
  contextWindowWarning: string | null
  contextWindowWarningMessage: string | null
  isDefault: boolean
  status: AgentProviderStatus
  lastVerifiedAt: string | null
  createdAt: string | null
  updatedAt: string | null
}

/** 模型目录条目（GET /agent/model-catalog → models[]） */
export interface ModelCatalogItem {
  /** 协议（'*' 表示通配） */
  protocol: string
  /** 模型名匹配模式（glob，大小写不敏感） */
  match: string
  contextWindow: number
  maxOutputTokens: number
}

export interface ContextWindowBounds {
  min: number
  max: number
  alignment: number
}

/** 模型目录（表单预填 + 覆盖校验边界） */
export interface ModelCatalog {
  fallbackContextWindow: number
  bounds: ContextWindowBounds
  models: ModelCatalogItem[]
}

/** POST /agent/providers/{id}/verify 结果 */
export interface AgentProviderVerification {
  providerId: string
  ok: boolean
  code: string
  message: string
  status: AgentProviderStatus
  lastVerifiedAt: string | null
}

/** 表单提交载荷（camelCase；api 层转 snake_case） */
export interface AgentProviderInput {
  name: string
  protocol: AgentProviderProtocol
  baseUrl: string
  model: string
  /** 新建必填；编辑留空 = 不变 */
  apiKey?: string
  /** null = 使用默认窗口（恢复默认） */
  contextWindow: number | null
}

/** 目录匹配（对齐后端 ContextWindowResolver.match：协议 + glob、首个命中生效） */
export function matchModelCatalogItem(
  catalog: ModelCatalog | undefined,
  protocol: AgentProviderProtocol,
  model: string
): ModelCatalogItem | null {
  if (!catalog) return null
  const wanted = model.trim().toLowerCase()
  if (!wanted) return null
  return (
    catalog.models.find((item) => {
      if (item.protocol !== '*' && item.protocol !== protocol) return false
      return globMatch(wanted, item.match.toLowerCase())
    }) ?? null
  )
}

/** glob → 正则（只支持 * 与 ?；与后端 fnmatchcase 常见用法一致） */
function globMatch(value: string, pattern: string): boolean {
  const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, '\\$&')
  const regex = new RegExp(`^${escaped.replace(/\*/g, '.*').replace(/\?/g, '.')}$`)
  return regex.test(value)
}

/** 表单预览：模拟后端「覆盖 → 目录默认 → 128k 兜底」的解析结果 */
export interface ContextWindowPreview {
  effectiveContextWindow: number
  source: ContextWindowSource
  catalogContextWindow: number | null
  catalogMaxOutputTokens: number | null
  warning: string | null
}

export function resolveContextWindowPreview(
  catalog: ModelCatalog | undefined,
  protocol: AgentProviderProtocol,
  model: string,
  override: number | null
): ContextWindowPreview {
  const entry = matchModelCatalogItem(catalog, protocol, model)
  if (override !== null) {
    const catalogWindow = entry?.contextWindow ?? null
    const above =
      catalogWindow !== null && catalogWindow > 0 && override > catalogWindow
    return {
      effectiveContextWindow: override,
      source: CONTEXT_WINDOW_SOURCE.USER_OVERRIDE,
      catalogContextWindow: catalogWindow,
      catalogMaxOutputTokens: entry?.maxOutputTokens ?? null,
      warning: above ? CONTEXT_WINDOW_WARNING_ABOVE_CATALOG : null,
    }
  }
  if (entry && entry.contextWindow > 0) {
    return {
      effectiveContextWindow: entry.contextWindow,
      source: CONTEXT_WINDOW_SOURCE.MODEL_DEFAULT,
      catalogContextWindow: entry.contextWindow,
      catalogMaxOutputTokens: entry.maxOutputTokens,
      warning: null,
    }
  }
  return {
    effectiveContextWindow:
      catalog?.fallbackContextWindow ?? DEFAULT_CONTEXT_WINDOW_FALLBACK,
    source: CONTEXT_WINDOW_SOURCE.FALLBACK,
    catalogContextWindow: null,
    catalogMaxOutputTokens: null,
    warning: null,
  }
}

/**
 * 覆盖值校验（对齐后端 ContextWindowResolver.validate_override）：
 * 整数、落在 bounds 内、按 alignment 对齐；返回中文错误文案或 null（合法）。
 */
export function validateContextWindowOverride(
  value: number,
  bounds: ContextWindowBounds = DEFAULT_CONTEXT_WINDOW_BOUNDS
): string | null {
  if (!Number.isFinite(value) || !Number.isInteger(value)) {
    return '上下文窗口必须是整数'
  }
  if (value < bounds.min || value > bounds.max) {
    return `上下文窗口需在 ${formatContextWindowTokens(bounds.min)}–${formatContextWindowTokens(bounds.max)} 之间`
  }
  if (bounds.alignment > 0 && value % bounds.alignment !== 0) {
    return `上下文窗口需按 ${bounds.alignment} 对齐`
  }
  return null
}

/** Token 数 → 简短中文（131072 → 128k；1048576 → 1M） */
export function formatContextWindowTokens(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return '—'
  if (value >= 1024 * 1024) {
    const millions = value / (1024 * 1024)
    const text = Number.isInteger(millions) ? String(millions) : millions.toFixed(1)
    return `${text}M`
  }
  if (value >= 1024) {
    const thousands = value / 1024
    const text = Number.isInteger(thousands) ? String(thousands) : thousands.toFixed(1)
    return `${text}k`
  }
  return String(value)
}

/** 最近验证时间（ISO → 本地可读；空 = 未验证） */
export function formatVerifiedAt(value: string | null | undefined): string {
  if (!value) return '未验证'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '未验证'
  return date.toLocaleString('zh-CN', { hour12: false })
}

/** 无可用供应商时 run 失败的后端错误码（§6.4-4） */
export const AGENT_PROVIDER_NOT_CONFIGURED_CODE = 'LLM_PROVIDER_NOT_CONFIGURED'

/** run 错误码 / 错误串是否表示「没有可用供应商」 */
export function isProviderNotConfiguredError(
  codeOrMessage: string | null | undefined
): boolean {
  return Boolean(
    codeOrMessage && codeOrMessage.includes(AGENT_PROVIDER_NOT_CONFIGURED_CODE)
  )
}
