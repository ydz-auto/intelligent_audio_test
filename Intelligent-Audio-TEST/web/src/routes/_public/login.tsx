import { createFileRoute, redirect } from '@tanstack/react-router'
import { z } from 'zod'

import { useAuthStore } from '@/infrastructure/stores/auth-store'
import AuthLayout from '@/features/auth/auth-layout'
import { SignIn } from '@/features/auth/sign-in'

const loginSearchSchema = z.object({ redirect: z.string().optional() })

/**
 * 登录页 /login（12_登录与错误页.md §3.1）：
 * search 携带 redirect；已登录直接进控制台，不重复渲染表单。
 */
export const Route = createFileRoute('/_public/login')({
  validateSearch: loginSearchSchema,
  beforeLoad: () => {
    if (useAuthStore.getState().user) {
      throw redirect({ to: '/dashboard' })
    }
  },
  component: LoginPage,
})

function LoginPage() {
  const { redirect: redirectTo } = Route.useSearch()
  return (
    <AuthLayout>
      <SignIn redirectTo={redirectTo} />
    </AuthLayout>
  )
}
