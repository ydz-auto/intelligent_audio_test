/**
 * 上传音频弹窗（§6.16；Dialog sm:max-w-2xl）。
 * 拖放区 + 文件列表 + 目标文件夹配置 + 音频类型自动识别 + 文件命名与冲突 + 上传选项
 * （UploadOptions 复用）+ 主钮「开始上传」→ 入队上传任务（audio-upload-store，§5.4 进度卡）。
 */
import { FileAudio, FileText, FolderOpen, HardDriveUpload, UploadCloud } from 'lucide-react'
import { useMemo, useRef, useState } from 'react'
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
import { Switch } from '@/components/ui/switch'
import { cn } from '@/lib/utils'
import { UploadOptions } from '@/features/audio-import/components/modals/upload-options'
import { useAudioUploadStore } from '@/infrastructure/stores/audio-upload-store'
import { formatFileSize } from '@/features/audio-import/lib/format'

export type AudioUploadDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const FOLDER_CONFIG_OPTIONS = [
  { value: 'select', label: '选择或创建目标文件夹' },
  { value: 'auto', label: '按音频类型自动分类' },
] as const

const NAMING_OPTIONS = [
  { value: 'auto', label: '自动生成文件名' },
  { value: 'keep', label: '保留原始文件名' },
] as const

const CONFLICT_OPTIONS = [
  { value: 'rename', label: '自动重命名冲突文件' },
  { value: 'overwrite', label: '覆盖冲突文件' },
  { value: 'skip', label: '跳过冲突文件' },
] as const

const ACCEPTED_AUDIO = '.wav,.mp3,.m4a,.flac,.aac,.ogg'

export function AudioUploadDialog(props: AudioUploadDialogProps) {
  const enqueueTask = useAudioUploadStore((s) => s.enqueueTask)
  const [dragging, setDragging] = useState(false)
  const [fileNames, setFileNames] = useState<string[]>([])
  const [audioType, setAudioType] = useState('dry')
  const [generateTestCase, setGenerateTestCase] = useState(false)
  const [algorithmType, setAlgorithmType] = useState('asr-v3')
  const [testTypes, setTestTypes] = useState<string[]>(['e2e'])
  const [playbackDevice, setPlaybackDevice] = useState('1')
  const [defaultSpl, setDefaultSpl] = useState(65)
  const [caseGroup, setCaseGroup] = useState('folder')
  const [customGroupName, setCustomGroupName] = useState('')
  const [inheritTags, setInheritTags] = useState(true)
  const [folderConfig, setFolderConfig] = useState('select')
  const [naming, setNaming] = useState('keep')
  const [conflict, setConflict] = useState('rename')
  const fileRef = useRef<HTMLInputElement | null>(null)

  const stats = useMemo(() => {
    const audioCount = fileNames.filter((name) => ACCEPTED_AUDIO.split(',').some((ext) => name.toLowerCase().endsWith(ext))).length
    const textCount = fileNames.filter((name) => /\.(json|jsonl|rttm|stm|txt)$/i.test(name)).length
    return {
      audioCount,
      textCount,
      totalSize: fileNames.length * 2_400_000,
      otherCount: Math.max(0, fileNames.length - audioCount - textCount),
    }
  }, [fileNames])

  const handleFiles = (files: FileList | null) => {
    if (!files) return
    const names = Array.from(files).map((file) => file.name)
    setFileNames((prev) => [...prev, ...names])
  }

  const handleStartUpload = () => {
    if (fileNames.length === 0) {
      toast.info('请先选择需要上传的文件')
      return
    }
    const audioNames = fileNames.filter((name) =>
      ACCEPTED_AUDIO.split(',').some((ext) => name.toLowerCase().endsWith(ext))
    )
    if (audioNames.length === 0) {
      toast.error('未选择任何音频文件')
      return
    }
    enqueueTask({
      name: `上传 ${audioNames.length} 个音频文件`,
      fileNames: audioNames,
    })
    if (generateTestCase) {
      toast.success(`已入队上传，上传完成后将自动生成 ${audioNames.length} 个测试用例`)
    } else {
      toast.success(`已入队上传 ${audioNames.length} 个音频文件`)
    }
    setFileNames([])
    props.onOpenChange(false)
  }

  return (
    <Dialog
      open={props.open}
      onOpenChange={(open) => {
        props.onOpenChange(open)
        if (!open) {
          setFileNames([])
          setDragging(false)
        }
      }}
    >
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>上传音频</DialogTitle>
          <DialogDescription>上传分片直传 + 按分组末文件自动生成测试用例</DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          {/* 拖放区 */}
          <div
            onDragOver={(e) => {
              e.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault()
              setDragging(false)
              handleFiles(e.dataTransfer.files)
            }}
            className={cn(
              'border-border/60 hover:bg-muted/30 flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-8 text-center transition-colors',
              dragging && 'border-primary bg-primary/[0.04]'
            )}
          >
            <UploadCloud aria-hidden='true' className='text-muted-foreground size-8' />
            <p className='text-sm'>
              {dragging ? '释放文件以上传' : '拖拽文件到此处或点击选择文件'}
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
              accept={`${ACCEPTED_AUDIO},.json,.jsonl,.rttm,.stm,.txt`}
              className='hidden'
              onChange={(e) => {
                handleFiles(e.target.files)
                e.target.value = ''
              }}
            />
          </div>

          {/* 已选统计三枚 */}
          {fileNames.length > 0 && (
            <div className='space-y-2'>
              <div className='text-muted-foreground flex items-center justify-between text-sm'>
                <span>已选择 {fileNames.length} 个文件</span>
                <Button variant='ghost' size='sm' className='h-7 px-2' onClick={() => setFileNames([])}>
                  重新选择
                </Button>
              </div>
              <div className='flex flex-wrap gap-2'>
                <span className='bg-muted/40 inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs'>
                  <FileAudio aria-hidden='true' className='size-3.5' />
                  音频文件 <span className='font-mono tabular-nums'>{stats.audioCount}</span>
                </span>
                <span className='bg-muted/40 inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs'>
                  <FileText aria-hidden='true' className='size-3.5' />
                  文本文件 <span className='font-mono tabular-nums'>{stats.textCount}</span>
                </span>
                <span className='bg-muted/40 inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs'>
                  <HardDriveUpload aria-hidden='true' className='size-3.5' />
                  总大小 <span className='font-mono tabular-nums'>{formatFileSize(stats.totalSize)}</span>
                </span>
              </div>
              <div className='text-muted-foreground max-h-28 space-y-0.5 overflow-y-auto font-mono text-xs'>
                {fileNames.map((name) => (
                  <p key={name} className='truncate'>{name}</p>
                ))}
              </div>
            </div>
          )}

          {/* 目标文件夹配置 */}
          <div className='grid grid-cols-1 gap-3 sm:grid-cols-2'>
            <div className='space-y-2'>
              <Label htmlFor='upload-folder-config'>目标文件夹</Label>
              <Select
                value={folderConfig}
                onValueChange={(value) => setFolderConfig(value ?? 'select')}
              >
                <SelectTrigger id='upload-folder-config' size='sm' className='w-full'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {FOLDER_CONFIG_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='space-y-2'>
              <Label htmlFor='upload-naming'>文件命名</Label>
              <Select value={naming} onValueChange={(value) => setNaming(value ?? 'keep')}>
                <SelectTrigger id='upload-naming' size='sm' className='w-full'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {NAMING_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className='space-y-2 sm:col-span-2'>
              <Label htmlFor='upload-conflict'>文件名冲突处理</Label>
              <Select value={conflict} onValueChange={(value) => setConflict(value ?? 'rename')}>
                <SelectTrigger id='upload-conflict' size='sm' className='w-full'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CONFLICT_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className='bg-muted/30 flex items-center justify-between gap-2 rounded-lg border px-3 py-2'>
            <div className='flex items-center gap-2 text-sm'>
              <FolderOpen aria-hidden='true' className='text-muted-foreground size-4' />
              按文件命名规则自动识别音频类型
            </div>
            <Switch checked aria-disabled />
          </div>

          {/* 上传选项 */}
          <UploadOptions
            audioType={audioType}
            onAudioTypeChange={setAudioType}
            generateTestCase={generateTestCase}
            onGenerateTestCaseChange={setGenerateTestCase}
            algorithmType={algorithmType}
            onAlgorithmTypeChange={setAlgorithmType}
            testTypes={testTypes}
            onTestTypesChange={setTestTypes}
            playbackDevice={playbackDevice}
            onPlaybackDeviceChange={setPlaybackDevice}
            defaultSpl={defaultSpl}
            onDefaultSplChange={setDefaultSpl}
            caseGroup={caseGroup}
            onCaseGroupChange={setCaseGroup}
            customGroupName={customGroupName}
            onCustomGroupNameChange={setCustomGroupName}
            inheritTags={inheritTags}
            onInheritTagsChange={setInheritTags}
          />
        </div>

        <DialogFooter>
          <Button variant='outline' size='sm' onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button size='sm' onClick={handleStartUpload}>
            开始上传
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
