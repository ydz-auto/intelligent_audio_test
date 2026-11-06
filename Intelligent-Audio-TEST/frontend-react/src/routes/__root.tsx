import { Outlet, createRootRoute } from '@tanstack/react-router'

import { GeneralError } from '@/features/errors/general-error'
import { NotFoundError } from '@/features/errors/not-found-error'

/**
 * 根路由双兜底接线（12_登录与错误页.md §4.7）：
 * 未匹配路径 → 404 版式；未捕获渲染异常 → 500 版式。
 */
export const Route = createRootRoute({
  component: () => <Outlet />,
  notFoundComponent: () => <NotFoundError />,
  errorComponent: ({ error }) => <GeneralError error={error} />,
})
