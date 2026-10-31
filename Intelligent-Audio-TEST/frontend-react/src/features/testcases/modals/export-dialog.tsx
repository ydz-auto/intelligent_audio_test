/**
 * 导出用例弹窗（11_用例域.md §5.7.2，Dialog sm:max-w-md）。
 * 导出范围 RadioGroup「按当前筛选条件导出（导出全部筛选结果）/仅导出已选 {n} 个用例」
 * + 格式 Select（ZIP 数据包 / Excel / JSON）+ ZIP 选项「包含参考参数文件」+ 主钮「开始导出」。
 * 与任务数据导出同型：ZIP 为完整用例数据包（manifest + testcases.json + 参考参数文件），
 * 可直接用于「导入用例」做跨环境搬运。
 * INT-1642 接线：真实 POST /testcases/export（testcase_export_service）——
 * - 已选范围直接用勾选 id；筛选范围由页面解析器（POST /testcases/ids 全量圈定，非仅当前页）；
 * - ZIP/Excel 后端回字节流直落下载；JSON 后端回数据信封，前端序列化为 .json 文件下载；
 * - 失败（空 ids 400「未指定要导出的用例ID」等）toast 透出后端 message。
 * INT-2154：弹窗给出「将导出 N 条用例」范围预览（开窗即按当前筛选解析全量 id，与真正导出
 * 同一份），未勾选时提示怎么去选，JSON 导出后按信封条数核对并提示不一致。
 * 注：页头「导入用例」为文件/用例包导入（ImportDialog：JSON/CSV/Excel/ZIP + 重复策略）；
 * 「导入音频生成用例」留在音频管理页（/AudioImport）上传并勾选生成，两个入口互不替代。
 */
import { FileSpreadsheet } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { downloadBlob } from '@/lib/download-blob'
import { ApiError } from '@/infrastructure/api/api-error'
import {
  exportTestCases,
  type TestCaseExportFormat,
} from '@/infrastructure/api/testcases-api'

type ExportScope = 'filter' | 'selected'

const FORMAT_OPTIONS: Array<{ value: TestCaseExportFormat; label: string }> = [
  { value: 'zip', label: 'ZIP 数据包（推荐）' },
  { value: 'xlsx', label: 'Excel' },
  { value: 'json', label: 'JSON' },
]

function formatLabel(format: TestCaseExportFormat): string {
  return FORMAT_OPTIONS.find((option) => option.value === format)?.label ?? format
}

/**
 * 导出失败文案（INT-2191）：504 是前端容器 nginx 反代 60s 超时返回的 HTML 错误体，
 * 后端 message 取不到，直接用 ApiError.message 会得到空的「导出失败：」。这里优先用
 * userMessage（服务端 message > 错误码 > HTTP 状态码兜底），504 另给可执行的缩小范围提示。
 */
function exportErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.httpStatus === 504) return '导出超时，请缩小筛选范围后重试'
    return error.userMessage || error.message || '请稍后重试'
  }
  return error instanceof Error && error.message ? error.message : '请稍后重试'
}

export function ExportDialog({
  open,
  onOpenChange,
  selectedCount = 0,
  selectedIds = [],
  resolveFilteredIds,
  filterSummary,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  selectedCount?: number
  /** 已选用例 id（导出范围=仅已选） */
  selectedIds?: string[]
  /**
   * 解析「当前筛选」全量 id（页面注入：POST /testcases/ids 按搜索/分组/标签/维度/算法圈定，
   * 非仅当前页；失败抛错由本弹窗 toast 透出）
   */
  resolveFilteredIds?: () => Promise<string[]>
  /** 当前筛选摘要（如「搜索：matrix」「标签：拒识」），用于弹窗内说明导出范围从何而来 */
  filterSummary?: string
}) {
  const [format, setFormat] = useState<TestCaseExportFormat>('zip')
  const [includeReferenceParams, setIncludeReferenceParams] = useState(true)
  const [scope, setScope] = useState<ExportScope>('filter')
  const [submitting, setSubmitting] = useState(false)
  /**
   * 「按当前筛选」全量 id 预览（INT-2154）：开窗即解析一次，弹窗直接展示「将导出 N 条用例」，
   * 与实际导出用同一份 id，避免用户以为导出的是眼前搜到的几条、实际导出全库。
   */
  const [filterIds, setFilterIds] = useState<string[] | null>(null)
  const [resolving, setResolving] = useState(false)
  const [resolveFailed, setResolveFailed] = useState(false)
  /** 解析器身份会随列表刷新变化，用 ref 取值避免预览 effect 被无意义地反复触发 */
  const resolveRef = useRef(resolveFilteredIds)
  useEffect(() => {
    resolveRef.current = resolveFilteredIds
  }, [resolveFilteredIds])
  /** 手动重试计数（解析失败时的「重试」只重新统计，不改筛选） */
  const [resolveAttempt, setResolveAttempt] = useState(0)
  const hasResolver = resolveFilteredIds != null

  /**
   * 导出范围复位（INT-1642 代码审计 P3-2）：弹窗常驻挂载，上次选「仅导出已选」→ 取消 →
   * 清空勾选 → 重开，该 radio 会停在「禁用 + 选中」，点导出只报「请先选择要导出的用例」。
   * 开窗回落「按当前筛选」；勾选清零时若仍停在「已选」也回落（防清选后残留）。
   */
  useEffect(() => {
    if (open) setScope('filter')
  }, [open])

  useEffect(() => {
    if (selectedCount === 0 && scope === 'selected') setScope('filter')
  }, [selectedCount, scope])

  /** 关窗清空预览，重开重新统计（列表可能已变） */
  useEffect(() => {
    if (open) return
    setFilterIds(null)
    setResolving(false)
    setResolveFailed(false)
  }, [open])

  /** 按当前筛选统计导出范围（仅此范围需要；「仅已选」直接取勾选项） */
  useEffect(() => {
    if (!open || scope !== 'filter' || !hasResolver) return
    const resolve = resolveRef.current
    if (resolve == null) return
    let cancelled = false
    setResolving(true)
    setResolveFailed(false)
    resolve()
      .then((ids) => {
        if (cancelled) return
        setFilterIds(ids)
      })
      .catch(() => {
        if (cancelled) return
        setFilterIds(null)
        setResolveFailed(true)
      })
      .finally(() => {
        if (!cancelled) setResolving(false)
      })
    return () => {
      cancelled = true
    }
  }, [open, scope, hasResolver, resolveAttempt])

  /** 导出范围预览条数（仅已选=勾选数；按筛选=解析到的全量 id 数） */
  const previewCount = scope === 'selected' ? selectedCount : (filterIds?.length ?? null)

  const handleExport = async () => {
    setSubmitting(true)
    try {
      const ids =
        scope === 'selected'
          ? selectedIds
          : (filterIds ?? (await resolveRef.current?.()) ?? [])
      if (ids.length === 0) {
        toast.error(
          scope === 'selected'
            ? '请先选择要导出的用例'
            : '当前筛选条件下没有可导出的用例'
        )
        return
      }
      const { blob, filename, exportedCount } = await exportTestCases(ids, format, {
        includeReferenceParams,
      })
      if (blob.size === 0) {
        toast.error('导出失败：后端返回空文件')
        return
      }
      downloadBlob(blob, filename, blob.type || 'application/octet-stream')
      // 导出后核对实际条数（JSON 信封可数；ZIP/Excel 为字节流，以请求 id 数为准）
      if (exportedCount != null && exportedCount !== ids.length) {
        toast.warning(
          `导出条数与筛选范围不一致：请求 ${ids.length} 条，实际 ${exportedCount} 条`,
          { description: filename }
        )
      } else {
        toast.success(`已导出 ${ids.length} 个用例`, { description: filename })
      }
      onOpenChange(false)
    } catch (error) {
      toast.error(`导出失败：${exportErrorMessage(error)}`)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>导出用例</DialogTitle>
          <DialogDescription>
            按当前筛选条件或已选用例导出；ZIP 数据包可直接用于「导入用例」跨环境搬运
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          <fieldset className='space-y-2'>
            <legend className='text-sm font-medium'>导出范围</legend>
            <label className='hover:bg-accent flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm'>
              <input
                type='radio'
                name='export-range'
                checked={scope === 'filter'}
                onChange={() => setScope('filter')}
              />
              按当前筛选条件导出（导出全部筛选结果）
            </label>
            <label
              className={
                selectedCount > 0
                  ? 'hover:bg-accent flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm'
                  : 'text-muted-foreground flex cursor-not-allowed items-center gap-2 rounded-md px-2 py-1.5 text-sm'
              }
            >
              <input
                type='radio'
                name='export-range'
                disabled={selectedCount === 0}
                checked={scope === 'selected'}
                onChange={() => setScope('selected')}
              />
              仅导出已选 {selectedCount} 个用例
            </label>
            {selectedCount === 0 && (
              <p className='text-muted-foreground ps-2 text-xs'>
                未选用例：先在列表勾选用例（或点列表头「全选用例」），再选此项；
                「按当前筛选条件导出」不受勾选影响。
              </p>
            )}
          </fieldset>

          {/* 导出范围预览（INT-2154）：说清这次到底导出多少条，避免把「搜到的几条」误当全部 */}
          <div className='bg-muted/40 rounded-lg px-3 py-2 text-xs'>
            {scope === 'selected' ? (
              <span>
                将导出{' '}
                <strong className='font-medium tabular-nums'>{selectedCount}</strong>{' '}
                条已选用例
              </span>
            ) : resolving ? (
              <span className='text-muted-foreground flex items-center gap-1.5'>
                <Spinner className='size-3.5' />
                正在统计当前筛选的导出条数…
              </span>
            ) : resolveFailed ? (
              <span className='flex flex-wrap items-center gap-1.5'>
                <span className='text-destructive'>无法预先统计导出条数</span>
                <span className='text-muted-foreground'>
                  导出时仍按当前筛选执行，失败会提示原因。
                </span>
                <Button
                  variant='link'
                  size='sm'
                  className='h-auto px-0 text-xs'
                  disabled={submitting}
                  onClick={() => setResolveAttempt((n) => n + 1)}
                >
                  重新统计
                </Button>
              </span>
            ) : previewCount === 0 ? (
              <span className='text-destructive'>当前筛选条件下没有可导出的用例</span>
            ) : (
              <span>
                将导出{' '}
                <strong className='font-medium tabular-nums'>{previewCount ?? 0}</strong>{' '}
                条用例
                {filterSummary ? `（${filterSummary}）` : ''}
              </span>
            )}
          </div>

          <div className='flex items-center gap-2'>
            <span className='text-muted-foreground text-sm'>格式</span>
            <Select
              value={format}
              onValueChange={(v) => setFormat(v as TestCaseExportFormat)}
              items={FORMAT_OPTIONS}
            >
              <SelectTrigger size='sm' className='h-8 w-44'>
                <SelectValue>{formatLabel(format)}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {FORMAT_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {format === 'zip' && (
            <label className='flex cursor-pointer items-center gap-2 text-sm'>
              <Checkbox
                checked={includeReferenceParams}
                onCheckedChange={(v) => setIncludeReferenceParams(!!v)}
              />
              包含参考参数文件
            </label>
          )}
        </div>

        <DialogFooter>
          <Button
            variant='outline'
            disabled={submitting}
            onClick={() => onOpenChange(false)}
          >
            取消
          </Button>
          <Button disabled={submitting} onClick={() => void handleExport()}>
            {submitting ? (
              <>
                <Spinner className='size-4' />
                导出中…
              </>
            ) : (
              <>
                <FileSpreadsheet aria-hidden='true' className='size-4' />
                开始导出
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
