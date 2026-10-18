/**
 * 日志详情行（interfaces 层；17_配置运维.md §4.4 DetailSection）。
 * 行点击展开/收起；展示时间/级别/分类/模块/算法类型/来源/设备ID/任务ID/线程ID/
 * 内容 + 上下文 JSON（category/deviceId/taskId/threadId/algorithmType）。
 */
import { ChevronDown } from 'lucide-react'

import type { LogItem } from '@/domain/models/log'
import { LOG_LEVEL_BADGE_VARIANT } from '@/features/logs/constants'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className='grid grid-cols-[88px_1fr] gap-2 text-xs'>
      <span className='text-muted-foreground'>{label}</span>
      <span className='min-w-0 break-all'>{value ?? '—'}</span>
    </div>
  )
}

export function LogRowDetails({ log }: { log: LogItem }) {
  const context = JSON.stringify(
    {
      category: log.category,
      deviceId: log.deviceId,
      taskId: log.taskId,
      threadId: log.threadId,
      algorithmType: log.algorithmType,
    },
    null,
    2
  )

  return (
    <tr className='border-border/50 border-b bg-muted/20'>
      <td colSpan={7} className='px-4 py-3'>
        <div className='mb-2 flex items-center gap-1.5 text-xs font-medium'>
          <ChevronDown aria-hidden='true' className='text-muted-foreground size-3.5' />
          详细信息
        </div>
        <div className='grid gap-x-6 gap-y-1.5 sm:grid-cols-2 lg:grid-cols-3'>
          <Field label='时间' value={log.time} />
          <Field
            label='级别'
            value={
              <StatusBadge
                label={log.level}
                variant={LOG_LEVEL_BADGE_VARIANT[log.level.toUpperCase()] ?? 'neutral'}
              />
            }
          />
          <Field label='分类' value={log.category} />
          <Field label='模块' value={log.module} />
          <Field label='算法类型' value={log.algorithmType} />
          <Field label='来源' value={log.source} />
          <Field label='设备ID' value={log.deviceId} />
          <Field label='任务ID' value={log.taskId} />
          <Field label='线程ID' value={log.threadId} />
        </div>
        <div className='mt-2'>
          <Field label='内容' value={<span className='font-mono whitespace-pre-wrap'>{log.content}</span>} />
        </div>
        <div className='mt-2'>
          <div className='text-muted-foreground mb-1 text-xs'>上下文信息</div>
          <pre className='bg-muted/60 rounded-md p-2 font-mono text-[11px] leading-5'>
            {context}
          </pre>
        </div>
      </td>
    </tr>
  )
}
