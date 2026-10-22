/**
 * 音频管理页 query hooks（application 层；16_设备域.md §10 组件树落位）。
 * queryKey 前缀 ['audios'] / ['audio-tags'] / ['audio-folder-tree']；
 * 增删改/批量/URL导入后 invalidate 自动刷新列表与统计。
 * INT-645 已切真实后端（audios-api 经 client.ts）。INT-1216：列表改服务端分页——
 * 页面按 page/perPage + scalar facet 服务端过滤；标签 OR 模式后端不表达
 * （GET tags 参数 422 / POST 仅 AND），OR 时置 allRows 拉全量行客户端过滤。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  batchActionAudios,
  batchUpdateAnnotations,
  convertAudio,
  deleteAudio,
  fetchAudioTags,
  fetchAudios,
  fetchFolderTree,
  updateAudioMetadata,
  urlImportAudios,
  type AudioBatchAction,
  type BatchAnnotationItem,
} from '@/infrastructure/api/audios-api'
import type { AudioAsset } from '@/domain/models/audio'

/** 全量行单次拉取上限（仅用于需要跨页完整行集的场景：OR 标签客户端过滤 / 文件夹视图 / 批量标注文件名匹配） */
const FETCH_ALL_PER_PAGE = 10_000

export interface AudioListQueryOptions {
  page?: number
  perPage?: number
  search?: string
  format?: string | null
  audioType?: string | null
  sampleRate?: string | null
  duration?: 'short' | 'medium' | 'long' | null
  tags?: string[]
  tagMode?: 'or' | 'and'
  /** 跨页完整行集（OR 标签客户端过滤 / 文件夹视图 / 批量标注匹配）；置 true 时按 page=1&per_page=全部 拉取 */
  allRows?: boolean
  /** 查询启用（批量标注弹窗懒加载，避免页面常驻时多拉一份全量） */
  enabled?: boolean
}

/** 音频列表（含 data.stats；列表/统计/批量浮条共用；INT-1216 服务端分页） */
export function useAudioList(options: AudioListQueryOptions = {}) {
  const allRows = options.allRows ?? false
  const tags = options.tags && options.tags.length > 0 ? options.tags : undefined
  // 后端仅 AND 标签语义；OR 标签由页面客户端过滤（allRows 全量行）
  const tagsServerSide = Boolean(tags) && options.tagMode === 'and'
  const page = allRows ? 1 : (options.page ?? 1)
  const perPage = allRows ? FETCH_ALL_PER_PAGE : (options.perPage ?? 20)

  return useQuery({
    queryKey: [
      'audios',
      {
        page,
        perPage,
        keyword: options.search || undefined,
        format: options.format ?? undefined,
        audioType: options.audioType ?? undefined,
        sampleRate: options.sampleRate ? Number(options.sampleRate) : undefined,
        duration: options.duration ?? undefined,
        tags: tagsServerSide ? tags : undefined,
      },
    ],
    queryFn: () =>
      fetchAudios({
        page,
        perPage,
        keyword: options.search || undefined,
        format: options.format ?? undefined,
        audioType: options.audioType ?? undefined,
        sampleRate: options.sampleRate ? Number(options.sampleRate) : undefined,
        duration: options.duration ?? undefined,
        tags: tagsServerSide ? tags : undefined,
      }),
    enabled: options.enabled,
    staleTime: 30_000,
    placeholderData: (prev) => prev,
  })
}

/** 标签 facet 选项（GET /audios/tags） */
export function useAudioTags() {
  return useQuery({
    queryKey: ['audio-tags'],
    queryFn: fetchAudioTags,
    staleTime: 5 * 60_000,
  })
}

/** 文件夹树（§5.5；左树） */
export function useFolderTree() {
  return useQuery({
    queryKey: ['audio-folder-tree'],
    queryFn: fetchFolderTree,
    staleTime: 5 * 60_000,
  })
}

/** 增删改/批量/转换/URL 导入（聚合 CRUD + invalidate） */
export function useAudioMutations() {
  const queryClient = useQueryClient()

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['audios'] })
  }

  const remove = useMutation({
    mutationFn: (id: number) => deleteAudio(id),
    onSuccess: invalidate,
  })

  const saveMetadata = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Partial<AudioAsset> }) =>
      updateAudioMetadata(id, patch),
    onSuccess: invalidate,
  })

  const convert = useMutation({
    mutationFn: ({ id, format }: { id: number; format: string }) =>
      convertAudio(id, format),
    onSuccess: invalidate,
  })

  const batch = useMutation({
    mutationFn: ({
      action,
      ids,
      tags,
    }: {
      action: AudioBatchAction
      ids: number[]
      /** 批量设置标签（batch-action tags）时传入，替换选中音频原有标签 */
      tags?: string[]
    }) => batchActionAudios(action, ids, tags),
    onSuccess: invalidate,
  })

  const urlImport = useMutation({
    mutationFn: ({
      urls,
      audioType,
    }: {
      urls: string[]
      audioType: string
    }) => urlImportAudios(urls, audioType),
    onSuccess: invalidate,
  })

  const batchAnnotations = useMutation({
    mutationFn: (payload?: {
      items?: BatchAnnotationItem[]
      algorithmType?: string
      refreshTestCases?: boolean
    }) => batchUpdateAnnotations(payload),
    onSuccess: invalidate,
  })

  return {
    remove,
    saveMetadata,
    convert,
    batch,
    urlImport,
    batchAnnotations,
    invalidate,
  }
}
