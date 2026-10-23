/**
 * 批量从文件夹导入弹窗（§6.17；Dialog sm:max-w-2xl）。
 * 拖放/选择文件夹（webkitdirectory + 递归子文件夹 + 按文件类型筛选）+ 真实统计四枚
 * + 文件夹分组设置（custom 时逐文件夹自定义分组名）+ 复用 UploadOptions
 * + 主钮「开始导入」→ 走真实上传（startRealAudioUpload，与上传弹窗同链路）。
 * V9.7.10 FolderImportModal 对位：per-folder 分组名（root/folder/custom 三型）与标注文件
 * 解析（json/jsonl/rttm/stm/txt）随 merge 载荷逐文件落库；标注代码取上传时选择的算法类型
 * （INT-1028 口径：导入窗口不选标注代码）。JSON 用例分组策略（testCaseStrategy
 * buildTestCaseGroups：Rounds/Flat/TxtArray 多轮用例）本卡未实现，显式标缺口（见交付评论）。
 */
import { FolderInput, FolderTree } from 'lucide-react'
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
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { UploadOptions } from '@/features/audio-import/components/modals/upload-options'
import { startRealAudioUpload, type PerFileUploadConfig } from '@/application/audio/useAudioUploadProcess'
import { DEFAULT_SPL } from '@/features/audio-import/constants'
import { parseAnnotationsForAudios } from '@/features/audio-import/lib/annotation'
import { formatFileSize } from '@/features/audio-import/lib/format'

export type AudioFolderImportDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
}

const FORMAT_FILTER_OPTIONS = [
  { value: 'all', label: '全部格式' },
  { value: 'MP3', label: 'MP3' },
  { value: 'WAV', label: 'WAV' },
  { value: 'FLAC', label: 'FLAC' },
  { value: 'AAC', label: 'AAC' },
  { value: 'M4A', label: 'M4A' },
] as const

/** 支持的音频扩展名（§6.17 supportedFormats 对位；目录选择后按此过滤） */
const AUDIO_EXTS = ['.wav', '.mp3', '.m4a', '.flac', '.aac', '.ogg']

/** 取文件所在的最子级文件夹名（V9.7.10 getLeafFolderName 对位：webkitRelativePath 倒数第二段；
 *  无文件夹结构时按文件名去扩展名回退） */
function folderNameOf(file: File): string {
  const rel = file.webkitRelativePath || ''
  if (rel) {
    const parts = rel.split('/').filter(Boolean)
    if (parts.length >= 2) return parts[parts.length - 2] ?? ''
  }
  return file.name.replace(/\.[^.]+$/, '')
}

export function AudioFolderImportDialog(props: AudioFolderImportDialogProps) {
  const [formatFilter, setFormatFilter] = useState('all')
  const [recursive, setRecursive] = useState(true)
  const [files, setFiles] = useState<File[]>([])
  const [groupNames, setGroupNames] = useState<Record<string, string>>({})
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
  const [importing, setImporting] = useState(false)
  const dirRef = useRef<HTMLInputElement | null>(null)

  const audioFiles = useMemo(() => {
    const ext = formatFilter === 'all' ? null : `.${formatFilter.toLowerCase()}`
    return files.filter(
      (f) =>
        AUDIO_EXTS.some((e) => f.name.toLowerCase().endsWith(e)) &&
        (ext ? f.name.toLowerCase().endsWith(ext) : true)
    )
  }, [files, formatFilter])

  const folderNames = useMemo(() => {
    const names = Array.from(new Set(files.map(folderNameOf)))
    return recursive || files.length === 0 ? names : [folderNameOf(files[0])]
  }, [files, recursive])

  const stats = useMemo(() => {
    const totalSize = audioFiles.reduce((sum, f) => sum + f.size, 0)
    const formats = Array.from(
      new Set(audioFiles.map((f) => f.name.split('.').pop()?.toUpperCase() ?? ''))
    ).filter(Boolean)
    return {
      audioCount: audioFiles.length,
      totalSize,
      folderCount: folderNames.length,
      formats: formats.length > 0 ? formats.join(' / ') : '—',
    }
  }, [audioFiles, folderNames])

  const handleDirChange = (incoming: FileList | null) => {
    if (!incoming) return
    setFiles(Array.from(incoming))
    // 为每个叶子文件夹预填分组名（V9.7.10 folderGroupNames 默认 folder→folder）
    const names = Array.from(
      new Set(Array.from(incoming).map(folderNameOf))
    )
    setGroupNames((prev) => {
      const next = { ...prev }
      for (const name of names) if (!(name in next)) next[name] = name
      return next
    })
  }

  const handleStartImport = async () => {
    if (audioFiles.length === 0) {
      toast.info('未选择任何音频文件，请先选择文件夹')
      return
    }
    setImporting(true)
    try {
      // 标注文件（json/jsonl/rttm/stm/txt）按文件名匹配音频解析；标注代码取导入算法类型随 merge 落库
      const perFileAnnotations = await parseAnnotationsForAudios(
        files,
        audioFiles,
        algorithmType || undefined
      )
      // per-folder 分组名（V9.7.10 groupNameType 对位：root=根目录 / folder=最子级文件夹 / custom=逐文件夹自定义名）
      const perFile: PerFileUploadConfig[] = audioFiles.map((f, idx) => {
        const folder = folderNameOf(f)
        return {
          groupName:
            caseGroup === 'custom'
              ? (groupNames[folder]?.trim() || folder || undefined)
              : caseGroup === 'folder'
                ? (folder || undefined)
                : undefined,
          annotations: perFileAnnotations[idx],
        }
      })
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
          `导入完成：成功 ${result.successCount} 个，生成 ${result.testCaseCount} 个测试用例`
        )
      } else if (result.failedCount === 0) {
        toast.success(`导入完成：成功 ${result.successCount} 个音频文件`)
      } else {
        toast.error(`导入完成：成功 ${result.successCount} 个，失败 ${result.failedCount} 个`)
      }
      result.failed.forEach((f) => toast.error(`${f.name}：${f.error}`))
      setFiles([])
      props.onOpenChange(false)
    } catch (err) {
      toast.error(`导入失败：${err instanceof Error ? err.message : String(err)}`)
    } finally {
      setImporting(false)
    }
  }

  return (
    <Dialog
      open={props.open}
      onOpenChange={(open) => {
        props.onOpenChange(open)
        if (!open) setFiles([])
      }}
    >
      <DialogContent className='sm:max-w-2xl'>
        <DialogHeader>
          <DialogTitle>批量从文件夹导入</DialogTitle>
          <DialogDescription>选择包含音频文件的文件夹进行批量导入</DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          {/* 文件夹选择区 */}
          <div className='border-border/60 hover:bg-muted/30 flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 text-center transition-colors'>
            <FolderInput aria-hidden='true' className='text-muted-foreground size-8' />
            <p className='text-sm'>选择包含音频文件的文件夹进行批量导入</p>
            <div className='flex items-center gap-2'>
              <Button
                variant='outline'
                size='sm'
                type='button'
                onClick={() => dirRef.current?.click()}
              >
                选择文件夹
              </Button>
              {files.length > 0 && (
                <span className='text-muted-foreground text-xs'>
                  已选 {files.length} 个文件
                </span>
              )}
            </div>
            <input
              ref={dirRef}
              type='file'
              multiple
              {...({ webkitdirectory: '', directory: '' } as Record<string, string>)}
              className='hidden'
              onChange={(e) => {
                handleDirChange(e.target.files)
                e.target.value = ''
              }}
            />
            <label className='flex items-center gap-2 text-xs'>
              <Switch checked={recursive} onCheckedChange={setRecursive} />
              递归导入子文件夹
            </label>
          </div>

          {/* 统计四枚（真实数据） */}
          {audioFiles.length > 0 && (
            <div className='flex flex-wrap gap-2'>
              <span className='bg-muted/40 inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs'>
                音频文件数量 <span className='font-mono tabular-nums'>{stats.audioCount}</span>
              </span>
              <span className='bg-muted/40 inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs'>
                总大小 <span className='font-mono tabular-nums'>{formatFileSize(stats.totalSize)}</span>
              </span>
              <span className='bg-muted/40 inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs'>
                文件夹数量 <span className='font-mono tabular-nums'>{stats.folderCount}</span>
              </span>
              <span className='bg-muted/40 inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs'>
                支持的文件格式 <span className='font-mono tabular-nums'>{stats.formats}</span>
              </span>
            </div>
          )}

          <div className='space-y-2'>
            <Label htmlFor='folder-import-format'>按文件类型筛选</Label>
            <Select
              value={formatFilter}
              onValueChange={(value) => setFormatFilter(value ?? 'all')}
            >
              <SelectTrigger id='folder-import-format' size='sm' className='w-48'>
                <SelectValue placeholder='全部格式'>
                  {FORMAT_FILTER_OPTIONS.find((o) => o.value === formatFilter)?.label ?? ''}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {FORMAT_FILTER_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* 文件夹分组设置（V9.7.10：custom 分组时逐文件夹自定义分组名） */}
          {generateTestCase && caseGroup === 'custom' && folderNames.length > 0 && (
            <div className='space-y-2'>
              <div className='text-muted-foreground flex items-center gap-1.5 text-sm font-medium'>
                <FolderTree aria-hidden='true' className='size-3.5' />
                文件夹分组设置
              </div>
              <div className='space-y-2'>
                {folderNames.map((folder) => (
                  <div key={folder} className='flex items-center gap-2'>
                    <span className='text-muted-foreground w-40 truncate font-mono text-xs'>
                      {folder}
                    </span>
                    <Input
                      aria-label={`为文件夹 ${folder} 设置自定义分组名`}
                      value={groupNames[folder] ?? ''}
                      onChange={(e) =>
                        setGroupNames((prev) => ({ ...prev, [folder]: e.target.value }))
                      }
                      placeholder={`为文件夹「${folder}」设置自定义分组名`}
                      className='h-8 flex-1 text-xs'
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

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
          <Button
            variant='outline'
            size='sm'
            disabled={importing}
            onClick={() => props.onOpenChange(false)}
          >
            取消
          </Button>
          <Button size='sm' onClick={handleStartImport} disabled={importing}>
            {importing ? '导入中...' : '开始导入'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
