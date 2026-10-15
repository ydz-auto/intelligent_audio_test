import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { LOGIN_BRAND_SLOGAN, MOCK_LOGIN_HINT } from '../constants'
import { UserAuthForm } from './components/user-auth-form'
import { cn } from '@/lib/utils'

/**
 * 登录页（对位 newAPI sign-in，12_登录与错误页.md §3.2/§3.3）：
 * 480 卡 + shadow-xl；标题「登录」左对齐。
 * 副行注册链接不落（注册页归 INT-357 卡）；服务端错误 toast 随 API 接线卡落。
 */
export function SignIn({
  className,
  redirectTo,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & { redirectTo?: string }) {
  return (
    <div className={cn('flex flex-col gap-6', className)} {...props}>
      <Card className='ring-border shadow-primary/5 w-full max-w-[480px] gap-0 py-0 shadow-xl'>
        <CardHeader className='space-y-1'>
          <CardTitle className='text-center text-2xl font-semibold tracking-tight sm:text-left'>
            登录
          </CardTitle>
          <CardDescription className='text-center text-sm sm:text-left'>
            {MOCK_LOGIN_HINT}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <UserAuthForm redirectTo={redirectTo} />
        </CardContent>
      </Card>
      <p className='text-muted-foreground text-center text-xs'>
        {LOGIN_BRAND_SLOGAN}
      </p>
    </div>
  )
}
