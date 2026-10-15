import { useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useNavigate } from '@tanstack/react-router'
import { Loader2, LogIn, TriangleAlert } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'

import { PasswordInput } from '@/components/password-input'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { AuthErrorCode } from '@/domain/models/auth'
import {
  encryptPassword,
  fetchEncryptionKey,
  MockAuthError,
  PasswordEncryptionUnavailableError,
  submitLoginMock,
} from '@/infrastructure/api/auth'
import { mockLogin, useAuthStore } from '@/infrastructure/stores/auth-store'
import {
  LOGIN_ERROR_COPY,
  MOCK_ERROR_HINT,
  loginFormSchema,
  type LoginForm,
} from '@/features/auth/constants'
import { sanitizeAuthRedirect } from '@/features/auth/lib/auth-redirect'
import { cn } from '@/lib/utils'

import { AuthAlert, AuthAlertTitle } from '../../components/auth-alert'
import { OAuthProviders } from '../../components/oauth-providers'

/**
 * 登录表单（对位 newAPI UserAuthForm，12_登录与错误页.md §3.3/§3.4/§3.5）：
 * RHF + zodResolver；OAuth 区在表单上方；三层错误分离——字段校验内联、
 * 服务端错误 sonner toast（106）、加密失败卡内 Alert（105/初始化失败）。
 * 不引入：忘记密码 / Passkey / Turnstile / ALTCHA（§2.1 不引入清单）。
 */
export function UserAuthForm({
  className,
  redirectTo,
  prefillUsername,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & {
  redirectTo?: string
  prefillUsername?: string
}) {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  /** 加密失败 Alert（105 / 初始化失败共用位；null=不渲染） */
  const [encryptionAlert, setEncryptionAlert] = useState<string | null>(null)
  const form = useForm<LoginForm>({
    resolver: zodResolver(loginFormSchema),
    defaultValues: { username: prefillUsername ?? '', password: '' },
  })

  async function onSubmit(values: LoginForm) {
    setEncryptionAlert(null)
    try {
      // RSA 加密链路桩：拿公钥 → 加密 → 提交（INT-188 禁明文回退语义占位）
      const publicKey = await fetchEncryptionKey()
      const { passwordEncrypted } = await encryptPassword(
        values.password,
        publicKey
      )
      await submitLoginMock(values.username, passwordEncrypted)

      // 红线④：mock 登录成功，任意账号密码可进
      // TODO(API 接线): POST /auth/login 回包 → authStore.login（拉 /auth/me 落 store）
      const user = mockLogin(values.username)
      setAuth(user)
      toast.success('欢迎回来！')
      const target = redirectTo
        ? (sanitizeAuthRedirect(redirectTo, window.location.origin) ??
          '/dashboard')
        : '/dashboard'
      await navigate({ to: target })
    } catch (error) {
      if (error instanceof PasswordEncryptionUnavailableError) {
        setEncryptionAlert(LOGIN_ERROR_COPY.encryptionInit)
        return
      }
      if (error instanceof MockAuthError) {
        if (error.code === AuthErrorCode.ENCRYPTION_INVALID) {
          // 105 ≠密码错误：不走 toast，卡内 Alert 引导刷新（§3.4）
          setEncryptionAlert(LOGIN_ERROR_COPY[AuthErrorCode.ENCRYPTION_INVALID])
          return
        }
        // 106 及其余服务端错误：sonner toast（handleServerError 对位）
        toast.error(LOGIN_ERROR_COPY[AuthErrorCode.CREDENTIALS_INVALID])
        return
      }
      toast.error(LOGIN_ERROR_COPY.network)
    }
  }

  return (
    <div className={cn('grid gap-4', className)} {...props}>
      {encryptionAlert && (
        <AuthAlert variant='destructive'>
          <TriangleAlert aria-hidden='true' />
          <AuthAlertTitle>{encryptionAlert}</AuthAlertTitle>
        </AuthAlert>
      )}
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className='grid gap-4'
        noValidate
      >
        <OAuthProviders disabled={form.formState.isSubmitting} />
        <div className='grid gap-2'>
          <Label htmlFor='username'>用户名或电子邮件</Label>
          <Input
            id='username'
            placeholder='请输入用户名或邮箱'
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
        <p className='text-muted-foreground text-center text-xs'>
          {MOCK_ERROR_HINT}
        </p>
      </form>
    </div>
  )
}
