/**
 * 音频选择库 API（infrastructure 层；11_用例域.md §5.1 音频选择子弹窗数据源）。
 * 真实 GET /api/v1/audios 经统一 client.ts（接线口径，删本页 mock 引用、不留双口径）。
 * 查询参数对照 api_gateway/schemas/audio.py AudioListQuery 实测：
 *   keyword（文件名/描述模糊）、audio_type（dry/noise/prompt/mixed）、page/per_page 分页。
 * 响应 data.items（AudioItemDto 数组）+ data.total/pages + data.stats（AudioListStatsDto）。
 * snake→camel 收敛在 adapters/audioAdapter.ts（audioFromDto/audioStatsFromDto）。
 */
import { apiClient } from './client'
import type { AudioAsset } from '@/domain/models/audio'
import { audioFromDto } from '@/infrastructure/adapters/audioAdapter'
import type { AudioItemDto, AudioListStatsDto } from '@/infrastructure/dto/audio.dto'

export interface AudioLibraryListQuery {
  /** 文件名/描述模糊搜索 */
  keyword?: string
  /** 音频类型过滤（noise 单选形态传 'noise'；缺省=全量） */
  audioType?: 'dry' | 'noise' | 'prompt' | 'mixed'
  page?: number
  perPage?: number
}

export interface AudioLibraryListResult {
  items: AudioAsset[]
  total: number
  pages: number
  stats: {
    totalFiles: number
    totalSize: string
    totalDuration: string
    todayUploads: number
  }
}

interface AudioLibraryListDto {
  items: AudioItemDto[]
  total: number
  page: number
  per_page: number
  pages: number
  stats: AudioListStatsDto
}

/** 音频列表（真实 GET /audios；音频选择子弹窗分页/facet 数据源） */
export async function fetchAudioLibrary(
  query: AudioLibraryListQuery = {}
): Promise<AudioLibraryListResult> {
  const dto = await apiClient.get<AudioLibraryListDto>('/audios', {
    params: {
      keyword: query.keyword,
      audio_type: query.audioType,
      page: query.page ?? 1,
      per_page: query.perPage ?? 12,
    },
  })
  return {
    items: (dto.items ?? []).map(audioFromDto),
    total: dto.total,
    pages: dto.pages,
    stats: {
      totalFiles: dto.stats?.total_files ?? 0,
      totalSize: dto.stats?.total_size ?? '',
      totalDuration: dto.stats?.total_duration ?? '',
      todayUploads: dto.stats?.today_uploads ?? 0,
    },
  }
}
