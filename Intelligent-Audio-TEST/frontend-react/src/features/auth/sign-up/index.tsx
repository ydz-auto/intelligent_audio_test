import { Link } from '@tanstack/react-router'

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from '@/components/ui/card'
import { MOCK_LOGIN_HINT } from '../constants'
import { UserRegisterForm } from './components/user-register-form'
import { cn } from '@/lib/utils'

/**
 * 注册页（对位 newAPI sign-up，12_登录与错误页.md §3.6）：
 * 版式同登录页（AuthLayout 共壳）；标题「创建账号」+ 副行「已有账户？登录」。
 * 403 引导态（注册开关关闭）由表单内切换呈现（§3.6）。
 */
export function SignUp({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn('flex w-full flex-col gap-6', className)} {...props}>
      <div className='space-y-2'>
        <h2 className='text-center text-2xl font-semibold tracking-tight sm:text-left'>
          创建账号
        </h2>
        <p className='text-muted-foreground text-left text-sm sm:text-base'>
          已有账户？{' '}
          <Link
            to='/login'
            className='hover:text-primary font-medium underline underline-offset-4'
          >
            登录
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
          <UserRegisterForm />
        </CardContent>
      </Card>
    </div>
  )
}
