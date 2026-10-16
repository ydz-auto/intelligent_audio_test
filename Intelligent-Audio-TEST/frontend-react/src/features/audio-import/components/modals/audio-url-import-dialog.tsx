/**
 * 从 URL 导入音频弹窗（§6.18；Dialog sm:max-w-lg）。
 * 批量 URL 导入（多行/逗号分隔）+ URL 格式验证（非法 URL 行红标并跳过）+ 下载进度显示。
 * 主钮「导入」（audio:upload → POST /audios/url-import）。
 */
import { Download, Globe } from 'lucide-react'
import { useMemo, useState } from 'react'
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
import { Textarea } from '@/components/ui/textarea'
import { AUDIO_TYPE_OPTIONS } from '@/features/audio-import/constants'
import { useAudioMutations } from '@/application/audio/useAudioList'

export type AudioUrlImportDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

export function AudioUrlImportDialog(props: AudioUrlImportDialogProps) {
  const { urlImport } = useAudioMutations()
  const [urlsText, setUrlsText] = useState('')
  const [audioType, setAudioType] = useState('dry')
  const [pending, setPending] = useState(false)

  const urls = useMemo(
    () =>
      urlsText
        .split(/[\n,]+/)
        .map((u) => u.trim())
        .filter(Boolean),
    [urlsText]
  )
  const invalid = urls.filter((url) => !/^https?:\/\//i.test(url))

  const handleImport = async () => {
    if (urls.length === 0) return
    setPending(true)
    try {
      const result = await urlImport.mutateAsync(urls)
      toast.success(
        `URL 导入成功：成功 ${result.successCount} 个，跳过 ${result.failedCount} 个`
      )
      setUrlsText('')
      props.onOpenChange(false)
    } catch {
      toast.error('URL 导入失败，请重试')
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog
      open={props.open}
      onOpenChange={(open) => {
        props.onOpenChange(open)
        if (!open) setPending(false)
      }}
    >
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>从 URL 导入音频</DialogTitle>
          <DialogDescription>支持多行或逗号分隔批量导入音频 URL</DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          <div className='space-y-2'>
            <Label htmlFor='url-import-text'>URL 列表</Label>
            <Textarea
              id='url-import-text'
              value={urlsText}
              onChange={(e) => setUrlsText(e.target.value)}
              rows={6}
              placeholder={'https://example.com/audio/1.wav\nhttps://example.com/audio/2.wav, https://example.com/audio/3.wav'}
              className='font-mono text-xs'
              aria-invalid={invalid.length > 0}
            />
            {invalid.length > 0 && (
              <p className='text-sm text-[var(--destructive)]'>
                以下 URL 格式非法，将跳过：{invalid.slice(0, 3).join('、')}
                {invalid.length > 3 ? ` 等 ${invalid.length} 条` : ''}
              </p>
            )}
            <p className='text-muted-foreground text-xs'>
              已识别 {urls.length} 条 URL
            </p>
          </div>

          <div className='space-y-2'>
            <Label htmlFor='url-import-type'>音频类型</Label>
            <Select
              value={audioType}
              onValueChange={(value) => setAudioType(value ?? 'dry')}
            >
              <SelectTrigger id='url-import-type' size='sm' className='w-full'>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {AUDIO_TYPE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {pending && (
            <div className='bg-muted/40 flex items-center gap-2 rounded-md px-2.5 py-2 text-xs'>
              <Download aria-hidden='true' className='text-primary size-3.5 animate-bounce' />
              正在下载并导入，请稍候...
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant='outline' size='sm' onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button size='sm' onClick={handleImport} disabled={pending || urls.length === 0}>
            <Globe aria-hidden='true' className='size-3.5' />
            导入
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
