import { Link, useNavigate } from '@tanstack/react-router'
import {
  ArrowUpRight,
  BookOpen,
  Code2,
  FileBarChart,
  Shield,
} from 'lucide-react'
import { useEffect, useState } from 'react'

import { usePermissions } from '@/application/hooks/use-permissions'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

/**
 * 文档链接卡组（06_关于.md §3.1.2）：
 * 使用手册 /user-guide、API 手册 /user-guide-api（公开）；
 * 报告中心 /reports（未登录「需要登录」Dialog / guest 可读 / device_admin 403 守卫）；
 * 权限说明 docs/RBAC权限划分.md（仓库内文档路径，暂不可点——不杜撰站内锚点）。
 */

const AUTH_PROMPT_SECONDS = 5

type LinkItem = {
  title: string
  desc: string
  icon: typeof BookOpen
  href?: string
  repoPath?: string
  guarded?: boolean
}

const LINKS: LinkItem[] = [
  {
    title: '使用手册',
    desc: '首次使用与功能操作指引',
    icon: BookOpen,
    href: '/user-guide',
  },
  {
    title: 'API 手册',
    desc: '接口认证、示例与错误码',
    icon: Code2,
    href: '/user-guide-api',
  },
  {
    title: '报告中心',
    desc: '查看测试报告与历史报告',
    icon: FileBarChart,
    href: '/reports',
    guarded: true,
  },
  {
    title: '权限说明',
    desc: '角色与权限说明',
    icon: Shield,
    repoPath: 'docs/RBAC权限划分.md',
  },
]

/** 「需要登录」对话框（06_关于.md §6 / 02_导航栏.md §3.10：5 秒倒计时跳登录页） */
function NeedLoginDialog({
  open,
  onOpenChange,
  moduleName,
  redirectTo,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  moduleName: string
  redirectTo: string
}) {
  const navigate = useNavigate()
  const [seconds, setSeconds] = useState(AUTH_PROMPT_SECONDS)

  useEffect(() => {
    if (!open) return
    setSeconds(AUTH_PROMPT_SECONDS)
    const timer = window.setInterval(() => {
      setSeconds((current) => current - 1)
    }, 1000)
    return () => window.clearInterval(timer)
  }, [open])

  useEffect(() => {
    if (!open || seconds > 0) return
    onOpenChange(false)
    void navigate({ to: '/login', search: { redirect: redirectTo } })
  }, [open, seconds, navigate, onOpenChange, redirectTo])

  const goLogin = () => {
    onOpenChange(false)
    void navigate({ to: '/login', search: { redirect: redirectTo } })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>需要登录</DialogTitle>
          <DialogDescription>请登录后查看 {moduleName}。</DialogDescription>
        </DialogHeader>
        <div className='bg-muted/40 rounded-lg px-3 py-2 text-sm'>
          将在 {Math.max(seconds, 0)} 秒后跳转到登录页。
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button onClick={goLogin}>立即登录</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function AboutLinks() {
  const navigate = useNavigate()
  const { user, hasPermission } = usePermissions()
  const [needLogin, setNeedLogin] = useState(false)

  const handleLinkClick = (item: LinkItem) => (event: React.MouseEvent) => {
    if (!item.guarded) {
      return // 公开链接走 TanStack Link 客户端导航
    }
    event.preventDefault()
    if (!user) {
      setNeedLogin(true)
      return
    }
    if (hasPermission('report:read')) {
      void navigate({ to: '/reports' })
    } else {
      void navigate({ to: '/403', search: { from: '/reports' } })
    }
  }

  return (
    <Card>
      <CardHeader className='[.border-b]:pb-4'>
        <CardTitle className='text-sm font-semibold'>文档链接</CardTitle>
      </CardHeader>
      <CardContent className='space-y-0'>
        {LINKS.map((item) => {
          const Icon = item.icon
          return (
            <div
              key={item.title}
              className='border-border/60 flex items-start gap-3 border-b py-3 last:border-0'
            >
              <Icon
                aria-hidden='true'
                className='text-muted-foreground mt-0.5 size-4 shrink-0'
              />
              <div className='min-w-0 flex-1'>
                {item.href ? (
                  <Link
                    to={item.href}
                    onClick={handleLinkClick(item)}
                    className={cn(
                      'text-primary inline-flex items-center gap-1 text-sm font-medium hover:underline',
                      item.guarded &&
                        !user &&
                        'cursor-pointer'
                    )}
                  >
                    {item.title}
                    <ArrowUpRight
                      aria-hidden='true'
                      className='text-muted-foreground size-3.5'
                    />
                  </Link>
                ) : (
                  <span className='text-muted-foreground text-sm'>
                    {item.title}
                  </span>
                )}
                <p className='text-muted-foreground mt-0.5 text-xs leading-5'>
                  {item.desc}
                  {item.repoPath && (
                    <>
                      {' · '}
                      <code className='text-muted-foreground font-mono text-xs'>
                        {item.repoPath}
                      </code>
                      <span>
                        {' '}
                        （仓库内文档，待站点文档托管立项后提供站内链接）
                      </span>
                    </>
                  )}
                </p>
              </div>
            </div>
          )
        })}
      </CardContent>
      <NeedLoginDialog
        open={needLogin}
        onOpenChange={setNeedLogin}
        moduleName='报告中心'
        redirectTo='/reports'
      />
    </Card>
  )
}
