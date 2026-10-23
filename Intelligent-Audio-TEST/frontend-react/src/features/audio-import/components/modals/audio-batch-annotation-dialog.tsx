/**
 * 批量更新标注弹窗（§6.19；Dialog sm:max-w-3xl）。
 * 拖放区（音频 + 标注文件）+ 真实进度（计算 MD5 → 查库 → 解析标注）+ 已解析摘要
 * + 算法 select + 「同步刷新关联测试用例的参考参数」checkbox + 匹配结果列表（仅看未匹配）
 * + 主钮「开始更新」（POST /audios/batch/annotations {items,algorithm_type,refresh_test_cases}）
 * → toast「更新完成 成功 {s} 失败 {f} 刷新用例 {z}」。
 *
 * 匹配口径与 V9.7.10 BatchAnnotationModal 一致（INT-1582）：
 *   拖入的音频文件按内容算 MD5（分块流式，lib/md5）→ 音频与标注按文件基名建立
 *   baseName→md5 桥接 → POST /audios/by-md5 全库按 MD5 命中（不受列表分页/筛选限制，
 *   文件名被改过但内容相同的音频同样命中）。未匹配行按原因分类：
 *   未拖入对应音频文件 / 音频 MD5 在库内不存在 / 标注解析失败。
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
import { useAlgorithmOptions } from '@/application/evaluation/use-dimensions'
import { fetchAudiosByMd5 } from '@/infrastructure/api/audios-api'
import { parseAnnotationFile as parseAnnotation } from '@/features/audio-import/lib/annotation'
import { md5OfFile } from '@/features/audio-import/lib/md5'

export type AudioBatchAnnotationDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const ANNOTATION_EXTS = ['.json', '.jsonl', '.rttm', '.stm', '.txt']
const AUDIO_EXTS = ['.wav', '.mp3', '.m4a', '.flac', '.aac', '.ogg']
/** 计算 MD5 的并发文件数（V9.7.10 同款） */
const MD5_CONCURRENCY = 4
/** by-md5 单次查询的 MD5 个数上限（V9.7.10 同款分块，避免 IN 列表过大） */
const MD5_QUERY_BATCH = 500

/** 去扩展名（音频与标注按文件基名配对） */
function baseName(name: string): string {
  return name.replace(/\.[^.]+$/, '')
}

function hasExt(name: string, exts: string[]): boolean {
  const lower = name.toLowerCase()
  return exts.some((ext) => lower.endsWith(ext))
}

type MatchRow = {
  annotationName: string
  audioName: string
  audioId: number | null
  matched: boolean
  /** 未匹配原因（UI 直出，替代笼统的「未匹配到音频」） */
  unmatchedReason?: string
  annotations: unknown[]
}

type Stage = '计算音频 MD5' | '按 MD5 查询音频库' | '解析标注文件'

export function AudioBatchAnnotationDialog(props: AudioBatchAnnotationDialogProps) {
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
  const [rows, setRows] = useState<MatchRow[]>([])
  const [pending, setPending] = useState(false)
  const fileRef = useRef<HTMLInputElement | null>(null)

  const matchedCount = useMemo(() => rows.filter((r) => r.matched).length, [rows])
  const unmatchedCount = useMemo(() => rows.length - matchedCount, [rows, matchedCount])
  const selectedAlgorithmLabel = algorithmOptions.find((o) => o.value === algorithmType)?.label

  const resetProgress = () => {
    setProcessed(0)
    setTotal(0)
    setStage('')
  }

  const exportUnmatched = () => {
    const lines = rows.filter((r) => !r.matched).map((r) => r.annotationName)
    if (lines.length === 0) return
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `未匹配标注_${new Date().toISOString().slice(0, 10)}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  const resultRows = useMemo(
    () => (onlyUnmatched ? rows.filter((r) => !r.matched) : rows),
    [onlyUnmatched, rows]
  )

  const handleFiles = async (incoming: FileList | null) => {
    if (!incoming) return
    const list = Array.from(incoming)
    const audioFiles = list.filter((f) => hasExt(f.name, AUDIO_EXTS))
    const annotationFiles = list.filter((f) => hasExt(f.name, ANNOTATION_EXTS))
    if (annotationFiles.length === 0) {
      toast.error('未选择标注文件（.json/.jsonl/.rttm/.stm/.txt）')
      return
    }

    setProcessing(true)
    setRows([])
    try {
      // 1. 音频文件按内容算 MD5，并以文件基名索引（audio1.wav → md5）
      setStage('计算音频 MD5')
      setProcessed(0)
      setTotal(audioFiles.length)
      const baseNameToMd5 = new Map<string, string>()
      const md5Set = new Set<string>()
      for (let i = 0; i < audioFiles.length; i += MD5_CONCURRENCY) {
        const batch = audioFiles.slice(i, i + MD5_CONCURRENCY)
        const results = await Promise.all(
          batch.map(async (file) => {
            try {
              return { name: file.name, md5: await md5OfFile(file) }
            } catch {
              return null
            }
          })
        )
        for (const result of results) {
          if (!result) continue
          md5Set.add(result.md5)
          baseNameToMd5.set(baseName(result.name).toLowerCase(), result.md5.toLowerCase())
        }
        setProcessed(Math.min(i + MD5_CONCURRENCY, audioFiles.length))
      }

      // 2. 分批按 MD5 查全库（不依赖当前列表已载入的行，分页/筛选之外同样命中）
      setStage('按 MD5 查询音频库')
      const md5ToAudio: Record<string, { id: number; name: string }> = {}
      const md5List = Array.from(md5Set)
      setTotal(md5List.length)
      for (let i = 0; i < md5List.length; i += MD5_QUERY_BATCH) {
        const chunk = md5List.slice(i, i + MD5_QUERY_BATCH)
        Object.assign(md5ToAudio, await fetchAudiosByMd5(chunk))
        setProcessed(Math.min(i + MD5_QUERY_BATCH, md5List.length))
      }

      // 3. 解析标注并出匹配结果（基名 → md5 → 库内音频）
      setStage('解析标注文件')
      setProcessed(0)
      setTotal(annotationFiles.length)
      const nextRows: MatchRow[] = []
      for (let i = 0; i < annotationFiles.length; i += 1) {
        const file = annotationFiles[i]
        const content = await file.text()
        const annotations = parseAnnotation(file.name, content)
        const md5 = baseNameToMd5.get(baseName(file.name).toLowerCase())
        const matchedAudio = md5 ? md5ToAudio[md5] : undefined
        nextRows.push({
          annotationName: file.name,
          audioName: matchedAudio ? matchedAudio.name : '',
          audioId: matchedAudio ? matchedAudio.id : null,
          matched: matchedAudio != null,
          unmatchedReason: matchedAudio
            ? undefined
            : audioFiles.length === 0
              ? '未拖入音频文件，无法按内容 MD5 匹配'
              : md5
                ? '音频内容 MD5 不在库内（该音频尚未上传）'
                : '未拖入与标注同名的音频文件',
          annotations,
        })
        setProcessed(i + 1)
      }
      setRows(nextRows)
      if (audioFiles.length === 0) {
        toast.info('未拖入音频文件：请同时拖入对应音频，按内容 MD5 匹配全库音频')
      }
    } catch {
      toast.error('标注文件处理失败，请重试')
    } finally {
      setProcessing(false)
      resetProgress()
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
          resetProgress()
        }
      }}
    >
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>批量更新标注</DialogTitle>
          <DialogDescription>
            同时拖入音频与标注文件，按音频内容 MD5 在音频库全量匹配（audio1.wav + audio1.json
            为一组）；文件名被改过但内容相同也能命中，不受列表分页与筛选限制。
          </DialogDescription>
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
              disabled={processing}
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
                void handleFiles(e.target.files)
                e.target.value = ''
              }}
            />
          </div>

          {/* 处理进度（计算 MD5 → 查库 → 解析标注） */}
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
              <Button variant='ghost' size='sm' className='h-7 px-2' onClick={() => { setRows([]); resetProgress() }}>
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
                  <SelectValue placeholder={algorithmOptionsQuery.isLoading ? '加载中…' : '选择算法'}>
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
                        {row.matched ? row.audioName : row.unmatchedReason}
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
