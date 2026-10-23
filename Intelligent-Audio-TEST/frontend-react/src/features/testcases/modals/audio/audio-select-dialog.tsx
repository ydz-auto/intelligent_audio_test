/**
 * 音频选择子弹窗（11_用例域.md §5.1 末段，Dialog sm:max-w-4xl「选择音频文件」）。
 * 用例编辑/批量噪声共用：搜索/标签筛选/文件夹树/多选/分页 + 头部「上传音频/批量从文件夹导入」入口
 * + 底部「当前页 {n} 个音频 ({总时长})｜已选择 {n} 个 ({时长})｜取消｜确认选择」。
 * mode='single'（audioType='noise'）单选形态供全局噪声/声纹/干扰人音频选择复用。
 *
 * 接线（INT-1424 返工 P2-1/P3-1，对照 V9.7.10 AudioSelectModal.vue + useAudioList）：
 * - 服务端分页：POST /audios（fetchAudios）按 page/per_page 请求，总数/页数取接口 data.total/data.pages，
 *   翻页重新请求后端；对齐 V9.7.10 useAudioList 默认 20/页、handlePageChange→loadAudios。
 * - 标签 chips 取 GET /audios/tags 全量 facet（V9.7.10 loadAllTags），选中标签按后端 AND 语义过滤。
 * - 文件夹树取 POST /audios/folder-tree（V9.7.10 fetchFolderTree，depth 10 一次渲染）；
 *   后端列表无 folder 过滤参数，选中文件夹时按全量行客户端过滤（同音频管理页文件夹视图口径）。
 * - 已选对象按 id 缓存：换关键词/翻页后先前勾选的音频仍保留（对齐 V9.7.10 allAudiosCache）。
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
import type { AudioAsset, AudioFolderNode } from '@/domain/models/audio'
import {
  fetchAudioTags,
  fetchAudios,
  fetchFolderTree,
  type AudioListResult,
} from '@/infrastructure/api/audios-api'
import { AudioUploadDialog } from '@/features/audio-import/components/modals/audio-upload-dialog'
import { AudioFolderImportDialog } from '@/features/audio-import/components/modals/audio-folder-import-dialog'

/** 服务端分页每页条数（V9.7.10 useAudioList 默认 pageSize=20） */
const PAGE_SIZE = 20
/** 文件夹视图整页拉取上限（后端列表接口无 folder 过滤参数，选中文件夹时按全量行客户端过滤，
 *  同音频管理页 folder 视图 allRows 口径） */
const FOLDER_ALL_PER_PAGE = 10_000

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

/** 后端文件夹树扁平化（含 depth，用于缩进渲染） */
function flattenFolders(
  nodes: AudioFolderNode[],
  depth = 0
): Array<{ node: AudioFolderNode; depth: number }> {
  return nodes.flatMap((node) => [
    { node, depth },
    ...flattenFolders(node.children ?? [], depth + 1),
  ])
}

/**
 * 音频相对路径（对齐 /audios/folder-tree 的 path 口径：相对音频库根）。
 * filePath 两种实存形态：`oss://audios/direct/x.wav` 与 `D:/00_static/static/audios/环境理解/…/x.wav`，
 * 统一取 `/audios/` 之后段，才能与文件夹树节点 path（如 `direct`、`环境理解`）前缀匹配。
 */
function audioRelativePath(filePath: string | null | undefined): string {
  if (!filePath) return ''
  const normalized = filePath.replace(/\\/g, '/')
  const m = normalized.match(/\/audios\/(.+)$/i)
  if (m) return m[1]
  return normalized.replace(/^[a-z]+:\/\//i, '')
}

/** 文件是否归属某文件夹节点（path 为树节点相对路径；按目录前缀匹配，避免同前缀文件夹串档） */
function inFolder(filePath: string | null | undefined, folder: string): boolean {
  return audioRelativePath(filePath).startsWith(`${folder}/`)
}

/** 由 filePath 派生顶层文件夹（后端文件夹树为空时的兜底；文件在根无文件夹则忽略） */
function deriveFolders(items: AudioAsset[]): AudioFolderNode[] {
  const seen = new Set<string>()
  for (const item of items) {
    const parts = audioRelativePath(item.filePath).split('/')
    const dir = parts.slice(0, -1).join('/')
    if (dir) seen.add(dir)
  }
  return [...seen].sort().map((path) => ({
    path,
    name: path.split('/').pop() ?? path,
    count: 0,
    fileCount: items.filter((a) => inFolder(a.filePath, path)).length,
    depth: 1,
    children: [],
  }))
}

/** 已选缓存占位对象（编辑回显只带 id/name；详情由加载行补齐） */
function placeholderAudio(a: { id: number | string; name?: string }): AudioAsset {
  return {
    id: Number(a.id),
    name: a.name ?? `#${a.id}`,
    originalFilename: null,
    filePath: null,
    duration: null,
    size: null,
    sampleRate: null,
    channels: null,
    bitrate: null,
    format: null,
    audioType: null,
    asrText: null,
    description: null,
    sourceLanguage: null,
    tags: [],
    annotations: [],
    createdAt: null,
    updatedAt: null,
  }
}

export interface AudioSelectDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** 单选形态（audioType='noise' 全局噪声/声纹/干扰人复用）；缺省多选 */
  mode?: 'multi' | 'single'
  /** 音频类型过滤（单选噪声形态传 'noise'；缺省全量） */
  audioType?: 'dry' | 'noise' | 'prompt' | 'mixed'
  /** 已选初始值（编辑回填；单选态取首个） */
  initialSelected?: Array<{ id: number | string; name?: string }>
  /** 确认回调（多选=数组；单选=单元素数组），对象为按 id 缓存的完整音频 */
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
  /** 服务端分页结果（「全部」视图） */
  const [data, setData] = useState<AudioListResult | null>(null)
  /** 文件夹视图全量行（选中文件夹后按 filePath 前缀客户端过滤） */
  const [folderRows, setFolderRows] = useState<AudioAsset[] | null>(null)
  const [folderTree, setFolderTree] = useState<AudioFolderNode[]>([])
  const [allTags, setAllTags] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  /** 已选缓存（id → 音频对象；跨关键词/翻页保留，对齐 V9.7.10 allAudiosCache） */
  const [selectedMap, setSelectedMap] = useState<Map<number, AudioAsset>>(new Map())
  /** 回显占位（仅 id，无真实行数据）：未真正加载到前不参与确认，避免把占位名写回表单 */
  const placeholderIds = useRef<Set<number>>(new Set())
  const [uploadOpen, setUploadOpen] = useState(false)
  const [folderImportOpen, setFolderImportOpen] = useState(false)

  // 打开时回填已选（编辑态）；仅在 open 从 false→true 的转换时重置（initialSelected 由调用方
  // 每次渲染新建数组，直接入 deps 会造成「重置→渲染→重置」死循环——Maximum update depth）
  const wasOpen = useRef(false)
  useEffect(() => {
    if (open && !wasOpen.current) {
      placeholderIds.current = new Set(initialSelected.map((a) => Number(a.id)))
      setSelectedMap(new Map(initialSelected.map((a) => [Number(a.id), placeholderAudio(a)])))
      setKeyword('')
      setDebouncedKeyword('')
      setSelectedTags(new Set())
      setActiveFolder(null)
      setPage(1)
      setData(null)
      setFolderRows(null)
    }
    wasOpen.current = open
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  // 搜索防抖（真实接口 keyword 参数；320ms）——关键词变化回到第 1 页
  useEffect(() => {
    const t = window.setTimeout(() => {
      setDebouncedKeyword(keyword.trim())
      setPage(1)
    }, 320)
    return () => window.clearTimeout(t)
  }, [keyword])

  // 打开时加载标签 facet + 文件夹树（V9.7.10 loadAllTags / fetchFolderTree）
  useEffect(() => {
    if (!open) return
    let cancelled = false
    void fetchAudioTags()
      .then((tags) => {
        if (!cancelled) setAllTags(tags)
      })
      .catch(() => {
        if (!cancelled) setAllTags([])
      })
    void fetchFolderTree()
      .then((tree) => {
        if (!cancelled) setFolderTree(tree)
      })
      .catch(() => {
        if (!cancelled) setFolderTree([])
      })
    return () => {
      cancelled = true
    }
  }, [open])

  const tagList = useMemo(() => [...selectedTags].sort(), [selectedTags])

  // 列表加载：全部视图走服务端分页；文件夹视图拉全量行后按 folder 前缀客户端过滤
  const load = useCallback(async () => {
    if (!open) return
    setLoading(true)
    setError(null)
    try {
      if (activeFolder !== null) {
        const result = await fetchAudios({
          keyword: debouncedKeyword || undefined,
          audioType,
          tags: tagList,
          page: 1,
          perPage: FOLDER_ALL_PER_PAGE,
        })
        setFolderRows(
          result.items.filter((a) => inFolder(a.filePath, activeFolder))
        )
        setData(null)
      } else {
        const result = await fetchAudios({
          keyword: debouncedKeyword || undefined,
          audioType,
          tags: tagList,
          page,
          perPage: PAGE_SIZE,
        })
        setData(result)
        setFolderRows(null)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '音频列表加载失败')
    } finally {
      setLoading(false)
    }
  }, [open, activeFolder, debouncedKeyword, audioType, tagList, page])

  useEffect(() => {
    if (open) void load()
  }, [open, load])

  const folderItems = useMemo(() => flattenFolders(folderTree), [folderTree])

  /** 文件夹树为空时回退：由当前已加载行派生（后端无数据/无音频归档时） */
  const derivedFolders = useMemo(() => {
    if (folderTree.length > 0) return []
    return deriveFolders([...(data?.items ?? []), ...(folderRows ?? [])])
  }, [folderTree, data, folderRows])

  /** 当前视图行集（文件夹视图为已过滤行，全部视图为服务端当前页） */
  const viewRows = useMemo(() => {
    if (activeFolder !== null) return folderRows ?? []
    return data?.items ?? []
  }, [activeFolder, folderRows, data])

  /** 总数/页数：全部视图取接口 data.total/pages（V9.7.10 totalAudios），文件夹视图按过滤集 */
  const totalCount = activeFolder === null ? (data?.total ?? 0) : viewRows.length
  const pageCount = Math.max(
    1,
    activeFolder === null
      ? (data?.pages ?? Math.ceil(totalCount / PAGE_SIZE))
      : Math.ceil(viewRows.length / PAGE_SIZE)
  )
  const safePage = Math.min(page, pageCount)

  /** 当前页行（文件夹视图客户端分页；全部视图即服务端返回页） */
  const pageItems = useMemo(() => {
    if (activeFolder === null) return viewRows
    return viewRows.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE)
  }, [activeFolder, viewRows, safePage])

  // 已选缓存补全：加载到的行若已被选中，用完整对象覆盖占位（时长/标签等）
  useEffect(() => {
    const rows = [...(data?.items ?? []), ...(folderRows ?? [])]
    if (rows.length === 0) return
    setSelectedMap((prev) => {
      if (prev.size === 0) return prev
      let changed = false
      const next = new Map(prev)
      for (const row of rows) {
        if (next.has(row.id) && next.get(row.id) !== row) {
          next.set(row.id, row)
          placeholderIds.current.delete(row.id)
          changed = true
        }
      }
      return changed ? next : prev
    })
  }, [data, folderRows])

  const toggleTag = (tag: string) => {
    setSelectedTags((prev) => {
      const next = new Set(prev)
      if (next.has(tag)) next.delete(tag)
      else next.add(tag)
      return next
    })
    setPage(1)
  }

  const toggleSelect = (audio: AudioAsset) => {
    const id = Number(audio.id)
    placeholderIds.current.delete(id)
    setSelectedMap((prev) => {
      if (isSingle) return new Map([[id, audio]])
      const next = new Map(prev)
      if (next.has(id)) next.delete(id)
      else next.set(id, audio)
      return next
    })
  }

  /** 全选当前页（V9.7.10 全选当前页语义；含标签/文件夹过滤后可见集） */
  const selectCurrentPage = () => {
    pageItems.forEach((a) => placeholderIds.current.delete(Number(a.id)))
    setSelectedMap((prev) => {
      const next = new Map(prev)
      pageItems.forEach((a) => next.set(Number(a.id), a))
      return next
    })
  }

  const selectedAudios = useMemo(() => [...selectedMap.values()], [selectedMap])
  /** 可确认项（排除只剩 id 的回显占位） */
  const confirmables = useMemo(
    () => selectedAudios.filter((a) => !placeholderIds.current.has(a.id)),
    [selectedAudios]
  )

  const handleConfirm = () => {
    if (confirmables.length === 0) return
    onConfirm(confirmables)
    onOpenChange(false)
  }

  const handleFolderSelect = (path: string | null) => {
    setActiveFolder(path)
    setPage(1)
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

          {/* 标签筛选 chips（GET /audios/tags 全量 facet；选中按后端 AND 语义过滤） */}
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
              {selectedTags.size > 0 && (
                <button
                  type='button'
                  onClick={() => {
                    setSelectedTags(new Set())
                    setPage(1)
                  }}
                  className='text-muted-foreground hover:text-foreground px-1 text-xs underline-offset-2 hover:underline'
                >
                  清空筛选
                </button>
              )}
            </div>
          )}
        </div>

        {/* 主体：文件夹树 + 音频列表 */}
        <div className='flex min-h-80 flex-col gap-3 sm:flex-row'>
          {/* 文件夹树（POST /audios/folder-tree；无数据时由已加载行派生兜底） */}
          <div className='border-border/60 w-full shrink-0 rounded-lg border p-2 sm:w-44'>
            <p className='text-muted-foreground px-1 pb-1 text-xs font-medium'>文件夹</p>
            <button
              type='button'
              onClick={() => handleFolderSelect(null)}
              className={cn(
                'flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-start text-xs transition-colors',
                activeFolder === null
                  ? 'bg-primary/10 text-primary font-medium'
                  : 'hover:bg-accent text-muted-foreground'
              )}
            >
              <FolderOpen aria-hidden='true' className='size-3.5 shrink-0' />
              全部
              <span className='text-muted-foreground/60 ms-auto font-mono text-[10px] tabular-nums'>
                {activeFolder === null ? totalCount : ''}
              </span>
            </button>
            <div className='mt-1 max-h-56 space-y-0.5 overflow-y-auto sm:max-h-64'>
              {folderItems.length === 0 && derivedFolders.length === 0 && (
                <p className='text-muted-foreground/70 px-2 py-1 text-[11px]'>暂无文件夹</p>
              )}
              {folderItems.length > 0
                ? folderItems.map(({ node, depth }) => {
                    const active = activeFolder === node.path
                    return (
                      <button
                        key={node.path}
                        type='button'
                        onClick={() => handleFolderSelect(active ? null : node.path)}
                        className={cn(
                          'flex w-full items-center gap-1.5 rounded-md py-1 pe-2 text-start text-xs transition-colors',
                          active
                            ? 'bg-primary/10 text-primary font-medium'
                            : 'hover:bg-accent text-muted-foreground'
                        )}
                        style={{ paddingInlineStart: `${depth * 12 + 8}px` }}
                        title={node.path}
                      >
                        <Folder aria-hidden='true' className='size-3.5 shrink-0' />
                        <span className='min-w-0 flex-1 truncate'>{node.name}</span>
                        <span className='text-muted-foreground/60 font-mono text-[10px] tabular-nums'>
                          {node.fileCount}
                        </span>
                      </button>
                    )
                  })
                : derivedFolders.map((node) => {
                    const active = activeFolder === node.path
                    return (
                      <button
                        key={node.path}
                        type='button'
                        onClick={() => handleFolderSelect(active ? null : node.path)}
                        className={cn(
                          'flex w-full items-center gap-1.5 rounded-md px-2 py-1 text-start text-xs transition-colors',
                          active
                            ? 'bg-primary/10 text-primary font-medium'
                            : 'hover:bg-accent text-muted-foreground'
                        )}
                        title={node.path}
                      >
                        <Folder aria-hidden='true' className='size-3.5 shrink-0' />
                        <span className='min-w-0 flex-1 truncate'>{node.path}</span>
                        <span className='text-muted-foreground/60 font-mono text-[10px] tabular-nums'>
                          {node.fileCount}
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
                  const checked = selectedMap.has(Number(audio.id))
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

            {/* 分页：全部视图服务端分页（总数/页数取接口），文件夹视图按过滤集客户端分页 */}
            {!loading && !error && pageCount > 1 && (
              <div className='mt-2 flex items-center justify-between gap-2'>
                <span className='text-muted-foreground/70 text-xs'>
                  共 {totalCount} 个音频 · {pageCount} 页
                </span>
                <div className='flex items-center gap-1'>
                  <Button
                    type='button'
                    variant='outline'
                    size='sm'
                    className='h-7'
                    disabled={safePage <= 1}
                    onClick={() => setPage(Math.max(1, safePage - 1))}
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
                    onClick={() => setPage(Math.min(pageCount, safePage + 1))}
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
            <div className='flex shrink-0 items-center gap-3'>
              <p className='text-muted-foreground text-xs tabular-nums'>
                当前页 {pageItems.length} 个音频 ({summarizeDuration(pageItems)}) ｜ 已选择{' '}
                {selectedAudios.length} 个 ({summarizeDuration(selectedAudios)})
              </p>
              {!isSingle && (
                <div className='flex items-center gap-1'>
                  <Button
                    type='button'
                    variant='ghost'
                    size='sm'
                    className='h-7 px-2 text-xs'
                    onClick={selectCurrentPage}
                  >
                    全选本页
                  </Button>
                  <Button
                    type='button'
                    variant='ghost'
                    size='sm'
                    className='h-7 px-2 text-xs'
                    disabled={selectedMap.size === 0}
                    onClick={() => setSelectedMap(new Map())}
                  >
                    清空选择
                  </Button>
                </div>
              )}
            </div>
            <div className='flex shrink-0 items-center justify-end gap-2'>
              <Button variant='outline' size='sm' onClick={() => onOpenChange(false)}>
                取消
              </Button>
              <Button size='sm' onClick={handleConfirm} disabled={confirmables.length === 0}>
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
