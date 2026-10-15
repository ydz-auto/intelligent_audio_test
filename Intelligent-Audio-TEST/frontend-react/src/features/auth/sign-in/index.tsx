import { Link } from '@tanstack/react-router'

import { Card, CardContent, CardDescription, CardHeader } from '@/components/ui/card'
import { LOGIN_BRAND_SLOGAN, MOCK_LOGIN_HINT } from '../constants'
import { UserAuthForm } from './components/user-auth-form'
import { cn } from '@/lib/utils'

/**
 * 登录页（对位 newAPI sign-in，12_登录与错误页.md §3.2/§3.3）：
 * 480 卡 + shadow-xl；标题「登录」左对齐 + 副行「没有账号？注册」（双页拆分）。
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
  return (
    <div className={cn('flex w-full flex-col gap-6', className)} {...props}>
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
        <CardHeader className='space-y-1'>
          <CardDescription className='text-sm'>
            {MOCK_LOGIN_HINT}
          </CardDescription>
        </CardHeader>
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
