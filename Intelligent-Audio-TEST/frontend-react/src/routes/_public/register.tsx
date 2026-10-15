import { createFileRoute, redirect } from '@tanstack/react-router'
import { z } from 'zod'

import { useAuthStore } from '@/infrastructure/stores/auth-store'
import AuthLayout from '@/features/auth/auth-layout'
import { SignUp } from '@/features/auth/sign-up'

const registerSearchSchema = z.object({})

/**
 * 注册页 /register（12_登录与错误页.md §3.1/§3.6）：
 * 已登录直接进控制台；注册开关关闭的 403 引导态在表单内切换。
 */
export const Route = createFileRoute('/_public/register')({
  validateSearch: registerSearchSchema,
  beforeLoad: () => {
    if (useAuthStore.getState().user) {
      throw redirect({ to: '/dashboard' })
    }
  },
  component: RegisterPage,
})

function RegisterPage() {
  return (
    <AuthLayout>
      <SignUp />
    </AuthLayout>
  )
}
