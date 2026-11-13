/**
 * 平台统一 API 错误（infrastructure/api 层）。
 * 服务端 error_response 契约 { success, code, message, detail, errors } 归一为
 * ApiError：code（业务错误码，枚举）、httpStatus、userMessage（页面直接呈现的中文文案）。
 * 网络层失败（fetch TypeError）也收敛为 ApiError（httpStatus=null → 网络文案）。
 */
import {
  ApiErrorCode,
  API_ERROR_COPY,
  HTTP_STATUS_COPY,
} from '@/domain/models/api'
import { NETWORK_FAILED_COPY } from '@/domain/models/auth'

export interface ApiErrorPayload {
  code?: unknown
  httpStatus?: number | null
  message?: string
  detail?: unknown
  errors?: unknown
  /**
   * 错误响应体里的 `data`（INT-2315）。
   * 部分接口把可执行的失败明细放在 `data` 而不是 `detail`（如用例导出作业 429
   * 「已有导出任务在进行」带 `data: {task_id, status}`），丢弃会让页面无法接管在办任务。
   */
  data?: unknown
  /** 网络层失败（fetch 未到达服务端），userMessage 固定为网络文案 */
  isNetworkError?: boolean
}

/** 后端 code 可能为数字或数字字符串，统一归一为数字 */
function normalizeCode(code: unknown): ApiErrorCode | null {
  if (typeof code === 'number' && Number.isFinite(code)) return code as ApiErrorCode
  if (typeof code === 'string' && code.trim() !== '' && Number.isFinite(Number(code))) {
    return Number(code) as ApiErrorCode
  }
  return null
}

function resolveUserMessage(payload: {
  code: ApiErrorCode | null
  httpStatus: number | null
  message: string
  detail: unknown
  isNetworkError: boolean
}): string {
  if (payload.isNetworkError) return NETWORK_FAILED_COPY
  // 服务端 message/detail 已是中文时优先用服务端文案（INT-606 认证卡对照
  // §3.4：其他 detail → 「登录失败：{detail}」）；本映射用于服务端文案
  // 缺失/过于笼统时的统一收敛，故 message > 已知错误码兜底 > detail。
  if (payload.message) return payload.message
  if (payload.code != null && API_ERROR_COPY[payload.code]) {
    return API_ERROR_COPY[payload.code]!
  }
  if (typeof payload.detail === 'string' && payload.detail) return payload.detail
  if (payload.httpStatus != null && HTTP_STATUS_COPY[payload.httpStatus]) {
    return HTTP_STATUS_COPY[payload.httpStatus]
  }
  return '请求失败，请稍后重试'
}

export class ApiError extends Error {
  /** 领域业务错误码（响应无业务码时为 null；网络层失败亦为 null） */
  readonly code: ApiErrorCode | null
  /**
   * 服务端原始业务码的字符串形态（如 agent_service 的
   * `APPROVAL_CONFIRMATION_REQUIRED`）。`code` 只收平台数字码，非数字业务码
   * 保留在这里供调用方分流；无业务码时为 null。
   */
  readonly rawCode: string | null
  /** HTTP 状态码（网络层失败为 null） */
  readonly httpStatus: number | null
  /** 服务端原始 message（可为空） */
  readonly serverMessage: string
  /** 服务端原始 detail（可为任意结构） */
  readonly detail: unknown
  /** 服务端字段级错误（errors） */
  readonly errors: unknown
  /** 服务端错误响应体里的 data（失败明细；无则 undefined） */
  readonly data: unknown
  /** 网络层失败标记（fetch 未到达服务端） */
  readonly isNetworkError: boolean
  /** 可直接呈现的中文文案（错误码映射 > 服务端 message > detail > HTTP 兜底 > 网络兜底） */
  readonly userMessage: string

  constructor(payload: ApiErrorPayload) {
    const code = normalizeCode(payload.code)
    const rawCode =
      typeof payload.code === 'string' && payload.code.trim() !== ''
        ? payload.code.trim()
        : typeof payload.code === 'number' && Number.isFinite(payload.code)
          ? String(payload.code)
          : null
    const message = typeof payload.message === 'string' ? payload.message : ''
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.rawCode = rawCode
    this.httpStatus = payload.httpStatus ?? null
    this.serverMessage = message
    this.detail = payload.detail
    this.errors = payload.errors
    this.data = payload.data
    this.isNetworkError = payload.isNetworkError ?? false
    this.userMessage = resolveUserMessage({
      code,
      httpStatus: this.httpStatus,
      message,
      detail: payload.detail,
      isNetworkError: this.isNetworkError,
    })
  }
}
