/**
 * 跨路由 search 更新辅助（interfaces/features/test-execution/lib；10_测试执行.md §3.2）。
 * /E2ETest 与 /APITest 共用同一组件树，navigate 的 to 不固定——照 reports-showcase
 * cast 口径更新 URL search（step/view），刷新/回退/分享保持。
 */
import { useNavigate } from '@tanstack/react-router'

export type SearchNavigator = ReturnType<typeof useNavigate>

export function navigateWithSearch(
  navigate: SearchNavigator,
  patch: Record<string, unknown>
) {
  ;(navigate as unknown as (opts: {
    search: (prev: Record<string, unknown>) => Record<string, unknown>
  }) => void)({
    search: (prev) => ({ ...prev, ...patch }),
  })
}
