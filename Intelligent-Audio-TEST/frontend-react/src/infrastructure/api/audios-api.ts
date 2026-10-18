/**
 * 音频管理 API（infrastructure 层；16_设备域.md §10 组件树落位；INT-714 接线）。
 * 对照后端 api_gateway/routes/audio_bp.py + schemas/audio.py 实测：
 *   GET    /api/v1/audios                           列表（data.items + data.total + data.stats）
 *   GET    /api/v1/audios/tags                      标签列表（分页字符串）
 *   POST   /api/v1/audios/folder-tree               文件夹树（body parent_path/depth → data.tree）
 *   DELETE /api/v1/audios/{id}                      删除
 *   PUT    /api/v1/audios/{id}/metadata             编辑元数据（UpdateMetadataRequest）
 *   POST   /api/v1/audios/{id}/convert              格式转换（ConvertFormatRequest）
 *   POST   /api/v1/audios/url-import                URL 导入（单 URL/次；列表逐条提交）
 *   POST   /api/v1/audios/batch-action              批量 action（BatchActionRequest）
 *   POST   /api/v1/audios/batch/annotations         批量更新标注（BatchUpdateAnnotationsRequest）
 *   GET    /api/v1/audios/{id}/stream               流预签名 URL
 * 分页：页面当前为客户端过滤/排序/分页，列表按 LIST_PAGE_SIZE 大页拉取供前端切分；
 * snake→camel 收敛在 adapters/audioAdapter。
 */
import type {
  AudioAsset,
  AudioFolderNode,
  AudioListStats,
} from '@/domain/models/audio'
import { apiClient } from './client'
import {
  audioFolderTreeFromDto,
  audioFromDto,
  audioStatsFromDto,
} from '@/infrastructure/adapters/audioAdapter'
import type {
  AudioFolderTreeDto,
  AudioListDataDto,
  AudioListStatsDto,
} from '@/infrastructure/dto/audio.dto'

/** 列表页当前为客户端懒加载分页，拉大页供前端切分（§5.2 口径） */
const LIST_PAGE_SIZE = 200

export type AudioListResult = {
  items: AudioAsset[]
  total: number
  stats: AudioListStats
}

/** 音频列表（§5.3；GET /audios，响应含 data.items/data.total/data.stats） */
export async function fetchAudios(): Promise<AudioListResult> {
  const dto = await apiClient.get<AudioListDataDto>('/audios', {
    params: { page: 1, per_page: LIST_PAGE_SIZE },
  })
  return {
    items: (dto.items ?? []).map(audioFromDto),
    total: dto.total ?? 0,
    stats: audioStatsFromDto(dto.stats ?? emptyStats()),
  }
}

/** 空统计兜底（后端异常未返回 stats 时不展示 NaN） */
function emptyStats(): AudioListStatsDto {
  return { total_files: 0, total_size: '0 B', total_duration: '0s', today_uploads: 0 }
}

/** 标签列表（§5.3.2 标签 facet 选项；GET /audios/tags） */
export async function fetchAudioTags(): Promise<string[]> {
  const dto = await apiClient.get<{ items: string[] }>('/audios/tags', {
    params: { page: 1, per_page: LIST_PAGE_SIZE },
  })
  return dto?.items ?? []
}

/** 文件夹树（§5.5；POST /audios/folder-tree，parent_path='' + depth=1 根节点增量） */
export async function fetchFolderTree(): Promise<AudioFolderNode[]> {
  const dto = await apiClient.post<{ tree?: AudioFolderTreeDto }>('/audios/folder-tree', {
    parent_path: '',
    depth: 1,
  })
  return audioFolderTreeFromDto(dto?.tree)
}

/** 删除音频（§5.3.1；DELETE /audios/{id}，引用四路拦截文案见 §9） */
export async function deleteAudio(
  id: number
): Promise<{ success: boolean; message?: string }> {
  const dto = await apiClient.delete<{ message?: string }>(`/audios/${id}`)
  return { success: true, message: dto?.message }
}

/** 编辑元数据（§6.13；PUT /audios/{id}/metadata，UpdateMetadataRequest snake_case） */
export async function updateAudioMetadata(
  id: number,
  patch: Partial<AudioAsset>
): Promise<AudioAsset | undefined> {
  const dto = await apiClient.put<AudioListDataDto['items'][number] | null>(
    `/audios/${id}/metadata`,
    {
      name: patch.name,
      audio_type: patch.audioType,
      asr_text: patch.asrText,
      description: patch.description,
      source_language: patch.sourceLanguage,
      tags: patch.tags && patch.tags.length > 0 ? patch.tags.join(',') : undefined,
      annotations: patch.annotations,
    }
  )
  return dto ? audioFromDto(dto) : undefined
}

/** 格式转换（§6.15；POST /audios/{id}/convert，ConvertFormatRequest） */
export async function convertAudio(
  id: number,
  format: string
): Promise<{ success: boolean; message?: string }> {
  await apiClient.post(`/audios/${id}/convert`, { format })
  return { success: true }
}

/** URL 导入（§6.18；POST /audios/url-import，URLImportRequest 单 URL/次，列表逐条提交） */
export async function urlImportAudios(
  urls: string[]
): Promise<{ successCount: number; failedCount: number }> {
  let successCount = 0
  let failedCount = 0
  for (const url of urls) {
    try {
      await apiClient.post('/audios/url-import', { url, audio_type: 'dry' })
      successCount += 1
    } catch {
      failedCount += 1
    }
  }
  return { successCount, failedCount }
}

/** 批量更新标注请求条目（camelCase 域契约；snake_case 化在本层完成） */
export interface BatchAnnotationItem {
  audioId: number
  annotations: unknown[]
}

/**
 * 批量更新标注（§6.19；POST /audios/batch/annotations；body 对照 BatchUpdateAnnotationsRequest，
 * 响应 data = { updated_count, failed_count, refreshed_test_case_ids } 归一为页面 toast 计数）。
 * 载荷（items/algorithmType/refreshTestCases）由批量标注弹窗解析匹配后传入；
 * 注：INT-645 同形改造已在收口分支，本卡保持 apiClient 风格兼容（INT-725 合入后统一）。
 */
export async function batchUpdateAnnotations(
  payload?: {
    items?: BatchAnnotationItem[]
    algorithmType?: string
    refreshTestCases?: boolean
  }
): Promise<{ success: number; failed: number; refreshed: number }> {
  const body = {
    items: (payload?.items ?? []).map((item) => ({
      audio_id: item.audioId,
      annotations: item.annotations ?? [],
    })),
    algorithm_type: payload?.algorithmType,
    refresh_test_cases: payload?.refreshTestCases,
  }
  const dto = await apiClient.post<{
    updated_count?: number
    failed_count?: number
    refreshed_test_case_ids?: number[]
  } | null>('/audios/batch/annotations', body)
  return {
    success: dto?.updated_count ?? 0,
    failed: dto?.failed_count ?? 0,
    refreshed: dto?.refreshed_test_case_ids?.length ?? 0,
  }
}

/** 批量 action（§5.6；POST /audios/batch-action，BatchActionRequest { audio_ids, action, tags }） */
export type AudioBatchAction =
  | 'delete'
  | 'export'
  | 'tags'
  | 'move'
  | 'copy'
  | 'rename'
  | 'modify-properties'

export async function batchActionAudios(
  action: AudioBatchAction,
  ids: number[],
  tags: string[] = []
): Promise<{ action: AudioBatchAction; total: number; successCount: number }> {
  const dto = await apiClient.post<{ success_count?: number } | null>(
    '/audios/batch-action',
    { audio_ids: ids, action, tags }
  )
  return {
    action,
    total: ids.length,
    successCount: dto?.success_count ?? ids.length,
  }
}

/** 音频流预签名 URL（§5.2 浏览器播放；GET /audios/{id}/stream → { url }，audio_bp.py:94） */
export async function fetchAudioStreamUrl(id: number): Promise<string | null> {
  const dto = await apiClient.get<{ url?: string | null }>(`/audios/${id}/stream`)
  return dto?.url ?? null
}
