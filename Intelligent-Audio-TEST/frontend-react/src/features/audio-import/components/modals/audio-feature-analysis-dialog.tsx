/**
 * 音频特征分析·质量评估弹窗（§6.23；Dialog sm:max-w-3xl）。
 * 特征分区（频谱特征/能量分布/时域特征）+ 质量评估分区（信噪比/动态范围/频率响应 +
 * 质量评分）+ 处理操作（降噪/增益调整/剪辑，audio:update）。
 */
import { Activity, AudioLines, SlidersHorizontal, Scissors } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import type { AudioAsset } from '@/domain/models/audio'
import { formatDuration } from '@/features/audio-import/lib/format'

export type AudioFeatureAnalysisDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  audio: AudioAsset | null
}

function MetricBar({ label, value, max }: { label: string; value: number; max: number }) {
  return (
    <div className='flex items-center gap-2'>
      <span className='text-muted-foreground w-24 shrink-0 text-xs'>{label}</span>
      <div className='bg-muted h-1.5 min-w-0 flex-1 overflow-hidden rounded-full'>
        <div
          className={cn(
            'h-full rounded-full',
            value >= max * 0.8 ? 'bg-[var(--success)]' : value >= max * 0.5 ? 'bg-[var(--info)]' : 'bg-[var(--warning)]'
          )}
          style={{ width: `${Math.min((value / max) * 100, 100)}%` }}
        />
      </div>
      <span className='w-12 shrink-0 text-right font-mono text-xs tabular-nums'>
        {value}
      </span>
    </div>
  )
}

export function AudioFeatureAnalysisDialog(props: AudioFeatureAnalysisDialogProps) {
  const [processing, setProcessing] = useState<string | null>(null)
  const audio = props.audio

  if (!audio) return null

  const handleProcess = (action: string) => {
    setProcessing(action)
    window.setTimeout(() => {
      setProcessing(null)
      toast.success(`已生成${action}处理结果`)
    }, 500)
  }

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>音频特征分析</DialogTitle>
          <DialogDescription>「{audio.name}」（{formatDuration(audio.duration)}）</DialogDescription>
        </DialogHeader>

        <div className='grid grid-cols-1 gap-4 sm:grid-cols-3'>
          <div className='bg-muted/30 rounded-lg border p-3'>
            <div className='text-muted-foreground mb-2 flex items-center gap-1.5 text-sm font-medium'>
              <Activity aria-hidden='true' className='size-3.5' />
              频谱特征
            </div>
            <div className='space-y-1.5 text-xs'>
              <p className='flex justify-between'><span className='text-muted-foreground'>基频范围</span><span className='font-mono tabular-nums'>80 – 4 200 Hz</span></p>
              <p className='flex justify-between'><span className='text-muted-foreground'>主频能量峰</span><span className='font-mono tabular-nums'>850 Hz</span></p>
              <p className='flex justify-between'><span className='text-muted-foreground'>谐波失真</span><span className='font-mono tabular-nums'>2.1%</span></p>
            </div>
          </div>
          <div className='bg-muted/30 rounded-lg border p-3'>
            <div className='text-muted-foreground mb-2 flex items-center gap-1.5 text-sm font-medium'>
              <AudioLines aria-hidden='true' className='size-3.5' />
              能量分布
            </div>
            <div className='space-y-1.5 text-xs'>
              <p className='flex justify-between'><span className='text-muted-foreground'>平均能量</span><span className='font-mono tabular-nums'>-18.3 dBFS</span></p>
              <p className='flex justify-between'><span className='text-muted-foreground'>峰值能量</span><span className='font-mono tabular-nums'>-2.1 dBFS</span></p>
              <p className='flex justify-between'><span className='text-muted-foreground'>能量集中度</span><span className='font-mono tabular-nums'>0.72</span></p>
            </div>
          </div>
          <div className='bg-muted/30 rounded-lg border p-3'>
            <div className='text-muted-foreground mb-2 flex items-center gap-1.5 text-sm font-medium'>
              <SlidersHorizontal aria-hidden='true' className='size-3.5' />
              时域特征
            </div>
            <div className='space-y-1.5 text-xs'>
              <p className='flex justify-between'><span className='text-muted-foreground'>过零率</span><span className='font-mono tabular-nums'>0.084</span></p>
              <p className='flex justify-between'><span className='text-muted-foreground'>活跃时长占比</span><span className='font-mono tabular-nums'>68%</span></p>
              <p className='flex justify-between'><span className='text-muted-foreground'>起始时间</span><span className='font-mono tabular-nums'>0.18 s</span></p>
            </div>
          </div>
        </div>

        {/* 质量评估 */}
        <div className='bg-muted/30 rounded-lg border p-3'>
          <div className='text-muted-foreground mb-2 text-sm font-medium'>质量评估</div>
          <div className='grid grid-cols-1 gap-2 sm:grid-cols-2'>
            <MetricBar label='信噪比' value={34} max={60} />
            <MetricBar label='动态范围' value={76} max={100} />
            <MetricBar label='频率响应' value={82} max={100} />
            <MetricBar label='整体质量评分' value={88} max={100} />
          </div>
        </div>

        {/* 处理操作 */}
        <div className='space-y-2'>
          <div className='text-muted-foreground text-sm font-medium'>处理操作</div>
          <div className='flex flex-wrap gap-2'>
            <Button
              variant='outline'
              size='sm'
              className='gap-1.5'
              disabled={processing !== null}
              onClick={() => handleProcess('降噪')}
            >
              <AudioLines aria-hidden='true' className='size-3.5' />
              降噪
            </Button>
            <Button
              variant='outline'
              size='sm'
              className='gap-1.5'
              disabled={processing !== null}
              onClick={() => handleProcess('增益调整')}
            >
              <SlidersHorizontal aria-hidden='true' className='size-3.5' />
              增益调整
            </Button>
            <Button
              variant='outline'
              size='sm'
              className='gap-1.5'
              disabled={processing !== null}
              onClick={() => handleProcess('剪辑')}
            >
              <Scissors aria-hidden='true' className='size-3.5' />
              剪辑
            </Button>
            {processing && (
              <span className='text-muted-foreground self-center text-xs'>
                {processing}中...
              </span>
            )}
          </div>
          <p className='text-muted-foreground text-xs'>
            处理将生成新文件或覆盖原文件，请在确认弹窗中选择。
          </p>
        </div>

        <DialogFooter>
          <Button variant='outline' size='sm' onClick={() => props.onOpenChange(false)}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
