import { zodResolver } from '@hookform/resolvers/zod'
import { useNavigate } from '@tanstack/react-router'
import { Loader2, LogIn } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'

import { PasswordInput } from '@/components/password-input'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { mockLogin, useAuthStore } from '@/infrastructure/stores/auth-store'
import { loginFormSchema, type LoginForm } from '@/features/auth/constants'
import { sanitizeAuthRedirect } from '@/features/auth/lib/auth-redirect'
import { cn } from '@/lib/utils'

/**
 * 登录表单（对位 newAPI UserAuthForm 精简版，12_登录与错误页.md §3.3）：
 * RHF + zodResolver；字段级校验内联、提交态 Loader2 +「登录中…」。
 * 不引入：忘记密码 / OAuth / Passkey / Turnstile / ALTCHA（§2.1 不引入清单）。
 */
export function UserAuthForm({
  className,
  redirectTo,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { redirectTo?: string }) {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const form = useForm<LoginForm>({
    resolver: zodResolver(loginFormSchema),
    defaultValues: { username: '', password: '' },
  })

  async function onSubmit(values: LoginForm) {
    // 红线④：mock 登录，任意账号密码可进
    // TODO(API 接线): 调 POST /auth/login（RSA 加密链路 + 错误码 toast 映射 §3.4）
    const user = mockLogin(values.username)
    setAuth(user)
    toast.success('登录成功')
    const target = redirectTo
      ? (sanitizeAuthRedirect(redirectTo, window.location.origin) ??
        '/dashboard')
      : '/dashboard'
    await navigate({ to: target })
  }

  return (
    <div className={cn('grid gap-4', className)} {...props}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className='grid gap-4'
        noValidate
      >
        <div className='grid gap-2'>
          <Label htmlFor='username'>用户名</Label>
          <Input
            id='username'
            placeholder='请输入用户名'
            autoComplete='username'
            {...form.register('username')}
          />
          {form.formState.errors.username && (
            <p className='text-destructive text-sm'>
              {form.formState.errors.username.message}
            </p>
          )}
        </div>
        <div className='grid gap-2'>
          <Label htmlFor='password'>密码</Label>
          <PasswordInput
            id='password'
            placeholder='请输入密码'
            autoComplete='current-password'
            {...form.register('password')}
          />
          {form.formState.errors.password && (
            <p className='text-destructive text-sm'>
              {form.formState.errors.password.message}
            </p>
          )}
        </div>
        <Button
          type='submit'
          className='mt-2 w-full justify-center gap-2'
          disabled={form.formState.isSubmitting}
        >
          {form.formState.isSubmitting ? (
            <>
              <Loader2 className='animate-spin' aria-hidden='true' />
              登录中…
            </>
          ) : (
            <>
              <LogIn aria-hidden='true' />
              登 录
            </>
          )}
        </Button>
      </form>
    </div>
  )
}
