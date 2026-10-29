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
 * 注：页头「导入用例」为文件/用例包导入（ImportDialog：JSON/CSV/Excel/ZIP + 重复策略）；
 * 「导入音频生成用例」留在音频管理页（/AudioImport）上传并勾选生成，两个入口互不替代。
 */
import { FileSpreadsheet } from 'lucide-react'
import { useEffect, useState } from 'react'
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

export function ExportDialog({
  open,
  onOpenChange,
  selectedCount = 0,
  selectedIds = [],
  resolveFilteredIds,
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
}) {
  const [format, setFormat] = useState<TestCaseExportFormat>('zip')
  const [includeReferenceParams, setIncludeReferenceParams] = useState(true)
  const [scope, setScope] = useState<ExportScope>('filter')
  const [submitting, setSubmitting] = useState(false)

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

  const handleExport = async () => {
    setSubmitting(true)
    try {
      const ids =
        scope === 'selected'
          ? selectedIds
          : resolveFilteredIds
            ? await resolveFilteredIds()
            : []
      if (ids.length === 0) {
        toast.error(
          scope === 'selected'
            ? '请先选择要导出的用例'
            : '当前筛选条件下没有可导出的用例'
        )
        return
      }
      const { blob, filename } = await exportTestCases(ids, format, {
        includeReferenceParams,
      })
      if (blob.size === 0) {
        toast.error('导出失败：后端返回空文件')
        return
      }
      downloadBlob(blob, filename, blob.type || 'application/octet-stream')
      toast.success(`已导出 ${ids.length} 个用例`, { description: filename })
      onOpenChange(false)
    } catch (error) {
      toast.error(
        `导出失败：${error instanceof Error ? error.message : '请稍后重试'}`
      )
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
          </fieldset>
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
