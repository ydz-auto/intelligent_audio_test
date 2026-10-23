/**
 * 上传音频弹窗（§6.16；Dialog sm:max-w-2xl；INT-714 接线）。
 * 拖放区 + 文件列表 + 目标文件夹配置 + 音频类型自动识别 + 文件命名与冲突 + 上传选项
 * （UploadOptions 复用）+ 主钮「开始上传」→ 真实上传（init/register/chunk/merge，
 * audio-upload-api；生成测试用例由 merge 载荷 create_test_case 控制，
 * test_types 不传——后端默认 ['api'] 落库，模态窗不再显示用例类型选择）。
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
import { startRealAudioUpload, type PerFileUploadConfig } from '@/application/audio/useAudioUploadProcess'
import { DEFAULT_SPL } from '@/features/audio-import/constants'
import { parseAnnotationsForAudios } from '@/features/audio-import/lib/annotation'
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
  const [dragging, setDragging] = useState(false)
  const [files, setFiles] = useState<File[]>([])
  const [audioType, setAudioType] = useState('dry')
  const [generateTestCase, setGenerateTestCase] = useState(false)
  const [algorithmType, setAlgorithmType] = useState('')
  const [dimensionIds, setDimensionIds] = useState<number[]>([])
  const [playbackDevice, setPlaybackDevice] = useState('')
  const [defaultSpl, setDefaultSpl] = useState(DEFAULT_SPL)
  const [caseGroup, setCaseGroup] = useState('folder')
  const [customGroupName, setCustomGroupName] = useState('')
  const [tags, setTags] = useState('')
  const [inheritTags, setInheritTags] = useState(true)
  const [folderConfig, setFolderConfig] = useState('select')
  const [naming, setNaming] = useState('keep')
  const [conflict, setConflict] = useState('rename')
  const [uploading, setUploading] = useState(false)
  const fileRef = useRef<HTMLInputElement | null>(null)

  const stats = useMemo(() => {
    const audioCount = files.filter((f) => ACCEPTED_AUDIO.split(',').some((ext) => f.name.toLowerCase().endsWith(ext))).length
    const textCount = files.filter((f) => /\.(json|jsonl|rttm|stm|txt)$/i.test(f.name)).length
    return {
      audioCount,
      textCount,
      totalSize: files.reduce((sum, f) => sum + f.size, 0),
      otherCount: Math.max(0, files.length - audioCount - textCount),
    }
  }, [files])

  const handleFiles = (incoming: FileList | null) => {
    if (!incoming) return
    setFiles((prev) => [...prev, ...Array.from(incoming)])
  }

  const handleStartUpload = async () => {
    if (files.length === 0) {
      toast.info('请先选择需要上传的文件')
      return
    }
    const audioFiles = files.filter((f) =>
      ACCEPTED_AUDIO.split(',').some((ext) => f.name.toLowerCase().endsWith(ext))
    )
    if (audioFiles.length === 0) {
      toast.error('未选择任何音频文件')
      return
    }
    setUploading(true)
    try {
      // 标注文件（json/jsonl/rttm/stm/txt）按文件名匹配音频解析；标注代码取上传算法类型随 merge 落库
      const perFileAnnotations = await parseAnnotationsForAudios(
        files,
        audioFiles,
        algorithmType || undefined
      )
      const perFile: PerFileUploadConfig[] = audioFiles.map((f, idx) => ({
        groupName:
          caseGroup === 'custom' && customGroupName.trim()
            ? customGroupName.trim()
            : caseGroup === 'folder'
              ? f.name.replace(/\.[^.]+$/, '')
              : undefined,
        annotations: perFileAnnotations[idx],
      }))
      // 真实上传 + 生成测试用例（merge 载荷 create_test_case 控制；test_types 不传，后端默认 ['api']）
      const result = await startRealAudioUpload(audioFiles, {
        createTestCase: generateTestCase,
        algorithmType: algorithmType || null,
        algorithmParams: [],
        dimensions: dimensionIds,
        playbackDeviceId: playbackDevice ? Number(playbackDevice) : null,
        spl: defaultSpl,
        noiseAudioId: null,
        noiseSpl: 60,
        inheritTags,
        groupName: undefined,
        tags: tags
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
        audioType,
      }, perFile)
      if (result.testCaseCount > 0) {
        toast.success(
          `上传完成：成功 ${result.successCount} 个，生成 ${result.testCaseCount} 个测试用例`
        )
      } else if (result.failedCount === 0) {
        toast.success(`上传完成：成功 ${result.successCount} 个音频文件`)
      } else {
        toast.error(`上传完成：成功 ${result.successCount} 个，失败 ${result.failedCount} 个`)
      }
      if (result.failed.length > 0) {
        result.failed.forEach((f) => toast.error(`${f.name}：${f.error}`))
      }
      setFiles([])
      props.onOpenChange(false)
    } catch (err) {
      toast.error(`上传失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setUploading(false)
    }
  }

  return (
    <Dialog
      open={props.open}
      onOpenChange={(open) => {
        props.onOpenChange(open)
        if (!open) {
          setFiles([])
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
          {files.length > 0 && (
            <div className='space-y-2'>
              <div className='text-muted-foreground flex items-center justify-between text-sm'>
                <span>已选择 {files.length} 个文件</span>
                <Button variant='ghost' size='sm' className='h-7 px-2' onClick={() => setFiles([])}>
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
                {files.map((file) => (
                  <p key={file.name + file.size} className='truncate'>{file.name}</p>
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
                  <SelectValue placeholder='选择或创建目标文件夹'>
                    {FOLDER_CONFIG_OPTIONS.find((o) => o.value === folderConfig)?.label ?? ''}
                  </SelectValue>
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
                  <SelectValue placeholder='保留原始文件名'>
                    {NAMING_OPTIONS.find((o) => o.value === naming)?.label ?? ''}
                  </SelectValue>
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
                  <SelectValue placeholder='自动重命名冲突文件'>
                    {CONFLICT_OPTIONS.find((o) => o.value === conflict)?.label ?? ''}
                  </SelectValue>
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
            dimensionIds={dimensionIds}
            onDimensionIdsChange={setDimensionIds}
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
            tags={tags}
            onTagsChange={setTags}
          />
        </div>

        <DialogFooter>
          <Button variant='outline' size='sm' onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button size='sm' onClick={handleStartUpload} disabled={uploading}>
            {uploading ? '上传中…' : '开始上传'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
