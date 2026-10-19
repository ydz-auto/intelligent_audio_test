/**
 * 音频格式转换弹窗（§6.15；Dialog sm:max-w-md）。
 * 目标格式 select（MP3/WAV/FLAC/AAC 输出白名单）+ 转换参数（目标采样率/声道数/
 * 位深度/比特率）+ 主钮「开始转换」（audio:convert → POST /audios/{id}/convert）。
 * 补现状 ConvertModal confirm 未调用 convert API 缺口（§11-15）。
 */
import { RefreshCw } from 'lucide-react'
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
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  CONVERT_BITRATE_OPTIONS,
  CONVERT_BIT_DEPTH_OPTIONS,
  CONVERT_CHANNEL_OPTIONS,
  CONVERT_SAMPLE_RATE_OPTIONS,
  CONVERT_TARGET_FORMATS,
} from '@/features/audio-import/constants'
import { useAudioMutations } from '@/application/audio/useAudioList'
import type { AudioAsset } from '@/domain/models/audio'

export type AudioConvertDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  audio: AudioAsset | null
}

export function AudioConvertDialog(props: AudioConvertDialogProps) {
  const { convert } = useAudioMutations()
  const [targetFormat, setTargetFormat] = useState('WAV')
  const [sampleRate, setSampleRate] = useState('44100')
  const [channels, setChannels] = useState('2')
  const [bitDepth, setBitDepth] = useState('16')
  const [bitrate, setBitrate] = useState('256')
  const [pending, setPending] = useState(false)

  if (!props.audio) return null
  const audio = props.audio

  const handleConvert = async () => {
    setPending(true)
    try {
      const result = await convert.mutateAsync({
        id: audio.id,
        format: targetFormat,
      })
      toast.success(result.message ?? '转换成功')
      props.onOpenChange(false)
    } catch {
      toast.error('转换失败，请重试')
    } finally {
      setPending(false)
    }
  }

  const isLossless = targetFormat === 'WAV' || targetFormat === 'FLAC'
  const paramOptions = isLossless ? CONVERT_BIT_DEPTH_OPTIONS : CONVERT_BITRATE_OPTIONS

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>音频格式转换</DialogTitle>
          <DialogDescription>「{audio.name}」（{audio.format ?? '未知格式'}）</DialogDescription>
        </DialogHeader>

        <div className='grid grid-cols-2 gap-3'>
          <div className='space-y-2'>
            <Label>目标格式</Label>
            <Select
              value={targetFormat}
              onValueChange={(value) => setTargetFormat(value ?? 'WAV')}
            >
              <SelectTrigger size='sm' className='w-full' aria-label='目标格式'>
                <SelectValue placeholder='选择目标格式'>{targetFormat}</SelectValue>
              </SelectTrigger>
              <SelectContent>
                {CONVERT_TARGET_FORMATS.map((format) => (
                  <SelectItem key={format} value={format}>
                    {format}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className='space-y-2'>
            <Label>目标采样率</Label>
            <Select
              value={sampleRate}
              onValueChange={(value) => setSampleRate(value ?? '44100')}
            >
              <SelectTrigger size='sm' className='w-full' aria-label='目标采样率'>
                <SelectValue placeholder='选择采样率'>
                  {CONVERT_SAMPLE_RATE_OPTIONS.find((o) => o.value === sampleRate)?.label ?? ''}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {CONVERT_SAMPLE_RATE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className='space-y-2'>
            <Label>声道数</Label>
            <Select value={channels} onValueChange={(value) => setChannels(value ?? '2')}>
              <SelectTrigger size='sm' className='w-full' aria-label='声道数'>
                <SelectValue placeholder='选择声道数'>
                  {CONVERT_CHANNEL_OPTIONS.find((o) => o.value === channels)?.label ?? ''}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {CONVERT_CHANNEL_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className='space-y-2'>
            <Label>{isLossless ? '位深度' : '比特率'}</Label>
            <Select
              value={isLossless ? bitDepth : bitrate}
              onValueChange={(value) => {
                const next = value ?? ''
                if (isLossless) setBitDepth(next)
                else setBitrate(next)
              }}
            >
              <SelectTrigger size='sm' className='w-full' aria-label='转换参数'>
                <SelectValue placeholder='选择参数'>
                  {paramOptions.find((o) => o.value === (isLossless ? bitDepth : bitrate))?.label ?? ''}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {paramOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        <p className='text-muted-foreground text-xs'>
          批量转换：在列表中勾选多个音频后可从批量操作进入本弹窗，逐文件执行转换。
        </p>
        <p className='text-muted-foreground text-xs'>
          注：采样率 / 声道数 / 位深度 / 比特率当前为展示项，后端 ConvertFormatRequest 仅接收
          format（待 FEAT 扩展后生效）。
        </p>

        <DialogFooter>
          <Button variant='outline' size='sm' onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button size='sm' onClick={handleConvert} disabled={pending}>
            {pending ? '转换中...' : (
              <>
                <RefreshCw aria-hidden='true' className='size-3.5' />
                开始转换
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
