/**
 * 音频选择子弹窗（11_用例域.md §5.1 末段，Dialog sm:max-w-4xl「选择音频文件」）。
 * 用例编辑/批量噪声共用：搜索/标签筛选/文件夹树/多选/分页 + 头部「上传音频/批量从文件夹导入」入口
 * + 底部「当前页 {n} 个音频 ({总时长})｜已选择 {n} 个 ({时长})｜取消｜确认选择」。
 * mode='single'（audioType='noise'）单选形态供全局噪声/声纹/干扰人音频选择复用。
 * 接线：真实 GET /audios（infrastructure/api/audioLibraryApi，经统一 client.ts），
 * 无 mock 双口径；文件夹树由已加载音频 filePath 派生（后端无独立 folder-tree 端点，探测 422）。
 */
import { AudioWaveform, Folder, FolderOpen, Search, UploadCloud } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import type { AudioAsset } from '@/domain/models/audio'
import {
  fetchAudioLibrary,
  type AudioLibraryListResult,
} from '@/infrastructure/api/audioLibraryApi'
import { AudioUploadDialog } from '@/features/audio-import/components/modals/audio-upload-dialog'
import { AudioFolderImportDialog } from '@/features/audio-import/components/modals/audio-folder-import-dialog'

/** 每页条数（客户端分页；列表经 per_page=200 一次拉大页，参照用例列表 LIST_PAGE_SIZE 口径） */
const PAGE_SIZE = 12
const FETCH_SIZE = 200

const formatDuration = (s: number | null | undefined) => {
  if (s == null) return '—'
  const sec = Math.round(s)
  return sec < 60 ? `${sec}s` : sec % 60 === 0 ? `${sec / 60}m` : `${Math.floor(sec / 60)}m ${sec % 60}s`
}

/** 时长累加（秒 → 摘要；<1m 秒 / 否则 m s） */
function summarizeDuration(items: AudioAsset[]): string {
  const total = items.reduce((sum, a) => sum + (a.duration ?? 0), 0)
  if (total <= 0) return '0s'
  return formatDuration(total)
}

/** 由 filePath 派生顶层文件夹（depth 1；文件在根无文件夹则归「未归档」） */
function deriveFolders(items: AudioAsset[]): string[] {
  const seen = new Set<string>()
  for (const item of items) {
    const raw = item.filePath
    if (!raw) continue
    // oss://audios/direct/sample/xxx.wav → 取目录段
    const withoutScheme = raw.replace(/^[a-z]+:\/\//i, '').split('/')
    const dir = withoutScheme.slice(0, -1).join('/')
    if (dir) seen.add(dir)
  }
  return [...seen].sort()
}

export interface AudioSelectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 单选形态（audioType='noise' 全局噪声/声纹/干扰人复用）；缺省多选 */
  mode?: 'multi' | 'single'
  /** 音频类型过滤（单选噪声形态传 'noise'；缺省全量） */
  audioType?: 'dry' | 'noise' | 'prompt' | 'mixed'
  /** 已选初始值（编辑回填；单选态取首个。仅按 id 高亮，完整对象由已加载列表解析） */
  initialSelected?: Array<{ id: number | string; name?: string }>
  /** 确认回调（多选=数组；单选=单元素数组） */
  onConfirm: (selected: AudioAsset[]) => void
  title?: string
}

export function AudioSelectDialog({
  open,
  onOpenChange,
  mode = 'multi',
  audioType,
  initialSelected = [],
  onConfirm,
  title = '选择音频文件',
}: AudioSelectDialogProps) {
  const isSingle = mode === 'single'
  const [keyword, setKeyword] = useState('')
  const [debouncedKeyword, setDebouncedKeyword] = useState('')
  const [selectedTags, setSelectedTags] = useState<Set<string>>(new Set())
  const [activeFolder, setActiveFolder] = useState<string | null>(null)
  const [page, setPage] = useState(1)
  const [data, setData] = useState<AudioLibraryListResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [uploadOpen, setUploadOpen] = useState(false)
  const [folderImportOpen, setFolderImportOpen] = useState(false)

  // 打开时回填已选（编辑态）；仅在 open 从 false→true 的转换时重置（initialSelected 由调用方
  // 每次渲染新建数组，直接入 deps 会造成「重置→渲染→重置」死循环——Maximum update depth）
  const wasOpen = useRef(false)
  useEffect(() => {
    if (open && !wasOpen.current) {
      setSelected(new Set(initialSelected.map((a) => Number(a.id))))
      setKeyword('')
      setDebouncedKeyword('')
      setSelectedTags(new Set())
      setActiveFolder(null)
      setPage(1)
    }
    wasOpen.current = open
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // 搜索防抖（真实接口 keyword 参数；320ms）
  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedKeyword(keyword.trim()), 320)
    return () => window.clearTimeout(t)
  }, [keyword])

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchAudioLibrary({
        keyword: debouncedKeyword || undefined,
        audioType,
        page: 1,
        perPage: FETCH_SIZE,
      })
      setData(result)
      setPage(1)
    } catch (err) {
      setError(err instanceof Error ? err.message : '音频列表加载失败')
    } finally {
      setLoading(false)
    }
  }, [debouncedKeyword, audioType])

  useEffect(() => {
    if (open) void load()
  }, [open, load])

  const items = useMemo(() => data?.items ?? [], [data])
  const folders = useMemo(() => deriveFolders(items), [items])
  const allTags = useMemo(
    () => [...new Set(items.flatMap((a) => a.tags ?? []))].sort(),
    [items]
  )

  /** 客户端过滤：标签 + 文件夹（搜索已走后端 keyword） */
  const filtered = useMemo(() => {
    return items.filter((a) => {
      if (selectedTags.size > 0 && !(a.tags ?? []).some((t) => selectedTags.has(t)))
        return false
      if (activeFolder) {
        const raw = a.filePath ?? ''
        const withoutScheme = raw.replace(/^[a-z]+:\/\//i, '').split('/')
        const dir = withoutScheme.slice(0, -1).join('/')
        if (dir !== activeFolder) return false
      }
      return true
    })
  }, [items, selectedTags, activeFolder])

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE))
  const safePage = Math.min(page, pageCount)
  const pageItems = useMemo(
    () => filtered.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE),
    [filtered, safePage]
  )

  const toggleTag = (tag: string) =>
    setSelectedTags((prev) => {
      const next = new Set(prev)
      if (next.has(tag)) next.delete(tag)
      else next.add(tag)
      return next
    })

  const toggleSelect = (audio: AudioAsset) => {
    const id = Number(audio.id)
    if (isSingle) {
      setSelected(new Set([id]))
      return
    }
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const selectedAudios = useMemo(
    () => (data?.items ?? []).filter((a) => selected.has(Number(a.id))),
    [data, selected]
  )

  const handleConfirm = () => {
    onConfirm(selectedAudios)
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-4xl'>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>
            {isSingle
              ? '选择一个噪声音频文件作为全局背景噪声'
              : '搜索并勾选音频文件，用于用例轮次或批量噪声配置'}
          </DialogDescription>
        </DialogHeader>

        {/* 头部：搜索 / 标签筛选 / 上传入口 */}
        <div className='space-y-2'>
          <div className='flex flex-wrap items-center gap-2'>
            <div className='relative min-w-0 flex-1'>
              <Search
                aria-hidden='true'
                className='text-muted-foreground absolute top-1/2 left-2.5 size-4 -translate-y-1/2'
              />
              <Input
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder='搜索音频文件名或描述'
                aria-label='搜索音频文件名或描述'
                className='h-8 ps-8'
              />
            </div>
            <Button
              type='button'
              variant='outline'
              size='sm'
              className='h-8 gap-1.5'
              onClick={() => setUploadOpen(true)}
            >
              <UploadCloud aria-hidden='true' className='size-3.5' />
              上传音频
            </Button>
            <Button
              type='button'
              variant='outline'
              size='sm'
              className='h-8 gap-1.5'
              onClick={() => setFolderImportOpen(true)}
            >
              <FolderOpen aria-hidden='true' className='size-3.5' />
              批量从文件夹导入
            </Button>
          </div>

          {/* 标签筛选 chips（当前页已加载集去重；无标签时不渲染） */}
          {allTags.length > 0 && (
            <div className='flex flex-wrap items-center gap-1.5'>
              <span className='text-muted-foreground shrink-0 text-xs'>标签：</span>
              {allTags.map((tag) => {
                const active = selectedTags.has(tag)
                return (
                  <button
                    key={tag}
                    type='button'
                    aria-pressed={active}
                    onClick={() => toggleTag(tag)}
                    className={cn(
                      'flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs transition-colors',
                      active
                        ? 'bg-primary/10 border-primary/40 text-primary font-medium'
                        : 'hover:bg-accent border-border text-muted-foreground'
                    )}
                  >
                    {tag}
                  </button>
                )
              })}
            </div>
          )}
        </div>

        {/* 主体：文件夹树 + 音频列表 */}
        <div className='flex min-h-80 flex-col gap-3 sm:flex-row'>
          {/* 文件夹树（filePath 派生；后端无独立 folder-tree 端点） */}
          <div className='border-border/60 w-full shrink-0 rounded-lg border p-2 sm:w-44'>
            <p className='text-muted-foreground px-1 pb-1 text-xs font-medium'>文件夹</p>
            <button
              type='button'
              onClick={() => setActiveFolder(null)}
              className={cn(
                'flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-start text-xs transition-colors',
                activeFolder === null
                  ? 'bg-primary/10 text-primary font-medium'
                  : 'hover:bg-accent text-muted-foreground'
              )}
            >
              <FolderOpen aria-hidden='true' className='size-3.5 shrink-0' />
              全部
            </button>
            <div className='mt-1 max-h-56 space-y-0.5 overflow-y-auto sm:max-h-64'>
              {folders.length === 0 && (
                <p className='text-muted-foreground/70 px-2 py-1 text-[11px]'>暂无文件夹</p>
              )}
              {folders.map((folder) => {
                const active = activeFolder === folder
                const count = items.filter((a) =>
                  (a.filePath ?? '').replace(/^[a-z]+:\/\//i, '').split('/').slice(0, -1).join('/') === folder
                ).length
                return (
                  <button
                    key={folder}
                    type='button'
                    onClick={() => setActiveFolder(active ? null : folder)}
                    className={cn(
                      'flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-start text-xs transition-colors',
                      active
                        ? 'bg-primary/10 text-primary font-medium'
                        : 'hover:bg-accent text-muted-foreground'
                    )}
                    title={folder}
                  >
                    <Folder aria-hidden='true' className='size-3.5 shrink-0' />
                    <span className='min-w-0 flex-1 truncate'>{folder}</span>
                    <span className='text-muted-foreground/60 font-mono text-[10px] tabular-nums'>
                      {count}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>

          {/* 音频列表 */}
          <div className='min-h-0 min-w-0 flex-1'>
            {loading ? (
              <div className='space-y-2'>
                {Array.from({ length: 4 }, (_, i) => (
                  <Skeleton key={i} className='h-10 w-full' />
                ))}
              </div>
            ) : error ? (
              <div className='flex flex-col items-center gap-2 py-8 text-center'>
                <p className='text-destructive text-sm'>{error}</p>
                <Button variant='outline' size='sm' onClick={() => void load()}>
                  重试
                </Button>
              </div>
            ) : pageItems.length === 0 ? (
              <div className='border-border/60 rounded-lg border border-dashed px-4 py-8 text-center'>
                <p className='text-muted-foreground text-sm'>没有匹配的音频文件</p>
                <p className='text-muted-foreground/70 mt-1 text-xs'>
                  {isSingle
                    ? '当前音频库暂无噪声类型音频，可点击「上传音频」导入'
                    : '可调整搜索关键词或标签筛选，或点击「上传音频」导入'}
                </p>
              </div>
            ) : (
              <div className='max-h-64 space-y-1.5 overflow-y-auto'>
                {pageItems.map((audio) => {
                  const checked = selected.has(Number(audio.id))
                  return (
                    <button
                      key={audio.id}
                      type='button'
                      onClick={() => toggleSelect(audio)}
                      aria-pressed={checked}
                      className={cn(
                        'flex w-full items-center gap-2 rounded-lg border px-2.5 py-2 text-start text-sm transition-colors',
                        checked
                          ? 'bg-primary/10 border-primary/40'
                          : 'hover:bg-accent border-border/60'
                      )}
                    >
                      {isSingle ? (
                        <span
                          aria-hidden='true'
                          className={cn(
                            'flex size-4 shrink-0 items-center justify-center rounded-full border',
                            checked ? 'border-primary bg-primary' : 'border-muted-foreground/50'
                          )}
                        >
                          {checked && <span className='size-1.5 rounded-full bg-white' />}
                        </span>
                      ) : (
                        <Checkbox
                          checked={checked}
                          aria-label={`选择音频 ${audio.name}`}
                          // 行级按钮统一处理勾选（视觉 checkbox 不拦截点击，防双触发）
                          className='pointer-events-none shrink-0'
                        />
                      )}
                      <AudioWaveform aria-hidden='true' className='text-muted-foreground size-4 shrink-0' />
                      <span className='min-w-0 flex-1 truncate'>{audio.name}</span>
                      <span className='text-muted-foreground shrink-0 font-mono text-xs tabular-nums'>
                        {formatDuration(audio.duration)}
                      </span>
                      {(audio.tags ?? []).length > 0 && (
                        <span className='flex shrink-0 gap-1'>
                          {audio.tags!.slice(0, 3).map((t) => (
                            <Badge key={t} variant='secondary' className='rounded-md px-1.5 text-[10px]'>
                              {t}
                            </Badge>
                          ))}
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>
            )}

            {/* 分页（客户端；/audios 已拉大页） */}
            {!loading && !error && pageCount > 1 && (
              <div className='mt-2 flex items-center justify-between gap-2'>
                <span className='text-muted-foreground/70 text-xs'>
                  共 {filtered.length} 个音频 · {pageCount} 页
                </span>
                <div className='flex items-center gap-1'>
                  <Button
                    type='button'
                    variant='outline'
                    size='sm'
                    className='h-7'
                    disabled={safePage <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                  >
                    上一页
                  </Button>
                  <span className='text-muted-foreground text-xs tabular-nums'>
                    {safePage} / {pageCount}
                  </span>
                  <Button
                    type='button'
                    variant='outline'
                    size='sm'
                    className='h-7'
                    disabled={safePage >= pageCount}
                    onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
                  >
                    下一页
                  </Button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* 底部计数 + 操作 */}
        <DialogFooter>
          <div className='flex w-full flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between'>
            <p className='text-muted-foreground shrink-0 text-xs tabular-nums'>
              当前页 {pageItems.length} 个音频 ({summarizeDuration(pageItems)}) ｜ 已选择{' '}
              {selectedAudios.length} 个 ({summarizeDuration(selectedAudios)})
            </p>
            <div className='flex shrink-0 items-center justify-end gap-2'>
              <Button variant='outline' size='sm' onClick={() => onOpenChange(false)}>
                取消
              </Button>
              <Button size='sm' onClick={handleConfirm} disabled={selectedAudios.length === 0}>
                确认选择
              </Button>
            </div>
          </div>
        </DialogFooter>
      </DialogContent>

      {/* 头部上传/批量导入入口（复用音频导入页弹窗） */}
      <AudioUploadDialog open={uploadOpen} onOpenChange={setUploadOpen} />
      <AudioFolderImportDialog open={folderImportOpen} onOpenChange={setFolderImportOpen} />
    </Dialog>
  )
}
