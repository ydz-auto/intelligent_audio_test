/**
 * 步骤一：选择算法（interfaces/features/test-execution/components；10_测试执行.md §3.4）。
 * 双通道：搜索选择器（Popover+Input 检索，照 model-group-selector 单列变体）+「浏览全部」
 * 切卡片网格；选中即写回全局算法 store（§3.3 双向同步）；汇总行 + 空态 starter。
 * readOnly（§3.1.1）：选择器/卡网格只读可见；选择/写回/新增算法隐藏。
 */
import { Box, Check, ChevronsUpDown, Settings2, Cpu } from 'lucide-react'
import { useMemo, useState } from 'react'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useAlgorithmChannel } from '@/application/test-execution/useAlgorithmChannel'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { Input } from '@/components/ui/input'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { cn } from '@/lib/utils'
import type { TestAlgorithmOption } from '@/infrastructure/mock/test-execution-mock'

interface StepAlgorithmProps {
  readOnly: boolean
  onOpenAlgorithmDetail: (algorithm: TestAlgorithmOption) => void
  onGoAlgorithmConfig: () => void
}

export function StepAlgorithm({
  readOnly,
  onOpenAlgorithmDetail,
  onGoAlgorithmConfig,
}: StepAlgorithmProps) {
  const { hasPermission } = usePermissions()
  const { current, enabledOptions, selectAlgorithm } = useAlgorithmChannel()
  const [mode, setMode] = useState<'selector' | 'grid'>('selector')
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)

  const canManageAlgorithms = hasPermission('algorithm:definition_manage')
  const canViewConfig = hasPermission('algorithm:read')

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return enabledOptions
    return enabledOptions.filter(
      (a) => a.name.toLowerCase().includes(q) || a.group.toLowerCase().includes(q)
    )
  }, [enabledOptions, query])

  if (enabledOptions.length === 0) {
    return (
      <Empty className='min-h-[280px] border-dashed'>
        <EmptyHeader>
          <EmptyMedia variant='icon'>
            <Box className='size-4' />
          </EmptyMedia>
          <EmptyTitle>暂无可用算法</EmptyTitle>
          <EmptyDescription>
            请先在算法配置中完成算法定义，再回到这里开始测试
          </EmptyDescription>
        </EmptyHeader>
        {!readOnly && canManageAlgorithms && (
          <EmptyContent>
            <Button size='sm' onClick={onGoAlgorithmConfig}>
              前往算法配置
            </Button>
          </EmptyContent>
        )}
      </Empty>
    )
  }

  return (
    <div className='space-y-4'>
      {/* 工具行 */}
      <div className='flex flex-wrap items-center gap-2'>
        {!readOnly ? (
          <Popover
            open={open}
            onOpenChange={(next) => {
              setOpen(next)
              if (!next) setQuery('')
            }}
          >
            <PopoverTrigger
              render={
                <Button
                  variant='outline'
                  size='sm'
                  className='h-8 max-w-56 gap-1.5 px-2.5 font-normal'
                  aria-label='选择测试算法'
                />
              }
            >
              <Cpu aria-hidden='true' className='size-4' />
              <span className='min-w-0 max-w-40 truncate'>
                {current ? current.name : '选择算法'}
              </span>
              <ChevronsUpDown aria-hidden='true' className='size-3.5 shrink-0' />
            </PopoverTrigger>
            <PopoverContent align='start' className='w-[22rem] p-2'>
              <div className='relative'>
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder='搜索算法名称…'
                  className='h-8'
                  autoFocus
                />
              </div>
              <div className='mt-1 max-h-64 overflow-auto'>
                {filtered.length === 0 ? (
                  <p className='text-muted-foreground px-3 py-6 text-center text-sm'>
                    未找到匹配算法
                  </p>
                ) : (
                  filtered.map((algorithm) => (
                    <button
                      key={algorithm.id}
                      type='button'
                      className={cn(
                        'hover:bg-accent flex w-full items-center justify-between gap-2 rounded-md px-2 py-1.5 text-start text-sm transition-colors',
                        algorithm.id === current?.id && 'bg-accent'
                      )}
                      onClick={() => {
                        selectAlgorithm(algorithm.id)
                        setOpen(false)
                      }}
                    >
                      <span className='min-w-0'>
                        <span className='block truncate font-medium'>
                          {algorithm.name}
                          <span className='text-muted-foreground ms-2 text-xs font-normal'>
                            v{algorithm.version}
                          </span>
                        </span>
                        <span className='text-muted-foreground block truncate text-xs'>
                          {algorithm.description}
                        </span>
                      </span>
                      <Badge variant='secondary'>{algorithm.group}</Badge>
                      {algorithm.id === current?.id && (
                        <Check aria-hidden='true' className='size-4 shrink-0' />
                      )}
                    </button>
                  ))
                )}
              </div>
            </PopoverContent>
          </Popover>
        ) : (
          <Button variant='outline' size='sm' className='pointer-events-none h-8 px-2.5 font-normal' aria-hidden='true'>
            <Cpu aria-hidden='true' className='size-4' />
            <span className='min-w-0 max-w-40 truncate'>{current ? current.name : '选择算法'}</span>
            <ChevronsUpDown aria-hidden='true' className='size-3.5 shrink-0' />
          </Button>
        )}

        {/* 浏览全部/收起（tabs 胶囊） */}
        <div className='bg-muted text-muted-foreground flex items-center rounded-lg p-0.5 text-xs'>
          <button
            type='button'
            className={cn(
              'rounded-md px-2.5 py-1 transition-colors',
              mode === 'selector' && 'bg-background text-foreground shadow-sm'
            )}
            onClick={() => setMode('selector')}
          >
            搜索
          </button>
          <button
            type='button'
            className={cn(
              'rounded-md px-2.5 py-1 transition-colors',
              mode === 'grid' && 'bg-background text-foreground shadow-sm'
            )}
            onClick={() => setMode('grid')}
          >
            浏览全部
          </button>
        </div>

        {!readOnly && canManageAlgorithms && (
          <Button variant='outline' size='sm' className='ml-auto' onClick={onGoAlgorithmConfig}>
            新增算法
          </Button>
        )}
      </div>

      {/* 双通道内容 */}
      {mode === 'selector' ? (
        <div className='mx-auto w-full max-w-5xl'>
          {current && (
            <div className='border-primary/40 bg-primary/5 rounded-lg border p-3 text-sm'>
              <span className='flex flex-wrap items-center gap-2'>
                <span className='font-medium'>当前算法：{current.name}</span>
                <Badge variant='outline'>分组 {current.group}</Badge>
                <Badge variant='secondary' className='rounded-md text-[11px]'>
                  v{current.version}
                </Badge>
                <StatusBadge label='已同步全局算法' variant='info' />
                {canViewConfig && (
                  <button
                    type='button'
                    className='text-primary ml-auto text-xs underline-offset-3 hover:underline'
                    onClick={() => onOpenAlgorithmDetail(current)}
                  >
                    查看参数定义
                  </button>
                )}
              </span>
            </div>
          )}
          {!current && (
            <p className='text-muted-foreground py-10 text-center text-sm'>
              通过搜索选择本次测试使用的算法，或切换「浏览全部」从卡片网格中选择
            </p>
          )}
        </div>
      ) : (
        <div className='mx-auto grid w-full max-w-5xl gap-3 sm:grid-cols-2 lg:grid-cols-3'>
          {enabledOptions.map((algorithm) => {
            const selected = algorithm.id === current?.id
            return (
              <div
                key={algorithm.id}
                className={cn(
                  'flex flex-col gap-2 rounded-xl border p-4 transition-colors',
                  selected && 'border-primary ring-primary/20 ring-2',
                  !selected && 'border-border hover:bg-muted/30'
                )}
              >
                <div className='flex items-start gap-3'>
                  <span className='bg-primary/10 text-primary flex size-10 shrink-0 items-center justify-center rounded-lg'>
                    <Box aria-hidden='true' className='size-5' />
                  </span>
                  <span className='min-w-0 flex-1'>
                    <span className='flex items-center gap-1.5 font-medium'>
                      <span className='truncate'>{algorithm.name}</span>
                      <Badge variant='outline' className='shrink-0 text-[11px]'>
                        {algorithm.group}
                      </Badge>
                    </span>
                    <span className='text-muted-foreground mt-0.5 block truncate text-xs'>
                      v{algorithm.version}
                    </span>
                  </span>
                  {canViewConfig && (
                    <button
                      type='button'
                      aria-label={`查看 ${algorithm.name} 配置`}
                      className='text-muted-foreground hover:bg-accent hover:text-foreground rounded-md p-1'
                      onClick={() => onOpenAlgorithmDetail(algorithm)}
                    >
                      <Settings2 aria-hidden='true' className='size-4' />
                    </button>
                  )}
                </div>
                <p className='text-muted-foreground line-clamp-1 text-xs'>
                  {algorithm.description}
                </p>
                {!readOnly && (
                  <Button
                    variant={selected ? 'secondary' : 'outline'}
                    size='sm'
                    className='mt-auto'
                    onClick={() => selectAlgorithm(algorithm.id)}
                  >
                    {selected ? '已选择' : '选择'}
                  </Button>
                )}
                {readOnly && selected && (
                  <span className='text-primary flex items-center gap-1 text-xs font-medium'>
                    <Check aria-hidden='true' className='size-3.5' />
                    已同步全局算法
                  </span>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
