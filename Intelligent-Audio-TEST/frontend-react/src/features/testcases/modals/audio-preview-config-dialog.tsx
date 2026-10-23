/**
 * 音频试听配置弹窗（11_用例域.md §5.2，Dialog sm:max-w-md）。
 * 播放模式 RadioGroup「浏览器播放/实验室播放」+ 偏移量 Input（number 秒，默认 0）
 * + 主钮「开始试听」；载荷 POST /audios/{id}/preview（实验室）或 GET /audios/{id}/stream
 * （浏览器，真实音频流播放，INT-1424 移除 toast 演示）。
 * 试听对象经 audioItem 传入（音频列表卡「试听」/全局噪声「试听」）；用例行预览
 * （previewCase 入口）未带 audioItem 时回退用例 config.rounds[0].audios[0]。
 */
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
import { Input } from '@/components/ui/input'
import { AudioPlayerPanel } from '@/features/testcases/modals/audio-player-dialog'
import type { TestCaseListItem } from '@/domain/models/testCase'

/** 试听对象（音频列表卡/全局噪声传入） */
export interface PreviewAudioItem {
  id: number | string
  name?: string | null
  spl?: number | null
  /** 音频时长（秒；音频库 AudioAsset.duration，实验室播放无浏览器流时作总时长兜底） */
  duration?: number | null
  /** 播放设备展示标签（实验室播放=用例配置设备；浏览器可为空） */
  deviceLabels?: string[]
  /** 播放设备记录 id（用例配置的 playback_device_id / 全局噪声 deviceIds）；
   *  实验室播放据此解析 device_unique_ids 发给后端，缺失时后端按默认设备播放（INT-1424 终审 P2-2） */
  deviceIds?: string[]
}

/** 用例 config 首轮首个音频回退（previewCase 入口无显式 audioItem 时） */
function firstRoundAudio(caseItem: TestCaseListItem | null): PreviewAudioItem | null {
  if (!caseItem) return null
  const rounds = (caseItem.config as Record<string, unknown> | undefined)?.rounds as
    | Array<{
        audios?: Array<{
          audio_id?: number | string | null
          audio_name?: string | null
          /** 播放设备（轮次音频配置的设备 id） */
          playback_device_id?: number | string | null
          playbackDeviceId?: number | string | null
          /** 部分存量 config 冗余时长（秒） */
          duration?: number | null
          audio_duration?: number | null
        }>
      }>
    | undefined
  const first = rounds?.[0]?.audios?.[0]
  if (!first?.audio_id) return null
  const deviceId = first.playback_device_id ?? first.playbackDeviceId ?? null
  return {
    id: first.audio_id,
    name: first.audio_name ?? null,
    duration: first.duration ?? first.audio_duration ?? null,
    deviceIds: deviceId == null || deviceId === '' ? [] : [String(deviceId)],
  }
}

export function AudioPreviewConfigDialog({
  open,
  onOpenChange,
  caseItem,
  audioItem,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  caseItem: TestCaseListItem | null
  /** 试听对象（可选；缺省回退用例首轮首个音频） */
  audioItem?: PreviewAudioItem | null
}) {
  const [mode, setMode] = useState<'frontend' | 'backend'>('frontend')
  const [offset, setOffset] = useState('0')
  /** 试听编排阶段：config=播放模式/偏移量配置；playing=音频播放器（§5.2） */
  const [stage, setStage] = useState<'config' | 'playing'>('config')

  const target = audioItem ?? firstRoundAudio(caseItem)

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        onOpenChange(o)
        if (!o) setStage('config')
      }}
    >
      <DialogContent className={stage === 'playing' ? 'sm:max-w-lg' : 'sm:max-w-md'}>
        <DialogHeader>
          <DialogTitle>
            {stage === 'playing'
              ? `测试用例预览｜${target?.name ?? caseItem?.name ?? '音频'} 音频`
              : '音频试听配置'}
          </DialogTitle>
          <DialogDescription>
            {stage === 'playing'
              ? '浏览器播放或实验室扬声器试听中'
              : target?.name
                ? `音频「${target.name}」`
                : caseItem
                  ? `用例「${caseItem.name}」`
                  : '预览所选用例的音频'}
          </DialogDescription>
        </DialogHeader>

        {stage === 'playing' ? (
          <AudioPlayerPanel
            mode={mode}
            audioId={target?.id ?? null}
            audioName={target?.name ?? null}
            deviceLabels={target?.deviceLabels ?? []}
            deviceIds={target?.deviceIds ?? []}
            spl={target?.spl ?? 65}
            durationHint={target?.duration ?? null}
            offset={Number(offset) || 0}
            onBack={() => setStage('config')}
          />
        ) : (
          <div className='space-y-4'>
            <div className='space-y-1.5'>
              <span className='text-sm font-medium'>播放模式</span>
              <div className='flex flex-col gap-1.5'>
                <label className='hover:bg-accent flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-sm'>
                  <input
                    type='radio'
                    name='preview-mode'
                    checked={mode === 'frontend'}
                    onChange={() => setMode('frontend')}
                  />
                  <span>
                    浏览器播放
                    <span className='text-muted-foreground block text-xs'>
                      音频将通过浏览器前端直接播放
                    </span>
                  </span>
                </label>
                <label className='hover:bg-accent flex cursor-pointer items-start gap-2 rounded-md px-2 py-1.5 text-sm'>
                  <input
                    type='radio'
                    name='preview-mode'
                    checked={mode === 'backend'}
                    onChange={() => setMode('backend')}
                  />
                  <span>
                    实验室播放
                    <span className='text-muted-foreground block text-xs'>
                      音频将通过用例配置中的播放设备在实验室播放
                    </span>
                  </span>
                </label>
              </div>
            </div>
            <div className='flex items-center gap-2'>
              <span className='text-sm font-medium'>偏移量（秒）</span>
              <Input
                type='number'
                value={offset}
                onChange={(e) => setOffset(e.target.value)}
                className='h-8 w-32'
                aria-label='偏移量秒数'
              />
            </div>
          </div>
        )}

        {stage !== 'playing' && (
          <DialogFooter>
            <Button variant='outline' onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button onClick={() => setStage('playing')}>开始试听</Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  )
}
