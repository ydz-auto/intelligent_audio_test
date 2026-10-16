/**
 * 音频试听弹窗（§6.14；三弹窗链归用例域卡 INT-356，本页入口=音频行「预览」）。
 * 试听配置 RadioGroup「浏览器播放/实验室播放」（playbackMode 默认 frontend）
 * + 播放器 mock（audioTypeLabel 干声/噪声/提示词音频/混合音频 对位）。
 */
import { Play, Square } from 'lucide-react'
import { useState } from 'react'

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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import type { AudioAsset } from '@/domain/models/audio'
import { formatDuration } from '@/features/audio-import/lib/format'

export type AudioPreviewDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  audio: AudioAsset | null
}

export function AudioPreviewDialog(props: AudioPreviewDialogProps) {
  const [playbackMode, setPlaybackMode] = useState('frontend')
  const [playing, setPlaying] = useState(false)
  const audio = props.audio

  return (
    <Dialog
      open={props.open}
      onOpenChange={(open) => {
        props.onOpenChange(open)
        if (!open) setPlaying(false)
      }}
    >
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>音频播放</DialogTitle>
          <DialogDescription>
            {audio ? `试听「${audio.name}」` : '试听音频'}
          </DialogDescription>
        </DialogHeader>

        {audio ? (
          <div className='space-y-4'>
            <div className='flex items-center gap-3'>
              <Button
                variant='outline'
                size='icon'
                aria-label={playing ? '停止播放' : '播放'}
                onClick={() => setPlaying((prev) => !prev)}
              >
                {playing ? (
                  <Square aria-hidden='true' className='size-4' />
                ) : (
                  <Play aria-hidden='true' className='size-4' />
                )}
              </Button>
              <div className='min-w-0 flex-1'>
                <div className='truncate text-sm font-medium'>{audio.name}</div>
                <div className='text-muted-foreground flex items-center gap-2 text-xs'>
                  <span>{audio.format ?? '—'}</span>
                  <span className='font-mono tabular-nums'>
                    {formatDuration(audio.duration)}
                  </span>
                  <span>{audio.audioType === 'dry' ? '干声（信号音频）' : audio.audioType === 'noise' ? '噪声' : audio.audioType === 'prompt' ? '提示词音频' : '混合音频'}</span>
                </div>
              </div>
            </div>

            <div className='bg-muted h-8 w-full overflow-hidden rounded-md'>
              {playing && (
                <div className='bg-primary/70 h-full rounded-md' style={{ width: '38%' }} />
              )}
            </div>

            <div className='space-y-2'>
              <div className='text-muted-foreground text-sm font-medium'>
                试听配置
              </div>
              <div className='flex flex-wrap items-center gap-2'>
                <span className='text-muted-foreground text-xs'>播放模式</span>
                <Select
                  value={playbackMode}
                  onValueChange={(value) => setPlaybackMode(value ?? 'frontend')}
                >
                  <SelectTrigger size='sm' className='w-44' aria-label='播放模式'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value='frontend'>浏览器播放</SelectItem>
                    <SelectItem value='laboratory'>实验室播放</SelectItem>
                  </SelectContent>
                </Select>
                {playbackMode === 'laboratory' && (
                  <span className='text-muted-foreground text-xs'>
                    通过实验室音频通道输出
                  </span>
                )}
              </div>
            </div>
          </div>
        ) : (
          <p className='text-muted-foreground py-6 text-center text-sm'>未选择音频</p>
        )}

        <DialogFooter>
          <Button variant='outline' size='sm' onClick={() => props.onOpenChange(false)}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
