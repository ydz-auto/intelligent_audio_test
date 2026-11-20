/**
 * 任意异常 → 可直接展示的中文文案（INT-2473 返工 P2-1）。
 *
 * 不能用 `error.message` 直接兜展示：`ApiError` 在两条常见路径上 message 恒为空——
 * fetch 网络层失败（`infrastructure/api/client.ts` 显式 `message: ''`）与
 * 服务端错误体只给 `detail`（`buildApiError` 只读 `payload.message`）。
 * 空串一旦被 `{saveError && …}` 这样的条件渲染吃到，写操作失败就**毫无反馈**
 * （保存 / 起草 / 恢复 / 导出都是这个坑）。
 *
 * `ApiError.userMessage` 已收敛「错误码 > 服务端 message > detail > HTTP 兜底 >
 * 网络兜底」且保证非空，故优先用它；非 ApiError 的异常沿用自身 message，
 * 仍为空时用调用方给的固定兜底文案（兜底必须是「操作名 + 请重试」这类可执行的话）。
 */
import { ApiError } from '@/infrastructure/api/api-error'

export function resolveApiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError) return error.userMessage || fallback
  if (error instanceof Error) return error.message || fallback
  return fallback
}
