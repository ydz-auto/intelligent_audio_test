import { useState } from 'react'
import { zodResolver } from '@hookform/resolvers/zod'
import { useNavigate } from '@tanstack/react-router'
import { Loader2, UserPlus } from 'lucide-react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'

import { PasswordInput } from '@/components/password-input'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { submitRegisterMock } from '@/infrastructure/api/auth'
import {
  MOCK_ERROR_HINT,
  registerFormSchema,
  type RegisterForm,
} from '@/features/auth/constants'
import { cn } from '@/lib/utils'

/**
 * 注册表单（对位 newAPI sign-up-form，12_登录与错误页.md §3.6）：
 * 四字段 RHF+zod；成功 toast + 切回 /login 预填用户名；
 * 403（注册开关关闭）切引导态；密码与登录同链（RSA 桩平移）。
 */
export function UserRegisterForm({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  const navigate = useNavigate()
  const [closed, setClosed] = useState(false)
  const form = useForm<RegisterForm>({
    resolver: zodResolver(registerFormSchema),
    defaultValues: {
      username: '',
      email: '',
      password: '',
      confirmPassword: '',
    },
  })

  async function onSubmit(values: RegisterForm) {
    try {
      // TODO(API 接线): 密码 RSA 加密同登录链；POST /auth/register
      await submitRegisterMock(values.username)
      toast.success('注册成功，请登录')
      await navigate({ to: '/login', search: { username: values.username } })
    } catch {
      if (form.getValues('username') === 'closed') {
        // 403：注册开关关闭 → 引导态（§3.6）
        toast.error('当前站点未开放注册，请联系管理员开通账号')
        setClosed(true)
        return
      }
      // 400/409：detail 文案（mock 统一口径）
      toast.error('注册失败：用户名或邮箱已被使用')
    }
  }

  if (closed) {
    return (
      <div className={cn('grid gap-4', className)} {...props}>
        <p className='text-sm font-medium'>当前站点未开放注册</p>
        <p className='text-muted-foreground text-sm'>
          请联系管理员开通账号后使用密码登录。
        </p>
        <Button
          type='button'
          variant='outline'
          className='w-full justify-center'
          onClick={() => navigate({ to: '/login' })}
        >
          返回登录
        </Button>
      </div>
    )
  }

  return (
    <div className={cn('grid gap-4', className)} {...props}>
      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className='grid gap-4'
        noValidate
      >
        <div className='grid gap-2'>
          <Label htmlFor='register-username'>用户名</Label>
          <Input
            id='register-username'
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
          <Label htmlFor='register-email'>邮箱</Label>
          <Input
            id='register-email'
            type='email'
            placeholder='请输入邮箱'
            autoComplete='email'
            {...form.register('email')}
          />
          {form.formState.errors.email && (
            <p className='text-destructive text-sm'>
              {form.formState.errors.email.message}
            </p>
          )}
        </div>
        <div className='grid gap-2'>
          <Label htmlFor='register-password'>密码</Label>
          <PasswordInput
            id='register-password'
            placeholder='请输入密码（至少 6 位）'
            autoComplete='new-password'
            {...form.register('password')}
          />
          {form.formState.errors.password && (
            <p className='text-destructive text-sm'>
              {form.formState.errors.password.message}
            </p>
          )}
        </div>
        <div className='grid gap-2'>
          <Label htmlFor='register-confirm'>确认密码</Label>
          <PasswordInput
            id='register-confirm'
            placeholder='请再次输入密码'
            autoComplete='new-password'
            {...form.register('confirmPassword')}
          />
          {form.formState.errors.confirmPassword && (
            <p className='text-destructive text-sm'>
              {form.formState.errors.confirmPassword.message}
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
              注册中…
            </>
          ) : (
            <>
              <UserPlus aria-hidden='true' />
              注 册
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
