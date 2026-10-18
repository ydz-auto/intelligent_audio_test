/**
 * 重新执行 / 重新评估范围选择弹窗（09_任务域.md §5.7，Dialog sm:max-w-xl）。
 * RadioGroup 三选项（全部用例/仅失败用例/手动选择用例）+ 手动勾选展开区
 * （全选 Checkbox + 标签/分组过滤 Select + 行 Checkbox 列表，空态「本任务暂无已执行用例」）；
 * 重评估追加：评估维度勾选网格（默认全选，候选=本任务用例聚合维度）+
 * 「重新提取设备输出（从存档日志）」Checkbox（默认不勾）；底栏「取消｜确认{已选 n 项}」。
 * 存在人工复核结果（task.detail.review_count > 0）时追加硬确认层（§5.7）：
 * 确认后先弹「该任务存在 {N} 条人工复核结果…是否继续？」主钮「覆盖并继续」（destructive）副钮「返回」。
 * 确认后经 infrastructure/api/tasks-control-api（client.ts）发起 retry / reevaluate。
 */
import { LoaderCircle } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { useTaskDetail } from '@/application/tasks/use-task-detail'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { ConfirmDialog } from '@/components/confirm-dialog'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ScrollArea } from '@/components/ui/scroll-area'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { ApiError } from '@/infrastructure/api/api-error'
import {
  reevaluateTask,
  retryTask,
  type ReexecuteScopeMode,
} from '@/infrastructure/api/tasks-control-api'
import { cn } from '@/lib/utils'

type ActionType = 'retry' | 'reevaluate'

const SCOPE_ALL: ReexecuteScopeMode = 'all'
const SCOPE_FAILED: ReexecuteScopeMode = 'failed_only'
const SCOPE_SELECTED: ReexecuteScopeMode = 'selected'

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
  const [caseFilter, setCaseFilter] = useState('all')
  const [selectedDimensionIds, setSelectedDimensionIds] = useState<number[]>([])
  const [reextractDeviceOutput, setReextractDeviceOutput] = useState(false)
  const [hardConfirmOpen, setHardConfirmOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  /** 维度候选集每次弹窗打开只初始化一次默认全选（用户后续改动不被覆盖） */
  const dimInitRef = useRef(false)

  const isReevaluate = actionType === 'reevaluate'
  const reviewCount = detail?.review_count ?? 0

  /** 本任务已执行用例集（task 详情 task.cases；非全库用例） */
  const taskCases = useMemo(() => detail?.cases ?? [], [detail])

  /** 标签/分组过滤选项（标签优先，无标签回退分组名；对齐 E2E 页过滤交互） */
  const caseFilterOptions = useMemo(() => {
    const names = new Set<string>()
    taskCases.forEach((tc) => {
      ;(tc.tags ?? []).forEach((t) => names.add(t))
      if (tc.group_name) names.add(tc.group_name)
    })
    return Array.from(names).sort()
  }, [taskCases])

  const filteredCases = useMemo(() => {
    if (caseFilter === 'all') return taskCases
    return taskCases.filter(
      (tc) => (tc.tags ?? []).includes(caseFilter) || tc.group_name === caseFilter
    )
  }, [taskCases, caseFilter])

  /** 重评估维度候选集 = 本任务用例聚合（task.cases[].evaluation_dimensions 去重） */
  const dimensionOptions = useMemo(() => {
    if (!isReevaluate) return []
    const dimMap = new Map<number, string>()
    taskCases.forEach((tc) => {
      ;(tc.evaluation_dimensions ?? []).forEach((d) => {
        const id = Number(d?.id)
        if (id && !dimMap.has(id)) dimMap.set(id, d?.name || `维度 ${id}`)
      })
    })
    return Array.from(dimMap, ([id, name]) => ({ id, name }))
  }, [taskCases, isReevaluate])

  const selectedCaseSet = useMemo(() => new Set(selectedCaseIds.map(String)), [selectedCaseIds])
  const selectedDimensionSet = useMemo(() => new Set(selectedDimensionIds), [selectedDimensionIds])

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

  const isAllCasesSelected =
    filteredCases.length > 0 && filteredCases.every((tc) => selectedCaseSet.has(String(tc.case_id)))

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
      const removeSet = new Set(filteredCases.map((tc) => String(tc.case_id)))
      setSelectedCaseIds((prev) => prev.filter((id) => !removeSet.has(id)))
    } else {
      setSelectedCaseIds((prev) => {
        const next = new Set(prev.map(String))
        filteredCases.forEach((tc) => next.add(String(tc.case_id)))
        return Array.from(next)
      })
    }
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
        <DialogContent className='sm:max-w-xl'>
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

            {/* 手动选择用例（§5.7：全选 + 过滤 Select + 行 Checkbox 列表） */}
            {scope === SCOPE_SELECTED && (
              <div className='flex flex-col gap-2 rounded-lg border bg-muted/30 p-3'>
                <div className='flex flex-wrap items-center justify-between gap-2'>
                  <label className='flex cursor-pointer items-center gap-2 text-sm'>
                    <Checkbox checked={isAllCasesSelected} onCheckedChange={toggleSelectAll} />
                    全选
                  </label>
                  <Select value={caseFilter} onValueChange={(value) => setCaseFilter(value ?? 'all')}>
                    <SelectTrigger size='sm' className='h-8 w-auto min-w-40' aria-label='标签/分组过滤'>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent align='start'>
                      <SelectItem value='all'>全部标签/分组</SelectItem>
                      {caseFilterOptions.map((name) => (
                        <SelectItem key={name} value={name}>
                          {name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
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
                    本任务暂无已执行用例
                  </p>
                ) : (
                  <ScrollArea className='max-h-60'>
                    <div className='flex flex-col gap-1.5'>
                      {filteredCases.map((tc) => {
                        const checked = selectedCaseSet.has(String(tc.case_id))
                        return (
                          <label
                            key={tc.case_id}
                            className={cn(
                              'flex cursor-pointer items-center gap-2 rounded-md border bg-background px-2.5 py-2 text-sm transition-colors',
                              checked && 'bg-accent/40'
                            )}
                          >
                            <Checkbox checked={checked} onCheckedChange={() => toggleCase(tc.case_id)} />
                            <span className='min-w-0 flex-1 truncate'>{tc.name}</span>
                            {tc.group_name && (
                              <span className='text-muted-foreground shrink-0 text-xs'>
                                {tc.group_name}
                              </span>
                            )}
                          </label>
                        )
                      })}
                    </div>
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
