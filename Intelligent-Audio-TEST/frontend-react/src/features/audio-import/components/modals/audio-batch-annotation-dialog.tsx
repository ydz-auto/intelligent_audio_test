/**
 * 批量更新标注弹窗（§6.19；Dialog sm:max-w-3xl）。
 * 拖放区（音频+标注文件按文件名匹配）+ 处理进度 + 已解析摘要 + 算法 select
 * + 「同步刷新关联测试用例的参考参数」checkbox + 匹配结果列表 + 主钮「开始更新」
 * （POST /audios/batch/annotations）→ toast「更新完成 成功 {s} 失败 {f} 刷新用例 {z}」。
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

export type AudioBatchAnnotationDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const MOCK_MATCH_RESULTS = [
  { annotation: '客厅_中文_命令集.json', audio: '客厅_中文_命令集.wav', audioId: 1, matched: true },
  { annotation: '车内_导航_1人.json', audio: '车内_导航_1人.wav', audioId: 2, matched: true },
  { annotation: '会议室_多人_中文.json', audio: '会议室_多人_中文.wav', audioId: 3, matched: true },
  { annotation: '英文_短信指令.json', audio: '未匹配到音频', audioId: null, matched: false },
]

export function AudioBatchAnnotationDialog(props: AudioBatchAnnotationDialogProps) {
  const { batchAnnotations } = useAudioMutations()
  const [parsed, setParsed] = useState(0)
  const [processing, setProcessing] = useState(false)
  const [refreshCases, setRefreshCases] = useState(true)
  const [algorithmType, setAlgorithmType] = useState('asr-v3')
  const [onlyUnmatched, setOnlyUnmatched] = useState(false)
  const fileRef = useRef<HTMLInputElement | null>(null)

  const resultRows = useMemo(
    () => (onlyUnmatched ? MOCK_MATCH_RESULTS.filter((r) => !r.matched) : MOCK_MATCH_RESULTS),
    [onlyUnmatched]
  )

  const matched = MOCK_MATCH_RESULTS.filter((r) => r.matched).length
  const unmatched = MOCK_MATCH_RESULTS.length - matched

  const handleFiles = () => {
    setProcessing(true)
    setParsed(0)
    const timer = window.setInterval(() => {
      setParsed((prev) => {
        const next = prev + 1
        if (next >= MOCK_MATCH_RESULTS.length) {
          window.clearInterval(timer)
          setProcessing(false)
        }
        return next
      })
    }, 150)
  }

  const handleStart = async () => {
    try {
      const result = await batchAnnotations.mutateAsync()
      toast.success(
        `更新完成 成功 ${result.success} 失败 ${result.failed} 刷新用例 ${result.refreshed}`
      )
      props.onOpenChange(false)
    } catch {
      toast.error('批量更新标注失败，请重试')
    }
  }

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>批量更新标注</DialogTitle>
          <DialogDescription>按文件名匹配音频与标注文件（audio1.wav ↔ audio1.json）</DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          {/* 拖放区 */}
          <div
            className='border-border/60 hover:bg-muted/30 flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-5 text-center transition-colors'
          >
            <FileCheck2 aria-hidden='true' className='text-muted-foreground size-8' />
            <p className='text-sm'>拖拽音频 + 标注文件到此处或点击选择</p>
            <p className='text-muted-foreground text-xs'>
              音频 .wav/.mp3/.m4a/.flac + 标注 .json/.jsonl/.rttm/.stm/.txt
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
              accept='.wav,.mp3,.m4a,.flac,.json,.jsonl,.rttm,.stm,.txt'
              className='hidden'
              onChange={handleFiles}
            />
          </div>

          {/* 处理进度 */}
          {processing && (
            <div className='bg-muted/40 rounded-md px-2.5 py-2'>
              <div className='bg-muted h-1.5 w-full overflow-hidden rounded-full'>
                <div
                  className='bg-primary h-full rounded-full transition-all duration-150'
                  style={{ width: `${(parsed / MOCK_MATCH_RESULTS.length) * 100}%` }}
                />
              </div>
              <p className='text-muted-foreground mt-1 text-xs tabular-nums'>
                正在处理... {parsed}/{MOCK_MATCH_RESULTS.length}
              </p>
            </div>
          )}

          {/* 已解析摘要 */}
          {parsed > 0 && (
            <div className='flex flex-wrap items-center gap-2 text-sm'>
              <span>已解析 <span className='font-mono tabular-nums'>{parsed}</span> 个标注</span>
              <span>
                匹配 <span className='font-mono text-[var(--success)] tabular-nums'>{matched}</span>
              </span>
              <span>
                未匹配 <span className='font-mono text-[var(--destructive)] tabular-nums'>{unmatched}</span>
              </span>
              <Button variant='ghost' size='sm' className='h-7 px-2' onClick={() => setParsed(0)}>
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
                onValueChange={(value) => setAlgorithmType(value ?? 'asr-v3')}
              >
                <SelectTrigger id='batch-anno-algo' size='sm' className='w-full'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='asr-v3'>通用识别引擎</SelectItem>
                  <SelectItem value='asr-stream'>流式识别引擎</SelectItem>
                  <SelectItem value='eval-ensemble'>多维评估集成</SelectItem>
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

          {/* 匹配结果列表 */}
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
                    key={row.annotation}
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
                    <span className='min-w-0 flex-1 truncate'>{row.annotation}</span>
                    <span className='text-muted-foreground text-xs'>→</span>
                    <span className={cn('min-w-0 flex-1 truncate', !row.matched && 'text-[var(--destructive)]')}>
                      {row.audio}
                      {row.audioId != null && (
                        <span className='text-muted-foreground font-mono text-xs tabular-nums'>
                          {' '}#{row.audioId}
                        </span>
                      )}
                    </span>
                    {row.matched && (
                      <Badge variant='secondary' className='rounded-md px-1.5 font-normal'>
                        {row.annotation.replace(/\.(json|jsonl|rttm|stm|txt)$/i, '').split('_')[0]} 标注
                      </Badge>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant='outline' size='sm' onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button size='sm' onClick={handleStart} disabled={parsed === 0 || processing}>
            开始更新
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
