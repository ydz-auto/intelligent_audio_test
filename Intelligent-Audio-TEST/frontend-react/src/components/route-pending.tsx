/**
 * 路由懒加载待定态（基座；INT-2392）。
 *
 * TanStack Router 在新路由的懒加载 chunk 未就绪时，只有目标路由（或 router）
 * 配置了 pendingComponent，才会把「待定 lane」呈现出来；两者都没有配置时，
 * `offerPending` 直接返回，旧的匹配继续渲染——表现就是「URL 变了、页面纹丝
 * 不动」（INT-2388 里连接被占满后点报告行的现象）。
 *
 * 本组件挂在 createRouter 的 defaultPendingComponent 上，覆盖全部路由：
 * - 位于父级 Outlet 内，认证壳的侧栏 / 头部保持可用，不遮挡到不可用；
 * - 文案与 Spinner 取自基座件（01_全局基座.md §加载 Spinner），不引入新样式值；
 * - 呈现时机由 defaultPendingMs / defaultPendingMinMs（见 app/router.ts）控制，
 *   正常网络下 chunk 早已就绪，不会出现闪烁。
 */
import { Spinner } from '@/components/ui/spinner'

export function RoutePending() {
  return (
    <div
      data-testid='route-pending'
      role='status'
      aria-live='polite'
      aria-busy='true'
      className='text-muted-foreground flex min-h-[50vh] w-full flex-1 flex-col items-center justify-center gap-3 px-6 py-12'
    >
      <Spinner size={24} className='text-primary' />
      <p className='text-sm'>页面加载中…</p>
    </div>
  )
}
