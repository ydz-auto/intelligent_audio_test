/**
 * 日志查看页（features/logs；17_配置运维.md §4 整页落地，INT-763）。
 * SectionPageLayout fixedContent + Title「日志查看」+ Actions（实时监控 Switch +
 * 全部/仅自己 Tabs[log:manage] + 刷新/导出/清除 + 查看归档 link）+ LogsFilterToolbar +
 * 统计徽章行（GET /logs/stats）+ 实时监控指示器 + DataTable（勾选/展开/详情行/移动卡片）+
 * 批量浮条 + 分页 Portal；弹窗群：导出 / 清除 / 实时监控配置。
 * 实时：WS/Socket.IO /ws/logs（log:websocket 判定）+ POST /logs/refresh 轮询兜底。
 */
import { Archive, FileDown, RefreshCw, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from '@tanstack/react-router'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import {
  Tabs,
  TabsList,
  TabsTrigger,
} from '@/components/ui/tabs'
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { PageFooterPortal } from '@/components/layout/components/page-footer'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import { usePermissions } from '@/application/hooks/use-permissions'
import { useAlgorithmOptions } from '@/application/hooks/use-algorithm-options'
import { useAlgorithmStore } from '@/infrastructure/stores/algorithm-store'
import { useLogsQuery, useLogStatsQuery, useLogMutations } from '@/application/logs/use-logs'
import { refreshLogs } from '@/infrastructure/api/logsApi'
import { LOG_LEVELS } from '@/domain/models/log'
import type { Log, LogQuery } from '@/domain/models/log'
import {
  DEFAULT_PAGE_SIZE,
  LOG_SEARCH_DEBOUNCE_MS,
  PAGE_SIZE_OPTIONS,
} from '@/features/logs/constants'
import {
  EMPTY_ADVANCED_STATE,
  EMPTY_FILTER_STATE,
  hasActiveFilters,
  type LogAdvancedState,
  type LogFilterState,
} from '@/features/logs/types'
import { LogsFilterToolbar } from '@/features/logs/components/logs-filter-toolbar'
import { LogsStatsRow } from '@/features/logs/components/logs-stats-row'
import { LogsTable } from '@/features/logs/components/logs-table'
import { LogsRealtimeIndicator } from '@/features/logs/components/logs-realtime-indicator'
import { LogsBulkActions } from '@/features/logs/components/logs-bulk-actions'
import { LogExportDialog } from '@/features/logs/components/log-export-dialog'
import { LogClearDialog } from '@/features/logs/components/log-clear-dialog'
import { RealtimeConfigDialog } from '@/features/logs/components/realtime-config-dialog'
import { useLogRealtime } from '@/features/logs/hooks/use-log-realtime'
import { cn } from '@/lib/utils'

type ViewScope = 'all' | 'self'

/** 300ms 防抖搜索（对照 algorithm-config §3.4；搜索钮即时 flush 提交） */
function useDebouncedSearch(initial = '') {
  const [value, setValue] = useState(initial)
  const [committed, setCommitted] = useState(initial)
  const timerRef = useRef<number | null>(null)
  const valueRef = useRef(value)
  valueRef.current = value

  const handleChange = useCallback((next: string) => {
    setValue(next)
    if (timerRef.current) window.clearTimeout(timerRef.current)
    timerRef.current = window.setTimeout(
      () => setCommitted(next.trim()),
      LOG_SEARCH_DEBOUNCE_MS
    )
  }, [])

  /** 立即提交当前输入（点「搜索」/Enter 时 flush 防抖） */
  const flush = useCallback(() => {
    if (timerRef.current) window.clearTimeout(timerRef.current)
    setCommitted(valueRef.current.trim())
  }, [])

  return [value, handleChange, committed, flush] as const
}

export function LogsPage() {
  const { user, hasPermission } = usePermissions()
  const canManage = hasPermission('log:manage')
  const canUseWs = hasPermission('log:websocket')
  const canRead = hasPermission('log:read')

  const algorithmOptionsQuery = useAlgorithmOptions()
  const globalAlgorithmType = useAlgorithmStore((s) => s.algorithmId)

  /** 算法筛选下拉选项（domain AlgorithmOption{id,name} → {value,label}，对照 algorithm-config 口径） */
  const algorithmFilterOptions = useMemo(
    () =>
      algorithmOptionsQuery.options.map((option) => ({
        value: option.id,
        label: option.name,
      })),
    [algorithmOptionsQuery.options]
  )

  /* ───────── 筛选状态（本地态，算法配置同款口径） ───────── */
  const [searchInput, handleSearchChange, searchKeyword, flushSearch] = useDebouncedSearch()
  const [filters, setFilters] = useState<LogFilterState>(EMPTY_FILTER_STATE)
  const [advanced, setAdvanced] = useState<LogAdvancedState>(EMPTY_ADVANCED_STATE)
  const [selectedLevels, setSelectedLevels] = useState<string[]>(() => [...LOG_LEVELS])
  const [viewScope, setViewScope] = useState<ViewScope>('all')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [liveLogs, setLiveLogs] = useState<Log[]>([])

  /* ───────── 弹窗群 ───────── */
  const [exportOpen, setExportOpen] = useState(false)
  const [clearOpen, setClearOpen] = useState(false)
  const [realtimeConfigOpen, setRealtimeConfigOpen] = useState(false)

  /* ───────── 实时配置 ───────── */
  const [realtimeEnabled, setRealtimeEnabled] = useState(false)
  const [pollIntervalMs, setPollIntervalMs] = useState(5000)
  const [autoScroll, setAutoScroll] = useState(true)
  const [toastEnabled, setToastEnabled] = useState(true)
  const scrollRef = useRef<HTMLDivElement | null>(null)

  const { mark, exportLogs, clearLogs } = useLogMutations()

  // 全局算法切换器联动（§2.2：切换全局算法后日志页算法筛选同步为当前全局算法）
  useEffect(() => {
    if (globalAlgorithmType) {
      setFilters((prev) => ({ ...prev, algorithmType: globalAlgorithmType }))
    }
  }, [globalAlgorithmType])

  const patchFilters = useCallback((patch: Partial<LogFilterState>) => {
    setFilters((prev) => ({ ...prev, ...patch }))
    setPage(1)
  }, [])

  const patchAdvanced = useCallback((patch: Partial<LogAdvancedState>) => {
    setAdvanced((prev) => ({ ...prev, ...patch }))
    setPage(1)
  }, [])

  const toggleLevel = useCallback((level: string) => {
    setSelectedLevels((prev) =>
      prev.includes(level) ? prev.filter((l) => l !== level) : [...prev, level]
    )
    setPage(1)
  }, [])

  /* ───────── 查询参数（LogQuery → adapter 转 snake_case） ───────── */
  const query = useMemo<LogQuery>(() => {
    const q: LogQuery = {
      keyword: searchKeyword || undefined,
      startTime: filters.startTime || undefined,
      endTime: filters.endTime || undefined,
      category: filters.category,
      module: filters.module,
      mark: filters.mark,
      algorithmType: filters.algorithmType,
      page,
      perPage: pageSize,
    }
    if (selectedLevels.length > 0 && selectedLevels.length < LOG_LEVELS.length) {
      q.level = selectedLevels.join(',')
    }
    if (advanced.deviceId) q.deviceId = advanced.deviceId
    if (advanced.taskId) q.taskId = advanced.taskId
    if (advanced.evaluationId) q.evaluationId = advanced.evaluationId
    if (advanced.threadId) q.threadId = advanced.threadId
    if (advanced.contentInclude) q.contentInclude = advanced.contentInclude
    if (advanced.contentExclude) q.contentExclude = advanced.contentExclude
    // 仅自己范围（后端 LogListQuery 无 user_id，待 FEAT INT-806；Tab 已置灰不可达，保留接线点）
    if (viewScope === 'self' && user) q.userId = user.id
    return q
  }, [
    searchKeyword,
    filters,
    advanced,
    selectedLevels,
    viewScope,
    user,
    page,
    pageSize,
  ])

  const logsQuery = useLogsQuery(query)
  const statsQuery = useLogStatsQuery(query)

  const rows = logsQuery.data?.items ?? []
  const total = logsQuery.data?.total ?? 0
  const pageCount = Math.max(1, logsQuery.data?.pages ?? 1)

  // 筛选变化 → 清空实时增量（新筛选下的轮询从新列表 lastId 续）
  const querySignature = JSON.stringify(query)
  useEffect(() => {
    setLiveLogs([])
  }, [querySignature])

  /* ───────── 实时监控（§4.6：WS 主通道 + refresh 轮询兜底） ───────── */
  const handleNewLogs = useCallback(
    (items: Log[]) => {
      if (page !== 1) return // 仅首页插顶（对照 Vue：非首页不轮询插顶）
      setLiveLogs((prev) => {
        const seen = new Set(prev.map((log) => log.id))
        const fresh = items.filter((log) => !seen.has(log.id))
        return [...fresh, ...prev]
      })
      if (autoScroll && scrollRef.current) {
        scrollRef.current.scrollTop = 0
      }
    },
    [page, autoScroll]
  )

  // mergedRows：实时增量插顶 + 去重（§4.4 流式；须在 useLogRealtime 之前声明）
  const mergedRows = useMemo(() => {
    if (liveLogs.length === 0) return rows
    const seen = new Set<number>()
    return [...liveLogs, ...rows].filter((log) => {
      if (seen.has(log.id)) return false
      seen.add(log.id)
      return true
    })
  }, [liveLogs, rows])

  const realtime = useLogRealtime({
    enabled: realtimeEnabled,
    canUseWs,
    canPoll: canManage,
    query,
    logs: mergedRows,
    onNewLogs: handleNewLogs,
    pollBaseIntervalMs: pollIntervalMs,
    toastEnabled,
  })

  const activeFilter = hasActiveFilters(filters, advanced)

  /* ───────── 选择 ───────── */
  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = (ids: number[]) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (ids.length > 0 && ids.every((id) => next.has(id))) {
        ids.forEach((id) => next.delete(id))
      } else {
        ids.forEach((id) => next.add(id))
      }
      return next
    })
  }

  const selectedLogs = useMemo(
    () => mergedRows.filter((log) => selectedIds.has(log.id)),
    [mergedRows, selectedIds]
  )

  /* ───────── 操作 ───────── */
  const copyLine = (log: Log) =>
    `[${log.time}] [${log.level.toUpperCase()}] [${log.module}] ${log.content}`

  const handleCopy = (log: Log) => {
    void navigator.clipboard.writeText(copyLine(log))
    toast.success('已复制')
  }

  const handleCopySelected = () => {
    void navigator.clipboard.writeText(selectedLogs.map(copyLine).join('\n'))
    toast.success(`已复制 ${selectedLogs.length} 条日志`)
  }

  const handleMarkColor = (logIds: number[], color: string) => {
    mark.mutate({ logIds, mark: color })
  }

  const handleRowMark = (logId: number, color: string) => {
    const log = mergedRows.find((row) => row.id === logId)
    // 同色切换 = 取消标记（对照 Vue markLog toggle）
    const nextMark = log?.mark === color ? '' : color
    handleMarkColor([logId], nextMark)
  }

  const handleBatchMark = (color: string) => {
    handleMarkColor([...selectedIds], color)
    setSelectedIds(new Set())
  }

  const handleExport = (format: string) => {
    const level =
      selectedLevels.length > 0 && selectedLevels.length < LOG_LEVELS.length
        ? selectedLevels.join(',')
        : undefined
    exportLogs.mutate({
      format,
      level,
      module: filters.module !== 'all' ? filters.module : undefined,
    })
    setExportOpen(false)
  }

  const handleExportSelected = () => {
    exportLogs.mutate({ logIds: [...selectedIds].join(',') })
  }

  const handleClear = (beforeDatetime: string, keepMarked: boolean) => {
    clearLogs.mutate(
      { beforeDatetime: beforeDatetime || undefined, keepMarked },
      {
        onSuccess: () => {
          setSelectedIds(new Set())
          setLiveLogs([])
          void logsQuery.refetch()
        },
      }
    )
    setClearOpen(false)
  }

  const handleRefresh = async () => {
    const lastId = mergedRows.reduce((max, log) => Math.max(max, log.id), 0)
    try {
      const result = await refreshLogs(lastId)
      if (result.newCount > 0) toast.success(`刷新到 ${result.newCount} 条新日志`)
      void logsQuery.refetch()
    } catch {
      void logsQuery.refetch()
      toast.info('日志已刷新')
    }
  }

  const resetFilters = () => {
    setFilters(EMPTY_FILTER_STATE)
    setAdvanced(EMPTY_ADVANCED_STATE)
    setSelectedLevels([...LOG_LEVELS])
    setLiveLogs([])
    setPage(1)
  }

  const canRealtime = canUseWs || canManage

  return (
    <>
      <SectionPageLayout fixedContent>
        <SectionPageLayout.Title>
          <span className='flex flex-wrap items-center gap-2'>
            日志查看
            {realtimeEnabled && (
              <Badge variant='outline' className='font-normal'>
                实时监控中
              </Badge>
            )}
          </span>
        </SectionPageLayout.Title>

        <SectionPageLayout.Actions>
          <div className='flex flex-wrap items-center gap-2'>
            <TooltipProvider delay={100}>
              <Tooltip>
                <TooltipTrigger
                  render={
                    <div className='flex items-center gap-1.5 text-sm'>
                      <Switch
                        size='sm'
                        checked={realtimeEnabled}
                        onCheckedChange={setRealtimeEnabled}
                        disabled={!canRealtime}
                        aria-label='实时监控'
                      />
                      <span className='text-muted-foreground'>实时监控</span>
                    </div>
                  }
                />
                {!canRealtime && (
                  <TooltipContent>实时推送鉴权待后端立项（log:websocket）</TooltipContent>
                )}
              </Tooltip>
            </TooltipProvider>
            {canManage && (
              <Tabs
                value={viewScope}
                onValueChange={(value) => setViewScope((value ?? 'all') as ViewScope)}
              >
                <TabsList variant='line'>
                  <TabsTrigger value='all'>全部</TabsTrigger>
                  {/* 仅自己过滤后端 LogListQuery 无 user_id（INT-763 审计 P3-1，FEAT INT-806）：
                      落地前置灰 + Tooltip，避免用户以为已过滤 */}
                  <TooltipProvider delay={100}>
                    <Tooltip>
                      <TooltipTrigger
                        render={
                          <span className='inline-flex'>
                            <TabsTrigger value='self' disabled>
                              仅自己
                            </TabsTrigger>
                          </span>
                        }
                      />
                      <TooltipContent>仅自己过滤待后端接口（FEAT INT-806）落地</TooltipContent>
                    </Tooltip>
                  </TooltipProvider>
                </TabsList>
              </Tabs>
            )}
            <Button variant='outline' size='sm' className='gap-1.5' onClick={() => void handleRefresh()}>
              <RefreshCw aria-hidden='true' className='size-3.5' />
              刷新日志
            </Button>
            {canRead && (
              <Button variant='outline' size='sm' className='gap-1.5' onClick={() => setExportOpen(true)}>
                <FileDown aria-hidden='true' className='size-3.5' />
                导出日志
              </Button>
            )}
            {canManage && (
              <Button variant='outline' size='sm' className='gap-1.5' onClick={() => setClearOpen(true)}>
                <Trash2 aria-hidden='true' className='size-3.5' />
                清除日志
              </Button>
            )}
            {canRead && (
              <Button
                variant='ghost'
                size='sm'
                className='gap-1.5'
                render={
                  <Link to='/system-settings/operations/log-maintenance'>
                    <Archive aria-hidden='true' className='size-3.5' />
                    查看归档
                  </Link>
                }
              />
            )}
          </div>
        </SectionPageLayout.Actions>

        <SectionPageLayout.Content>
          <div className='flex h-full min-h-0 flex-col gap-3' ref={scrollRef}>
            <LogsFilterToolbar
              searchValue={searchInput}
              onSearchChange={handleSearchChange}
              onSearch={() => {
                flushSearch()
                setPage(1)
              }}
              searchLoading={logsQuery.isFetching}
              filters={filters}
              onFilterChange={patchFilters}
              selectedLevels={selectedLevels}
              onToggleLevel={toggleLevel}
              advanced={advanced}
              onAdvancedChange={patchAdvanced}
              algorithmOptions={algorithmFilterOptions}
              onReset={resetFilters}
              hasActiveFilters={activeFilter}
            />

            <LogsStatsRow
              stats={statsQuery.data}
              loading={statsQuery.isLoading}
              hasError={statsQuery.isError}
            />

            {realtimeEnabled && (
              <LogsRealtimeIndicator
                status={realtime.status}
                statusText={realtime.statusText}
                logRate={realtime.logRate}
                logDelay={realtime.logDelay}
                autoScroll={autoScroll}
                onToggleAutoScroll={() => setAutoScroll((v) => !v)}
                onOpenConfig={() => setRealtimeConfigOpen(true)}
              />
            )}

            <div className='min-h-0 flex-1 overflow-y-auto'>
              <LogsTable
                rows={mergedRows}
                loading={logsQuery.isLoading}
                error={logsQuery.isError}
                onRetry={() => void logsQuery.refetch()}
                hasActiveFilters={activeFilter || searchKeyword !== ''}
                selectedIds={selectedIds}
                onToggleSelect={toggleSelect}
                onToggleSelectAll={toggleSelectAll}
                canManage={canManage}
                onMarkColor={handleRowMark}
                onCopy={handleCopy}
                sortOrder='desc'
                onSortChange={() => undefined}
              />
            </div>

            {selectedIds.size > 0 && (
              <LogsBulkActions
                count={selectedIds.size}
                canManage={canManage}
                onMarkColor={handleBatchMark}
                onCopySelected={handleCopySelected}
                onExportSelected={handleExportSelected}
              />
            )}

            <PageFooterPortal>
              <PaginationBar
                page={page}
                pageCount={pageCount}
                pageSize={pageSize}
                total={total}
                onPageChange={setPage}
                onPageSizeChange={(size) => {
                  setPageSize(size)
                  setPage(1)
                }}
              />
            </PageFooterPortal>
          </div>
        </SectionPageLayout.Content>
      </SectionPageLayout>

      {/* 弹窗群（§7.9-7.11） */}
      <LogExportDialog
        open={exportOpen}
        onOpenChange={setExportOpen}
        filters={filters}
        selectedLevels={selectedLevels}
        pending={exportLogs.isPending}
        onExport={handleExport}
      />
      <LogClearDialog
        open={clearOpen}
        onOpenChange={setClearOpen}
        totalCount={statsQuery.data?.total}
        pending={clearLogs.isPending}
        onClear={handleClear}
      />
      <RealtimeConfigDialog
        open={realtimeConfigOpen}
        onOpenChange={setRealtimeConfigOpen}
        pollIntervalMs={pollIntervalMs}
        onPollIntervalChange={setPollIntervalMs}
        autoScroll={autoScroll}
        onAutoScrollChange={setAutoScroll}
        toastEnabled={toastEnabled}
        onToastEnabledChange={setToastEnabled}
      />
    </>
  )
}

/* ───────────────────────── 分页条（对照 algorithm-config §3.7） ───────────────────────── */

function PaginationBar({
  page,
  pageCount,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
}: {
  page: number
  pageCount: number
  pageSize: number
  total: number
  onPageChange: (page: number) => void
  onPageSizeChange: (size: number) => void
}) {
  return (
    <div className='flex flex-wrap items-center justify-end gap-2 text-sm'>
      <span className='text-muted-foreground tabular-nums'>
        共 {total.toLocaleString()} 条日志 · {page}/{pageCount} 页
      </span>
      <Select
        value={String(pageSize)}
        onValueChange={(value) => onPageSizeChange(Number(value ?? DEFAULT_PAGE_SIZE))}
      >
        <SelectTrigger size='sm' className='w-24'>
          <SelectValue>{pageSize} 条/页</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {PAGE_SIZE_OPTIONS.map((size) => (
            <SelectItem key={size} value={String(size)}>
              {size} 条/页
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <div className='flex items-center gap-1'>
        <Button
          variant='outline'
          size='sm'
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
        >
          上一页
        </Button>
        <Button
          variant='outline'
          size='sm'
          disabled={page >= pageCount}
          onClick={() => onPageChange(page + 1)}
        >
          下一页
        </Button>
      </div>
    </div>
  )
}
