/**
 * 音频播放历史弹窗（§6.24；Dialog sm:max-w-2xl）。
 * StaticDataTable 列表（播放时间/使用的测试用例/播放设备/结果/时长，音频导入功能设计文档.md:196-200）。
 * 现状：后端无音频播放历史端点（audio_bp / playback_bp 无 history 路由）→ **待 FEAT**，
 * 弹窗显示空态并注明缺口，不展示 mock 数据。
 */
import { Clock3 } from 'lucide-react'

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

export type AudioPlaybackHistoryDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  audio: AudioAsset | null
}

export function AudioPlaybackHistoryDialog(props: AudioPlaybackHistoryDialogProps) {
  const audio = props.audio

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>播放历史</DialogTitle>
          <DialogDescription>{audio ? `「${audio.name}」的播放记录` : '播放记录'}</DialogDescription>
        </DialogHeader>

        <Empty className='h-64'>
          <EmptyMedia variant='icon'>
            <Clock3 aria-hidden='true' className='size-4' />
          </EmptyMedia>
          <EmptyHeader>
            <EmptyTitle>播放历史待后端接口</EmptyTitle>
            <EmptyDescription>
              后端当前未提供音频播放历史端点（audio_bp/playback_bp 无 history 路由），
              本功能已开【FEAT】卡补齐，接口就绪后展示播放时间/测试用例/设备/结果/时长列表。
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            <span className='text-muted-foreground text-xs'>字段口径：音频导入功能设计文档.md:196-200</span>
          </EmptyContent>
        </Empty>

        <DialogFooter>
          <Button variant='outline' size='sm' onClick={() => props.onOpenChange(false)}>
            关闭
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
