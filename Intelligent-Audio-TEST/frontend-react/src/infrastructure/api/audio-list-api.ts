/**
 * 音频列表真实 API（infrastructure/api 层；INT-710 批量设置噪声接线）。
 * GET /audios（audio_bp.py:17 get_all；per_page/page/keyword/folder 过滤）。
 * snake→camel 转换复用 adapters/audioAdapter.audioFromDto（与 mock 桩同一 domain 形态）。
 */
import { apiClient } from './client'
import type { AudioAsset } from '@/domain/models/audio'
import type { AudioItemDto } from '@/infrastructure/dto/audio.dto'
import { audioFromDto } from '@/infrastructure/adapters/audioAdapter'

interface AudioListDataDto {
  items?: AudioItemDto[]
  total?: number
}

/** 真实音频列表（GET /audios；默认大页供前端筛选） */
export async function fetchRealAudios(params?: {
  keyword?: string
  audioType?: string
  perPage?: number
}): Promise<{ items: AudioAsset[]; total: number }> {
  const dto = await apiClient.get<AudioListDataDto>('/audios', {
    params: {
      per_page: params?.perPage ?? 200,
      keyword: params?.keyword,
    },
  })
  const items = (dto?.items ?? []).map(audioFromDto)
  if (params?.audioType) {
    return { items: items.filter((a) => a.audioType === params.audioType), total: dto?.total ?? items.length }
  }
  return { items, total: dto?.total ?? items.length }
}
