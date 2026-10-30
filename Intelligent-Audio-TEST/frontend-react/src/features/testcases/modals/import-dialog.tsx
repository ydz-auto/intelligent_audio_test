/**
 * 导入用例弹窗（11_用例域.md §5.7.1；与任务数据导入同型：选文件 → 预检 → 执行 → 回执）。
 *
 * - 文件：JSON / CSV / Excel / ZIP（ZIP = 「导出」产出的用例数据包，可含参考参数文件）
 * - 预检展示总用例数 + 重复用例清单（后端按 ID 或同分组同名命中）
 * - 重复策略：跳过（默认）/ 覆盖 / 另存副本（copy 自动追加 _copy 保证同组唯一）
 * - 「导入音频生成用例」不在本弹窗：统一走音频管理页上传并勾选生成用例
 *
 * 请求一律经 infrastructure/api/testcases-api（client.ts），页面层只见 camelCase Domain。
 */
import { FileDown, Upload } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Spinner } from '@/components/ui/spinner'
import type {
  TestCaseDuplicateStrategy,
  TestCaseImportPreview,
  TestCaseImportResult,
} from '@/domain/models/testCase'
import { downloadBlob } from '@/lib/download-blob'
import {
  downloadTestCaseTemplate,
  importTestCases,
  previewTestCasesImport,
} from '@/infrastructure/api/testcases-api'

const ACCEPTED_FILE_TYPES = '.json,.csv,.xlsx,.xls,.zip'

/** 重复清单预览条数上限（完整清单以回执/后端为准） */
const DUPLICATE_PREVIEW_LIMIT = 5

const DUPLICATE_STRATEGIES: Array<{
  value: TestCaseDuplicateStrategy
  label: string
  desc: string
}> = [
  {
    value: 'skip',
    label: '跳过重复用例',
    desc: '已存在的用例保持不变（默认）',
  },
  {
    value: 'overwrite',
    label: '覆盖已有用例',
    desc: '用文件内容更新已存在的用例',
  },
  {
    value: 'copy',
    label: '另存副本',
    desc: '保留原用例，导入为新用例（名称追加 _copy）',
  },
]

type Phase = 'select' | 'done'

function errorText(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message) return error.message
  return fallback
}

export function ImportDialog({
  open,
  onOpenChange,
  onImported,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 导入成功后回调（页面刷新列表/分组/标签） */
  onImported?: () => void
}) {
  const fileInputRef = useRef<HTMLInputElement | null>(null)
  const [phase, setPhase] = useState<Phase>('select')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<TestCaseImportPreview | null>(null)
  const [strategy, setStrategy] = useState<TestCaseDuplicateStrategy>('skip')
  const [previewing, setPreviewing] = useState(false)
  const [importing, setImporting] = useState(false)
  const [result, setResult] = useState<TestCaseImportResult | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  /** 模板下载进行中（INT-2154：弹窗内直达入口，与页头「模板下载」同一 GET /testcases/template/download） */
  const [templateDownloading, setTemplateDownloading] = useState(false)

  /**
   * 下载 Excel 导入模板（INT-2154 P3）：格式口径在弹窗内一处说清——导入接受
   * xlsx/xls/csv/json/zip，模板只提供 Excel 一种，其余格式无模板、按导出的文件结构填。
   */
  const handleTemplateDownload = async () => {
    setTemplateDownloading(true)
    try {
      const { blob, filename } = await downloadTestCaseTemplate()
      if (blob.size === 0) {
        toast.error('模板下载失败：后端返回空文件')
        return
      }
      downloadBlob(
        blob,
        filename,
        blob.type || 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
      )
      toast.success('模板已下载', {
        description: `${filename}（仅 Excel；CSV/JSON/ZIP 无模板，直接按导出结构填写）`,
      })
    } catch (error) {
      toast.error(
        `模板下载失败：${error instanceof Error ? error.message : '请稍后重试'}`
      )
    } finally {
      setTemplateDownloading(false)
    }
  }

  // 常驻挂载：关闭即复位，重开从选文件重新走
  useEffect(() => {
    if (open) return
    setPhase('select')
    setFile(null)
    setPreview(null)
    setResult(null)
    setErrorMessage('')
    setStrategy('skip')
    setPreviewing(false)
    setImporting(false)
  }, [open])

  const handleFileChange = async (
    event: React.ChangeEvent<HTMLInputElement>
  ) => {
    const selected = event.target.files?.[0]
    // 允许再次选择同一个文件（清空 value，否则 change 不触发）
    event.target.value = ''
    if (!selected) return

    setFile(selected)
    setPreview(null)
    setResult(null)
    setErrorMessage('')
    setPhase('select')
    setPreviewing(true)
    try {
      const data = await previewTestCasesImport(selected)
      setPreview(data)
      setStrategy('skip')
    } catch (error) {
      setErrorMessage(errorText(error, '预检失败：无法解析该文件'))
    } finally {
      setPreviewing(false)
    }
  }

  const handleImport = async () => {
    if (!file || !preview || importing) return
    setImporting(true)
    setErrorMessage('')
    try {
      const data = await importTestCases(file, strategy)
      setResult(data)
      setPhase('done')
      onImported?.()
      toast.success(
        `导入完成：新增 ${data.importedCount}，覆盖 ${data.updatedCount}，跳过 ${data.skippedCount}，副本 ${data.copiedCount}`
      )
    } catch (error) {
      toast.error(`导入失败：${errorText(error, '请稍后重试')}`)
    } finally {
      setImporting(false)
    }
  }

  const canImport = file != null && preview != null && !previewing && !importing

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>导入用例</DialogTitle>
          <DialogDescription>
            支持 JSON / CSV / Excel / ZIP 用例包；如需「导入音频生成用例」，请前往音频管理页操作。
          </DialogDescription>
        </DialogHeader>

        {phase === 'done' && result ? (
          <div className='space-y-3'>
            <div className='grid grid-cols-2 gap-2 rounded-lg border px-3 py-2.5 text-sm'>
              <span>
                新增 <strong>{result.importedCount}</strong>
              </span>
              <span>
                覆盖 <strong>{result.updatedCount}</strong>
              </span>
              <span>
                跳过 <strong>{result.skippedCount}</strong>
              </span>
              <span>
                副本 <strong>{result.copiedCount}</strong>
              </span>
            </div>
            {result.errors.length > 0 && (
              <Alert variant='destructive'>
                <AlertTitle>部分用例导入失败（{result.errors.length}）</AlertTitle>
                <AlertDescription>
                  <ul className='list-disc pl-4'>
                    {result.errors.slice(0, 5).map((message, index) => (
                      <li key={index}>{message}</li>
                    ))}
                  </ul>
                  {result.errors.length > 5 && (
                    <p className='mt-1'>仅展示前 5 条，共 {result.errors.length} 条。</p>
                  )}
                </AlertDescription>
              </Alert>
            )}
          </div>
        ) : (
          <div className='space-y-4'>
            <div className='space-y-1.5'>
              <p className='text-sm font-medium'>选择文件</p>
              <input
                ref={fileInputRef}
                type='file'
                accept={ACCEPTED_FILE_TYPES}
                aria-label='选择导入文件'
                className='hidden'
                onChange={(event) => void handleFileChange(event)}
              />
              <Button
                variant='outline'
                className='w-full justify-start gap-2'
                disabled={importing}
                onClick={() => fileInputRef.current?.click()}
              >
                <Upload aria-hidden='true' className='size-3.5' />
                <span className='truncate'>{file ? file.name : '点击选择文件'}</span>
              </Button>
              <p className='text-muted-foreground text-xs'>
                支持 .xlsx / .xls / .csv / .json / .zip；ZIP 可直接用「导出」生成的用例包。
                模板仅提供 Excel（.xlsx），CSV/JSON 无模板、按同样字段填写即可。
              </p>
              <Button
                variant='link'
                size='sm'
                className='text-muted-foreground hover:text-foreground h-auto gap-1 px-0 text-xs'
                disabled={templateDownloading || importing}
                onClick={() => void handleTemplateDownload()}
              >
                <FileDown aria-hidden='true' className='size-3.5' />
                {templateDownloading ? '模板下载中…' : '下载 Excel 模板（.xlsx）'}
              </Button>
            </div>

            {previewing && (
              <p className='text-muted-foreground flex items-center gap-2 text-xs'>
                <Spinner size={14} />
                正在预检文件…
              </p>
            )}

            {errorMessage && (
              <Alert variant='destructive'>
                <AlertTitle>预检失败</AlertTitle>
                <AlertDescription>{errorMessage}</AlertDescription>
              </Alert>
            )}

            {preview && (
              <div className='space-y-3'>
                <div className='rounded-lg border px-3 py-2 text-sm'>
                  共 {preview.totalRows} 条用例
                  {preview.duplicateCount > 0 ? (
                    <span className='text-amber-600'>
                      {' '}
                      · 重复 {preview.duplicateCount} 条
                    </span>
                  ) : (
                    <span className='text-emerald-600'> · 无重复用例</span>
                  )}
                </div>

                {preview.duplicates.length > 0 && (
                  <div className='rounded-lg border'>
                    <ul className='divide-y divide-border'>
                      {preview.duplicates
                        .slice(0, DUPLICATE_PREVIEW_LIMIT)
                        .map((item, index) => (
                          <li
                            key={`${item.id ?? item.name ?? index}-${index}`}
                            className='flex items-center justify-between gap-2 px-3 py-1.5 text-xs'
                          >
                            <span className='min-w-0 flex-1 truncate'>
                              {item.name || '未命名用例'}
                            </span>
                            <span className='text-muted-foreground shrink-0'>
                              {item.matchedBy === 'id' ? 'ID 已存在' : '同分组同名'}
                              {item.existingName &&
                              item.existingName !== item.name
                                ? ` · 已有「${item.existingName}」`
                                : ''}
                            </span>
                          </li>
                        ))}
                    </ul>
                    {preview.duplicateCount > DUPLICATE_PREVIEW_LIMIT && (
                      <p className='text-muted-foreground border-t px-3 py-1.5 text-xs'>
                        仅展示前 {DUPLICATE_PREVIEW_LIMIT} 条，共{' '}
                        {preview.duplicateCount} 条重复
                      </p>
                    )}
                  </div>
                )}

                {preview.duplicateScanTruncated && (
                  <p className='text-muted-foreground text-xs'>
                    文件较大，重复清单仅覆盖前 500 条；导入时仍会全量判重。
                  </p>
                )}

                <fieldset className='space-y-1.5'>
                  <legend className='text-sm font-medium'>重复用例处理</legend>
                  {DUPLICATE_STRATEGIES.map((option) => (
                    <label
                      key={option.value}
                      className='hover:bg-accent flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-sm'
                    >
                      <input
                        type='radio'
                        name='testcase-import-duplicate'
                        className='mt-1'
                        checked={strategy === option.value}
                        onChange={() => setStrategy(option.value)}
                      />
                      <span>
                        <span className='block'>{option.label}</span>
                        <span className='text-muted-foreground block text-xs'>
                          {option.desc}
                        </span>
                      </span>
                    </label>
                  ))}
                </fieldset>
              </div>
            )}
          </div>
        )}

        <DialogFooter>
          {phase === 'done' ? (
            <Button onClick={() => onOpenChange(false)}>完成</Button>
          ) : (
            <>
              <Button
                variant='outline'
                disabled={importing}
                onClick={() => onOpenChange(false)}
              >
                取消
              </Button>
              <Button disabled={!canImport} onClick={() => void handleImport()}>
                {importing ? (
                  <>
                    <Spinner className='size-4' />
                    导入中…
                  </>
                ) : (
                  '开始导入'
                )}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
