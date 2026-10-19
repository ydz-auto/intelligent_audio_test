/**
 * 音频特征分析·质量评估弹窗（§6.23；Dialog sm:max-w-3xl）。
 * 特征分区（频谱特征/能量分布/时域特征）+ 质量评估分区（信噪比/动态范围/频率响应 + 质量评分）
 * + 处理操作（降噪/增益调整/剪辑）。
 * 现状：后端无音频特征分析/质量评估端点（audio_bp 无 feature/analysis 路由）→ **待 FEAT**，
 * 展示空态与缺口说明，处理操作禁用，不展示 mock 特征值。
 */
import { Activity, AudioLines, SlidersHorizontal, Scissors } from 'lucide-react'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import type { AudioAsset } from '@/domain/models/audio'
import { formatDuration } from '@/features/audio-import/lib/format'

export type AudioFeatureAnalysisDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  audio: AudioAsset | null
}

export function AudioFeatureAnalysisDialog(props: AudioFeatureAnalysisDialogProps) {
  const audio = props.audio

  if (!audio) return null

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>音频特征分析</DialogTitle>
          <DialogDescription>「{audio.name}」（{formatDuration(audio.duration)}）</DialogDescription>
        </DialogHeader>

        <Empty className='h-64'>
          <EmptyMedia variant='icon'>
            <Activity aria-hidden='true' className='size-4' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>特征分析待后端接口</EmptyTitle>
            <EmptyDescription>
              后端当前未提供音频特征/质量评估端点，本功能已开【FEAT】卡补齐。
              就绪后展示频谱特征 / 能量分布 / 时域特征与信噪比 / 动态范围 / 频率响应 / 质量评分。
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <span className='text-muted-foreground text-xs'>处理操作：降噪 / 增益调整 / 剪辑</span>
          </EmptyContent>
        </Empty>

        <div className='flex flex-wrap gap-2'>
          <Button variant='outline' size='sm' className='gap-1.5' disabled>
            <AudioLines aria-hidden='true' className='size-3.5' />
            降噪
          </Button>
          <Button variant='outline' size='sm' className='gap-1.5' disabled>
            <SlidersHorizontal aria-hidden='true' className='size-3.5' />
            增益调整
          </Button>
          <Button variant='outline' size='sm' className='gap-1.5' disabled>
            <Scissors aria-hidden='true' className='size-3.5' />
            剪辑
          </Button>
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
