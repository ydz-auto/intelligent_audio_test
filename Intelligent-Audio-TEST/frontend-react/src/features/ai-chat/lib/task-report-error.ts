/**
 * 任务上下文 → 报告解析失败的可展示文案（INT-2473 返工 P2-2 残留）。
 *
 * 不能用 `error.message`：ApiError 在两条常见路径上 message 恒为空——
 * fetch 网络层失败（`infrastructure/api/client.ts` 显式 `message: ''`）与
 * 服务端错误体只给 `detail`（`buildApiError` 只读 `payload.message`）。
 * 空串会让面板的 `resolveError ?` 落到 else 分支，把「报告服务故障 / 断网」
 * 冒充成「该任务暂无关联报告」，正是 P2-2 要消除的「文案与事实相反」。
 *
 * 通用收敛见 `./api-error-message`（`resolveApiErrorMessage`）：本函数只是带着
 * 「任务关联报告解析失败」这条兜底文案的薄封装。
 */
import { resolveApiErrorMessage } from './api-error-message'

export const TASK_REPORT_RESOLVE_FALLBACK_COPY = '任务关联报告解析失败'

export function resolveTaskReportErrorMessage(error: unknown): string {
  return resolveApiErrorMessage(error, TASK_REPORT_RESOLVE_FALLBACK_COPY)
}
