/**
 * 按 JSON 批量更新标注弹窗：
 * 只选择文件夹，读取第一层 .json（忽略嵌套目录），按 JSON 内的音频名称匹配音频库，
 * 再复用 POST /audios/batch/annotations 批量写入标注。
 */
import { FileJson, FolderOpen, Link, Link2Off } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { useAudioMutations } from '@/application/audio/useAudioList'
import { useAlgorithmOptions } from '@/application/evaluation/use-dimensions'
import { fetchAudios } from '@/infrastructure/api/audios-api'
import {
  buildAudioNameLookup,
  findAudioByName,
  isTopLevelJsonFile,
  parseAnnotationJsonEntries,
  type NamedAudio,
} from '@/features/audio-import/lib/annotation-json'

export type AudioJsonBatchAnnotationDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

type JsonRow = {
  key: string
  jsonName: string
  segmentLabel: string
  audioName: string
  audioId: number | null
  matched: boolean
  unmatchedReason?: string
  annotations: unknown[]
}

type Stage = '读取 JSON' | '匹配音频库'

type DirectoryEntryHandle =
  | { kind: 'file'; name: string; getFile: () => Promise<File> }
  | { kind: 'directory'; name: string }

type DirectoryHandleLike = {
  values?: () => AsyncIterable<DirectoryEntryHandle>
  entries?: () => AsyncIterable<[string, DirectoryEntryHandle]>
}

type DirectoryPickerWindow = Window & {
  showDirectoryPicker?: () => Promise<DirectoryHandleLike>
}

/** 音频库全量索引的单页条数（只取 id/name，用于按名称精确匹配） */
const AUDIO_LOOKUP_PAGE_SIZE = 200

async function fetchAudioNameLookup(): Promise<Map<string, NamedAudio>> {
  const audios: NamedAudio[] = []
  let page = 1
  let pages = 1
  do {
    const result = await fetchAudios({ page, perPage: AUDIO_LOOKUP_PAGE_SIZE })
    for (const item of result.items) {
      audios.push({ id: item.id, name: item.name })
    }
    pages = result.pages
    page += 1
  } while (page <= pages)
  return buildAudioNameLookup(audios)
}

export function AudioJsonBatchAnnotationDialog(
  props: AudioJsonBatchAnnotationDialogProps
) {
  const { batchAnnotations } = useAudioMutations()
  const algorithmOptionsQuery = useAlgorithmOptions()
  const algorithmOptions = algorithmOptionsQuery.data ?? []

  const [processed, setProcessed] = useState(0)
  const [total, setTotal] = useState(0)
  const [stage, setStage] = useState<Stage | ''>('')
  const [processing, setProcessing] = useState(false)
  const [refreshCases, setRefreshCases] = useState(true)
  const [algorithmType, setAlgorithmType] = useState('')
  const [onlyUnmatched, setOnlyUnmatched] = useState(false)
  const [rows, setRows] = useState<JsonRow[]>([])
  const [selectionSummary, setSelectionSummary] = useState('')
  const [pending, setPending] = useState(false)
  const folderRef = useRef<HTMLInputElement | null>(null)

  const matchedCount = useMemo(() => rows.filter((row) => row.matched).length, [rows])
  const jsonCount = useMemo(
    () => new Set(rows.map((row) => row.jsonName)).size,
    [rows]
  )
  const unmatchedCount = rows.length - matchedCount
  const selectedAlgorithmLabel = algorithmOptions.find(
    (option) => option.value === algorithmType
  )?.label
  const resultRows = useMemo(
    () => (onlyUnmatched ? rows.filter((row) => !row.matched) : rows),
    [onlyUnmatched, rows]
  )

  const resetProgress = () => {
    setProcessed(0)
    setTotal(0)
    setStage('')
  }

  const exportUnmatched = () => {
    const lines = rows.filter((row) => !row.matched).map((row) => row.jsonName)
    if (lines.length === 0) return
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `未匹配JSON_${new Date().toISOString().slice(0, 10)}.txt`
    anchor.click()
    URL.revokeObjectURL(url)
  }

  const processFiles = async (list: File[], alreadyFlat = false) => {
    const allJsonFiles = list.filter((file) =>
      file.name.toLowerCase().endsWith('.json')
    )
    // showDirectoryPicker 返回的本身就是当前目录的直接子项，不再按相对路径层级过滤；
    // 兼容输入框会带 webkitRelativePath，需要排除子目录。
    const jsonFiles = alreadyFlat
      ? allJsonFiles
      : allJsonFiles.filter((file) =>
          isTopLevelJsonFile(file.webkitRelativePath || file.name)
        )
    setSelectionSummary(
      `已选择 ${list.length} 个文件，其中第一层 JSON ${jsonFiles.length} 个`
    )
    if (jsonFiles.length === 0) {
      toast.error(
        alreadyFlat
          ? '所选文件夹内没有 .json 文件'
          : '所选文件夹第一层没有 .json 文件（嵌套目录不会读取）'
      )
      return
    }

    const ignoredCount = allJsonFiles.length - jsonFiles.length
    if (ignoredCount > 0) {
      toast.info(`已忽略嵌套目录中的 ${ignoredCount} 个 JSON 文件`)
    }

    setProcessing(true)
    setRows([])
    try {
      setStage('读取 JSON')
      setProcessed(0)
      setTotal(jsonFiles.length)
      const nextRows: JsonRow[] = []

      for (let index = 0; index < jsonFiles.length; index += 1) {
        const file = jsonFiles[index]
        try {
          const content = await file.text()
          const raw: unknown = JSON.parse(content)
          const entries = parseAnnotationJsonEntries(file.name, raw)
          if (entries.length === 0) {
            nextRows.push({
              key: `${file.name}#empty`,
              jsonName: file.name,
              segmentLabel: '',
              audioName: '',
              audioId: null,
              matched: false,
              unmatchedReason: 'JSON 内未找到音频名称（audio/audio_name）',
              annotations: [],
            })
          } else {
            entries.forEach((entry, entryIndex) => {
              const row: JsonRow = {
                key: `${file.name}#${entryIndex}`,
                jsonName: file.name,
                segmentLabel: entry.segmentLabel,
                audioName: entry.audioName,
                audioId: null,
                matched: false,
                annotations: entry.annotations,
              }
              if (!row.audioName) {
                row.unmatchedReason = 'JSON 内未找到音频名称（audio/audio_name）'
              } else if (row.annotations.length === 0) {
                row.unmatchedReason = '未解析到标注内容'
              }
              nextRows.push(row)
            })
          }
        } catch {
          nextRows.push({
            key: `${file.name}#invalid`,
            jsonName: file.name,
            segmentLabel: '',
            audioName: '',
            audioId: null,
            matched: false,
            unmatchedReason: 'JSON 解析失败',
            annotations: [],
          })
        }
        setProcessed(index + 1)
      }

      // 先把已读取的 JSON/音频逐条展示出来，匹配音频库阶段不阻塞用户看到结果
      setRows(nextRows)
      setStage('匹配音频库')
      setProcessed(0)
      setTotal(nextRows.length)
      try {
        const lookup = await fetchAudioNameLookup()
        const matchedRows = nextRows.map((row, index) => {
          const nextRow = { ...row }
          if (!nextRow.unmatchedReason && nextRow.audioName) {
            const audio = findAudioByName(nextRow.audioName, lookup)
            if (audio) {
              nextRow.audioId = audio.id
              nextRow.matched = true
            } else {
              nextRow.unmatchedReason = '音频库中未找到同名音频'
            }
          }
          setProcessed(index + 1)
          return nextRow
        })
        setRows(matchedRows)
      } catch {
        setRows(
          nextRows.map((row) =>
            row.unmatchedReason
              ? row
              : { ...row, unmatchedReason: '音频库加载失败，请重新选择文件夹' }
          )
        )
        toast.error('读取到 JSON，但音频库匹配失败，请重试')
      }
    } catch {
      toast.error('读取 JSON 或匹配音频失败，请重试')
    } finally {
      setProcessing(false)
      resetProgress()
    }
  }

  const handleChooseFolder = async () => {
    const picker = (window as DirectoryPickerWindow).showDirectoryPicker
    if (typeof picker !== 'function') {
      folderRef.current?.click()
      return
    }

    try {
      const handle = await picker.call(window)
      const files: File[] = []
      let entries: AsyncIterable<DirectoryEntryHandle | [string, DirectoryEntryHandle]>
      if (handle.values) {
        entries = handle.values()
      } else if (handle.entries) {
        entries = handle.entries()
      } else {
        throw new Error('浏览器不支持读取文件夹内容')
      }

      for await (const item of entries) {
        const entry = Array.isArray(item) ? item[1] : item
        if (entry.kind !== 'file') continue
        if (!entry.name.toLowerCase().endsWith('.json')) continue
        files.push(await entry.getFile())
      }
      await processFiles(files, true)
    } catch (error) {
      if (
        error instanceof DOMException &&
        (error.name === 'AbortError' || error.name === 'NotAllowedError')
      ) {
        return
      }
      const message = error instanceof Error ? error.message : '未知错误'
      toast.error(`读取文件夹失败：${message}`)
      // 部分浏览器/内嵌 WebView 的目录 API 不可用或受限，回退到 webkitdirectory 输入框
      folderRef.current?.click()
    }
  }

  const handleStart = async () => {
    if (matchedCount === 0) {
      toast.info('没有匹配到音频的 JSON 文件')
      return
    }
    setPending(true)
    try {
      const items = rows
        .filter((row) => row.matched && row.audioId != null)
        .map((row) => ({
          audioId: row.audioId as number,
          annotations: row.annotations,
        }))
      const result = await batchAnnotations.mutateAsync({
        items,
        algorithmType: algorithmType || undefined,
        refreshTestCases: refreshCases,
      })
      toast.success(
        `更新完成 成功 ${result.success} 失败 ${result.failed} 刷新用例 ${result.refreshed}`
      )
      setRows([])
      resetProgress()
      props.onOpenChange(false)
    } catch {
      toast.error('批量更新标注失败，请重试')
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog
      open={props.open}
      onOpenChange={(open) => {
        props.onOpenChange(open)
        if (!open) {
          setRows([])
          setSelectionSummary('')
          resetProgress()
        }
      }}
    >
      <DialogContent className='flex max-h-[calc(100dvh-2rem)] w-[min(90vw,64rem)] max-w-[calc(100vw-2rem)] flex-col gap-3 overflow-hidden p-0'>
        <DialogHeader className='px-4 pt-4'>
          <DialogTitle>按 JSON 批量更新标注</DialogTitle>
          <DialogDescription>
            选择文件夹后读取第一层 .json（嵌套目录忽略），按 JSON 内的音频名称匹配音频库并批量更新标注。
          </DialogDescription>
        </DialogHeader>

        <div className='min-h-0 flex-1 overflow-y-auto px-4 pb-2'>
          <div className='space-y-4'>
          <div className='border-border/60 hover:bg-muted/30 flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-5 text-center transition-colors'>
            <FileJson aria-hidden='true' className='text-muted-foreground size-8' />
            <p className='text-sm'>选择包含标注 JSON 的文件夹</p>
            <p className='text-muted-foreground text-xs'>
              仅读取文件夹第一层的 .json 文件，子文件夹内的 JSON 不会读取
            </p>
            <Button
              variant='outline'
              size='sm'
              type='button'
              disabled={processing}
              onClick={() => void handleChooseFolder()}
            >
              <FolderOpen aria-hidden='true' className='size-3.5' />
              选择文件夹
            </Button>
            <input
              ref={(node) => {
                folderRef.current = node
                if (!node) return
                node.setAttribute('webkitdirectory', '')
                node.setAttribute('directory', '')
              }}
              type='file'
              multiple
              accept='.json'
              className='hidden'
              {...({ webkitdirectory: '', directory: '' } as Record<string, string>)}
              onChange={(event) => {
                const files = event.target.files
                void processFiles(files ? Array.from(files) : [])
                event.target.value = ''
              }}
            />
            {selectionSummary && (
              <p className='text-muted-foreground text-xs'>{selectionSummary}</p>
            )}
          </div>

          {processing && (
            <div className='bg-muted/40 rounded-md px-2.5 py-2'>
              <div className='bg-muted h-1.5 w-full overflow-hidden rounded-full'>
                <div
                  className='bg-primary h-full rounded-full transition-all duration-150'
                  style={{ width: `${total > 0 ? (processed / total) * 100 : 0}%` }}
                />
              </div>
              <p className='text-muted-foreground mt-1 text-xs tabular-nums'>
                {stage || '处理中'}... {processed}/{total}
              </p>
            </div>
          )}

          {rows.length > 0 && (
            <div className='flex flex-wrap items-center gap-2 text-sm'>
              <span>
                已读取 <span className='font-mono tabular-nums'>{jsonCount}</span> 个 JSON
              </span>
              <span>
                解析 <span className='font-mono tabular-nums'>{rows.length}</span> 条音频标注
              </span>
              <span>
                匹配{' '}
                <span className='font-mono text-[var(--success)] tabular-nums'>
                  {matchedCount}
                </span>
              </span>
              <span>
                未匹配{' '}
                <span className='font-mono text-[var(--destructive)] tabular-nums'>
                  {unmatchedCount}
                </span>
              </span>
              <Button
                variant='ghost'
                size='sm'
                className='h-7 px-2'
                onClick={() => {
                  setRows([])
                  resetProgress()
                }}
              >
                重新选择
              </Button>
            </div>
          )}

          <div className='grid grid-cols-1 gap-3 sm:grid-cols-2'>
            <div className='space-y-2'>
              <Label htmlFor='json-batch-anno-algo'>算法</Label>
              <Select
                value={algorithmType}
                onValueChange={(value) => setAlgorithmType(value ?? '')}
              >
                <SelectTrigger id='json-batch-anno-algo' size='sm' className='w-full'>
                  <SelectValue
                    placeholder={algorithmOptionsQuery.isLoading ? '加载中…' : '选择算法'}
                  >
                    {selectedAlgorithmLabel ?? ''}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {algorithmOptions.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='flex items-center justify-between gap-2'>
              <Label htmlFor='json-batch-anno-refresh' className='text-sm'>
                同步刷新关联测试用例的参考参数
              </Label>
              <Switch
                id='json-batch-anno-refresh'
                checked={refreshCases}
                onCheckedChange={setRefreshCases}
              />
            </div>
          </div>
          <p className='text-muted-foreground -mt-2 text-xs'>
            更新后自动重新提取用例参数
          </p>

          {rows.length > 0 && (
            <div className='space-y-2'>
              <div className='flex items-center justify-between'>
                <div className='text-muted-foreground text-sm font-medium'>匹配结果</div>
                <div className='flex items-center gap-1'>
                  {unmatchedCount > 0 && (
                    <Button
                      variant='ghost'
                      size='sm'
                      className='h-7 gap-1 px-2'
                      onClick={exportUnmatched}
                    >
                      导出未匹配（{unmatchedCount}）
                    </Button>
                  )}
                  <Button
                    variant='ghost'
                    size='sm'
                    className='h-7 gap-1 px-2'
                    onClick={() => setOnlyUnmatched((prev) => !prev)}
                  >
                    <Link2Off aria-hidden='true' className='size-3.5' />
                    {onlyUnmatched ? '显示全部' : '仅看未匹配'}
                  </Button>
                </div>
              </div>
              <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
                <div className='max-h-[min(40dvh,13rem)] overflow-y-auto'>
                  {resultRows.map((row) => (
                    <div
                      key={row.key}
                      className={cn(
                        'hover:bg-muted/40 flex items-center gap-2 border-b px-3 py-2 text-sm last:border-b-0',
                        !row.matched && 'bg-[var(--destructive)]/[0.03]'
                      )}
                    >
                      {row.matched ? (
                        <Link
                          aria-hidden='true'
                          className='text-[var(--success)] size-3.5 shrink-0'
                        />
                      ) : (
                        <Link2Off
                          aria-hidden='true'
                          className='text-[var(--destructive)] size-3.5 shrink-0'
                        />
                      )}
                      <span className='min-w-0 flex-1 truncate'>
                        {row.jsonName}
                        {row.segmentLabel && (
                          <span className='text-muted-foreground ml-1 text-xs'>
                            {row.segmentLabel}
                          </span>
                        )}
                      </span>
                      <span className='text-muted-foreground text-xs'>→</span>
                      <span
                        className={cn(
                          'min-w-0 flex-1 truncate',
                          !row.matched && 'text-[var(--destructive)]'
                        )}
                      >
                        {row.matched ? row.audioName : row.unmatchedReason}
                        {row.audioId != null && (
                          <span className='text-muted-foreground font-mono text-xs tabular-nums'>
                            {' '}#{row.audioId}
                          </span>
                        )}
                      </span>
                      {row.matched && (
                        <Badge variant='secondary' className='rounded-md px-1.5 font-normal'>
                          JSON 标注
                        </Badge>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
          </div>
        </div>

        <DialogFooter className='mx-0 mb-0 rounded-b-xl px-4'>
          <Button
            variant='outline'
            size='sm'
            disabled={pending}
            onClick={() => props.onOpenChange(false)}
          >
            取消
          </Button>
          <Button size='sm' onClick={handleStart} disabled={pending || rows.length === 0}>
            {pending ? '更新中...' : `开始更新（${matchedCount}）`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
