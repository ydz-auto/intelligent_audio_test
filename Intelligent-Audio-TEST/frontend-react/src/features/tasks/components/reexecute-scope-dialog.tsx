/**
 * 重新执行 / 重新评估范围选择弹窗（09_任务域.md §5.7，Dialog sm:max-w-3xl）。
 * RadioGroup 三选项（全部用例/仅失败用例/手动选择用例）+ 手动勾选展开区
 * （工具行 = 搜索名称或 ID + 平铺/标签/分组视图 + 状态筛选，照任务详情「关联用例」口径；
 * 全选 Checkbox + 按视图分组的行 Checkbox 列表（组头三态勾选整组全选/取消、组头可展开/收起）；
 * 状态筛选与搜索联动「全选」= 按当前筛选条件全选（含按状态全选）；
 * 重评估追加：评估维度勾选网格（默认全选，候选=本任务用例聚合维度）+
 * 「重新提取设备输出（从存档日志）」Checkbox（默认不勾）；底栏「取消｜确认{已选 n 项}」。
 * 存在人工复核结果（task.detail.reviewCount > 0）时追加硬确认层（§5.7）：
 * 确认后先弹「该任务存在 {N} 条人工复核结果…是否继续？」主钮「覆盖并继续」（destructive）副钮「返回」。
 * 确认后经 infrastructure/api/tasks-control-api（client.ts）发起 retry / reevaluate。
 */
import { ChevronRight, LoaderCircle, Search } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { useTaskDetail } from '@/application/tasks/use-task-detail'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { ConfirmDialog } from '@/components/confirm-dialog'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ApiError } from '@/infrastructure/api/api-error'
import {
  reevaluateTask,
  retryTask,
  type ReexecuteScopeMode,
} from '@/infrastructure/api/tasks-control-api'
import { cn } from '@/lib/utils'
import type { TaskCaseBrief } from '@/domain/models/task'
import {
  caseEvaluationStatusLabel,
  caseEvaluationStatusTone,
} from '@/domain/models/review'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'

type ActionType = 'retry' | 'reevaluate'

const SCOPE_ALL: ReexecuteScopeMode = 'all'
const SCOPE_FAILED: ReexecuteScopeMode = 'failed_only'
const SCOPE_SELECTED: ReexecuteScopeMode = 'selected'

/** 手动选择用例视图（平铺/标签/分组，照任务详情「关联用例」口径） */
type CaseViewMode = 'flat' | 'tag' | 'group'

const CASE_VIEW_OPTIONS: Array<{ value: CaseViewMode; label: string }> = [
  { value: 'flat', label: '平铺' },
  { value: 'tag', label: '标签' },
  { value: 'group', label: '分组' },
]

/** 状态筛选选项（与任务详情「关联用例」同源） */
const CASE_STATUS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: 'all', label: '全部状态' },
  { value: 'pending', label: '等待中' },
  { value: 'queued', label: '排队中' },
  { value: 'running', label: '执行中' },
  { value: 'evaluating', label: '计算指标中' },
  { value: 'completed', label: '已完成' },
  { value: 'execution_failed', label: '执行失败' },
  { value: 'evaluation_failed', label: '评估失败' },
  { value: 'failed', label: '已失败' },
  { value: 'skipped', label: '已跳过' },
  { value: 'stopped', label: '已停止' },
]

const EXECUTION_STATUS_LABEL: Record<string, string> = {
  pending: '等待中',
  queued: '排队中',
  running: '执行中',
  evaluating: '计算指标中',
  calculating: '计算指标中',
  completed: '已完成',
  failed: '执行失败',
  skipped: '已跳过',
  stopped: '已停止',
  deleted: '已删除',
}

/**
 * 状态筛选（照任务详情「关联用例」matchesStatusFilter 口径）：
 * 执行失败 = executionStatus 为 failed；评估失败 = evaluationStatus 为 failed 且执行未失败（互斥）；
 * 其余按任务级/执行/评估任一命中。
 */
function matchesCaseStatus(c: TaskCaseBrief, status: string): boolean {
  if (status === 'all') return true
  if (status === 'execution_failed') return c.executionStatus === 'failed'
  if (status === 'evaluation_failed')
    return c.evaluationStatus === 'failed' && c.executionStatus !== 'failed'
  return c.status === status || c.executionStatus === status || c.evaluationStatus === status
}

export function ReexecuteScopeDialog({
  open,
  onOpenChange,
  taskId,
  taskName,
  actionType,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  taskId: number
  taskName: string
  actionType: ActionType
}) {
  const detailQuery = useTaskDetail(taskId, open && taskId > 0)
  const detail = detailQuery.data

  const [scope, setScope] = useState<ReexecuteScopeMode>(SCOPE_ALL)
  const [selectedCaseIds, setSelectedCaseIds] = useState<string[]>([])
  const [caseView, setCaseView] = useState<CaseViewMode>('flat')
  const [caseKeyword, setCaseKeyword] = useState('')
  const [caseStatus, setCaseStatus] = useState('all')
  /** 标签/分组视图的展开组（默认全部收起，组头可展开；照任务详情「关联用例」口径） */
  const [openGroupKeys, setOpenGroupKeys] = useState<Set<string>>(new Set())
  const [selectedDimensionIds, setSelectedDimensionIds] = useState<number[]>([])
  const [reextractDeviceOutput, setReextractDeviceOutput] = useState(false)
  const [hardConfirmOpen, setHardConfirmOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  /** 维度候选集每次弹窗打开只初始化一次默认全选（用户后续改动不被覆盖） */
  const dimInitRef = useRef(false)

  const isReevaluate = actionType === 'reevaluate'
  const reviewCount = detail?.reviewCount ?? 0

  /** 本任务已执行用例集（task 详情 task.cases；非全库用例） */
  const taskCases = useMemo(() => detail?.cases ?? [], [detail])

  /** 搜索（名称或用例 ID 子串，忽略大小写）+ 状态筛选后的用例集 */
  const filteredCases = useMemo(() => {
    const q = caseKeyword.trim().toLowerCase()
    return taskCases.filter((tc) => {
      if (!matchesCaseStatus(tc, caseStatus)) return false
      if (!q) return true
      return tc.name.toLowerCase().includes(q) || tc.caseId.toLowerCase().includes(q)
    })
  }, [taskCases, caseKeyword, caseStatus])

  /** 按视图分组（标签视图按首标签、分组视图按分组名；无归属归兜底桶） */
  const caseGroups = useMemo(() => {
    if (caseView === 'flat') return null
    const map = new Map<string, TaskCaseBrief[]>()
    for (const tc of filteredCases) {
      const key =
        caseView === 'tag' ? (tc.tags?.[0] ?? '未设置标签') : (tc.groupName ?? '未分组')
      const bucket = map.get(key)
      if (bucket) bucket.push(tc)
      else map.set(key, [tc])
    }
    return [...map.entries()]
  }, [filteredCases, caseView])

  /** 重评估维度候选集 = 本任务用例聚合（task.cases[].evaluationDimensions 去重） */
  const dimensionOptions = useMemo(() => {
    if (!isReevaluate) return []
    const dimMap = new Map<number, string>()
    taskCases.forEach((tc) => {
      ;(tc.evaluationDimensions ?? []).forEach((d) => {
        const id = Number(d?.id)
        if (id && !dimMap.has(id)) dimMap.set(id, d?.name || `维度 ${id}`)
      })
    })
    return Array.from(dimMap, ([id, name]) => ({ id, name }))
  }, [taskCases, isReevaluate])

  const selectedCaseSet = useMemo(() => new Set(selectedCaseIds.map(String)), [selectedCaseIds])
  const selectedDimensionSet = useMemo(() => new Set(selectedDimensionIds), [selectedDimensionIds])

  // 弹窗每次打开重置选择域（§5.7 默认「全部用例」、勾选/过滤/维度/提取开关清空）：
  // 选择域只属于当前打开的任务，上一任务的 scope/caseIds 不得残留到下一任务（代码审计 P2-1）。
  // 必须在维度默认全选 effect 之前声明——先清空再初始化，避免重开同任务时被旧维度覆盖。
  useEffect(() => {
    if (!open) return
    setScope(SCOPE_ALL)
    setSelectedCaseIds([])
    setCaseView('flat')
    setCaseKeyword('')
    setCaseStatus('all')
    setOpenGroupKeys(new Set())
    setSelectedDimensionIds([])
    setReextractDeviceOutput(false)
  }, [open])

  // 重评估维度默认全选（§5.7）：候选集就绪后初始化一次，用户改动不被后续渲染覆盖
  useEffect(() => {
    if (!open) {
      dimInitRef.current = false
      return
    }
    if (isReevaluate && dimensionOptions.length > 0 && !dimInitRef.current) {
      setSelectedDimensionIds(dimensionOptions.map((d) => d.id))
      dimInitRef.current = true
    }
  }, [open, isReevaluate, dimensionOptions])

  const selectedFilteredCount = filteredCases.filter((tc) =>
    selectedCaseSet.has(String(tc.caseId))
  ).length
  const isAllCasesSelected =
    filteredCases.length > 0 && selectedFilteredCount === filteredCases.length
  const isSomeCasesSelected = selectedFilteredCount > 0 && !isAllCasesSelected

  const canConfirm = (() => {
    if (isReevaluate && dimensionOptions.length > 0 && selectedDimensionIds.length === 0) {
      // 空 dimensionIds 后端语义为「不过滤=全量重评」，与「全部取消勾选」界面意图相反，禁止该组合下发
      return false
    }
    if (scope !== SCOPE_SELECTED) return true
    return selectedCaseIds.length > 0
  })()

  const confirmCountText = (() => {
    if (scope === SCOPE_SELECTED) {
      const n = selectedCaseIds.length
      const dimSuffix =
        isReevaluate && selectedDimensionIds.length < dimensionOptions.length
          ? ` / ${selectedDimensionIds.length} 个维度`
          : ''
      return `（已选 ${n} 个用例${dimSuffix}）`
    }
    return ''
  })()

  const toggleCase = (caseId: string) => {
    const key = String(caseId)
    setSelectedCaseIds((prev) =>
      prev.includes(key) ? prev.filter((id) => id !== key) : [...prev, key]
    )
  }

  const toggleSelectAll = () => {
    if (isAllCasesSelected) {
      const removeSet = new Set(filteredCases.map((tc) => String(tc.caseId)))
      setSelectedCaseIds((prev) => prev.filter((id) => !removeSet.has(id)))
    } else {
      setSelectedCaseIds((prev) => {
        const next = new Set(prev.map(String))
        filteredCases.forEach((tc) => next.add(String(tc.caseId)))
        return Array.from(next)
      })
    }
  }

  /** 组内勾选态（组头 Checkbox 三态；照用例管理「组头全选」口径） */
  const groupSelectionState = (groupCases: TaskCaseBrief[]) => {
    const selectedCount = groupCases.filter((tc) =>
      selectedCaseSet.has(String(tc.caseId))
    ).length
    return {
      all: groupCases.length > 0 && selectedCount === groupCases.length,
      some: selectedCount > 0 && selectedCount < groupCases.length,
    }
  }

  /** 组头全选/取消全选（按分组/标签整组勾选，折叠态同样生效） */
  const toggleGroupSelect = (groupCases: TaskCaseBrief[], checked: boolean) => {
    const ids = groupCases.map((tc) => String(tc.caseId))
    setSelectedCaseIds((prev) => {
      const next = new Set(prev.map(String))
      if (checked) ids.forEach((id) => next.add(id))
      else ids.forEach((id) => next.delete(id))
      return Array.from(next)
    })
  }

  const toggleGroupOpen = (groupKey: string) => {
    setOpenGroupKeys((prev) => {
      const next = new Set(prev)
      if (next.has(groupKey)) next.delete(groupKey)
      else next.add(groupKey)
      return next
    })
  }

  /** 用例行（Checkbox + 名称 + 执行/评估状态徽章；平铺态补分组名，分组态由组头承载） */
  const renderCaseRow = (tc: TaskCaseBrief) => {
    const caseId = String(tc.caseId)
    const checked = selectedCaseSet.has(caseId)
    return (
      <label
        key={caseId}
        className={cn(
          'flex cursor-pointer items-center gap-2 rounded-md border bg-background px-2.5 py-1.5 text-sm transition-colors',
          checked && 'bg-accent/40'
        )}
      >
        <Checkbox checked={checked} onCheckedChange={() => toggleCase(tc.caseId)} />
        <span className='min-w-0 flex-1 truncate' title={tc.name}>
          {tc.name}
        </span>
        {tc.executionStatus && (
          <StatusBadge
            label={EXECUTION_STATUS_LABEL[tc.executionStatus] ?? tc.executionStatus}
            variant={
              tc.executionStatus === 'failed'
                ? 'danger'
                : tc.executionStatus === 'completed'
                  ? 'success'
                  : 'neutral'
            }
            className='shrink-0 text-[11px]'
          />
        )}
        <StatusBadge
          label={caseEvaluationStatusLabel(tc.executionStatus, tc.evaluationStatus)}
          variant={caseEvaluationStatusTone(tc.executionStatus, tc.evaluationStatus)}
          className='shrink-0 text-[11px]'
        />
        {caseView === 'flat' && tc.groupName && (
          <span className='text-muted-foreground max-w-24 shrink-0 truncate text-xs'>
            {tc.groupName}
          </span>
        )}
      </label>
    )
  }

  const toggleDimension = (dimId: number) => {
    setSelectedDimensionIds((prev) =>
      prev.includes(dimId) ? prev.filter((id) => id !== dimId) : [...prev, dimId]
    )
  }

  /** 确认：有复核结果先弹硬确认层（§5.7），否则直发 */
  const handleConfirmClick = () => {
    if (!canConfirm) return
    if (reviewCount > 0) {
      setHardConfirmOpen(true)
      return
    }
    void doSubmit()
  }

  const doSubmit = async () => {
    setSubmitting(true)
    try {
      const payload = {
        mode: scope,
        caseIds: scope === SCOPE_SELECTED ? selectedCaseIds : [],
      }
      if (isReevaluate) {
        // 空数组 = 全选（不过滤），仅显式子集时下发
        const dimensionIds =
          selectedDimensionIds.length === dimensionOptions.length ? [] : selectedDimensionIds
        const result = await reevaluateTask(taskId, {
          ...payload,
          dimensionIds,
          reextractDeviceOutput,
        })
        toast.success(result.message || '已发起重新评估')
      } else {
        await retryTask(taskId, payload)
        toast.success('已发起重新执行')
      }
      onOpenChange(false)
    } catch (error) {
      const msg = error instanceof ApiError ? (error.userMessage || error.message) : '操作失败，请稍后重试'
      toast.error(msg)
    } finally {
      setSubmitting(false)
      setHardConfirmOpen(false)
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className='sm:max-w-3xl'>
          <DialogHeader>
            <DialogTitle>{isReevaluate ? '重新评估' : '重新执行'}</DialogTitle>
            <DialogDescription className='truncate'>
              {taskName} · 请选择{isReevaluate ? '评估' : '执行'}范围
            </DialogDescription>
          </DialogHeader>

          <div className='flex flex-col gap-4'>
            {/* 范围三选项（§5.7） */}
            <div className='grid gap-2'>
              {(
                [
                  {
                    key: SCOPE_ALL,
                    title: '全部用例',
                    desc: isReevaluate
                      ? '对该任务下所有执行成功的用例进行重新评估'
                      : '重置并重新执行该任务的全部用例',
                  },
                  {
                    key: SCOPE_FAILED,
                    title: '仅失败用例',
                    desc: isReevaluate
                      ? '仅对评估结果为失败的用例进行重新评估'
                      : '仅重新执行执行失败或评估失败的用例',
                  },
                  {
                    key: SCOPE_SELECTED,
                    title: '手动选择用例',
                    desc: '从本任务已执行的用例集中勾选（支持按标签/分组过滤）',
                  },
                ] as const
              ).map((opt) => {
                const active = scope === opt.key
                return (
                  <button
                    key={opt.key}
                    type='button'
                    data-testid={`reexecute-scope-${opt.key}`}
                    className={cn(
                      'rounded-lg border px-3 py-2.5 text-left transition-colors',
                      active
                        ? 'border-primary bg-primary/[0.06] ring-primary/30 dark:bg-primary/10'
                        : 'hover:bg-muted/50'
                    )}
                    onClick={() => setScope(opt.key)}
                  >
                    <span className='flex items-center gap-2 text-sm font-medium'>
                      <span
                        className={cn(
                          'flex size-4 items-center justify-center rounded-full border',
                          active
                            ? 'border-primary bg-primary text-primary-foreground'
                            : 'border-muted-foreground/40'
                        )}
                      >
                        {active && <span className='size-1.5 rounded-full bg-current' />}
                      </span>
                      {opt.title}
                    </span>
                    <span className='text-muted-foreground mt-1 block text-xs leading-relaxed'>
                      {opt.desc}
                    </span>
                  </button>
                )
              })}
            </div>

            {/* 手动选择用例（§5.7：搜索 + 平铺/标签/分组视图 + 状态筛选 + 全选 + 行 Checkbox 列表） */}
            {scope === SCOPE_SELECTED && (
              <div className='flex flex-col gap-2 rounded-lg border bg-muted/30 p-3'>
                {/* 工具行（照任务详情「关联用例」口径）：搜索名称/ID + 平铺/标签/分组 + 状态筛选 */}
                <div className='flex flex-wrap items-center gap-2'>
                  <div className='relative min-w-40 flex-1'>
                    <Search
                      aria-hidden='true'
                      className='text-muted-foreground pointer-events-none absolute top-1/2 start-2 size-3.5 -translate-y-1/2'
                    />
                    <Input
                      value={caseKeyword}
                      onChange={(e) => setCaseKeyword(e.target.value)}
                      placeholder='搜索用例名称或 ID…'
                      aria-label='搜索用例'
                      className='h-8 ps-7 text-xs'
                    />
                  </div>
                  <Tabs
                    value={caseView}
                    onValueChange={(v) => setCaseView(v as CaseViewMode)}
                    aria-label='用例查看方式'
                  >
                    <TabsList className='h-8 gap-0.5 p-0.5'>
                      {CASE_VIEW_OPTIONS.map((option) => (
                        <TabsTrigger
                          key={option.value}
                          value={option.value}
                          className='px-2 text-xs'
                        >
                          {option.label}
                        </TabsTrigger>
                      ))}
                    </TabsList>
                  </Tabs>
                  <Select
                    value={caseStatus}
                    onValueChange={(value) => setCaseStatus(value ?? 'all')}
                  >
                    <SelectTrigger size='sm' className='h-8 gap-1.5 px-2.5' aria-label='状态筛选'>
                      <SelectValue>
                        {CASE_STATUS_OPTIONS.find((option) => option.value === caseStatus)?.label ??
                          '全部状态'}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent align='end'>
                      {CASE_STATUS_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div className='flex items-center justify-between gap-2'>
                  <label className='flex cursor-pointer items-center gap-2 text-sm'>
                    <Checkbox
                      checked={isAllCasesSelected}
                      indeterminate={isSomeCasesSelected}
                      onCheckedChange={toggleSelectAll}
                    />
                    全选
                  </label>
                  <span className='text-muted-foreground text-xs tabular-nums'>
                    共 {filteredCases.length} 条
                  </span>
                </div>

                {detailQuery.isLoading ? (
                  <div className='flex items-center justify-center gap-2 py-6 text-xs text-muted-foreground'>
                    <Spinner size={14} />
                    正在加载本任务用例...
                  </div>
                ) : detailQuery.isError ? (
                  <div className='flex flex-col items-center gap-2 py-6 text-xs'>
                    <span className='text-destructive'>本任务用例加载失败，请重试</span>
                    <Button
                      size='sm'
                      variant='outline'
                      className='h-7'
                      onClick={() => void detailQuery.refetch()}
                    >
                      重试
                    </Button>
                  </div>
                ) : filteredCases.length === 0 ? (
                  <p className='text-muted-foreground py-6 text-center text-xs'>
                    {taskCases.length === 0 ? '本任务暂无已执行用例' : '没有匹配的用例'}
                  </p>
                ) : (
                  <ScrollArea className='max-h-60'>
                    {caseGroups ? (
                      <div className='flex flex-col gap-2'>
                        {caseGroups.map(([groupName, groupCases]) => {
                          const groupState = groupSelectionState(groupCases)
                          const open = openGroupKeys.has(groupName)
                          return (
                            <Collapsible
                              key={groupName}
                              open={open}
                              onOpenChange={() => toggleGroupOpen(groupName)}
                              className='rounded-lg border bg-background'
                            >
                              {/* 组头：三态勾选（整组全选/取消）+ 展开/收起（照用例管理「组头全选」口径） */}
                              <div className='flex items-center gap-1.5 px-2 py-1.5'>
                                <Checkbox
                                  checked={groupState.all}
                                  indeterminate={groupState.some}
                                  aria-label={`全选 ${groupName}`}
                                  onCheckedChange={(checked) =>
                                    toggleGroupSelect(groupCases, !!checked)
                                  }
                                />
                                <CollapsibleTrigger className='hover:bg-muted/40 flex min-w-0 flex-1 items-center gap-1.5 rounded-md py-1 pr-2 text-left text-sm font-medium transition-colors'>
                                  <ChevronRight
                                    aria-hidden='true'
                                    className={cn(
                                      'text-muted-foreground size-3.5 shrink-0 transition-transform',
                                      open && 'rotate-90'
                                    )}
                                  />
                                  <span className='truncate'>{groupName}</span>
                                  <span className='text-muted-foreground shrink-0 text-xs tabular-nums'>
                                    ({groupCases.length})
                                  </span>
                                </CollapsibleTrigger>
                              </div>
                              <CollapsibleContent className='border-t'>
                                <div className='flex flex-col gap-1.5 p-1.5'>
                                  {groupCases.map(renderCaseRow)}
                                </div>
                              </CollapsibleContent>
                            </Collapsible>
                          )
                        })}
                      </div>
                    ) : (
                      <div className='flex flex-col gap-1.5'>{filteredCases.map(renderCaseRow)}</div>
                    )}
                  </ScrollArea>
                )}
              </div>
            )}

            {/* 重评估追加：维度勾选网格 + 重新提取设备输出（§5.7） */}
            {isReevaluate && dimensionOptions.length > 0 && (
              <div className='flex flex-col gap-2 rounded-lg border bg-muted/30 p-3'>
                <p className='text-sm font-medium'>评估维度（默认全选）</p>
                <div className='grid gap-1.5 sm:grid-cols-2'>
                  {dimensionOptions.map((dim) => {
                    const checked = selectedDimensionSet.has(dim.id)
                    return (
                      <label
                        key={dim.id}
                        className={cn(
                          'flex cursor-pointer items-center gap-2 rounded-md border bg-background px-2.5 py-1.5 text-sm transition-colors',
                          checked && 'bg-accent/40'
                        )}
                      >
                        <Checkbox
                          checked={checked}
                          onCheckedChange={() => toggleDimension(dim.id)}
                        />
                        <span className='truncate'>{dim.name}</span>
                      </label>
                    )
                  })}
                </div>
                <label className='mt-1 flex cursor-pointer items-center gap-2 text-sm'>
                  <Checkbox
                    checked={reextractDeviceOutput}
                    onCheckedChange={(v) => setReextractDeviceOutput(!!v)}
                  />
                  重新提取设备输出（从存档日志）
                </label>
                <span className='text-muted-foreground ml-6 text-xs'>
                  从文件资源管理器中的存档日志重新提取设备输出数据
                </span>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant='outline' disabled={submitting} onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button disabled={!canConfirm || submitting} onClick={handleConfirmClick}>
              {submitting ? (
                <>
                  <LoaderCircle aria-hidden='true' className='size-3.5 animate-spin' />
                  提交中...
                </>
              ) : (
                <>确认{confirmCountText}</>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 硬确认层（§5.7：存在人工复核结果时，未确认不得发起、不做静默覆盖） */}
      <ConfirmDialog
        open={hardConfirmOpen}
        onOpenChange={setHardConfirmOpen}
        title={`该任务存在 ${reviewCount} 条人工复核结果`}
        desc="重新执行/重新评估后人工复核填写的结果将被覆盖，是否继续？"
        destructive
        confirmText='覆盖并继续'
        cancelBtnText='返回'
        isLoading={submitting}
        handleConfirm={() => void doSubmit()}
      />
    </>
  )
}
