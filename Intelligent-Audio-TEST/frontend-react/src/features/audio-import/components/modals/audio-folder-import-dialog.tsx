/**
 * 批量从文件夹导入弹窗（§6.17；Dialog sm:max-w-2xl）。
 * 拖放区（选择包含音频文件的文件夹 + 递归子文件夹导入 + 按文件类型筛选）
 * + 统计四枚 + 文件夹分组设置（逐文件夹自定义分组名）+ 复用 UploadOptions
 * + 标注代码 select。主钮「开始导入」（groupAudioFilesByLeafFolder 按最子级分组）。
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
import { useAudioUploadStore } from '@/infrastructure/stores/audio-upload-store'

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

const MOCK_FOLDERS = ['test_data/dry/中文', 'test_data/dry/外语', 'test_data/noise/环境']

export function AudioFolderImportDialog(props: AudioFolderImportDialogProps) {
  const enqueueTask = useAudioUploadStore((s) => s.enqueueTask)
  const [formatFilter, setFormatFilter] = useState('all')
  const [recursive, setRecursive] = useState(true)
  const [groupNames, setGroupNames] = useState<Record<string, string>>({})
  const [audioType, setAudioType] = useState('dry')
  const [generateTestCase, setGenerateTestCase] = useState(false)
  const [algorithmType, setAlgorithmType] = useState('')
  const [testTypes, setTestTypes] = useState<string[]>(['e2e'])
  const [apiDimensionIds, setApiDimensionIds] = useState<number[]>([])
  const [e2eDimensionIds, setE2eDimensionIds] = useState<number[]>([])
  const [playbackDevice, setPlaybackDevice] = useState('')
  const [defaultSpl, setDefaultSpl] = useState(65)
  const [caseGroup, setCaseGroup] = useState('folder')
  const [customGroupName, setCustomGroupName] = useState('')
  const [inheritTags, setInheritTags] = useState(true)
  const dirRef = useRef<HTMLInputElement | null>(null)

  const stats = useMemo(
    () => ({
      audioCount: 28,
      totalSize: 420_000_000,
      folderCount: recursive ? MOCK_FOLDERS.length + 1 : MOCK_FOLDERS.length,
      formats: formatFilter === 'all' ? 'WAV / MP3 / FLAC' : formatFilter,
    }),
    [formatFilter, recursive]
  )

  const handleStartImport = () => {
    enqueueTask({ name: `批量导入 ${stats.audioCount} 个音频文件`, fileNames: ['目录批量导入任务'] })
    toast.success(`已开始批量导入 ${stats.audioCount} 个音频文件`)
    props.onOpenChange(false)
  }

  return (
    <Dialog open={props.open} onOpenChange={props.onOpenChange}>
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
              <span className='text-muted-foreground text-xs'>webkitdirectory 演示</span>
            </div>
            <input
              ref={dirRef}
              type='file'
              multiple
              // 真实浏览器文件夹选择（webkitdirectory）；mock 阶段保留入口
              {...({ webkitdirectory: '', directory: '' } as Record<string, string>)}
              className='hidden'
            />
            <label className='flex items-center gap-2 text-xs'>
              <Switch checked={recursive} onCheckedChange={setRecursive} />
              递归导入子文件夹
            </label>
          </div>

          {/* 统计四枚 */}
          <div className='flex flex-wrap gap-2'>
            <span className='bg-muted/40 inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs'>
              音频文件数量 <span className='font-mono tabular-nums'>{stats.audioCount}</span>
            </span>
            <span className='bg-muted/40 inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs'>
              总大小 <span className='font-mono tabular-nums'>400.4 MB</span>
            </span>
            <span className='bg-muted/40 inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs'>
              文件夹数量 <span className='font-mono tabular-nums'>{stats.folderCount}</span>
            </span>
            <span className='bg-muted/40 inline-flex h-7 items-center gap-1.5 rounded-md px-2.5 text-xs'>
              支持的文件格式 <span className='font-mono tabular-nums'>{stats.formats}</span>
            </span>
          </div>

          <div className='space-y-2'>
            <Label htmlFor='folder-import-format'>按文件类型筛选</Label>
            <Select
              value={formatFilter}
              onValueChange={(value) => setFormatFilter(value ?? 'all')}
            >
              <SelectTrigger id='folder-import-format' size='sm' className='w-48'>
                <SelectValue />
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

          {/* 文件夹分组设置 */}
          <div className='space-y-2'>
            <div className='text-muted-foreground flex items-center gap-1.5 text-sm font-medium'>
              <FolderTree aria-hidden='true' className='size-3.5' />
              文件夹分组设置
            </div>
            <div className='space-y-2'>
              {MOCK_FOLDERS.map((folder) => (
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
                    placeholder={`为文件夹「${folder.split('/').pop()}」设置自定义分组名`}
                    className='h-8 flex-1 text-xs'
                  />
                </div>
              ))}
            </div>
          </div>

          <div className='space-y-2'>
            <Label htmlFor='folder-import-annotation'>标注代码</Label>
            <Select defaultValue=''>
              <SelectTrigger id='folder-import-annotation' size='sm' className='w-full'>
                <SelectValue placeholder='留空则使用 JSON 内 code/name 字段' />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value=''>留空</SelectItem>
                <SelectItem value='asr'>ASR 标注</SelectItem>
                <SelectItem value='wake'>唤醒词标注</SelectItem>
              </SelectContent>
            </Select>
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
            apiDimensionIds={apiDimensionIds}
            onApiDimensionIdsChange={setApiDimensionIds}
            e2eDimensionIds={e2eDimensionIds}
            onE2eDimensionIdsChange={setE2eDimensionIds}
          />
        </div>

        <DialogFooter>
          <Button variant='outline' size='sm' onClick={() => props.onOpenChange(false)}>
            取消
          </Button>
          <Button size='sm' onClick={handleStartImport}>
            开始导入
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
