/**
 * 监控告警面板（16_设备域.md §3.7；页级 Collapsible，开关②展开，仅测试设备页签可见）。
 * 告警统计徽章行（StatBadge ×4：待处理 active(warning)/已确认 acknowledged(info)/已恢复
 * resolved(neutral)/总计 total）+ 告警/历史监控 Tabs：
 * - 告警列表：状态 facet + 级别 facet +「告警规则」outline 钮；列=级别/设备/规则/指标/内容/
 *   触发值·阈值/邮件/触发时间/操作（确认钮 device:control / 已确认态显 acknowledged_by）
 * - 历史监控：事件类型 facet + 时间范围 Select；列=设备/事件类型/变更/来源/结果/详情/时间
 * 数据 GET /alarms（含 stats）+ /status-history 实测；30s 轮询兜底（§11-4 SSE 断链）。
 */
import { Bell, ChevronDown, Circle, CircleCheck, X } from 'lucide-react'
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { cn } from '@/lib/utils'
import type {
  Alarm,
  AlarmStats,
  DeviceStatusEvent,
} from '@/domain/models/alarm'
import {
  ALARM_METRIC_META,
  ALARM_SEVERITY_META,
  ALARM_STATUS_META,
  DEVICE_EVENT_TYPE_META,
} from '@/domain/models/alarm'

export interface AlarmPanelProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  alarms: Alarm[]
  stats: AlarmStats | null
  statusHistory: DeviceStatusEvent[]
  loading: boolean
  canControl: boolean
  canUpdate: boolean
  onAcknowledge: (alarm: Alarm) => void
  onManageRules: () => void
}

const SEVERITY_FILTER_OPTIONS = [
  { value: 'info', label: '提示' },
  { value: 'warning', label: '警告' },
  { value: 'critical', label: '严重' },
]

const STATUS_FILTER_OPTIONS = [
  { value: 'active', label: '待处理' },
  { value: 'acknowledged', label: '已确认' },
  { value: 'resolved', label: '已恢复' },
]

const TIME_RANGE_OPTIONS = [
  { value: 'today', label: '今日' },
  { value: '7d', label: '近7天' },
  { value: '30d', label: '近30天' },
  { value: 'custom', label: '自定义' },
]

function StatBadge({
  label,
  value,
  dotClass,
}: {
  label: string
  value: number
  dotClass: string
}) {
  return (
    <span className='border-border/60 bg-muted/25 inline-flex h-7 items-center gap-2 rounded-md border px-2.5 text-xs shadow-xs'>
      <span aria-hidden='true' className={`h-3.5 w-0.5 rounded-full ${dotClass}`} />
      <span className='text-muted-foreground'>{label}</span>
      <span className='font-mono font-medium tabular-nums'>{value}</span>
    </span>
  )
}

/** 告警级别 IconBadge（critical=destructive/warning=warning/info=info，Bell 图标） */
function SeverityIcon({ severity }: { severity: Alarm['severity'] }) {
  if (!severity) return <span className='text-muted-foreground'>—</span>
  const meta = ALARM_SEVERITY_META[severity]
  const toneClass = {
    destructive: 'bg-destructive/10 text-destructive',
    warning: 'bg-warning/10 text-warning',
    info: 'bg-info/10 text-info',
  }[meta.tone]
  return (
    <span
      className={cn('inline-flex size-6 items-center justify-center rounded-md', toneClass)}
    >
      <Bell aria-hidden='true' className='size-3.5' />
    </span>
  )
}

export function AlarmPanel(props: AlarmPanelProps) {
  const [view, setView] = useState<'alarms' | 'history'>('alarms')
  const [severity, setSeverity] = useState<string>('all')
  const [alarmStatus, setAlarmStatus] = useState<string>('all')
  const [eventType, setEventType] = useState<string>('all')
  const [timeRange, setTimeRange] = useState<string>('7d')

  const filteredAlarms = props.alarms.filter((alarm) => {
    if (severity !== 'all' && alarm.severity !== severity) return false
    if (alarmStatus !== 'all' && alarm.status !== alarmStatus) return false
    return true
  })

  const filteredHistory = props.statusHistory.filter((event) => {
    if (eventType !== 'all' && event.eventType !== eventType) return false
    return true
  })

  return (
    <Collapsible
      open={props.open}
      onOpenChange={props.onOpenChange}
      className='bg-card/50 rounded-lg border p-2.5 sm:p-3'
    >
      <div className='flex items-center justify-between'>
        <CollapsibleTrigger
          render={
            <Button variant='ghost' size='sm' className='h-7 gap-1.5 px-2 text-sm font-medium' />
          }
        >
          <Bell aria-hidden='true' className='text-muted-foreground size-3.5' />
          监控告警
          {props.stats && (
            <Badge variant='outline' className='rounded-sm px-1 font-normal tabular-nums'>
              {props.stats.active} 待处理
            </Badge>
          )}
          <ChevronDown
            aria-hidden='true'
            className={cn('text-muted-foreground size-3.5 transition-transform', props.open && 'rotate-180')}
          />
        </CollapsibleTrigger>
      </div>

      <CollapsibleContent>
        <div className='mt-2.5 flex flex-col gap-2.5'>
          {/* 告警统计徽章行（§3.7） */}
          {props.loading ? (
            <div className='flex flex-wrap items-center gap-2'>
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className='h-7 w-28 rounded-md' />
              ))}
            </div>
          ) : (
            props.stats && (
              <div className='flex flex-wrap items-center gap-2'>
                <StatBadge label='待处理' value={props.stats.active} dotClass='bg-[var(--warning)]' />
                <StatBadge label='已确认' value={props.stats.acknowledged} dotClass='bg-[var(--info)]' />
                <StatBadge label='已恢复' value={props.stats.resolved} dotClass='bg-[var(--muted-foreground)]' />
                <StatBadge label='总计' value={props.stats.total} dotClass='bg-[var(--muted-foreground)]' />
              </div>
            )
          )}

          <Tabs value={view} onValueChange={(value) => setView(value as 'alarms' | 'history')}>
            <TabsList variant='line' className='w-fit'>
              <TabsTrigger value='alarms'>告警列表</TabsTrigger>
              <TabsTrigger value='history'>历史监控</TabsTrigger>
            </TabsList>
          </Tabs>

          {view === 'alarms' ? (
            <div className='flex flex-col gap-2'>
              {/* 工具行：状态 facet + 级别 facet + 「告警规则」 */}
              <div className='flex flex-wrap items-center gap-2'>
                <Select value={alarmStatus} onValueChange={(value) => setAlarmStatus(value ?? 'all')}>
                  <SelectTrigger size='sm' className='w-28'>
                    <SelectValue placeholder='全部状态' />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value='all'>全部状态</SelectItem>
                    {STATUS_FILTER_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={severity} onValueChange={(value) => setSeverity(value ?? 'all')}>
                  <SelectTrigger size='sm' className='w-28'>
                    <SelectValue placeholder='全部级别' />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value='all'>全部级别</SelectItem>
                    {SEVERITY_FILTER_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {props.canUpdate && (
                  <Button variant='outline' size='sm' className='h-8 gap-1 text-xs' onClick={props.onManageRules}>
                    告警规则
                  </Button>
                )}
              </div>
              <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
                <div className='overflow-x-auto'>
                  <table className='w-full min-w-[900px] text-xs'>
                    <thead>
                      <tr className='bg-[var(--table-header)]'>
                        <th className='px-2.5 py-1.5 text-left font-medium'>级别</th>
                        <th className='px-2.5 py-1.5 text-left font-medium'>设备</th>
                        <th className='px-2.5 py-1.5 text-left font-medium'>规则</th>
                        <th className='px-2.5 py-1.5 text-left font-medium'>指标</th>
                        <th className='px-2.5 py-1.5 text-left font-medium'>内容</th>
                        <th className='px-2.5 py-1.5 text-right font-medium'>触发值/阈值</th>
                        <th className='px-2.5 py-1.5 text-center font-medium'>邮件</th>
                        <th className='px-2.5 py-1.5 text-left font-medium'>触发时间</th>
                        <th className='px-2.5 py-1.5 text-right font-medium'>操作</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredAlarms.length === 0 ? (
                        <tr>
                          <td colSpan={9} className='text-muted-foreground px-3 py-6 text-center'>
                            暂无告警
                          </td>
                        </tr>
                      ) : (
                        filteredAlarms.map((alarm) => {
                          const metricLabel = alarm.metricType
                            ? ALARM_METRIC_META[alarm.metricType].label
                            : '—'
                          return (
                            <tr key={alarm.id} className='hover:bg-muted/40 border-border/50 border-b last:border-b-0'>
                              <td className='px-2.5 py-1.5'>
                                <SeverityIcon severity={alarm.severity} />
                              </td>
                              <td className='max-w-36 px-2.5 py-1.5'>
                                <span className='min-w-0 block truncate'>{alarm.deviceName ?? '—'}</span>
                                {alarm.deviceId != null && (
                                  <span className='text-muted-foreground font-mono text-[11px]'>#{alarm.deviceId}</span>
                                )}
                              </td>
                              <td className='max-w-36 px-2.5 py-1.5'>
                                <span className='min-w-0 block truncate'>{alarm.ruleName ?? '—'}</span>
                              </td>
                              <td className='px-2.5 py-1.5'>{metricLabel}</td>
                              <td className='max-w-56 px-2.5 py-1.5'>
                                <Tooltip>
                                  <TooltipTrigger
                                    render={<span className='min-w-0 block truncate text-start' />}
                                  >
                                    {alarm.content ?? '—'}
                                  </TooltipTrigger>
                                  {alarm.content && (
                                    <TooltipContent className='max-w-80'>
                                      {alarm.content}
                                    </TooltipContent>
                                  )}
                                </Tooltip>
                              </td>
                              <td className='px-2.5 py-1.5 text-right font-mono tabular-nums'>
                                {alarm.triggerValue ?? '—'}/{alarm.thresholdValue ?? '—'}
                              </td>
                              <td className='px-2.5 py-1.5 text-center'>
                                {alarm.emailSent ? (
                                  <CircleCheck aria-label='已发送邮件' className='text-success mx-auto size-3.5' />
                                ) : (
                                  <Circle aria-hidden='true' className='text-muted-foreground mx-auto size-3.5' />
                                )}
                              </td>
                              <td className='px-2.5 py-1.5 font-mono tabular-nums'>
                                {alarm.createdAt ? alarm.createdAt.replace('T', ' ').slice(0, 16) : '—'}
                              </td>
                              <td className='px-2.5 py-1.5 text-right'>
                                {alarm.status === 'active' && props.canControl ? (
                                  <Button
                                    variant='outline'
                                    size='sm'
                                    className='h-6 gap-1 px-2 text-xs'
                                    onClick={() => props.onAcknowledge(alarm)}
                                  >
                                    确认
                                  </Button>
                                ) : alarm.status === 'acknowledged' ? (
                                  <span className='text-muted-foreground text-[11px]'>
                                    {alarm.acknowledgedBy ?? '已确认'}
                                  </span>
                                ) : (
                                  <Badge variant='outline' className='rounded-sm px-1 font-normal'>
                                    {ALARM_STATUS_META[alarm.status ?? 'resolved']?.label ?? '已恢复'}
                                  </Badge>
                                )}
                              </td>
                            </tr>
                          )
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          ) : (
            <div className='flex flex-col gap-2'>
              <div className='flex flex-wrap items-center gap-2'>
                <Select value={eventType} onValueChange={(value) => setEventType(value ?? 'all')}>
                  <SelectTrigger size='sm' className='w-32'>
                    <SelectValue placeholder='全部事件' />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value='all'>全部事件</SelectItem>
                    {Object.entries(DEVICE_EVENT_TYPE_META).map(([value, meta]) => (
                      <SelectItem key={value} value={value}>
                        {meta.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={timeRange} onValueChange={(value) => setTimeRange(value ?? '7d')}>
                  <SelectTrigger size='sm' className='w-28'>
                    <SelectValue placeholder='全部时间' />
                  </SelectTrigger>
                  <SelectContent>
                    {TIME_RANGE_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
                <div className='overflow-x-auto'>
                  <table className='w-full min-w-[760px] text-xs'>
                    <thead>
                      <tr className='bg-[var(--table-header)]'>
                        <th className='px-2.5 py-1.5 text-left font-medium'>设备</th>
                        <th className='px-2.5 py-1.5 text-left font-medium'>事件类型</th>
                        <th className='px-2.5 py-1.5 text-left font-medium'>变更</th>
                        <th className='px-2.5 py-1.5 text-left font-medium'>来源</th>
                        <th className='px-2.5 py-1.5 text-center font-medium'>结果</th>
                        <th className='px-2.5 py-1.5 text-left font-medium'>详情</th>
                        <th className='px-2.5 py-1.5 text-left font-medium'>时间</th>
                      </tr>
                    </thead>
                    <tbody>
                      {filteredHistory.length === 0 ? (
                        <tr>
                          <td colSpan={7} className='text-muted-foreground px-3 py-6 text-center'>
                            暂无历史记录
                          </td>
                        </tr>
                      ) : (
                        filteredHistory.map((event) => {
                          const meta = DEVICE_EVENT_TYPE_META[event.eventType]
                          return (
                            <tr key={event.id} className='hover:bg-muted/40 border-border/50 border-b last:border-b-0'>
                              <td className='max-w-36 px-2.5 py-1.5'>
                                <span className='min-w-0 block truncate'>{event.deviceName ?? '—'}</span>
                              </td>
                              <td className='px-2.5 py-1.5'>
                                <Badge variant='outline' className='rounded-sm px-1 font-normal'>
                                  {meta.label}
                                </Badge>
                              </td>
                              <td className='px-2.5 py-1.5 font-mono text-[11px]'>
                                {event.fromStatus ?? '—'} <span aria-hidden='true'>→</span> {event.toStatus ?? '—'}
                              </td>
                              <td className='px-2.5 py-1.5 text-muted-foreground'>{event.source ?? '—'}</td>
                              <td className='px-2.5 py-1.5 text-center'>
                                {event.result === 'success' ? (
                                  <CircleCheck aria-label='成功' className='text-success mx-auto size-3.5' />
                                ) : event.result === 'failed' ? (
                                  <CircleXLabel />
                                ) : (
                                  <span className='text-muted-foreground'>—</span>
                                )}
                              </td>
                              <td className='max-w-52 px-2.5 py-1.5'>
                                <Tooltip>
                                  <TooltipTrigger
                                    render={<span className='min-w-0 block truncate text-start' />}
                                  >
                                    {event.detail ?? '—'}
                                  </TooltipTrigger>
                                  {event.detail && (
                                    <TooltipContent className='max-w-80'>{event.detail}</TooltipContent>
                                  )}
                                </Tooltip>
                              </td>
                              <td className='px-2.5 py-1.5 font-mono tabular-nums'>
                                {event.createdAt ? event.createdAt.replace('T', ' ').slice(0, 16) : '—'}
                              </td>
                            </tr>
                          )
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}

/** 失败结果圆叉 */
function CircleXLabel() {
  return (
    <span className='bg-destructive/10 text-destructive inline-flex size-4 items-center justify-center rounded-full'>
      <X aria-label='失败' className='size-3' />
    </span>
  )
}
