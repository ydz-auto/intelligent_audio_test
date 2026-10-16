/**
 * 音频元数据编辑弹窗（§6.13；Dialog sm:max-w-3xl）。
 * info-grid 可编辑（文件名/音频类型/标签/格式/时长/大小/源语言/ASR文本/描述）
 * + 标注管理卡（标注列表 + 格式 text/json/rttm/stm/txt + 内容编辑器）。
 * 主钮「保存」（audio:update）；toast「元数据保存成功」。
 */
import { Save } from 'lucide-react'
import { useEffect, useState } from 'react'
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
import { Input } from '@/components/ui/input'
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
import type { AudioAsset } from '@/domain/models/audio'

export type AudioMetadataDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  audio: AudioAsset | null
}

const ANNOTATION_FORMAT_OPTIONS = ['text', 'json', 'rttm', 'stm', 'txt'] as const

export function AudioMetadataDialog(props: AudioMetadataDialogProps) {
  const { saveMetadata } = useAudioMutations()
  const [name, setName] = useState('')
  const [audioType, setAudioType] = useState<string>('dry')
  const [sourceLanguage, setSourceLanguage] = useState('')
  const [asrText, setAsrText] = useState('')
  const [description, setDescription] = useState('')
  const [tags, setTags] = useState('')
  const [annotationFormat, setAnnotationFormat] = useState<string>('text')
  const [annotationContent, setAnnotationContent] = useState('')
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!props.audio) return
    setName(props.audio.name)
    setAudioType(props.audio.audioType ?? 'dry')
    setSourceLanguage(props.audio.sourceLanguage ?? '')
    setAsrText(props.audio.asrText ?? '')
    setDescription(props.audio.description ?? '')
    setTags(props.audio.tags.join(', '))
    setAnnotationFormat('text')
    setAnnotationContent('')
  }, [props.audio])

  if (!props.audio) return null
  const audio = props.audio

  const handleSave = async () => {
    setPending(true)
    try {
      await saveMetadata.mutateAsync({
        id: audio.id,
        patch: {
          name,
          audioType: audioType as AudioAsset['audioType'],
          sourceLanguage: sourceLanguage || null,
          asrText: asrText || null,
          description: description || null,
          tags: tags
            .split(',')
            .map((t) => t.trim())
            .filter(Boolean),
        },
      })
      toast.success('元数据保存成功')
      props.onOpenChange(false)
    } catch {
      toast.error('保存失败，请重试')
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
      <DialogContent className='sm:max-w-3xl'>
        <DialogHeader>
          <DialogTitle>编辑元数据</DialogTitle>
          <DialogDescription>「{props.audio.name}」的元数据与标注管理</DialogDescription>
        </DialogHeader>

        <div className='grid grid-cols-1 gap-4 sm:grid-cols-2'>
          <div className='space-y-2'>
            <Label htmlFor='audio-meta-name'>文件名</Label>
            <Input
              id='audio-meta-name'
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <div className='space-y-2'>
            <Label htmlFor='audio-meta-type'>音频类型</Label>
            <Select
              value={audioType}
              onValueChange={(value) => setAudioType(value ?? 'dry')}
            >
              <SelectTrigger id='audio-meta-type' size='sm' className='w-full'>
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
          <div className='space-y-2'>
            <Label htmlFor='audio-meta-lang'>源语言</Label>
            <Input
              id='audio-meta-lang'
              value={sourceLanguage}
              onChange={(e) => setSourceLanguage(e.target.value)}
              placeholder='如 zh-CN / en-US'
            />
          </div>
          <div className='space-y-2'>
            <Label htmlFor='audio-meta-tags'>标签</Label>
            <Input
              id='audio-meta-tags'
              value={tags}
              onChange={(e) => setTags(e.target.value)}
              placeholder='逗号分隔，如 客厅, 中文'
            />
            {tags && (
              <div className='flex flex-wrap gap-1'>
                {tags
                  .split(',')
                  .map((t) => t.trim())
                  .filter(Boolean)
                  .map((t) => (
                    <Badge key={t} variant='secondary' className='rounded-md px-1.5 font-normal'>
                      {t}
                    </Badge>
                  ))}
              </div>
            )}
          </div>
          <div className='space-y-2 sm:col-span-2'>
            <Label htmlFor='audio-meta-asr'>ASR 文本</Label>
            <Textarea
              id='audio-meta-asr'
              value={asrText}
              onChange={(e) => setAsrText(e.target.value)}
              rows={2}
              placeholder='自动识别文本'
            />
          </div>
          <div className='space-y-2 sm:col-span-2'>
            <Label htmlFor='audio-meta-desc'>描述</Label>
            <Textarea
              id='audio-meta-desc'
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={2}
            />
          </div>
        </div>

        {/* 标注管理卡（§6.13：格式 select + 内容编辑器） */}
        <div className='bg-muted/30 rounded-lg border p-3'>
          <div className='text-muted-foreground mb-2 text-sm font-medium'>
            标注管理
          </div>
          <div className='grid grid-cols-1 gap-3 sm:grid-cols-[160px_minmax(0,1fr)]'>
            <div className='space-y-2'>
              <Label htmlFor='audio-meta-anno-format'>格式</Label>
              <Select
                value={annotationFormat}
                onValueChange={(value) => setAnnotationFormat(value ?? 'text')}
              >
                <SelectTrigger id='audio-meta-anno-format' size='sm' className='w-full'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ANNOTATION_FORMAT_OPTIONS.map((format) => (
                    <SelectItem key={format} value={format}>
                      {format.toUpperCase()}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {annotationFormat === 'json' ? (
                <p className='text-muted-foreground text-xs'>
                  以 segments 表格形式编辑 JSON 标注
                </p>
              ) : (
                <p className='text-muted-foreground text-xs'>
                  {annotationFormat.toUpperCase()} 标注内容
                </p>
              )}
            </div>
            <Textarea
              aria-label='标注内容'
              value={annotationContent}
              onChange={(e) => setAnnotationContent(e.target.value)}
              rows={5}
              placeholder={
                annotationFormat === 'json'
                  ? '[{ "start": 0, "end": 1.2, "text": "..." }]'
                  : '标注内容'
              }
              className='font-mono text-xs'
            />
          </div>
        </div>

        <DialogFooter>
          <Button
            variant='outline'
            size='sm'
            onClick={() => props.onOpenChange(false)}
          >
            取消
          </Button>
          <Button size='sm' onClick={handleSave} disabled={pending}>
            {pending ? '保存中...' : (
              <>
                <Save aria-hidden='true' className='size-3.5' />
                保存
              </>
            )}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
