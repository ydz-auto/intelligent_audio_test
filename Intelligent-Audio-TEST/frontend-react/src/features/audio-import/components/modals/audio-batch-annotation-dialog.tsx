/**
 * 批量更新标注弹窗（§6.19；Dialog sm:max-w-3xl）。
 * 拖放区（音频+标注文件按文件名匹配）+ 真实解析进度 + 已解析摘要 + 算法 select
 * + 「同步刷新关联测试用例的参考参数」checkbox + 匹配结果列表（仅看未匹配）
 * + 主钮「开始更新」（POST /audios/batch/annotations {items,algorithm_type,refresh_test_cases}）
 * → toast「更新完成 成功 {s} 失败 {f} 刷新用例 {z}」。
 * V9.7.10 BatchAnnotationModal 对位：标注解析（txt/json/jsonl/rttm/stm）+ 文件名匹配；
 * 提交载荷经 useAudioMutations.batchAnnotations（items 随请求提交）。
 */
import { FileCheck2, Link, Link2Off } from 'lucide-react'
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
import { useAudioList } from '@/application/audio/useAudioList'
import { useAlgorithmOptions } from '@/application/evaluation/use-dimensions'

export type AudioBatchAnnotationDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const AUDIO_EXTS = ['.wav', '.mp3', '.m4a', '.flac', '.aac', '.ogg']
const ANNOTATION_EXTS = ['.json', '.jsonl', '.rttm', '.stm', '.txt']

/** 去扩展名（用于音频/标注按文件名匹配） */
function baseName(name: string): string {
  return name.replace(/\.[^.]+$/, '')
}

/** 标注文件解析（V9.7.10 parseAnnotationContent 对位：txt/json/jsonl/rttm/stm） */
function parseAnnotationFile(fileName: string, content: string): unknown[] {
  const ext = fileName.split('.').pop()?.toLowerCase() ?? ''
  const trimmed = content.trim()
  if (!trimmed) return []
  if (ext === 'txt') {
    const lines = trimmed.split(/\r?\n/).filter(Boolean)
    const text = lines[0] ?? trimmed
    return [
      {
        format: 'text',
        code: 'asr',
        data: { text },
        source_language: '',
        target_language: '',
      },
    ]
  }
  if (ext === 'json' || ext === 'jsonl') {
    try {
      const lines = trimmed.split(/\r?\n/).filter(Boolean)
      const parsed = lines.map((line) => JSON.parse(line))
      return [
        {
          format: 'json',
          code: '',
          data: { segments: parsed },
          source_language: '',
          target_language: '',
        },
      ]
    } catch {
      return []
    }
  }
  // rttm/stm：段解析留批量标注专项；先按文本协议落库
  return [
    {
      format: ext,
      code: 'diarization',
      data: { text: trimmed },
      source_language: '',
      target_language: '',
    },
  ]
}

type MatchRow = {
  annotationName: string
  audioName: string
  audioId: number | null
  matched: boolean
  annotations: unknown[]
}

export function AudioBatchAnnotationDialog(props: AudioBatchAnnotationDialogProps) {
  const { batchAnnotations } = useAudioMutations()
  const audioListQuery = useAudioList()
  const audioList = audioListQuery.data?.items ?? []
  const algorithmOptionsQuery = useAlgorithmOptions()
  const algorithmOptions = algorithmOptionsQuery.data ?? []

  const [parsed, setParsed] = useState(0)
  const [total, setTotal] = useState(0)
  const [processing, setProcessing] = useState(false)
  const [refreshCases, setRefreshCases] = useState(true)
  const [algorithmType, setAlgorithmType] = useState('')
  const [onlyUnmatched, setOnlyUnmatched] = useState(false)
  const [rows, setRows] = useState<MatchRow[]>([])
  const [pending, setPending] = useState(false)
  const fileRef = useRef<HTMLInputElement | null>(null)

  const matchedCount = useMemo(() => rows.filter((r) => r.matched).length, [rows])

  const resultRows = useMemo(
    () => (onlyUnmatched ? rows.filter((r) => !r.matched) : rows),
    [onlyUnmatched, rows]
  )

  const handleFiles = (incoming: FileList | null) => {
    if (!incoming) return
    const list = Array.from(incoming)
    const audioNames = new Set(
      audioList.map((a) => baseName(a.originalFilename ?? a.name).toLowerCase())
    )
    const annotationFiles = list.filter((f) =>
      ANNOTATION_EXTS.some((e) => f.name.toLowerCase().endsWith(e))
    )
    if (annotationFiles.length === 0) {
      toast.error('未选择标注文件（.json/.jsonl/.rttm/.stm/.txt）')
      return
    }

    setProcessing(true)
    setParsed(0)
    setTotal(annotationFiles.length)

    // 逐文件解析（真实文本读取）+ 按文件名匹配音频
    const nextRows: MatchRow[] = []
    let done = 0
    for (const file of annotationFiles) {
      const reader = new FileReader()
      reader.onload = () => {
        const content = String(reader.result ?? '')
        const annotations = parseAnnotationFile(file.name, content)
        const base = baseName(file.name).toLowerCase()
        const matchedAudio = audioList.find(
          (a) => baseName(a.originalFilename ?? a.name).toLowerCase() === base
        )
        nextRows.push({
          annotationName: file.name,
          audioName: matchedAudio ? matchedAudio.name : '未匹配到音频',
          audioId: matchedAudio ? matchedAudio.id : null,
          matched: matchedAudio != null,
          annotations,
        })
        done += 1
        setParsed(done)
        if (done === annotationFiles.length) {
          setRows(nextRows)
          setProcessing(false)
        }
      }
      reader.readAsText(file)
    }
  }

  const handleStart = async () => {
    if (matchedCount === 0) {
      toast.info('没有匹配到音频的标注文件')
      return
    }
    setPending(true)
    try {
      const items = rows
        .filter((r) => r.matched && r.audioId != null)
        .map((r) => ({ audioId: r.audioId as number, annotations: r.annotations }))
      const result = await batchAnnotations.mutateAsync({
        items,
        algorithmType: algorithmType || undefined,
        refreshTestCases: refreshCases,
      })
      toast.success(
        `更新完成 成功 ${result.success} 失败 ${result.failed} 刷新用例 ${result.refreshed}`
      )
      setRows([])
      setParsed(0)
      setTotal(0)
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
          setParsed(0)
          setTotal(0)
        }
      }}
    >
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>批量更新标注</DialogTitle>
          <DialogDescription>按文件名匹配音频与标注文件（audio1.wav ↔ audio1.json）</DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          {/* 拖放区 */}
          <div className='border-border/60 hover:bg-muted/30 flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-5 text-center transition-colors'>
            <FileCheck2 aria-hidden='true' className='text-muted-foreground size-8' />
            <p className='text-sm'>拖拽音频 + 标注文件到此处或点击选择</p>
            <p className='text-muted-foreground text-xs'>
              音频 .wav/.mp3/.m4a/.flac/.aac/.ogg + 标注 .json/.jsonl/.rttm/.stm/.txt
            </p>
            <Button
              variant='outline'
              size='sm'
              type='button'
              onClick={() => fileRef.current?.click()}
            >
              选择文件
            </Button>
            <input
              ref={fileRef}
              type='file'
              multiple
              accept='.wav,.mp3,.m4a,.flac,.aac,.ogg,.json,.jsonl,.rttm,.stm,.txt'
              className='hidden'
              onChange={(e) => {
                handleFiles(e.target.files)
                e.target.value = ''
              }}
            />
          </div>

          {/* 处理进度（真实解析进度） */}
          {processing && (
            <div className='bg-muted/40 rounded-md px-2.5 py-2'>
              <div className='bg-muted h-1.5 w-full overflow-hidden rounded-full'>
                <div
                  className='bg-primary h-full rounded-full transition-all duration-150'
                  style={{ width: `${total > 0 ? (parsed / total) * 100 : 0}%` }}
                />
              </div>
              <p className='text-muted-foreground mt-1 text-xs tabular-nums'>
                正在处理... {parsed}/{total}
              </p>
            </div>
          )}

          {/* 已解析摘要 */}
          {rows.length > 0 && (
            <div className='flex flex-wrap items-center gap-2 text-sm'>
              <span>已解析 <span className='font-mono tabular-nums'>{rows.length}</span> 个标注</span>
              <span>
                匹配 <span className='font-mono text-[var(--success)] tabular-nums'>{matchedCount}</span>
              </span>
              <span>
                未匹配 <span className='font-mono text-[var(--destructive)] tabular-nums'>{rows.length - matchedCount}</span>
              </span>
              <Button variant='ghost' size='sm' className='h-7 px-2' onClick={() => { setRows([]); setParsed(0); setTotal(0) }}>
                重新选择
              </Button>
            </div>
          )}

          {/* 算法 + 刷新用例 */}
          <div className='grid grid-cols-1 gap-3 sm:grid-cols-2'>
            <div className='space-y-2'>
              <Label htmlFor='batch-anno-algo'>算法</Label>
              <Select
                value={algorithmType}
                onValueChange={(value) => setAlgorithmType(value ?? '')}
              >
                <SelectTrigger id='batch-anno-algo' size='sm' className='w-full'>
                  <SelectValue placeholder={algorithmOptionsQuery.isLoading ? '加载中…' : '选择算法'} />
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
              <Label htmlFor='batch-anno-refresh' className='text-sm'>
                同步刷新关联测试用例的参考参数
              </Label>
              <Switch
                id='batch-anno-refresh'
                checked={refreshCases}
                onCheckedChange={setRefreshCases}
              />
            </div>
          </div>
          <p className='text-muted-foreground -mt-2 text-xs'>
            更新后自动重新提取用例参数
          </p>

          {/* 匹配结果列表（真实匹配行） */}
          {rows.length > 0 && (
            <div className='space-y-2'>
              <div className='flex items-center justify-between'>
                <div className='text-muted-foreground text-sm font-medium'>匹配结果</div>
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
              <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
                <div className='max-h-52 overflow-y-auto'>
                  {resultRows.map((row) => (
                    <div
                      key={row.annotationName}
                      className={cn(
                        'hover:bg-muted/40 flex items-center gap-2 border-b px-3 py-2 text-sm last:border-b-0',
                        !row.matched && 'bg-[var(--destructive)]/[0.03]'
                      )}
                    >
                      {row.matched ? (
                        <Link aria-hidden='true' className='text-[var(--success)] size-3.5 shrink-0' />
                      ) : (
                        <Link2Off aria-hidden='true' className='text-[var(--destructive)] size-3.5 shrink-0' />
                      )}
                      <span className='min-w-0 flex-1 truncate'>{row.annotationName}</span>
                      <span className='text-muted-foreground text-xs'>→</span>
                      <span className={cn('min-w-0 flex-1 truncate', !row.matched && 'text-[var(--destructive)]')}>
                        {row.audioName}
                        {row.audioId != null && (
                          <span className='text-muted-foreground font-mono text-xs tabular-nums'>
                            {' '}#{row.audioId}
                          </span>
                        )}
                      </span>
                      {row.matched && (
                        <Badge variant='secondary' className='rounded-md px-1.5 font-normal'>
                          {row.annotationName.split('.').pop()?.toUpperCase()} 标注
                        </Badge>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            variant='outline'
            size='sm'
            disabled={pending}
            onClick={() => props.onOpenChange(false)}
          >
            取消
          </Button>
          <Button size='sm' onClick={handleStart} disabled={pending || matchedCount === 0}>
            {pending ? '更新中...' : `开始更新（${matchedCount}）`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
