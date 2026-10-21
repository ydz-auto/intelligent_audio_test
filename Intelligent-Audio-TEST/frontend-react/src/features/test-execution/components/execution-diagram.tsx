/**
 * 底部并行/串行示意图（interfaces/features/test-execution/components；10_测试执行.md
 * §3.6.4，INT-1119 2026-10-21）。随「选中目标 + 每卡模式」实时更新，展示当前配置下
 * 哪些目标并行（同阶段并发）、哪些串行（依次排队）。语义对齐 INT-1115 引擎调度：
 * 并行目标启动即并发、不受门控；串行目标仅当其全部前序目标（含前序并行目标）终态后
 * 才派发；两个串行目标不重叠。并行=同组并列+无箭头+success 色系；串行=箭头链+info 色系，
 * 布局与色彩双通道可辨，深浅色同构（全语义 token，无硬编码 hex）。
 * 组件**不返回 null**——空态渲染占位，保持版式稳定。
 */
import { ArrowRight, Globe, RadioTower, Server, Smartphone } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useExecutionDiagram } from '@/application/test-execution/useExecutionDiagram'
import type { DiagramTarget } from '@/application/test-execution/useExecutionDiagram'
import type { Device } from '@/domain/models/device'
import type { ApiConfig } from '@/domain/models/apiConfig'
import type { DeviceType } from '@/domain/models/device'
import { cn } from '@/lib/utils'

const TARGET_ICON: Record<DeviceType | 'api', typeof Smartphone> = {
  physical: Smartphone,
  http_api: Server,
  websocket_api: RadioTower,
  api: Globe,
}

const NOTE_LINE =
  '并行目标同时启动、互不等待；串行目标按选择顺序依次执行，前序目标（含并行目标）全部完成后启动'

interface ExecutionDiagramProps {
  devices: Device[]
  apis: ApiConfig[]
  className?: string
}

function TargetNode({ target }: { target: DiagramTarget }) {
  const Icon = target.iconKind ? TARGET_ICON[target.iconKind] : Smartphone
  const serial = target.mode === 'serial'
  return (
    <span
      className={cn(
        'flex items-center gap-1.5 rounded-lg border bg-card px-2.5 py-1.5 text-xs'
      )}
    >
      <Icon aria-hidden='true' className='text-muted-foreground size-3.5' />
      <Tooltip>
        <TooltipTrigger
          render={
            <span className='max-w-[10rem] truncate font-medium'>{target.name}</span>
          }
        />
        <TooltipContent side='bottom'>{target.name}</TooltipContent>
      </Tooltip>
      <Badge
        className={cn(
          'rounded-4xl px-1.5 text-[10px] font-medium',
          serial ? 'bg-info/10 text-info' : 'bg-success/10 text-success'
        )}
      >
        {serial ? '串行' : '并行'}
      </Badge>
    </span>
  )
}

export function ExecutionDiagram({
  devices,
  apis,
  className,
}: ExecutionDiagramProps) {
  const { parallelTargets, serialTargets, hasStageArrow, isEmpty } = useExecutionDiagram(
    devices,
    apis
  )

  return (
    <section
      aria-label='执行示意'
      className={cn(
        'border-border/70 bg-background/95 ring-foreground/5 rounded-xl border p-4 ring-1',
        'dark:bg-background/80',
        className
      )}
    >
      <div className='mb-3'>
        <h3 className='text-sm font-semibold'>执行示意</h3>
        <p className='text-muted-foreground mt-0.5 text-xs'>
          展示所选目标并行与串行的执行方式，随配置实时更新
        </p>
      </div>

      {isEmpty ? (
        <div className='text-muted-foreground rounded-xl border border-dashed p-6 text-center text-sm'>
          选择设备或 API 后，此处实时展示并行/串行执行示意
        </div>
      ) : (
        <div className='flex flex-col gap-3'>
          {/* 并行组：同阶段并发（无箭头 + success 色系） */}
          {parallelTargets.length > 0 && (
            <div className='border-success/40 bg-success/5 rounded-xl border border-dashed p-3'>
              <h4 className='text-success mb-2 text-xs font-medium'>
                并行 · 同时执行
              </h4>
              <ul aria-label='并行目标' className='flex flex-wrap gap-2'>
                {parallelTargets.map((target) => (
                  <li key={`${target.targetType}:${target.targetId}`}>
                    <TargetNode target={target} />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 阶段箭头：并行目标完成后，串行目标按顺序依次启动 */}
          {hasStageArrow && (
            <div className='flex justify-center'>
              <ArrowRight aria-hidden='true' className='text-muted-foreground size-4' />
            </div>
          )}

          {/* 串行链：依次排队（箭头链 + info 色系） */}
          {serialTargets.length > 0 && (
            <div className='flex flex-col gap-1.5'>
              <h4 className='text-info text-xs font-medium'>串行 · 依次执行</h4>
              <ul aria-label='串行目标' className='flex flex-wrap items-center gap-2'>
                {serialTargets.map((target, index) => (
                  <li key={`${target.targetType}:${target.targetId}`} className='flex items-center gap-2'>
                    {index > 0 && (
                      <ArrowRight aria-hidden='true' className='text-muted-foreground size-4' />
                    )}
                    <TargetNode target={target} />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* 注记行（恒显）：承载 INT-1115 混排时序语义 */}
          <p className='text-muted-foreground text-xs'>{NOTE_LINE}</p>
        </div>
      )}
    </section>
  )
}
