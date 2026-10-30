/**
 * 批量从文件夹导入弹窗（§6.17；Dialog sm:max-w-2xl）。
 * 拖放/选择文件夹（webkitdirectory + 递归子文件夹 + 按文件类型筛选）+ 真实统计四枚
 * + 文件夹分组设置（custom 时逐文件夹自定义分组名）+ 复用 UploadOptions
 * + 主钮「开始导入」→ 走真实上传（startRealAudioUpload，与上传弹窗同链路）。
 * V9.7.10 FolderImportModal 对位：per-folder 分组名（root/folder/custom 三型）与标注文件
 * 解析（json/jsonl/rttm/stm/txt）随 merge 载荷逐文件落库；标注代码取上传时选择的算法类型
 * （INT-1028 口径：导入窗口不选标注代码）。
 * §5.7.6 恢复多轮导入（INT-1613）：随附的 `.json` 用例文件 = 一个用例分组（其 `rounds`
 * 数组即该用例轮数），组内**最后一个待处理文件** merge 时才建用例、整组 rounds 一次提交；
 * 无 JSON 用例文件时按最子级文件夹分组并推断单轮（1 音频 1 轮 / 多音频 1 轮多音频）。
 */
import { FolderInput, FolderTree } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
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
import { useUploadRoundScope } from '@/application/audio/useUploadRoundScope'
import type { AudioTagSource, UploadRoundConfig } from '@/infrastructure/api/audio-upload-api'
import { DEFAULT_SPL, DEFAULT_TAG_SOURCE } from '@/features/audio-import/constants'
import { parseAnnotationsForAudios } from '@/features/audio-import/lib/annotation'
import {
  buildAudioImportGroups,
  buildCaseGroups,
  leafFolderName,
  relativePathOf,
  type CaseGroup,
} from '@/features/audio-import/lib/case-rounds'
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

/** JSON 用例文件扩展名（文件夹导入：每个 .json 作为一个用例分组的候选，§5.7.6） */
const CASE_JSON_EXTS = ['.json']

/** §5.7.2 文件夹导入未附 JSON 用例时的 N=1 收敛 Tooltip（与上传窗同一收敛规则，文案按本窗语义改写） */
const SINGLE_ROUND_HINT =
  '本次导入未附多轮 JSON 用例文件，生成的用例为单轮；多轮用例请在导入时随附 JSON 用例文件'

export function AudioFolderImportDialog(props: AudioFolderImportDialogProps) {
  const [formatFilter, setFormatFilter] = useState('all')
  const [recursive, setRecursive] = useState(true)
  const [files, setFiles] = useState<File[]>([])
  const [groupNames, setGroupNames] = useState<Record<string, string>>({})
  const [audioType, setAudioType] = useState('dry')
  const [generateTestCase, setGenerateTestCase] = useState(false)
  const [algorithmType, setAlgorithmType] = useState('')
  const [defaultSpl, setDefaultSpl] = useState(DEFAULT_SPL)
  const [caseGroup, setCaseGroup] = useState('folder')
  const [customGroupName, setCustomGroupName] = useState('')
  const [tags, setTags] = useState('')
  const [tagSource, setTagSource] = useState<AudioTagSource>(DEFAULT_TAG_SOURCE)
  const [inheritTags, setInheritTags] = useState(true)
  const [importing, setImporting] = useState(false)
  const [caseGroups, setCaseGroups] = useState<Map<string, CaseGroup>>(new Map())
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
    const names = Array.from(new Set(files.map(leafFolderName)))
    return recursive || files.length === 0 ? names : [leafFolderName(files[0])]
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
      new Set(Array.from(incoming).map(leafFolderName))
    )
    setGroupNames((prev) => {
      const next = { ...prev }
      for (const name of names) if (!(name in next)) next[name] = name
      return next
    })
  }

  // JSON 用例文件（§5.7.6）：选择文件后即解析，供 §5.7.2 轮次基数 N（各分组 rounds 最大长度）
  const jsonFiles = useMemo(
    () =>
      files.filter((f) => CASE_JSON_EXTS.some((ext) => f.name.toLowerCase().endsWith(ext))),
    [files]
  )
  useEffect(() => {
    let cancelled = false
    if (!generateTestCase || jsonFiles.length === 0) {
      setCaseGroups(new Map())
      return
    }
    void buildCaseGroups(jsonFiles).then((groups) => {
      if (!cancelled) setCaseGroups(groups)
    })
    return () => {
      cancelled = true
    }
  }, [jsonFiles, generateTestCase])

  const roundCount = useMemo(() => {
    let max = 1
    for (const group of caseGroups.values()) {
      max = Math.max(max, group.rounds.length)
    }
    return max
  }, [caseGroups])

  // 改选文件夹 / 改文件集时轮次选择重置为默认（§5.7.2）
  const fileSignature = useMemo(() => files.map(relativePathOf).sort().join('|'), [files])
  const roundScope = useUploadRoundScope({
    roundCount,
    resetKey: `${fileSignature}#${generateTestCase}`,
  })

  /** 关闭统一出口：标签来源复位为默认「两者都要」（重开不残留上次选择，§B.1）。
   *  取消 / 成功后自动关闭 / Esc / 点遮罩 都走这里——页脚「取消」直连 props.onOpenChange
   *  会绕过 Dialog 的 onOpenChange，故单列此函数。 */
  const closeDialog = () => {
    setTagSource(DEFAULT_TAG_SOURCE)
    props.onOpenChange(false)
  }

  const handleStartImport = async () => {
    if (audioFiles.length === 0) {
      toast.info('未选择任何音频文件，请先选择文件夹')
      return
    }
    setImporting(true)
    try {
      // JSON 用例文件（§5.7.6）：每个 .json 解析为一个用例分组，其 rounds 数组即该用例轮数。
      // 仅在生成测试用例时解析；解析失败的 JSON 不参与分组（全失败时提示，避免静默按文件夹推断）。
      const jsonFiles = files.filter((f) =>
        CASE_JSON_EXTS.some((ext) => f.name.toLowerCase().endsWith(ext))
      )
      const caseGroups = generateTestCase
        ? await buildCaseGroups(jsonFiles)
        : new Map<string, CaseGroup>()
      if (generateTestCase && jsonFiles.length > 0 && caseGroups.size === 0) {
        toast.error(
          `检测到 ${jsonFiles.length} 个 JSON 用例文件，但全部解析失败（请检查 JSON 格式），本次不会按 JSON 生成用例分组`
        )
      }
      // 分组轮次：JSON rounds 优先，否则按最子级文件夹推断（1 音频 1 轮 / 多音频 1 轮多音频）
      const importGroups = buildAudioImportGroups(audioFiles, caseGroups)
      const groupOfFile = new Map<
        File,
        { rounds: UploadRoundConfig[]; tags: string[]; isGroupFinalMerge: boolean }
      >()
      for (const group of importGroups) {
        group.files.forEach((file, index) => {
          groupOfFile.set(file, {
            rounds: group.rounds,
            // 分组 JSON 顶层 tags（INT-1979；按标签来源档位与手填标签组装后随 merge 落库）
            tags: group.tags,
            // 组内最后一个待处理文件才建用例（前序文件只入库）
            isGroupFinalMerge: index === group.files.length - 1,
          })
        })
      }
      // 已识别为用例分组的 JSON 不再当标注文件解析（V9.7.10 nonTestCaseAnnotationFiles 同口径）
      const caseJsonFiles = new Set(
        Array.from(caseGroups.values()).map((group) => group.fileName)
      )
      const annotationSourceFiles = files.filter(
        (f) => !caseJsonFiles.has(relativePathOf(f))
      )
      // 标注文件（jsonl/rttm/stm/txt）按文件名匹配音频解析；标注代码取导入算法类型随 merge 落库
      const perFileAnnotations = await parseAnnotationsForAudios(
        annotationSourceFiles,
        audioFiles,
        algorithmType || undefined
      )
      // per-folder 分组名（V9.7.10 groupNameType 对位：root=根目录 / folder=最子级文件夹 / custom=逐文件夹自定义名）
      const perFile: PerFileUploadConfig[] = audioFiles.map((f, idx) => {
        const folder = leafFolderName(f)
        const group = groupOfFile.get(f)
        return {
          groupName:
            caseGroup === 'custom'
              ? (groupNames[folder]?.trim() || folder || undefined)
              : caseGroup === 'folder'
                ? (folder || undefined)
                : undefined,
          annotations: perFileAnnotations[idx],
          rounds: group?.rounds,
          tags: group?.tags,
          isGroupFinalMerge: group?.isGroupFinalMerge,
        }
      })
      const result = await startRealAudioUpload(audioFiles, {
        createTestCase: generateTestCase,
        algorithmType: algorithmType || null,
        algorithmParams: [],
        dimensions: roundScope.dimensionItems,
        multiDimensions: roundScope.multiDimensionItems,
        dimensionPlan: roundScope.dimensionPlan,
        devicePlan: roundScope.devicePlan,
        // 用例只关联逻辑音箱：devicePlan / defaultDeviceId 里的值均为逻辑音箱组 id
        playbackDeviceId: null,
        playbackSpeakerGroupId: roundScope.defaultDeviceId,
        spl: defaultSpl,
        noiseAudioId: null,
        noiseSpl: 60,
        inheritTags,
        groupName: undefined,
        tags: tags
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
        // 标签来源（INT-1979）：手填 tags 始终提交，分组 JSON tags 与路径解析按此档取舍
        tagSource,
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
      closeDialog()
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
        if (open) {
          props.onOpenChange(true)
          return
        }
        setFiles([])
        // 关闭即复位标签来源（重开回到默认「两者都要」，§B.1 不残留上次选择）
        closeDialog()
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
            roundCount={roundCount}
            roundScope={roundScope}
            singleRoundHint={SINGLE_ROUND_HINT}
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
            tagSource={tagSource}
            onTagSourceChange={setTagSource}
          />
        </div>

        <DialogFooter>
          <Button
            variant='outline'
            size='sm'
            disabled={importing}
            onClick={closeDialog}
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
