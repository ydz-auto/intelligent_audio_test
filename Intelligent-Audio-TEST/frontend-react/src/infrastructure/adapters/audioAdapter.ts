/**
 * 音频 DTO→Domain 适配器（infrastructure/adapters 层；16_设备域.md §10 契约）。
 * 消费 dto/ 原始 snake_case 类型，产出 domain 模型；Presentation 层不感知 snake_case。
 * 对齐整站 DDD 契约（基座规范 §10.1：infrastructure 唯一知 snake_case）。
 */
import type {
  AudioAsset,
  AudioFolderNode,
  AudioListStats,
  AudioType,
} from '@/domain/models/audio'
import type {
  AudioFolderTreeDto,
  AudioItemDto,
  AudioListStatsDto,
} from '@/infrastructure/dto/audio.dto'

const AUDIO_TYPE_SET: ReadonlySet<string> = new Set([
  'dry',
  'noise',
  'prompt',
  'mixed',
])

/** audio_type 归一：非四值回 null（§5.3.2 口径） */
export function toAudioType(type: string | null): AudioType | null {
  if (!type || !AUDIO_TYPE_SET.has(type)) return null
  return type as AudioType
}

export function audioFromDto(dto: AudioItemDto): AudioAsset {
  return {
    id: dto.id,
    name: dto.name,
    originalFilename: dto.original_filename,
    filePath: dto.file_path,
    duration: dto.duration,
    size: dto.size,
    sampleRate: dto.sample_rate,
    channels: dto.channels,
    bitrate: dto.bitrate,
    format: dto.format,
    audioType: toAudioType(dto.audio_type),
    asrText: dto.asr_text,
    description: dto.description,
    sourceLanguage: dto.source_language,
    tags: dto.tags,
    annotations: dto.annotations,
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}

export function audioStatsFromDto(dto: AudioListStatsDto): AudioListStats {
  return {
    totalFiles: dto.total_files,
    totalSize: dto.total_size,
    totalDuration: dto.total_duration,
    todayUploads: dto.today_uploads,
  }
}

/**
 * 文件夹树 DTO→Domain（§5.5 左树）。
 * 后端 data.tree 为嵌套 folders/files 结构：节点 `count`（其下音频总数）+ `file_count`
 * （本文件夹直接音频数）→ 前端节点 count=子文件夹数、fileCount=文件夹内音频文件数；
 * 递归 children 取 folders 子树，files 仅计数不展开。
 */
export function audioFolderTreeFromDto(
  dto: AudioFolderTreeDto | null | undefined
): AudioFolderNode[] {
  if (!dto?.folders) return []
  return dto.folders.map((node) => ({
    path: node.path,
    name: node.name,
    count: node.folders?.length ?? 0,
    fileCount: node.file_count ?? 0,
    depth: 1,
    children: audioFolderTreeFromDto(node),
  }))
}
