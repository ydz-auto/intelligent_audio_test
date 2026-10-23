/**
 * 日志查看页（interfaces 层；17_配置运维.md §4，usage-logs 版式对位）。
 * SectionPageLayout fixedContent + Title「日志查看」实时徽标 + Actions（实时监控 Switch
 * log:websocket + 视图范围 Tabs log:manage + 刷新/导出/清除 + 查看归档 link）
 * + LogsFilterToolbar + 统计徽章行 ×4 + 实时监控指示器 + 日志表格（流式增量插顶）+
 * 批量浮条 + 分页 Portal + 三弹窗（§7.9 导出 / §7.10 清除 / §7.11 实时配置）。
 * 数据真实接口（INT-693 接线）：GET /logs、GET /logs/stats、POST /logs/refresh、
 * PUT /logs/mark、POST /logs/clear、POST /logs/export（经 client.ts）。
 */
import { Link } from '@tanstack/react-router'
import { FileText, RefreshCw } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { PageFooterPortal } from '@/components/layout/components/page-footer'
import { SectionPageLayout } from '@/components/layout/components/section-page-layout'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { useAlgorithmOptions } from '@/application/hooks/use-algorithm-options'
import { useGlobalAlgorithm } from '@/application/hooks/use-global-algorithm'
import { usePermissions } from '@/application/hooks/use-permissions'
import { useLogListQuery, useLogStatsQuery } from '@/application/logs/useLogList'
import { useLogRealtime } from '@/application/logs/useLogRealtime'
import { useLogMutations } from '@/application/logs/useLogMutations'
import type { LogWsFilter } from '@/infrastructure/realtime/useLogRealtimeWs'
import type { LogExportInput, LogItem, LogQuery } from '@/domain/models/log'
import {
  DEFAULT_REALTIME_CONFIG,
  LOG_CATEGORY_OPTIONS,
  LOG_DEFAULT_PAGE_SIZE,
  LOG_LEVEL_OPTIONS,
  LOG_MARK_FILTER_OPTIONS,
  LOG_MODULE_OPTIONS,
  LOG_PAGE_SIZE_OPTIONS,
  LOG_SCOPE_OPTIONS,
  getLogOptionLabel,
  type LogScope,
} from '@/features/logs/constants'
import {
  LogsFilterToolbar,
  type LogAdvancedFilters,
} from '@/features/logs/components/logs-filter-toolbar'
import { LogsStatsRow } from '@/features/logs/components/logs-stats-row'
import {
  LogsTable,
  formatLogCopy,
  sortLogItems,
  type LogSort,
  type LogSortKey,
} from '@/features/logs/components/logs-table'
import { RealtimeMonitorBar } from '@/features/logs/components/realtime-monitor-bar'
import { LogsBulkActions } from '@/features/logs/components/logs-bulk-actions'
import { ExportLogsDialog, type LogFilterSummary } from '@/features/logs/components/modals/export-logs-dialog'
import { ClearLogsDialog } from '@/features/logs/components/modals/clear-logs-dialog'
import { RealtimeConfigDialog } from '@/features/logs/components/modals/realtime-config-dialog'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { useDialog } from '@/hooks/use-dialog'

const EMPTY_ADVANCED: LogAdvancedFilters = {
  deviceId: '',
  taskId: '',
  evaluationId: '',
  userId: '',
  threadId: '',
  contentInclude: '',
  contentExclude: '',
}

export function LogsPage() {
  const { hasPermission, user } = usePermissions()
  const canManage = hasPermission('log:manage')
  const canRealtime = hasPermission('log:websocket')
  const canViewScope = canManage

  const algorithmOptionsQuery = useAlgorithmOptions()
  const { algorithmId } = useGlobalAlgorithm()

  /* ───────── 筛选状态（§4.2；本地态，接线后 validateSearch 化） ───────── */
  const [searchInput, setSearchInput] = useState('')
  const [searchKeyword, setSearchKeyword] = useState('')
  const [category, setCategory] = useState('all')
  const [module, setModule] = useState('all')
  const [markFilter, setMarkFilter] = useState('all')
  const [algorithmType, setAlgorithmType] = useState('all')
  const [startTime, setStartTime] = useState('')
  const [endTime, setEndTime] = useState('')
  const [selectedLevels, setSelectedLevels] = useState<string[]>(
    LOG_LEVEL_OPTIONS.map((option) => option.value)
  )
  const [advanced, setAdvanced] = useState<LogAdvancedFilters>(EMPTY_ADVANCED)
  const [scope, setScope] = useState<LogScope>('all')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(LOG_DEFAULT_PAGE_SIZE)
  /* 列头排序（§4.4 排序列；null=服务端原序，客户端排序对齐 V9.7.10 sortLogs） */
  const [sort, setSort] = useState<LogSort | null>(null)

  /* ───────── 弹窗 + 选择 + 展开 ───────── */
  const [exportOpen, exportDialog] = useDialog()
  const [clearOpen, clearDialog] = useDialog()
  const [realtimeConfigOpen, realtimeConfigDialog] = useDialog()
  /** 清除弹窗的时间点（弹窗持有输入、页面持有值：估算按它另发统计，INT-1654） */
  const [clearBefore, setClearBefore] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [expandedId, setExpandedId] = useState<number | null>(null)

  /* ───────── 搜索防抖（Enter 应用 → 300ms 提交，§4.2） ───────── */
  const searchTimerRef = useRef<number | null>(null)
  const handleSearchInput = useCallback((value: string) => {
    setSearchInput(value)
    if (searchTimerRef.current) window.clearTimeout(searchTimerRef.current)
    searchTimerRef.current = window.setTimeout(() => {
      setSearchKeyword(value.trim())
      setPage(1)
    }, 300)
  }, [])

  /* ───────── 全局算法切换器联动（§2.2） ───────── */
  useEffect(() => {
    if (algorithmId) setAlgorithmType(algorithmId)
  }, [algorithmId])

  /* ───────── 查询装配（筛选/徽章/表格/导出摘要同源，§4.2/验收 3） ───────── */
  const query = useMemo<LogQuery>(() => {
    const next: LogQuery = {
      page,
      perPage: pageSize,
      keyword: searchKeyword || undefined,
    }
    if (category !== 'all') next.category = category
    if (module !== 'all') next.module = module
    if (markFilter !== 'all') next.mark = markFilter
    if (algorithmType !== 'all') next.algorithmType = algorithmType
    if (startTime) next.startTime = startTime
    if (endTime) next.endTime = endTime
    // 级别：全选/空不传；部分选 → 逗号串（对齐 Vue LogView 语义）
    if (selectedLevels.length > 0 && selectedLevels.length < LOG_LEVEL_OPTIONS.length) {
      next.level = selectedLevels.join(',')
    }
    if (advanced.deviceId) next.deviceId = advanced.deviceId
    if (advanced.taskId) next.taskId = advanced.taskId
    if (advanced.evaluationId) next.evaluationId = advanced.evaluationId
    if (advanced.userId) next.userId = advanced.userId
    if (advanced.threadId) next.threadId = advanced.threadId
    if (advanced.contentInclude) next.contentInclude = advanced.contentInclude
    if (advanced.contentExclude) next.contentExclude = advanced.contentExclude
    if (scope === 'mine' && user?.id) next.userId = user.id
    return next
  }, [
    page, pageSize, searchKeyword, category, module, markFilter, algorithmType,
    startTime, endTime, selectedLevels, advanced, scope, user?.id,
  ])

  /* ───────── 实时 WS 订阅条件（§4.6 set_filter：levels/modules/keyword/task_id 四维收敛） ───────── */
  const realtimeWsFilter = useMemo<LogWsFilter>(() => ({
    // 全选级别 = 无级别过滤（后端 levels 为空数组/缺失即全放行）
    levels: selectedLevels.length < LOG_LEVEL_OPTIONS.length ? selectedLevels : undefined,
    modules: module !== 'all' ? [module] : undefined,
    keyword: searchKeyword || undefined,
    taskId: advanced.taskId || undefined,
  }), [selectedLevels, module, searchKeyword, advanced.taskId])

  const listQuery = useLogListQuery(query)
  const statsQuery = useLogStatsQuery(query)
  /* 清除弹窗范围估算：POST /logs/clear 只按 before_datetime/keep_marked 生效，
     与分类/级别/关键词等列表筛选无关 → 另发「无筛选 + 时间点之前」的统计（INT-1654） */
  const clearEstimateQuery = useMemo<LogQuery>(() => ({
    page: 1,
    perPage: 1,
    endTime: clearBefore || undefined,
  }), [clearBefore])
  const clearEstimateStatsQuery = useLogStatsQuery(clearEstimateQuery, { enabled: clearOpen })
  const realtime = useLogRealtime(DEFAULT_REALTIME_CONFIG, {
    wsFilter: realtimeWsFilter,
    canPollFallback: canManage,
  })
  const { mark, clear, exportLogs } = useLogMutations()

  // 筛选条件变更 → 清空实时增量缓冲（新日志与旧筛选不匹配，避免脏显示）
  useEffect(() => {
    realtime.resetNewLogs()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query])

  /* ───────── 表格行 = 实时增量插顶 + 服务端分页列表（去重） ───────── */
  const rows = useMemo(() => {
    const server = listQuery.data?.items ?? []
    if (realtime.newLogs.length === 0) return server
    const seen = new Set(realtime.newLogs.map((log) => log.id))
    return [...realtime.newLogs, ...server.filter((log) => !seen.has(log.id))]
  }, [realtime.newLogs, listQuery.data])

  /* ───────── 列头排序（§4.4 排序列；点升/降切换，第三次回服务端原序） ───────── */
  const toggleSort = useCallback((key: LogSortKey) => {
    setSort((prev) => {
      if (!prev || prev.key !== key) return { key, direction: 'desc' }
      if (prev.direction === 'desc') return { key, direction: 'asc' }
      return null
    })
  }, [])

  const sortedRows = useMemo(() => sortLogItems(rows, sort), [rows, sort])

  const total = listQuery.data?.total ?? 0
  const pageCount = Math.max(1, Math.ceil(total / pageSize))

  /* ───────── 自动滚动（§4.6：新日志到达滚到列表底部） ───────── */
  const tableScrollRef = useRef<HTMLDivElement | null>(null)
  useEffect(() => {
    if (realtime.enabled && realtime.config.autoScroll && tableScrollRef.current) {
      tableScrollRef.current.scrollTop = tableScrollRef.current.scrollHeight
    }
  }, [realtime.enabled, realtime.config.autoScroll, realtime.newLogs.length])

  /* ───────── 选择 / 展开 ───────── */
  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleSelectAll = () => {
    setSelectedIds((prev) => {
      if (rows.length > 0 && prev.size === rows.length) return new Set()
      return new Set(rows.map((log) => log.id))
    })
  }

  const selectedLogs = useMemo(
    () => rows.filter((log) => selectedIds.has(log.id)),
    [rows, selectedIds]
  )

  /* ───────── 实时开关（§4.6：log:websocket 判定；WS 主通道 + refresh 兜底需 log:manage） ───────── */
  const handleRealtimeToggle = (value: boolean) => {
    if (value && !canRealtime) {
      toast.info('实时推送鉴权待后端立项')
      return
    }
    realtime.setEnabled(value)
    if (!value) {
      setExpandedId(null)
      setSelectedIds(new Set())
    }
  }

  /* ───────── 写操作 ───────── */
  const handleMark = (log: LogItem, markColor: string) => {
    mark.mutate({ logIds: [log.id], mark: markColor })
  }

  const handleBatchMark = (markColor: string) => {
    if (selectedIds.size === 0) return
    mark.mutate(
      { logIds: Array.from(selectedIds), mark: markColor },
      { onSuccess: () => setSelectedIds(new Set()) }
    )
  }

  const handleCopySelected = () => {
    if (selectedLogs.length === 0) return
    const text = selectedLogs.map(formatLogCopy).join('\n')
    void navigator.clipboard.writeText(text).then(() => toast.success('已复制到剪贴板'))
  }

  const handleExportSelected = () => {
    if (selectedIds.size === 0) return
    exportLogs.mutate({ input: { logIds: Array.from(selectedIds), format: 'txt' }, query })
    setSelectedIds(new Set())
  }

  const handleExport = (format: LogExportInput['format']) => {
    // 导出成功后关闭弹窗（V9.7.10 口径：确认即关；避免停在弹窗上重复误触）
    exportLogs.mutate(
      { input: { format }, query },
      { onSuccess: () => exportDialog.close() }
    )
  }

  const handleClear = (beforeDatetime: string | null, keepMarked: boolean) => {
    clear.mutate({ beforeDatetime, keepMarked })
    setClearBefore('')
    clearDialog.close()
  }

  /* ───────── 清除过滤器（§4.2 onReset） ───────── */
  const hasActiveFilters =
    searchKeyword !== '' ||
    category !== 'all' ||
    module !== 'all' ||
    markFilter !== 'all' ||
    algorithmType !== 'all' ||
    startTime !== '' ||
    endTime !== '' ||
    selectedLevels.length < LOG_LEVEL_OPTIONS.length ||
    Object.values(advanced).some(Boolean)

  const handleReset = () => {
    setSearchInput('')
    setSearchKeyword('')
    setCategory('all')
    setModule('all')
    setMarkFilter('all')
    setAlgorithmType(algorithmId || 'all')
    setStartTime('')
    setEndTime('')
    setSelectedLevels(LOG_LEVEL_OPTIONS.map((option) => option.value))
    setAdvanced(EMPTY_ADVANCED)
    setScope('all')
    setPage(1)
  }

  /* ───────── 导出弹窗筛选摘要（§7.9，随筛选实时联动；取值中文标签，不外露后端枚举） ───────── */
  const algorithmTypeLabel = useMemo(() => {
    if (algorithmType === 'all') return undefined
    return (
      algorithmOptionsQuery.options.find((option) => option.value === algorithmType)
        ?.name ?? algorithmType
    )
  }, [algorithmType, algorithmOptionsQuery.options])

  const exportSummary = useMemo<LogFilterSummary>(() => {
    const levelLabel =
      selectedLevels.length === LOG_LEVEL_OPTIONS.length
        ? '全部'
        : selectedLevels.join(',') || '全部'
    return {
      startTime: startTime || undefined,
      endTime: endTime || undefined,
      category:
        category === 'all'
          ? undefined
          : getLogOptionLabel(LOG_CATEGORY_OPTIONS, category),
      module:
        module === 'all' ? undefined : getLogOptionLabel(LOG_MODULE_OPTIONS, module),
      level: levelLabel,
      mark:
        markFilter === 'all'
          ? undefined
          : getLogOptionLabel(LOG_MARK_FILTER_OPTIONS, markFilter),
      algorithmType: algorithmTypeLabel,
      keyword: searchKeyword || undefined,
    }
  }, [
    startTime, endTime, category, module, markFilter, algorithmTypeLabel, searchKeyword,
    selectedLevels,
  ])

  /* ───────── 页面装配（§4.1 骨架） ───────── */
  return (
    <>
      <SectionPageLayout fixedContent>
        <SectionPageLayout.Title>
          <span className='flex flex-wrap items-center gap-2'>
            日志查看
            <StatusBadge
              label={realtime.enabled ? '实时监控中' : '实时监控已停止'}
              variant={realtime.enabled ? 'info' : 'neutral'}
            />
          </span>
        </SectionPageLayout.Title>

        <SectionPageLayout.Actions>
          <span className='flex flex-wrap items-center gap-2'>
            {canRealtime && (
              <Tooltip>
                <TooltipTrigger render={<label />}>
                  <span className='flex items-center gap-1.5 text-xs'>
                    实时日志
                    <Switch
                      checked={realtime.enabled}
                      onCheckedChange={handleRealtimeToggle}
                      size='sm'
                      aria-label='实时日志开关'
                    />
                  </span>
                </TooltipTrigger>
                {!canManage && (
                  <TooltipContent>
                    已开通 WS 实时订阅；refresh 轮询兜底需 log:manage，WS 不可用时无法降级
                  </TooltipContent>
                )}
              </Tooltip>
            )}
            {canViewScope && (
              <Tabs
                value={scope}
                onValueChange={(value) => {
                  setScope((value ?? 'all') as LogScope)
                  setPage(1)
                }}
              >
                <TabsList>
                  {LOG_SCOPE_OPTIONS.map((option) => (
                    <TabsTrigger key={option.value} value={option.value}>
                      {option.label}
                    </TabsTrigger>
                  ))}
                </TabsList>
              </Tabs>
            )}
            <Button
              variant='outline'
              size='sm'
              className='h-7 gap-1.5 text-xs'
              onClick={() => void listQuery.refetch()}
              disabled={listQuery.isFetching}
            >
              <RefreshCw aria-hidden='true' className='size-3.5' />
              刷新日志
            </Button>
            <Button
              variant='outline'
              size='sm'
              className='h-7 gap-1.5 text-xs'
              onClick={exportDialog.open}
            >
              导出日志
            </Button>
            {canManage && (
              <Button
                variant='outline'
                size='sm'
                className='h-7 gap-1.5 text-xs'
                onClick={clearDialog.open}
              >
                清除日志
              </Button>
            )}
            <Button variant='ghost' size='sm' className='h-7 gap-1.5 text-xs' render={<Link to='/system-settings/$domain/$section' params={{ domain: 'operations', section: 'log-maintenance' }} />}>
              <FileText aria-hidden='true' className='size-3.5' />
              查看归档
            </Button>
          </span>
        </SectionPageLayout.Actions>

        <SectionPageLayout.Content>
          <div className='flex h-full min-h-0 flex-col gap-2.5'>
            <LogsFilterToolbar
              searchValue={searchInput}
              onSearchInput={handleSearchInput}
              category={category}
              onCategory={(v) => {
                setCategory(v)
                setPage(1)
              }}
              module={module}
              onModule={(v) => {
                setModule(v)
                setPage(1)
              }}
              markFilter={markFilter}
              onMarkFilter={(v) => {
                setMarkFilter(v)
                setPage(1)
              }}
              algorithmType={algorithmType}
              onAlgorithmType={(v) => {
                setAlgorithmType(v)
                setPage(1)
              }}
              algorithmOptions={algorithmOptionsQuery.options}
              startTime={startTime}
              onStartTime={(v) => {
                setStartTime(v)
                setPage(1)
              }}
              endTime={endTime}
              onEndTime={(v) => {
                setEndTime(v)
                setPage(1)
              }}
              selectedLevels={selectedLevels}
              onToggleLevel={(level) => {
                setSelectedLevels((prev) =>
                  prev.includes(level)
                    ? prev.filter((item) => item !== level)
                    : [...prev, level]
                )
                setPage(1)
              }}
              advanced={advanced}
              onAdvancedChange={(patch) => {
                setAdvanced((prev) => ({ ...prev, ...patch }))
                setPage(1)
              }}
              onReset={handleReset}
              isFetching={listQuery.isFetching}
              hasActiveFilters={hasActiveFilters}
            />

            <LogsStatsRow stats={statsQuery.data} isLoading={statsQuery.isLoading} />

            {realtime.enabled && (
              <RealtimeMonitorBar
                connection={realtime.connection}
                logRate={realtime.logRate}
                logDelay={realtime.logDelay}
                config={realtime.config}
                onAutoScrollChange={(v) => realtime.setConfig({ autoScroll: v })}
                onOpenConfig={realtimeConfigDialog.open}
              />
            )}

            <div
              ref={tableScrollRef}
              className='min-h-0 flex-1 overflow-y-auto'
            >
              <LogsTable
                rows={sortedRows}
                loading={listQuery.isLoading}
                error={listQuery.isError}
                onRetry={() => void listQuery.refetch()}
                total={total}
                searchKeyword={searchKeyword}
                selectedIds={selectedIds}
                onToggleSelect={toggleSelect}
                onToggleSelectAll={toggleSelectAll}
                canManage={canManage}
                expandedId={expandedId}
                onToggleExpand={(id) =>
                  setExpandedId((prev) => (prev === id ? null : id))
                }
                onMark={handleMark}
                sort={sort}
                onToggleSort={toggleSort}
              />
            </div>

            {selectedIds.size > 0 && (
              <LogsBulkActions
                count={selectedIds.size}
                canManage={canManage}
                onBatchMark={handleBatchMark}
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

      {/* 三弹窗（§7.9-7.11） */}
      <ExportLogsDialog
        open={exportOpen}
        onOpenChange={(open) => (open ? exportDialog.open() : exportDialog.close())}
        summary={exportSummary}
        onExport={handleExport}
        isPending={exportLogs.isPending}
      />
      <ClearLogsDialog
        open={clearOpen}
        onOpenChange={(open) => (open ? clearDialog.open() : clearDialog.close())}
        estimatedCount={clearEstimateStatsQuery.data?.total}
        before={clearBefore}
        onBeforeChange={setClearBefore}
        onClear={handleClear}
        isPending={clear.isPending}
      />
      <RealtimeConfigDialog
        open={realtimeConfigOpen}
        onOpenChange={(open) =>
          open ? realtimeConfigDialog.open() : realtimeConfigDialog.close()
        }
        config={realtime.config}
        onConfigChange={realtime.setConfig}
      />
    </>
  )
}

/* ───────────────────────── 分页条（§4.4 PageFooterPortal） ───────────────────────── */

/** 每页条数 Select 选项（value=字符串化条数；作 items 供关闭态回显「N 条/页」） */
const PAGE_SIZE_ITEMS = LOG_PAGE_SIZE_OPTIONS.map((size) => ({
  value: String(size),
  label: `${size} 条/页`,
}))

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
        onValueChange={(value) =>
          onPageSizeChange(Number(value ?? LOG_DEFAULT_PAGE_SIZE))
        }
        items={PAGE_SIZE_ITEMS}
      >
        <SelectTrigger size='sm' className='w-24'>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {LOG_PAGE_SIZE_OPTIONS.map((size) => (
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
