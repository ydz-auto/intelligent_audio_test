/**
 * 被测 API 的「配置能否跑起来」自检（domain 单一来源）。
 *
 * 目标：把「新接一个厂商要写代码还是填配置」这件事在**保存前**说清楚——
 *
 * - `configurable`：协议 + 流式性 + meta 全部落在通用驱动能表达的能力面内，
 *   保存后可直接执行（不需要写适配器代码）；
 * - `needs_adapter`：命中通用驱动表达不了的能力（缺必填 meta / 未注册适配器），
 *   保存前拦截，并给出具体缺口，避免"存进去、跑的时候才炸"。
 *
 * 能力面与执行侧同一口径：
 * - 协议 × 流式性可用矩阵：`shared/models/common_enums.AVAILABLE_PROTOCOL_STREAMING`
 *   → 前端镜像在 `domain/models/apiProtocol.ts`；
 * - gRPC 必填 `meta.grpc`：`api_test_service/domain/value_objects/grpc_meta.py`；
 * - 适配器词表：`domain/models/vendorAdapter.ts`（后端 `VendorAdapterType` 同值域）。
 *
 * 未识别的 meta 键只给 warning（可能是新能力尚未进本表），不拦截。
 */
import { isCombinationImplemented, type ApiProtocol } from './apiProtocol'
import { VENDOR_ADAPTER_TYPES } from './vendorAdapter'

export type CapabilityLevel = 'configurable' | 'needs_adapter'

export type CapabilityIssueSeverity = 'error' | 'warning'

export interface CapabilityIssue {
  severity: CapabilityIssueSeverity
  /** 面向用户的短句（直接展示，不拼接技术细节） */
  message: string
}

export interface CapabilityInput {
  protocol: string
  streaming: boolean
  /** 当前 meta 草稿（含存量键） */
  meta: Record<string, unknown>
}

export interface CapabilityResult {
  level: CapabilityLevel
  issues: CapabilityIssue[]
}

/** 通用驱动已消费的 meta 键（新增能力时同步本表，避免误报"未识别"） */
export const KNOWN_META_KEYS: readonly string[] = [
  'method',
  'headers',
  'body_template',
  'body',
  'ws_headers',
  'session_config',
  'pacing',
  'vendor_adapter',
  'first_frame',
  'audio_frame',
  'result_parser',
  'append_mode',
  'sse',
  'grpc',
  // 存量解析器键：UI 已不暴露，但存量行仍可能带，不算未知
  'asr_mapping',
  'trans_mapping',
  'sentence_end_mapping',
  'session_end_mapping',
  'error_code_mapping',
  'error_msg_mapping',
]

/** gRPC 必须声明的子键（`validate_grpc_meta` 的执行期必填集） */
const GRPC_REQUIRED_KEYS = ['proto_object_key', 'service', 'method', 'method_kind'] as const

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

function isNonEmpty(value: unknown): boolean {
  return typeof value === 'string' ? value.trim() !== '' : value != null
}

/**
 * 判定当前配置是否「纯前端配置即可跑」。
 *
 * 只做写前拦截用的硬校验（缺必填 / 未注册值），其余降为 warning。
 */
export function evaluateAdapterCapability(input: CapabilityInput): CapabilityResult {
  const issues: CapabilityIssue[] = []
  const protocol = input.protocol as ApiProtocol

  // 1) 协议 × 流式性必须落在已实现矩阵内
  if (!isCombinationImplemented(protocol, input.streaming)) {
    issues.push({
      severity: 'error',
      message: `当前「${input.protocol} + ${
        input.streaming ? '流式' : '非流式'
      }」组合的后端执行器未上线，保存后无法执行`,
    })
  }

  // 2) 厂商适配器必须是已注册值：存量脏值不阻断保存（下拉里已显式标注），
  //    但执行期会被拒绝，所以给 warning 让用户知情。
  const vendorAdapter = String(input.meta.vendor_adapter ?? '').trim()
  if (
    vendorAdapter &&
    !(VENDOR_ADAPTER_TYPES as readonly string[]).includes(vendorAdapter)
  ) {
    issues.push({
      severity: 'warning',
      message: `厂商适配器「${vendorAdapter}」未注册，执行期会被拒绝；请改选下拉里的标准值或留空`,
    })
  }

  // 3) gRPC 的 meta.grpc 是协议必填面
  if (protocol === 'grpc') {
    const grpc = asRecord(input.meta.grpc)
    const missing = GRPC_REQUIRED_KEYS.filter((key) => !isNonEmpty(grpc[key]))
    if (missing.length > 0) {
      issues.push({
        severity: 'error',
        message: `gRPC 缺少必填项：${missing.join(' / ')}（在「请求模板 → gRPC」补齐）`,
      })
    }
  }

  // 4) 未识别的 meta 键：可能是通用驱动不消费的残留，只提示
  const unknownKeys = Object.keys(input.meta).filter(
    (key) => !KNOWN_META_KEYS.includes(key) && !key.startsWith('_')
  )
  if (unknownKeys.length > 0) {
    issues.push({
      severity: 'warning',
      message: `meta 中有通用驱动未消费的键：${unknownKeys.join(', ')}（不报错，但不参与执行）`,
    })
  }

  return {
    level: issues.some((issue) => issue.severity === 'error')
      ? 'needs_adapter'
      : 'configurable',
    issues,
  }
}
