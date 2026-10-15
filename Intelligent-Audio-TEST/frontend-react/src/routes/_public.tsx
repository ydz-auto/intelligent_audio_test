import { Outlet, createFileRoute } from '@tanstack/react-router'

/** 公开页无路径布局组（登录页等，不挂控制台壳） */
export const Route = createFileRoute('/_public')({
  component: () => <Outlet />,
})
