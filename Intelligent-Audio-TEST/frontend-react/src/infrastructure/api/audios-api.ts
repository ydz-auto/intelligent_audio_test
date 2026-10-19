/**
 * 音频管理 API（infrastructure 层；16_设备域.md §10 组件树落位）。
 * 【接线·React·音频】INT-645：从 mock 切真实后端端点，全部经 client.ts 统一 fetch 封装
 * （baseURL /api/v1、JWT 自动注入、信封解包、错误码归一为 ApiError）。
 *
 * 端点契约对照 api_gateway/routes/audio_bp.py + api_gateway/schemas/audio.py：
 *   GET    /audios                          列表（分页/facet；响应信封内 data.stats）
 *   GET    /audios/tags                     标签列表（PaginatedData 信封）
 *   POST   /audios/folder-tree              文件夹树（depth 增量）
 *   DELETE /audios/{id}                     删除（引用四路拦截文案由后端错误响应带回）
 *   PUT    /audios/{id}/metadata            编辑元数据（§6.13）
 *   POST   /audios/{id}/convert             格式转换（§6.15，body { format }）
 *   POST   /audios/url-import               单条 URL 导入（§6.18；批量由本层循环）
 *   POST   /audios/batch/annotations        批量更新标注（§6.19）
 *   POST   /audios/batch-action             批量 action（§5.6，body { action, audio_ids }）
 *   GET    /audios/{id}/stream              预签名 URL（§6.14 浏览器播放 + §5.3.1 下载二次取流）
 *   POST   /audios/{id}/preview             实验室播放（BatchPlaybackRequest，§6.14）
 *   POST   /audios/{id}/stop-preview        停止实验室播放（§6.14）
 *
 * snake_case 契约：infrastructure 是唯一 snake→camel 转换层（adapters/audioAdapter.ts），
 * application/domain 层只见 camelCase Domain，展示层不感知 wire 字段。
 */
import type {
  AudioAsset,
  AudioFolderNode,
  AudioListStats,
} from '@/domain/models/audio'
import { request } from '@/infrastructure/api/client'
import { ApiError } from '@/infrastructure/api/api-error'
import {
  audioFromDto,
  audioStatsFromDto,
  folderNodeFromDto,
} from '@/infrastructure/adapters/audioAdapter'
import type {
  AudioItemDto,
  AudioListDto,
  AudioTagListDto,
  FolderTreeDto,
} from '@/infrastructure/dto/audio.dto'

export type AudioListResult = {
  items: AudioAsset[]
  stats: AudioListStats
}

const EMPTY_STATS: AudioListStats = {
  totalFiles: 0,
  totalSize: '0 B',
  totalDuration: '0:00',
  todayUploads: 0,
}

/**
 * 音频列表（GET /audios；响应信封内 data = { items, total, page, per_page, pages, stats }）。
 * 页面当前为前端过滤/排序/分页（§5.2「接线后 URL 态化」前的过渡态），故以 per_page=10000
 * 拉全量由页面 useMemo 本地派生；URL 态化后改为把 filters 传后端分页/facet。
 */
export async function fetchAudios(): Promise<AudioListResult> {
  const dto = await request<AudioListDto>('GET', '/audios', undefined, {
    params: { page: 1, per_page: 10_000 },
  })
  return {
    items: (dto?.items ?? []).map(audioFromDto),
    stats: dto?.stats ? audioStatsFromDto(dto.stats) : EMPTY_STATS,
  }
}

/** 标签列表（GET /audios/tags；INT-297 PaginatedData 信封，取 data.items） */
export async function fetchAudioTags(): Promise<string[]> {
  const dto = await request<AudioTagListDto>('GET', '/audios/tags')
  return dto?.items ?? []
}

/** 文件夹树（POST /audios/folder-tree；depth=10 全量渲染，响应信封内 data.tree.folders 为顶层节点） */
export async function fetchFolderTree(): Promise<AudioFolderNode[]> {
  const dto = await request<FolderTreeDto>('POST', '/audios/folder-tree', {
    depth: 10,
  })
  return (dto?.tree?.folders ?? []).map((node) => folderNodeFromDto(node, 1))
}

/** 删除音频（DELETE /audios/{id}；引用四路拦截文案由后端错误响应带回） */
export async function deleteAudio(
  id: number
): Promise<{ success: boolean; message?: string }> {
  try {
    await request('DELETE', `/audios/${id}`)
    return { success: true }
  } catch (err) {
    return {
      success: false,
      message: err instanceof ApiError ? err.userMessage : '删除失败，请重试',
    }
  }
}

/**
 * 下载音频（§5.3.1 二次取流）：GET /audios/{id}/stream 返 OSS 预签名 URL，
 * 前端再取字节流；网关相对路径（本地降级 /api/v1/audios/download?path=…）经
 * client 注入 JWT 取 blob。
 */
export async function downloadAudio(id: number): Promise<Blob> {
  const result = await request<{ url?: string }>('GET', `/audios/${id}/stream`)
  const url = result?.url
  if (!url) throw new ApiError({ message: '获取音频下载地址失败' })
  if (/^https?:\/\//i.test(url)) {
    const resp = await fetch(url)
    if (!resp.ok) throw new ApiError({ message: `下载音频失败: ${resp.status}` })
    return await resp.blob()
  }
  const relative = url.replace(/^\/api\/v1\//i, '')
  const data = await request<Blob>('GET', relative, undefined, {
    responseType: 'blob',
  })
  return data instanceof Blob ? data : new Blob([data as unknown as BlobPart])
}

/**
 * 音频流 URL（§6.14 浏览器播放）：GET /audios/{id}/stream 返回 JSON 预签名 URL
 * （V9.7.31 契约，非裸字节流），前端 <audio> 直接以该 URL 播放。
 */
export async function stream(id: number): Promise<string> {
  const result = await request<{ url?: string }>('GET', `/audios/${id}/stream`)
  const url = result?.url
  if (!url) throw new ApiError({ message: '获取音频播放地址失败' })
  return url
}

/** 实验室播放载荷（BatchPlaybackRequest，api_gateway/schemas/audio.py:207；
 * playback_device_id | playback_device_ids | device_unique_ids 三选一 + spl + offset） */
export interface AudioPreviewPayload {
  playbackDeviceId?: number | null
  playbackDeviceIds?: number[]
  deviceUniqueIds?: string[]
  spl?: number | null
  offset?: number
}

/** 实验室播放（POST /audios/{id}/preview → 后端扬声器播放；请求成功即设备端输出） */
export async function preview(
  id: number,
  payload: AudioPreviewPayload
): Promise<{ success: boolean; message?: string }> {
  try {
    await request('POST', `/audios/${id}/preview`, {
      playback_device_id: payload.playbackDeviceId ?? undefined,
      playback_device_ids: payload.playbackDeviceIds,
      device_unique_ids: payload.deviceUniqueIds,
      spl: payload.spl ?? undefined,
      offset: payload.offset ?? 0,
    })
    return { success: true }
  } catch (err) {
    return {
      success: false,
      message: err instanceof ApiError ? err.userMessage : '试听启动失败，请重试',
    }
  }
}

/** 停止实验室播放（POST /audios/{id}/stop-preview） */
export async function stopPreview(
  id: number
): Promise<{ success: boolean; message?: string }> {
  try {
    await request('POST', `/audios/${id}/stop-preview`)
    return { success: true }
  } catch (err) {
    return {
      success: false,
      message: err instanceof ApiError ? err.userMessage : '停止试听失败，请重试',
    }
  }
}

/**
 * 编辑元数据（PUT /audios/{id}/metadata；patch 为 camelCase Domain，出参按 UpdateMetadataRequest
 * snake_case 化；tags 为逗号分隔字符串——后端 update_metadata 按 split(',') 重建标签）。
 * 后端仅回 message 不回完整对象，由 queryClient invalidate 刷新列表。
 */
export async function updateAudioMetadata(
  id: number,
  patch: Partial<AudioAsset>
): Promise<AudioAsset | undefined> {
  const body: Record<string, unknown> = {}
  if (patch.name !== undefined) body.name = patch.name
  if (patch.audioType !== undefined) body.audio_type = patch.audioType
  if (patch.asrText !== undefined) body.asr_text = patch.asrText
  if (patch.description !== undefined) body.description = patch.description
  if (patch.sourceLanguage !== undefined) body.source_language = patch.sourceLanguage
  if (patch.tags !== undefined) body.tags = patch.tags.join(', ')
  if (patch.annotations !== undefined) body.annotations = patch.annotations
  const dto = await request<AudioItemDto | null>(
    'PUT',
    `/audios/${id}/metadata`,
    body
  )
  return dto ? audioFromDto(dto) : undefined
}

/** 格式转换（POST /audios/{id}/convert；body { format } 对照 ConvertFormatRequest） */
export async function convertAudio(
  id: number,
  format: string
): Promise<{ success: boolean; message?: string }> {
  await request('POST', `/audios/${id}/convert`, { format })
  return { success: true, message: `已提交转换为 ${format}` }
}

/**
 * URL 导入（POST /audios/url-import；后端为单条契约 URLImportRequest{ url, audio_type }，
 * 批量由本层循环逐条提交并统计成功/失败）。
 */
export async function urlImportAudios(
  urls: string[],
  audioType = 'dry'
): Promise<{ successCount: number; failedCount: number }> {
  let successCount = 0
  let failedCount = 0
  for (const url of urls) {
    try {
      await request('POST', '/audios/url-import', { url, audio_type: audioType })
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
 * 批量更新标注（POST /audios/batch/annotations；body 对照 BatchUpdateAnnotationsRequest，
 * 响应 data = { updated_count, failed_count, refreshed_test_case_ids } 归一为页面 toast 计数）。
 * items 缺省为空（对话框文件解析/匹配流尚未接线，本卡只切 infra；传空后端回「标注列表不能为空」）。
 */
export async function batchUpdateAnnotations(
  payload: {
    items?: BatchAnnotationItem[]
    algorithmType?: string
    refreshTestCases?: boolean
  } = {}
): Promise<{ success: number; failed: number; refreshed: number }> {
  const body = {
    items: (payload.items ?? []).map((item) => ({
      audio_id: item.audioId,
      annotations: item.annotations ?? [],
    })),
    algorithm_type: payload.algorithmType,
    refresh_test_cases: payload.refreshTestCases,
  }
  const result = await request<{
    updated_count?: number
    failed_count?: number
    refreshed_test_case_ids?: number[]
  }>('POST', '/audios/batch/annotations', body)
  return {
    success: result?.updated_count ?? 0,
    failed: result?.failed_count ?? 0,
    refreshed: result?.refreshed_test_case_ids?.length ?? 0,
  }
}

/** 批量 action（§5.6；POST /audios/batch-action，body { action, audio_ids }） */
export type AudioBatchAction =
  | 'delete'
  | 'export'
  | 'tags'
  | 'move'
  | 'copy'
  | 'rename'
  | 'modify-properties'

export type BatchActionResult = {
  action: AudioBatchAction
  total: number
  successCount: number
  /** 后端消息（delete/tags 仅回 message 不回逐项计数；页面 toast 优先呈现） */
  message?: string
  /** export 响应 data（zip_base64/filename）透传，供页面解码下载 */
  zipBase64?: string
  filename?: string
}

/** batch-action 扩展参数（INT-818：move/copy/rename/modify-properties 四分支；snake_case 化在本层完成） */
export type AudioBatchActionOptions = {
  /** 批量设置标签（action=tags）时传入，替换选中音频原有标签 */
  tags?: string[]
  /** 批量移动/复制目标文件夹（move/copy；对应后端 target_folder，如 test_data/dry） */
  targetFolder?: string
  /** 批量重命名统一规则前缀（rename；对应后端 rename_rule，自动追加序号） */
  renameRule?: string
  /** 批量修改属性名（modify-properties：metadata / audio-type / spl） */
  property?: string
  /** 批量修改属性值（modify-properties：metadata 为字段字典、audio-type 为类型值） */
  propertyValue?: unknown
}

export async function batchActionAudios(
  action: AudioBatchAction,
  ids: number[],
  options?: AudioBatchActionOptions
): Promise<BatchActionResult> {
  // 契约对照 api_gateway/schemas/audio.py BatchActionRequest：
  // audio_ids / action / tags / target_folder / rename_rule / property / property_value
  const body: Record<string, unknown> = { action, audio_ids: ids }
  if (options?.tags && options.tags.length > 0) body.tags = options.tags
  if (options?.targetFolder) body.target_folder = options.targetFolder
  if (options?.renameRule) body.rename_rule = options.renameRule
  if (options?.property) body.property = options.property
  if (options?.propertyValue !== undefined) body.property_value = options.propertyValue

  // unwrapResponse: false 保留信封 message（delete/tags 的引用跳过明细以 message 呈现，
  // 后端不回逐项计数）；错误信封仍由 client 在非 2xx 时抛 ApiError。
  const envelope = await request<{
    message?: string
    data?: {
      zip_base64?: string
      filename?: string
      /** move/copy/rename/modify-properties 回逐项计数（INT-818） */
      success_count?: number
      failed_count?: number
    }
  }>('POST', '/audios/batch-action', body, { unwrapResponse: false })

  const dto = envelope?.data
  return {
    action,
    total: ids.length,
    // 四分支后端回 success_count/failed_count 按实计；delete/tags/export 不回逐项计数，
    // 整批成功即按 ids.length 计（引用跳过明细以 message 呈现）
    successCount:
      dto?.success_count ??
      (dto?.failed_count != null ? ids.length - dto.failed_count : ids.length),
    message: envelope?.message,
    zipBase64: dto?.zip_base64,
    filename: dto?.filename,
  }
}
