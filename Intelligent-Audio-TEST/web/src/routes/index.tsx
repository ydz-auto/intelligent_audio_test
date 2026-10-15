import { createFileRoute, redirect } from '@tanstack/react-router'

/** / → /dashboard（04_控制台.md §3.2 路径拍板；未登录由 _authenticated 守卫转 /login） */
export const Route = createFileRoute('/')({
  beforeLoad: () => {
    throw redirect({ to: '/dashboard' })
  },
})
