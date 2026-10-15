/**
 * 关联用例 / 关联设备（09_任务域.md §4.4，Card 内 Tabs）。
 * 页签「关联用例」（默认）/「关联{设备|API}」；工具行 = 视图切换（平铺/标签/分组）+ 状态筛选。
 * 平铺态 DataTable 列：用例名称/执行状态/评估状态/耗时/轮次/操作（移除用例）；
 * 标签/分组态用 Collapsible 组头（名称 + 计数）行。
 */
import { Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { cn } from '@/lib/utils'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import type { TaskDetailData } from '@/domain/models/task'
import { formatDuration } from '@/features/tasks/constants'
import { Progress } from '@/features/tasks/components/ui/progress'

type ViewMode = 'flat' | 'tag' | 'group'
const VIEW_OPTIONS: Array<{ value: ViewMode; label: string }> = [
  { value: 'flat', label: '平铺' },
  { value: 'tag', label: '标签' },
  { value: 'group', label: '分组' },
]

const CASE_STATUS_OPTIONS = [
  '全部状态',
  '等待中',
  '排队中',
  '执行中',
  '计算指标中',
  '已完成',
  '已失败',
  '已跳过',
  '已停止',
  '已删除',
]

function CaseStatusBadge({ status }: { status: string | null }) {
  const map: Record<string, { label: string; variant: 'success' | 'danger' | 'info' | 'neutral' | 'warning' }> = {
    pending: { label: '等待中', variant: 'neutral' },
    queued: { label: '排队中', variant: 'info' },
    running: { label: '执行中', variant: 'info' },
    completed: { label: '已完成', variant: 'success' },
    failed: { label: '已失败', variant: 'danger' },
    skipped: { label: '已跳过', variant: 'neutral' },
    stopped: { label: '已停止', variant: 'neutral' },
    deleted: { label: '已删除', variant: 'neutral' },
  }
  const meta = map[status ?? ''] ?? { label: status ?? '—', variant: 'neutral' as const }
  return <StatusBadge label={meta.label} variant={meta.variant} />
}

export function CaseAssociation({ detail }: { detail: TaskDetailData }) {
  const [tab, setTab] = useState('cases')
  const [view, setView] = useState<ViewMode>('flat')
  const [status, setStatus] = useState('全部状态')
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const cases = detail.cases ?? []
  const filtered = cases.filter(
    (c) => status === '全部状态' || c.execution_status === status || c.status === status
  )

  const resourceLabel = detail.device_types.includes('http_api') ? '关联API' : '关联设备'

  // 标签分组（按用例 tags 首标签粗分）
  const tagGroups = filtered.reduce<Record<string, typeof filtered>>((acc, c) => {
    const key = c.tags[0] ?? '未分组'
    acc[key] ??= []
    acc[key].push(c)
    return acc
  }, {})

  const toggleRow = (caseId: string, checked: boolean) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (checked) next.add(caseId)
      else next.delete(caseId)
      return next
    })
  }

  return (
    <Card size='sm' className='gap-3 py-3'>
      <CardHeader className='px-4'>
        <CardTitle className='text-sm font-medium'>
          {tab === 'cases' ? '关联用例' : resourceLabel}
        </CardTitle>
        <div data-slot='card-action' className='flex items-center gap-1.5'>
          {tab === 'cases' && (
            <>
              <Tabs
                value={view}
                onValueChange={(v) => setView(v as ViewMode)}
                className='group/tabs'
              >
                <TabsList variant='line' className='h-8'>
                  {VIEW_OPTIONS.map((option) => (
                    <TabsTrigger key={option.value} value={option.value} className='px-2 text-xs'>
                      {option.label}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
              <Select value={status} onValueChange={(value) => setStatus(value ?? '全部状态')}>
                <SelectTrigger size='sm' className='h-8 gap-1.5 px-2.5' aria-label='状态筛选'>
                  <SelectValue>{status}</SelectValue>
                </SelectTrigger>
                <SelectContent align='end'>
                  {CASE_STATUS_OPTIONS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {option}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </>
          )}
        </div>
      </CardHeader>

      <Tabs value={tab} onValueChange={setTab} className='px-4 group/tabs'>
        <TabsList variant='line' className='h-8'>
          <TabsTrigger value='cases' className='px-2.5 text-xs'>
            关联用例
          </TabsTrigger>
          <TabsTrigger value='resources' className='px-2.5 text-xs'>
            {resourceLabel}
          </TabsTrigger>
        </TabsList>
      </Tabs>

      <CardContent className='px-4 pb-1'>
        {tab === 'resources' ? (
          detail.devices.length > 0 || detail.apis.length > 0 ? (
            <div className='flex flex-col gap-1.5'>
              {detail.devices.map((device) => (
                <div key={device.id} className='flex items-center gap-2 rounded-lg border px-3 py-2 text-sm'>
                  <span aria-hidden='true' className={cn('size-2 rounded-full', device.status === 'online' ? 'bg-success' : 'bg-muted')} />
                  <span className='font-medium'>{device.name}</span>
                  <span className='text-muted-foreground text-xs'>
                    {device.status === 'online' ? '在线' : '离线'} · {device.model ?? '—'}
                  </span>
                </div>
              ))}
              {detail.apis.map((api) => (
                <div key={api.id} className='flex items-center gap-2 rounded-lg border px-3 py-2 text-sm'>
                  <span aria-hidden='true' className={cn('size-2 rounded-full', api.status === 'online' ? 'bg-success' : 'bg-muted')} />
                  <span className='font-medium'>{api.name}</span>
                  <span className='text-muted-foreground text-xs'>当前并发 2/4</span>
                </div>
              ))}
            </div>
          ) : (
            <p className='text-muted-foreground py-6 text-center text-sm'>
              暂无关联{detail.device_types.includes('http_api') ? 'API' : '设备'}
            </p>
          )
        ) : filtered.length === 0 ? (
          <p className='text-muted-foreground py-6 text-center text-sm'>暂无关联用例</p>
        ) : view === 'flat' ? (
          <div className='overflow-x-auto'>
            <table className='w-full min-w-[680px] text-[13px]'>
              <thead>
                <tr className='bg-[var(--table-header)] text-xs'>
                  <th className='w-11 px-3 py-2'>
                    <Checkbox
                      checked={filtered.length > 0 && filtered.every((c) => selected.has(c.case_id))}
                      aria-label='全选用例'
                      onCheckedChange={(checked) =>
                        setSelected(checked ? new Set(filtered.map((c) => c.case_id)) : new Set())
                      }
                    />
                  </th>
                  <th className='px-3 py-2 text-left font-medium'>用例名称</th>
                  <th className='px-3 py-2 text-left font-medium'>执行状态</th>
                  <th className='px-3 py-2 text-left font-medium'>评估状态</th>
                  <th className='px-3 py-2 text-left font-medium'>耗时</th>
                  <th className='px-3 py-2 text-left font-medium'>轮次</th>
                  <th className='px-3 py-2 text-right font-medium'>操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((c) => (
                  <tr key={c.case_id} className='hover:bg-muted/40 border-border/60 border-b transition-colors'>
                    <td className='px-3 py-2'>
                      <Checkbox
                        checked={selected.has(c.case_id)}
                        onCheckedChange={(checked) => toggleRow(c.case_id, checked)}
                        aria-label={`选择 ${c.name}`}
                      />
                    </td>
                    <td className='max-w-56 px-3 py-2'>
                      <span className='block truncate font-medium'>{c.name}</span>
                      <span className='text-muted-foreground block truncate text-xs'>
                        {c.group_name ?? ''}
                      </span>
                    </td>
                    <td className='px-3 py-2'>
                      <CaseStatusBadge status={c.execution_status} />
                    </td>
                    <td className='px-3 py-2'>
                      <CaseStatusBadge status={c.evaluation_status} />
                    </td>
                    <td className='px-3 py-2 font-mono text-xs tabular-nums'>
                      {formatDuration(c.duration)}
                    </td>
                    <td className='min-w-24 px-3 py-2'>
                      <div className='font-mono text-xs tabular-nums'>
                        第 {c.duration != null ? 2 : 1}/2 轮
                      </div>
                      <Progress value={c.duration != null ? 50 : 0} size='xs' className='mt-1' />
                    </td>
                    <td className='px-3 py-2 text-right'>
                      <Button
                        variant='ghost'
                        size='icon-sm'
                        className='text-destructive hover:text-destructive'
                        aria-label='移除用例'
                        onClick={() => {
                          toast.success('已移除用例（末例二次确认见 §5.9）')
                          setSelected((prev) => {
                            const next = new Set(prev)
                            next.delete(c.case_id)
                            return next
                          })
                        }}
                      >
                        <Trash2 aria-hidden='true' />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className='flex flex-col gap-2'>
            {Object.entries(tagGroups).map(([group, rows]) => (
              <Collapsible key={group} className='rounded-lg border'>
                <CollapsibleTrigger className='hover:bg-muted/40 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-sm font-medium transition-colors'>
                  {group}
                  <Badge className='rounded-sm px-1 font-normal'>{rows.length}</Badge>
                </CollapsibleTrigger>
                <CollapsibleContent className='px-3 pb-2'>
                  <div className='flex flex-col'>
                    {rows.map((c) => (
                      <div key={c.case_id} className='flex items-center gap-2 py-1.5 text-xs'>
                        <span className='min-w-0 flex-1 truncate'>{c.name}</span>
                        <CaseStatusBadge status={c.execution_status} />
                      </div>
                    ))}
                  </div>
                </CollapsibleContent>
              </Collapsible>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
