/**
 * 音频播放 Modal（15_报告域.md §4.11，AudioPlayerModal 平移）。
 * props：audioId/audioTitle/audioType/spl/playOrder/noiseSpl/deviceName 全参。
 * 可视稿：展示音频元信息 + 播放/暂停演示（真实音频流待 API 接线）。
 */
import { Pause, Play } from 'lucide-react'
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

export interface AudioItemMeta {
  audio_id: number | string
  audio_name?: string
  audio_type?: string
  spl?: number
  play_order?: number
  noise_spl?: number
  device_name?: string
}

interface AudioPlayerModalProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  audio?: AudioItemMeta
}

export function AudioPlayerModal({ open, onOpenChange, audio }: AudioPlayerModalProps) {
  const [playing, setPlaying] = useState(false)

  return (
    <Dialog open={open} onOpenChange={(next) => { onOpenChange(next); if (!next) setPlaying(false) }}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>音频播放</DialogTitle>
        </DialogHeader>
        {audio ? (
          <div className='space-y-3'>
            <div>
              <p className='font-medium'>{audio.audio_name ?? `音频 ${audio.audio_id}`}</p>
              <div className='mt-1 flex flex-wrap gap-1.5'>
                {audio.audio_type && <Badge variant='outline'>{audio.audio_type}</Badge>}
                {audio.device_name && <Badge variant='secondary'>{audio.device_name}</Badge>}
              </div>
            </div>
            <div className='text-muted-foreground grid grid-cols-2 gap-x-4 gap-y-1 text-xs'>
              <span>声压级 (SPL)：<span className='font-mono'>{audio.spl ?? '—'} dB</span></span>
              <span>噪声级：<span className='font-mono'>{audio.noise_spl ?? '—'} dB</span></span>
              <span>播放顺序：<span className='font-mono'>{audio.play_order ?? '—'}</span></span>
              <span>音频 ID：<span className='font-mono'>{audio.audio_id}</span></span>
            </div>
            <div className='bg-muted/40 flex items-center justify-center gap-3 rounded-lg border p-6'>
              <Button
                size='lg'
                className='size-14 rounded-full'
                aria-label={playing ? '暂停' : '播放'}
                onClick={() => setPlaying((v) => !v)}
              >
                {playing ? (
                  <Pause aria-hidden='true' className='size-5' />
                ) : (
                  <Play aria-hidden='true' className='size-5' />
                )}
              </Button>
            </div>
            <p className='text-muted-foreground text-center text-xs'>
              {playing ? '播放中...' : '点击播放按钮预览音频（mock，音频流待 API 接线）'}
            </p>
          </div>
        ) : (
          <p className='text-muted-foreground p-4 text-center text-sm'>无音频信息</p>
        )}
      </DialogContent>
    </Dialog>
  )
}
