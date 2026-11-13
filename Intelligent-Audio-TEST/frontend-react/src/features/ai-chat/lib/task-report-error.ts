/**
 * 任务上下文 → 报告解析失败的可展示文案（INT-2473 返工 P2-2 残留）。
 *
 * 不能用 `error.message`：ApiError 在两条常见路径上 message 恒为空——
 * fetch 网络层失败（`infrastructure/api/client.ts` 显式 `message: ''`）与
 * 服务端错误体只给 `detail`（`buildApiError` 只读 `payload.message`）。
 * 空串会让面板的 `resolveError ?` 落到 else 分支，把「报告服务故障 / 断网」
 * 冒充成「该任务暂无关联报告」，正是 P2-2 要消除的「文案与事实相反」。
 *
 * `ApiError.userMessage` 已收敛「错误码 > 服务端 message > detail > HTTP 兜底 >
 * 网络兜底」且保证非空，故优先用它；非 ApiError 的异常沿用自身 message，
 * 仍为空时给固定兜底文案。
 */
import { ApiError } from '@/infrastructure/api/api-error'

export const TASK_REPORT_RESOLVE_FALLBACK_COPY = '任务关联报告解析失败'

export function resolveTaskReportErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return error.userMessage || TASK_REPORT_RESOLVE_FALLBACK_COPY
  }
  if (error instanceof Error) {
    return error.message || TASK_REPORT_RESOLVE_FALLBACK_COPY
  }
  return TASK_REPORT_RESOLVE_FALLBACK_COPY
}
