/**
 * 监控告警面板（16_设备域.md §3.7；页级 Collapsible，开关②展开，仅测试设备页签可见）。
 * 告警统计徽章行（StatBadge ×4：待处理 active(warning)/已确认 acknowledged(info)/已恢复
 * resolved(neutral)/总计 total）+ 告警/历史监控 Tabs：
 * - 告警列表：状态 facet + 级别 facet +「告警规则」outline 钮；列=级别/设备/规则/指标/内容/
 *   触发值·阈值/邮件/触发时间/操作（确认钮 device:control / 已确认态显 acknowledged_by）
 * - 历史监控：事件类型 facet + 时间范围 Select（今日/近7天/近30天/自定义 start/end）+ 四类历史
 *   子页签（状态/性能/操作/错误）+ 统计分析 vChart 区（可用性/性能/错误/使用）
 * 数据 GET /alarms（含 stats）+ /status-history 实测；30s 轮询兜底（§11-4 SSE 断链）。
 * P2-4 返修：时间范围筛选接入 createdAt；P2-12 返修：四类历史 + 统计分析区；
 * P3-27 返修：复用 StaticDataTable；P3-28 返修：复用 IconBadge。
 */
import { Bell, ChevronDown, Circle, CircleCheck } from 'lucide-react'
import { useMemo, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible'
import { IconBadge } from '@/components/ui/icon-badge'
import { Input } from '@/components/ui/input'
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
import { StaticDataTable } from '@/features/system-settings/components/static-data-table'
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
import {
  HISTORY_CATEGORY_EVENT_TYPES,
  filterByTimeRange,
  type HistoryTimeRange,
} from '@/features/devices/lib/alarm-history-stats'
import { HistoryStatsCharts } from '@/features/devices/components/monitor/history-stats-charts'

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

const HISTORY_CATEGORIES = [
  { value: 'status', label: '状态历史' },
  { value: 'performance', label: '性能历史' },
  { value: 'operation', label: '操作历史' },
  { value: 'error', label: '错误历史' },
] as const

type HistoryCategory = (typeof HISTORY_CATEGORIES)[number]['value']

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

/** 告警级别 IconBadge（P3-28：复用 ui/icon-badge，critical=destructive/warning=warning/info=info） */
function SeverityIcon({ severity }: { severity: Alarm['severity'] }) {
  if (!severity) return <span className='text-muted-foreground'>—</span>
  const meta = ALARM_SEVERITY_META[severity]
  return (
    <IconBadge tone={meta.tone} size='xs'>
      <Bell aria-hidden='true' />
    </IconBadge>
  )
}

/** 状态码中文（P4：历史变更列显中文而非英文状态码） */
function statusCodeLabel(status: string | null): string {
  if (!status) return '—'
  return DEVICE_EVENT_TYPE_META[status as keyof typeof DEVICE_EVENT_TYPE_META]?.label ?? status
}

export function AlarmPanel(props: AlarmPanelProps) {
  const [view, setView] = useState<'alarms' | 'history'>('alarms')
  const [severity, setSeverity] = useState<string>('all')
  const [alarmStatus, setAlarmStatus] = useState<string>('all')
  const [eventType, setEventType] = useState<string>('all')
  const [timeRange, setTimeRange] = useState<HistoryTimeRange>('7d')
  const [customStart, setCustomStart] = useState<string>('')
  const [customEnd, setCustomEnd] = useState<string>('')
  const [historyCategory, setHistoryCategory] = useState<HistoryCategory>('status')

  const filteredAlarms = useMemo(
    () =>
      props.alarms.filter((alarm) => {
        if (severity !== 'all' && alarm.severity !== severity) return false
        if (alarmStatus !== 'all' && alarm.status !== alarmStatus) return false
        return true
      }),
    [props.alarms, severity, alarmStatus]
  )

  // P2-4：时间范围筛选接入 createdAt（今日/近7天/近30天/自定义）
  const filteredHistory = useMemo(() => {
    const categoryTypes = HISTORY_CATEGORY_EVENT_TYPES[historyCategory]
    return props.statusHistory.filter((event) => {
      if (categoryTypes && !categoryTypes.includes(event.eventType)) return false
      if (eventType !== 'all' && event.eventType !== eventType) return false
      if (!filterByTimeRange(event.createdAt, timeRange, customStart, customEnd)) return false
      return true
    })
  }, [props.statusHistory, historyCategory, eventType, timeRange, customStart, customEnd])

  const alarmColumns = [
    {
      key: 'severity',
      header: '级别',
      render: (alarm: Alarm) => <SeverityIcon severity={alarm.severity} />,
    },
    {
      key: 'device',
      header: '设备',
      className: 'max-w-36',
      render: (alarm: Alarm) => (
        <>
          <span className='min-w-0 block truncate'>{alarm.deviceName ?? '—'}</span>
          {alarm.deviceId != null && (
            <span className='text-muted-foreground font-mono text-[11px]'>#{alarm.deviceId}</span>
          )}
        </>
      ),
    },
    {
      key: 'rule',
      header: '规则',
      className: 'max-w-36',
      render: (alarm: Alarm) => (
        <span className='min-w-0 block truncate'>{alarm.ruleName ?? '—'}</span>
      ),
    },
    {
      key: 'metric',
      header: '指标',
      render: (alarm: Alarm) =>
        alarm.metricType ? ALARM_METRIC_META[alarm.metricType].label : '—',
    },
    {
      key: 'content',
      header: '内容',
      className: 'max-w-56',
      render: (alarm: Alarm) => (
        <Tooltip>
          <TooltipTrigger render={<span className='min-w-0 block truncate text-start' />}>
            {alarm.content ?? '—'}
          </TooltipTrigger>
          {alarm.content && <TooltipContent className='max-w-80'>{alarm.content}</TooltipContent>}
        </Tooltip>
      ),
    },
    {
      key: 'threshold',
      header: '触发值/阈值',
      className: 'text-right font-mono tabular-nums',
      render: (alarm: Alarm) => `${alarm.triggerValue ?? '—'}/${alarm.thresholdValue ?? '—'}`,
    },
    {
      key: 'email',
      header: '邮件',
      className: 'text-center',
      render: (alarm: Alarm) =>
        alarm.emailSent ? (
          alarm.emailError ? (
            // P4：邮件失败 Tooltip（email_error）
            <Tooltip>
              <TooltipTrigger
                render={
                  <CircleCheck
                    aria-label='邮件发送失败'
                    className='text-warning mx-auto size-3.5'
                  />
                }
              />
              <TooltipContent>{alarm.emailError}</TooltipContent>
            </Tooltip>
          ) : (
            <CircleCheck aria-label='已发送邮件' className='text-success mx-auto size-3.5' />
          )
        ) : (
          <Circle aria-hidden='true' className='text-muted-foreground mx-auto size-3.5' />
        ),
    },
    {
      key: 'createdAt',
      header: '触发时间',
      className: 'font-mono tabular-nums',
      render: (alarm: Alarm) =>
        alarm.createdAt ? alarm.createdAt.replace('T', ' ').slice(0, 16) : '—',
    },
  ]

  const historyColumns = [
    {
      key: 'device',
      header: '设备',
      className: 'max-w-36',
      render: (event: DeviceStatusEvent) => (
        <span className='min-w-0 block truncate'>{event.deviceName ?? '—'}</span>
      ),
    },
    {
      key: 'eventType',
      header: '事件类型',
      render: (event: DeviceStatusEvent) => (
        <Badge variant='outline' className='rounded-sm px-1 font-normal'>
          {DEVICE_EVENT_TYPE_META[event.eventType]?.label ?? event.eventType}
        </Badge>
      ),
    },
    {
      key: 'transition',
      header: '变更',
      className: 'font-mono text-[11px]',
      render: (event: DeviceStatusEvent) => (
        <>
          {statusCodeLabel(event.fromStatus)} <span aria-hidden='true'>→</span>{' '}
          {statusCodeLabel(event.toStatus)}
        </>
      ),
    },
    {
      key: 'source',
      header: '来源',
      render: (event: DeviceStatusEvent) => (
        <span className='text-muted-foreground'>{event.source ?? '—'}</span>
      ),
    },
    {
      key: 'result',
      header: '结果',
      className: 'text-center',
      render: (event: DeviceStatusEvent) =>
        event.result === 'success' ? (
          <CircleCheck aria-label='成功' className='text-success mx-auto size-3.5' />
        ) : event.result === 'failed' ? (
          <span className='bg-destructive/10 text-destructive inline-flex size-4 items-center justify-center rounded-full'>
            <svg aria-label='失败' className='size-3' viewBox='0 0 24 24' fill='none' stroke='currentColor' strokeWidth='2.5'>
              <path d='M18 6 6 18M6 6l12 12' strokeLinecap='round' />
            </svg>
          </span>
        ) : (
          <span className='text-muted-foreground'>—</span>
        ),
    },
    {
      key: 'detail',
      header: '详情',
      className: 'max-w-52',
      render: (event: DeviceStatusEvent) => (
        <Tooltip>
          <TooltipTrigger render={<span className='min-w-0 block truncate text-start' />}>
            {event.detail ?? '—'}
          </TooltipTrigger>
          {event.detail && <TooltipContent className='max-w-80'>{event.detail}</TooltipContent>}
        </Tooltip>
      ),
    },
    {
      key: 'createdAt',
      header: '时间',
      className: 'font-mono tabular-nums',
      render: (event: DeviceStatusEvent) =>
        event.createdAt ? event.createdAt.replace('T', ' ').slice(0, 16) : '—',
    },
  ]

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
                <Select
                  value={alarmStatus}
                  onValueChange={(value) => setAlarmStatus(value ?? 'all')}
                  items={[{ value: 'all', label: '全部状态' }, ...STATUS_FILTER_OPTIONS]}
                >
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
                <Select
                  value={severity}
                  onValueChange={(value) => setSeverity(value ?? 'all')}
                  items={[{ value: 'all', label: '全部级别' }, ...SEVERITY_FILTER_OPTIONS]}
                >
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
              {/* P3-27：告警表复用 StaticDataTable */}
              <StaticDataTable
                columns={alarmColumns}
                rows={filteredAlarms}
                rowKey={(alarm) => String(alarm.id)}
                emptyText='暂无告警'
                minWidth='900px'
                actions={(alarm) =>
                  alarm.status === 'active' && props.canControl ? (
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
                  )
                }
              />
            </div>
          ) : (
            <div className='flex flex-col gap-2'>
              <div className='flex flex-wrap items-center gap-2'>
                <Select
                  value={eventType}
                  onValueChange={(value) => setEventType(value ?? 'all')}
                  items={[
                    { value: 'all', label: '全部事件' },
                    ...Object.entries(DEVICE_EVENT_TYPE_META).map(([value, meta]) => ({
                      value,
                      label: meta.label,
                    })),
                  ]}
                >
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
                <Select
                  value={timeRange}
                  onValueChange={(value) => setTimeRange((value ?? '7d') as HistoryTimeRange)}
                  items={TIME_RANGE_OPTIONS}
                >
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
                {/* P2-4：自定义时间范围起止输入 */}
                {timeRange === 'custom' && (
                  <>
                    <Input
                      type='date'
                      value={customStart}
                      onChange={(e) => setCustomStart(e.target.value)}
                      className='h-8 w-36'
                      aria-label='自定义开始时间'
                    />
                    <Input
                      type='date'
                      value={customEnd}
                      onChange={(e) => setCustomEnd(e.target.value)}
                      className='h-8 w-36'
                      aria-label='自定义结束时间'
                    />
                  </>
                )}
              </div>
              {/* P2-12：四类历史子页签（状态/性能/操作/错误） */}
              <Tabs
                value={historyCategory}
                onValueChange={(value) => setHistoryCategory(value as HistoryCategory)}
              >
                <TabsList variant='line' className='w-fit'>
                  {HISTORY_CATEGORIES.map((category) => (
                    <TabsTrigger key={category.value} value={category.value}>
                      {category.label}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
              {/* P3-27：历史表复用 StaticDataTable */}
              <StaticDataTable
                columns={historyColumns}
                rows={filteredHistory}
                rowKey={(event) => String(event.id)}
                emptyText='暂无历史记录'
                minWidth='760px'
              />
              {/* P2-12：统计分析 vChart 区（可用性/性能/错误/使用） */}
              <HistoryStatsCharts />
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  )
}
