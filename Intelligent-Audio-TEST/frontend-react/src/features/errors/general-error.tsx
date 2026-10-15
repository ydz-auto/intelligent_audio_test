/*
Copyright (C) 2023-2026 QuantumNous

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program. If not, see <https://www.gnu.org/licenses/>.

For commercial licensing, please contact support@quantumnous.com
*/
import { useNavigate, useRouter } from '@tanstack/react-router'

import { ErrorState } from '@/components/error-state'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

type GeneralErrorProps = React.HTMLAttributes<HTMLDivElement> & {
  minimal?: boolean
  error?: unknown
}

function getHttpStatus(error: unknown): number | undefined {
  if (typeof error !== 'object' || error === null) return undefined
  const response = (error as Record<string, unknown>).response
  if (typeof response !== 'object' || response === null) return undefined
  const status = (response as Record<string, unknown>).status
  return typeof status === 'number' ? status : undefined
}

/**
 * 500 页面（newAPI 版式照搬；minimal 变体隐藏大数字与按钮组供内嵌复用；
 * 429 特判；ChunkLoadError 降级为 ErrorState）。
 * 去 newAPI 的 GitHub Issues 反馈外链（本平台无公开仓库）。
 */
export function GeneralError({
  className,
  minimal = false,
  error,
}: GeneralErrorProps) {
  const navigate = useNavigate()
  const { history } = useRouter()
  const status = getHttpStatus(error)
  if (
    error &&
    typeof error === 'object' &&
    (('name' in error && error.name === 'ChunkLoadError') ||
      ('code' in error && error.code === 'CSS_CHUNK_LOAD_FAILED') ||
      ('message' in error &&
        typeof error.message === 'string' &&
        /^(Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed)/.test(
          error.message
        )))
  ) {
    return (
      <div
        className={cn(
          'flex h-svh w-full items-center justify-center',
          className
        )}
      >
        <ErrorState
          title='页面加载失败'
          description='请检查网络连接后刷新页面重试。'
          action={
            <Button
              nativeButton={false}
              role='link'
              render={<a href={history.location.href} />}
            >
              刷新页面
            </Button>
          }
        />
      </div>
    )
  }
  const isRateLimited = status === 429
  const title = isRateLimited ? '请求过于频繁' : '糟糕！出错了'
  const description = isRateLimited ? '请稍候再试。' : '请稍后再试。'

  return (
    <div className={cn('h-svh w-full', className)}>
      <div className='m-auto flex h-full w-full flex-col items-center justify-center gap-2'>
        {!minimal && (
          <h1 className='text-[7rem] leading-tight font-bold'>
            {status ?? 500}
          </h1>
        )}
        <span className='font-medium'>{title}</span>
        <p className='text-muted-foreground text-center'>
          对于由此造成的不便，我们深表歉意。 <br /> {description}
        </p>
        {!minimal && (
          <div className='mt-6 flex flex-wrap justify-center gap-4'>
            <Button variant='outline' onClick={() => history.go(-1)}>
              返回
            </Button>
            <Button variant='outline' onClick={() => window.location.reload()}>
              刷新页面
            </Button>
            <Button onClick={() => navigate({ to: '/' })}>返回主页</Button>
          </div>
        )}
      </div>
    </div>
  )
}
