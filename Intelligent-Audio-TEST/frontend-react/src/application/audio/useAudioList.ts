/**
 * 音频管理页 query hooks（application 层；16_设备域.md §10 组件树落位）。
 * queryKey 前缀 ['audios'] / ['audio-tags'] / ['audio-folder-tree']；
 * 增删改/批量/URL导入后 invalidate 自动刷新列表与统计。
 * INT-645 已切真实后端（audios-api 经 client.ts）；列表当前仍前端过滤分页
 * （§5.2 现接口支持分页/facet，URL 态化后传参后端）。
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

/** 音频列表（含 data.stats；列表/统计/批量浮条共用） */
export function useAudioList() {
  return useQuery({
    queryKey: ['audios'],
    queryFn: fetchAudios,
    staleTime: 30_000,
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
    }: {
      action: AudioBatchAction
      ids: number[]
    }) => batchActionAudios(action, ids),
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
