import { Link, useNavigate } from '@tanstack/react-router'
import { TriangleAlert } from 'lucide-react'

import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { LOGIN_BRAND_SLOGAN, AUTH_MODE_OFF_ALERT_TEXT, AUTH_MODE_OFF_ENTER_ACTION } from '../constants'
import { UserAuthForm } from './components/user-auth-form'
import { AuthAlert, AuthAlertTitle } from '../components/auth-alert'
import { AUTH_MODE, useAuthMode } from '@/application/auth/use-auth-mode'
import { cn } from '@/lib/utils'

/**
 * 登录页（对位 newAPI sign-in，12_登录与错误页.md §3.2/§3.3）：
 * 480 卡 + shadow-xl；标题「登录」左对齐 + 副行「没有账号？注册」（双页拆分）。
 * AUTH_MODE=off 开放模式 Alert（§3.1）在卡片上方渲染。
 */
export function SignIn({
  className,
  redirectTo,
  prefillUsername,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & {
  redirectTo?: string
  prefillUsername?: string
}) {
  const navigate = useNavigate()
  const { data: authMode } = useAuthMode()
  const isOpenMode = authMode === AUTH_MODE.OFF

  return (
    <div className={cn('flex w-full flex-col gap-6', className)} {...props}>
      {isOpenMode && (
        <AuthAlert>
          <TriangleAlert aria-hidden='true' />
          <div className='flex flex-wrap items-center justify-between gap-2'>
            <AuthAlertTitle>{AUTH_MODE_OFF_ALERT_TEXT}</AuthAlertTitle>
            <Button
              type='button'
              size='sm'
              onClick={() => navigate({ to: '/dashboard' })}
            >
              {AUTH_MODE_OFF_ENTER_ACTION}
            </Button>
          </div>
        </AuthAlert>
      )}
      <div className='space-y-2'>
        <h2 className='text-center text-2xl font-semibold tracking-tight sm:text-left'>
          登录
        </h2>
        <p className='text-muted-foreground text-left text-sm sm:text-base'>
          没有账号？{' '}
          <Link
            to='/register'
            className='hover:text-primary font-medium underline underline-offset-4'
          >
            注册
          </Link>
        </p>
      </div>
      <Card className='ring-border shadow-primary/5 w-full max-w-[480px] gap-0 py-0 shadow-xl'>
        <CardContent>
          <UserAuthForm
            redirectTo={redirectTo}
            prefillUsername={prefillUsername}
          />
        </CardContent>
      </Card>
      <p className='text-muted-foreground text-center text-xs'>
        {LOGIN_BRAND_SLOGAN}
      </p>
    </div>
  )
}
