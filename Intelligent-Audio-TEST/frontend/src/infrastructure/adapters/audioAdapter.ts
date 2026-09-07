/**
 * Audio Adapter —— AudioItemDto(snake_case) → AudioInfo(camelCase)
 *
 * 后端契约：api_gateway/schemas/audio.py。
 * 本文件是 audio 相关接口唯一允许做 snake_case → camelCase 键名转换的地方。
 * ReadModel 定义在 domain/model/audio.ts，本文件只做转换。
 */
import type {
  AudioItemDto,
  AudioListDto,
  AudioListStatsDto,
  AudioIdsDto,
  AudioTagListDto,
  AudioAlgorithmRelationDto,
} from '../dto/audioDto'
import type {
  AudioInfo,
  AudioListStats,
  AudioTagList,
  AudioIdsResult,
  AudioAnnotation,
  AudioAlgorithmRelation,
} from '../../domain/model/audio'
import type { Paginated } from '../../domain/model/common'
import { toPaginated } from './commonAdapter'

/** Record 标注 → AudioAnnotation（标注内容为自由结构，仅转已知键） */
function toAnnotation(raw: Record<string, unknown>): AudioAnnotation {
  return {
    format: typeof raw.format === 'string' ? raw.format : undefined,
    name: typeof raw.name === 'string' ? raw.name : undefined,
    data: raw.data,
    sourceLanguage: typeof raw.source_language === 'string' ? raw.source_language : (typeof raw.sourceLanguage === 'string' ? raw.sourceLanguage : undefined),
    targetLanguage: typeof raw.target_language === 'string' ? raw.target_language : (typeof raw.targetLanguage === 'string' ? raw.targetLanguage : undefined),
  }
}

/** AudioItemDto → AudioInfo（逐字段显式映射，可选缺失用 ?.） */
export function toAudioInfo(dto: AudioItemDto): AudioInfo {
  const audioType = dto?.audio_type
  return {
    id: dto?.id ?? '',
    name: dto?.name ?? '',
    originalFilename: dto?.original_filename,
    filePath: dto?.file_path,
    size: dto?.size,
    duration: dto?.duration,
    format: dto?.format,
    sampleRate: dto?.sample_rate,
    channels: dto?.channels,
    bitrate: dto?.bitrate,
    audioType,
    asrText: dto?.asr_text,
    description: dto?.description,
    sourceLanguage: dto?.source_language,
    tags: dto?.tags ?? [],
    annotations: (dto?.annotations ?? []).map(toAnnotation),
    createdAt: dto?.created_at,
    updatedAt: dto?.updated_at,
    // 本地兼容别名（W2 由消费方清理）
    filename: dto?.original_filename ?? dto?.name,
    filepath: dto?.file_path,
    type: audioType as AudioInfo['type'],
  }
}

/** 音频数组转换 */
export function toAudioInfoList(dtos: AudioItemDto[] | null | undefined): AudioInfo[] {
  return (dtos ?? []).map(toAudioInfo)
}

/** 音频分页列表（不含 stats 时兜底空统计） */
export function toAudioPage(dto: AudioListDto | null | undefined): Paginated<AudioInfo> & { stats?: AudioListStats } {
  const empty: AudioListDto = {
    items: [], total: 0, page: 1, per_page: 0, pages: 1,
    stats: { total_files: 0, total_size: '0 B', total_duration: '0:00', today_uploads: 0 },
  }
  const source = dto ?? empty
  return {
    ...toPaginated(source, toAudioInfo),
    stats: toAudioStats(source.stats),
  }
}

/** AudioListStatsDto → AudioListStats */
export function toAudioStats(dto: AudioListStatsDto | null | undefined): AudioListStats {
  return {
    totalFiles: dto?.total_files ?? 0,
    totalSize: dto?.total_size ?? '0 B',
    totalDuration: dto?.total_duration ?? '0:00',
    todayUploads: dto?.today_uploads ?? 0,
  }
}

/** AudioTagListDto → AudioTagList */
export function toAudioTagList(dto: AudioTagListDto | null | undefined): AudioTagList {
  return {
    items: dto?.items ?? [],
    total: dto?.total ?? 0,
  }
}

/** AudioIdsDto → AudioIdsResult */
export function toAudioIdsResult(dto: AudioIdsDto | null | undefined): AudioIdsResult {
  return {
    ids: dto?.ids ?? [],
    total: dto?.total ?? 0,
  }
}

/** AudioAlgorithmRelationDto → AudioAlgorithmRelation */
export function toAudioAlgorithmRelation(dto: AudioAlgorithmRelationDto): AudioAlgorithmRelation {
  return {
    algorithmType: dto?.algorithm_type ?? '',
    isPrimary: dto?.is_primary ?? false,
    weight: dto?.weight ?? 1,
    params: dto?.params,
  }
}

/** 关联列表转换 */
export function toAudioAlgorithmRelationList(
  dtos: AudioAlgorithmRelationDto[] | null | undefined
): AudioAlgorithmRelation[] {
  return (dtos ?? []).map(toAudioAlgorithmRelation)
}

/** AudioAlgorithmRelation（Domain）→ DTO（请求体） */
export function toAudioAlgorithmRelationDto(relation: AudioAlgorithmRelation): AudioAlgorithmRelationDto {
  return {
    algorithm_type: relation.algorithmType,
    is_primary: relation.isPrimary,
    weight: relation.weight,
    params: relation.params,
  }
}

// ===== 文件夹树 =====

/** 文件树节点 DTO（snake_case，后端原值） */
interface FolderTreeNodeDto {
  name?: string
  path?: string
  count?: number
  total?: number
  file_count?: number
  has_children?: boolean
  files?: AudioItemDto[]
  folders?: FolderTreeNodeDto[]
}

/** 文件树节点 ReadModel（camelCase） */
export interface FolderTreeNode {
  name: string
  path: string
  count: number
  fileCount: number
  hasChildren: boolean
  files: AudioInfo[]
  folders: FolderTreeNode[]
}

/** 文件树节点 DTO → ReadModel（递归转换 files/folders） */
export function toFolderNode(dto: FolderTreeNodeDto | null | undefined): FolderTreeNode {
  if (!dto) return { name: 'root', path: '', count: 0, fileCount: 0, hasChildren: false, files: [], folders: [] }
  return {
    name: dto.name || 'unnamed',
    path: dto.path ?? '',
    count: dto.count ?? dto.total ?? 0,
    fileCount: dto.file_count ?? (Array.isArray(dto.files) ? dto.files.length : 0),
    hasChildren: dto.has_children ?? false,
    files: Array.isArray(dto.files) ? dto.files.map(toAudioInfo) : [],
    folders: Array.isArray(dto.folders) ? dto.folders.map(toFolderNode) : [],
  }
}
