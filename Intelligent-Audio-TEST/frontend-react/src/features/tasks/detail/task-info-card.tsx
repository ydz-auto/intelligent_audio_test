/**
 * 任务信息卡（09_任务域.md §4.2，Card）。
 * 头行：任务名 + 双状态徽章 + 创建时间 + 创建人；
 * 信息网格 `grid gap-4 sm:grid-cols-3 lg:grid-cols-4`（label text-xs muted + 值 text-sm font-medium tabular-nums）；
 * 标签行 BadgeListCell。
 */
import { Badge } from '@/components/ui/badge'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { TaskDetailData } from '@/domain/models/task'
import {
  formatDateTime,
  getEvaluationStatusMeta,
  getExecutionStatusMeta,
} from '@/features/tasks/constants'

function InfoGrid({ items }: { items: Array<{ label: string; value: string | number }> }) {
  return (
    <div className='grid gap-4 sm:grid-cols-3 lg:grid-cols-4'>
      {items.map((item) => (
        <div key={item.label}>
          <p className='text-muted-foreground text-xs'>{item.label}</p>
          <p className='text-sm font-medium tabular-nums'>{item.value}</p>
        </div>
      ))}
    </div>
  )
}

export function TaskInfoCard({
  detail,
  headerExtra,
}: {
  detail: TaskDetailData
  /** 头行附加内容（容器信息头徽章组，§5.5.2 ②；非容器不传） */
  headerExtra?: React.ReactNode
}) {
  const execMeta = getExecutionStatusMeta(detail.execution_status)
  const evalMeta = getEvaluationStatusMeta(detail.evaluation_status)

  return (
    <Card size='sm' className='gap-3 py-3'>
      <CardHeader className='px-4'>
        <div className='flex flex-wrap items-center gap-2'>
          <CardTitle className='text-base font-semibold'>{detail.name}</CardTitle>
          <StatusBadge
            label={execMeta.label}
            variant={execMeta.variant}
            pulse={execMeta.pulse}
          />
          <StatusBadge
            label={evalMeta.label}
            variant={evalMeta.variant}
            pulse={evalMeta.pulse}
          />
          {headerExtra}
        </div>
        <div className='text-muted-foreground text-xs tabular-nums'>
          创建时间 {formatDateTime(detail.created_at)} · 创建人 张测试
        </div>
      </CardHeader>
      <CardContent className='px-4 pb-1'>
        <InfoGrid
          items={[
            { label: '任务名称', value: detail.name },
            { label: '预计完成时间', value: formatDateTime(detail.expected_complete_time) },
            { label: '预计总时长', value: detail.expected_total_time ?? '—' },
            { label: '已用时长', value: detail.used_time ?? '—' },
            // INT-1241：资源计数按真实数据无条件展示（不再按任务类型条件显隐）
            { label: '测试API数量', value: detail.api_count ?? 0 },
            { label: '测试设备数量', value: detail.device_count ?? 0 },
            { label: '测试用例数量', value: detail.case_count ?? detail.total_cases ?? 0 },
            { label: '并发数', value: detail.concurrency ?? '—' },
          ]}
        />
        <div className='mt-3 flex flex-wrap items-center gap-1'>
          {detail.tags.length === 0 ? (
            <span className='text-muted-foreground text-xs'>—</span>
          ) : (
            detail.tags.map((tag) => (
              <Badge key={tag} variant='outline' className='rounded-md px-1.5'>
                {tag}
              </Badge>
            ))
          )}
        </div>
      </CardContent>
    </Card>
  )
}
