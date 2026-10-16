/**
 * ① 开始使用引导卡（04_控制台.md §3.4，照 newAPI OverviewDashboard 设置引导卡双形态）：
 * 展开态（默认四步未全部完成时展开，localStorage 持久化）/ 折叠态横条。
 */
import { Link } from '@tanstack/react-router'
import {
  Check,
  ChevronDown,
  ChevronUp,
  ClipboardList,
  Copy,
  FileBarChart,
  Headphones,
  ListChecks,
  Music,
  Smartphone,
  Star,
  Terminal,
  type LucideIcon,
} from 'lucide-react'
import { motion, useReducedMotion } from 'motion/react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { IconBadge, type IconBadgeTone } from '@/components/ui/icon-badge'
import { usePermissions } from '@/application/hooks/use-permissions'
import type { SetupStep } from '@/application/dashboard/use-setup-guide'
import type { HomeStatsDetails } from '@/domain/models/home'
import { MOTION_TRANSITION } from '@/lib/motion'
import { cn } from '@/lib/utils'

import {
  CardStaggerContainer,
  CardStaggerItem,
} from './page-transition'

interface QuickAction {
  title: string
  description: string
  to: string
  icon: LucideIcon
  requiredPermission?: string
}

interface HeroSignal {
  label: string
  value: string
  icon: LucideIcon
  tone: IconBadgeTone
}

/** 背景光斑（newAPI SetupGuideBackdrop 逐类等价移植，accent 随预设 chart-1..3 联动） */
function SetupGuideBackdrop(props: { compact?: boolean }) {
  return (
    <>
      <div
        className={cn(
          'pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_48%_120%_at_78%_0%,color-mix(in_oklch,var(--overview-accent-1)_14%,transparent)_0%,transparent_62%),linear-gradient(112deg,color-mix(in_oklch,var(--card)_94%,var(--overview-accent-2)_6%)_0%,color-mix(in_oklch,var(--card)_94%,var(--overview-accent-3)_6%)_48%,color-mix(in_oklch,var(--background)_90%,var(--overview-accent-1)_10%)_100%)] dark:opacity-60',
          props.compact
            ? '[mask-image:linear-gradient(90deg,black_0%,black_48%,transparent_74%)] opacity-55'
            : 'opacity-85'
        )}
        aria-hidden='true'
      />
      <div
        className='from-background/35 to-background/70 dark:from-background/20 dark:to-background/80 pointer-events-none absolute inset-0 bg-linear-to-b via-transparent'
        aria-hidden='true'
      />
    </>
  )
}

function buildCurlCommand(taskId: number): string {
  const origin =
    typeof window === 'undefined' ? 'http://localhost:8000' : window.location.origin
  return [
    `curl "${origin}/api/v1/tasks/${taskId}/progress" \\`,
    '  -H "Accept: text/event-stream" \\',
    '  -H "Authorization: Bearer <token>"',
  ].join('\n')
}

/** 左列「接口驱动测试」卡（对位 newAPI RequestPreview，换本平台语义） */
function ApiPreviewCard(props: { signals: HeroSignal[] }) {
  const shouldReduceMotion = useReducedMotion()
  const [isCopying, setIsCopying] = useState(false)
  // TODO(API 接线): 示例任务 id 换真实最近任务；progress 为 SSE 订阅端点（首页卡 §3.6 同源）
  const previewLines = useMemo(
    () => buildCurlCommand(1042).split('\n'),
    []
  )

  const handleCopy = async () => {
    if (isCopying) return
    setIsCopying(true)
    try {
      await navigator.clipboard.writeText(previewLines.join('\n'))
      toast.success('已复制')
    } catch {
      toast.error('复制失败')
    } finally {
      setIsCopying(false)
    }
  }

  return (
    <motion.div
      initial={shouldReduceMotion ? false : { opacity: 0, y: 10, scale: 0.98 }}
      animate={shouldReduceMotion ? undefined : { opacity: 1, y: 0, scale: 1 }}
      transition={MOTION_TRANSITION.slow}
      className='bg-background/75 relative overflow-hidden rounded-2xl border p-3 shadow-sm backdrop-blur'
    >
      {!shouldReduceMotion && (
        <motion.div
          className='via-foreground/30 pointer-events-none absolute inset-x-0 top-0 h-px bg-linear-to-r from-transparent to-transparent'
          animate={{ x: ['-100%', '100%'] }}
          transition={{ duration: 3.2, repeat: Infinity, ease: 'easeInOut' }}
          aria-hidden='true'
        />
      )}

      <div className='space-y-3 border-b pb-4'>
        <h3 className='text-base font-semibold'>通过 API 驱动测试</h3>
        <p className='text-muted-foreground text-sm leading-relaxed'>
          平台全部能力开放为 REST 与 SSE
          接口：创建任务、订阅进度、拉取报告，脚本化集成与页面操作同样简单。
        </p>
        <Button render={<Link to='/start-test' />}>开始测试</Button>
      </div>

      <Collapsible className='my-3 space-y-3'>
        <CollapsibleTrigger
          render={
            <Button
              variant='ghost'
              className='text-muted-foreground w-full justify-between text-xs'
            />
          }
        >
          开发者 API 示例
          <ChevronDown aria-hidden className='size-4' />
        </CollapsibleTrigger>
        <CollapsibleContent>
          <div className='flex items-center justify-between gap-3 border-b pb-3'>
            <div className='flex min-w-0 items-center gap-2'>
              <IconBadge tone='info'>
                <Terminal />
              </IconBadge>
              <div className='min-w-0'>
                <div className='truncate text-sm font-medium'>首个 API 请求</div>
                <div className='text-muted-foreground truncate text-xs'>
                  订阅任务执行进度（SSE）
                </div>
              </div>
            </div>
            <Button
              variant='outline'
              size='sm'
              className='h-7 gap-1.5 px-2 text-xs'
              disabled={isCopying}
              onClick={handleCopy}
              aria-label='复制 curl 示例'
            >
              <Copy data-icon='inline-start' />
              {isCopying ? '复制中…' : '复制 curl'}
            </Button>
          </div>

          <div className='bg-foreground/[0.035] my-3 rounded-xl p-3 font-mono text-xs'>
            <div className='mb-2 flex items-center gap-1.5'>
              <span className='bg-destructive size-2 rounded-full' />
              <span className='bg-warning size-2 rounded-full' />
              <span className='bg-success size-2 rounded-full' />
            </div>
            <div className='flex flex-col gap-1 overflow-hidden'>
              {previewLines.map((line) => (
                <code
                  key={line}
                  className='text-muted-foreground truncate'
                  title={line}
                >
                  {line}
                </code>
              ))}
            </div>
          </div>
        </CollapsibleContent>
      </Collapsible>

      <div className='grid gap-2'>
        {props.signals.map((signal) => {
          const Icon = signal.icon

          return (
            <div
              key={signal.label}
              className='bg-muted/40 flex items-center justify-between gap-3 rounded-xl px-3 py-2'
            >
              <span className='flex min-w-0 items-center gap-2'>
                <IconBadge tone={signal.tone} size='xs'>
                  <Icon />
                </IconBadge>
                <span className='truncate text-xs font-medium'>
                  {signal.label}
                </span>
              </span>
              <span className='text-muted-foreground shrink-0 text-xs'>
                {signal.value}
              </span>
            </div>
          )
        })}
      </div>
    </motion.div>
  )
}

function QuickActionItem(props: { action: QuickAction }) {
  const Icon = props.action.icon

  return (
    <Button
      variant='outline'
      className='h-auto justify-start rounded-xl px-3 py-3 text-left'
      render={<Link to={props.action.to} />}
    >
      <span className='bg-muted flex size-9 shrink-0 items-center justify-center rounded-lg'>
        <Icon className='size-4' aria-hidden='true' />
      </span>
      <span className='flex min-w-0 flex-1 flex-col gap-0.5'>
        <span className='truncate text-sm font-medium'>{props.action.title}</span>
        <span className='text-muted-foreground line-clamp-2 text-xs leading-relaxed'>
          {props.action.description}
        </span>
      </span>
    </Button>
  )
}

function CompactQuickAction(props: { action: QuickAction }) {
  const Icon = props.action.icon

  return (
    <Button
      variant='outline'
      size='sm'
      className='bg-background/70 h-8 min-w-24 gap-1.5 px-2.5'
      render={<Link to={props.action.to} />}
    >
      <Icon data-icon='inline-start' />
      <span>{props.action.title}</span>
    </Button>
  )
}

const ALL_QUICK_ACTIONS: QuickAction[] = [
  {
    title: '开始测试',
    description: '选用例 + 设备/API，同一流程完成测试',
    to: '/start-test',
    icon: Smartphone,
    requiredPermission: 'task:execute',
  },
  {
    title: '任务管理',
    description: '跟踪执行进度与历史任务',
    to: '/tasks',
    icon: ClipboardList,
    requiredPermission: 'task:read',
  },
  {
    title: '用例管理',
    description: '创建或导入测试用例',
    to: '/testcases',
    icon: ListChecks,
    requiredPermission: 'testcase:read',
  },
  {
    title: '音频管理',
    description: '导入干音、噪声与提示音频',
    to: '/audio-import',
    icon: Music,
    requiredPermission: 'audio:read',
  },
  {
    title: '设备管理',
    description: '接入真机或播放设备',
    to: '/devices',
    icon: Headphones,
    requiredPermission: 'device:read',
  },
  {
    title: '报告中心',
    description: '分析评估结果',
    to: '/reports',
    icon: FileBarChart,
    requiredPermission: 'report:read',
  },
  {
    title: '评估维度',
    description: '维护评估维度与评分端点',
    to: '/Evaluation',
    icon: Star,
    requiredPermission: 'evaluation:read',
  },
]

export interface SetupGuideProps {
  steps: SetupStep[]
  completedCount: number
  expanded: boolean
  details?: HomeStatsDetails
  onToggle: () => void
}

export function SetupGuide(props: SetupGuideProps) {
  const { hasPermission } = usePermissions()

  const visibleQuickActions = useMemo(
    () =>
      ALL_QUICK_ACTIONS.filter(
        (action) =>
          !action.requiredPermission || hasPermission(action.requiredPermission)
      ),
    [hasPermission]
  )

  const signals = useMemo<HeroSignal[]>(
    () => [
      {
        label: '设备接入',
        value: `${props.details?.devices.online ?? 0} 台在线`,
        icon: Headphones,
        tone: 'info',
      },
      {
        label: '用例就绪',
        value: `${props.details?.test_cases.total ?? 0} 条`,
        icon: ListChecks,
        tone: 'success',
      },
      {
        label: '报告产出',
        value: `${props.details?.reports ?? 0} 份`,
        icon: FileBarChart,
        tone: 'chart-4',
      },
    ],
    [props.details]
  )

  if (!props.expanded) {
    return (
      <CardStaggerContainer>
        <CardStaggerItem className='bg-card overflow-hidden rounded-2xl border shadow-xs'>
          <div className='relative overflow-hidden px-4 py-3 sm:px-5'>
            <SetupGuideBackdrop compact />
            <div className='relative flex flex-wrap items-center justify-between gap-3'>
              <div className='flex min-w-0 items-center gap-3'>
                <span className='bg-background/70 flex size-9 shrink-0 items-center justify-center rounded-xl border shadow-xs'>
                  <Check className='text-success size-4' aria-hidden='true' />
                </span>
                <div className='min-w-0'>
                  <div className='flex items-center gap-2'>
                    <h3 className='truncate text-sm font-semibold'>开始使用</h3>
                    <span className='text-muted-foreground bg-background/60 rounded-md border px-2 py-0.5 text-xs'>
                      已完成 {props.completedCount}/{props.steps.length}
                    </span>
                  </div>
                  <p className='text-muted-foreground line-clamp-1 text-xs'>
                    引导已收起，随时可再次展开。
                  </p>
                </div>
              </div>

              <div className='flex flex-wrap items-center gap-2'>
                {visibleQuickActions.slice(0, 4).map((action) => (
                  <CompactQuickAction key={action.title} action={action} />
                ))}
                <Button
                  variant='outline'
                  size='sm'
                  className='bg-background/70 h-8 min-w-28'
                  aria-expanded={false}
                  onClick={props.onToggle}
                >
                  <ChevronDown data-icon='inline-start' />
                  显示引导
                </Button>
              </div>
            </div>
          </div>
        </CardStaggerItem>
      </CardStaggerContainer>
    )
  }

  return (
    <CardStaggerContainer className='grid items-stretch gap-4'>
      <CardStaggerItem className='bg-card h-full overflow-hidden rounded-2xl border shadow-xs'>
        <div className='relative h-full overflow-hidden p-4 sm:p-5'>
          <SetupGuideBackdrop />
          <div className='relative grid gap-5 lg:grid-cols-[21rem_minmax(0,1fr)]'>
            <ApiPreviewCard signals={signals} />
            <div className='flex min-w-0 flex-col gap-4'>
              <div className='flex flex-wrap items-start justify-between gap-3'>
                <div className='flex flex-col gap-1'>
                  <div className='text-muted-foreground text-xs font-medium tracking-wider uppercase'>
                    推荐操作
                  </div>
                  <h3 className='text-lg font-semibold tracking-tight'>
                    让平台保持就绪
                  </h3>
                </div>
                <Button
                  variant='outline'
                  size='sm'
                  aria-expanded={true}
                  onClick={props.onToggle}
                >
                  <ChevronUp data-icon='inline-start' />
                  隐藏引导
                </Button>
              </div>
              <div className='grid gap-2'>
                {visibleQuickActions.map((action) => (
                  <QuickActionItem key={action.title} action={action} />
                ))}
              </div>
            </div>
          </div>
        </div>
      </CardStaggerItem>
    </CardStaggerContainer>
  )
}
