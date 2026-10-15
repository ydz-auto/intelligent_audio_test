import { Link } from '@tanstack/react-router'
import { Headphones } from 'lucide-react'

import { LOGIN_BRAND_NAME } from './constants'

/**
 * 认证布局（对位 newAPI auth-layout，12_登录与错误页.md §3.2）：
 * 左上角品牌角标（回首页）+ 主区居中；auth-shell 双光斑背景见
 * styles/index.css（随主题预设联动，lake-view 下为品牌绿光斑）。
 */
export default function AuthLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div className='auth-shell relative min-h-svh'>
      <div className='absolute top-4 left-4 sm:top-8 sm:left-8'>
        <Link
          to='/'
          className='inline-flex items-center gap-2 transition-opacity hover:opacity-80'
        >
          <div className='bg-primary/10 text-primary flex size-8 items-center justify-center rounded-lg'>
            <Headphones aria-hidden='true' className='size-4' />
          </div>
          <span className='font-semibold'>{LOGIN_BRAND_NAME}</span>
        </Link>
      </div>
      <div className='container flex min-h-svh items-center justify-center px-4 pt-24 pb-8 sm:py-24'>
        {children}
      </div>
    </div>
  )
}
