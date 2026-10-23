/**
 * 音频 DTO→Domain 适配器（infrastructure/adapters 层；16_设备域.md §10 契约）。
 * 消费 dto/ 原始 snake_case 类型，产出 domain 模型；Presentation 层不感知 snake_case。
 * 对齐整站 DDD 契约（基座规范 §10.1：infrastructure 唯一知 snake_case）。
 */
import type {
  AudioAsset,
  AudioFeatures,
  AudioFolderNode,
  AudioListStats,
  AudioProcessMode,
  AudioProcessOperation,
  AudioProcessResult,
  AudioQuality,
  AudioType,
} from '@/domain/models/audio'
import type {
  AudioFeaturesDto,
  AudioItemDto,
  AudioListStatsDto,
  AudioProcessResultDto,
  AudioQualityDto,
  FolderTreeNodeDto,
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

/** 文件夹树节点 DTO→Domain（后端 folder-tree 节点 file_count/folders → fileCount/children；depth 按递归层级显式传递） */
export function folderNodeFromDto(
  dto: FolderTreeNodeDto,
  depth: number
): AudioFolderNode {
  return {
    path: dto.path ?? '',
    name: dto.name ?? '',
    count: dto.count ?? 0,
    fileCount: dto.file_count ?? 0,
    depth,
    children: (dto.folders ?? []).map((child) => folderNodeFromDto(child, depth + 1)),
  }
}

const PROCESS_OPERATIONS: ReadonlySet<string> = new Set(['denoise', 'gain', 'trim'])

/** operation 归一：非 denoise/gain/trim 回 denoise（后端已校验，前端仅收窄类型） */
export function toProcessOperation(operation: string): AudioProcessOperation {
  return PROCESS_OPERATIONS.has(operation)
    ? (operation as AudioProcessOperation)
    : 'denoise'
}

/** mode 归一：非 overwrite 一律按 new（后端缺省 new） */
export function toProcessMode(mode: string): AudioProcessMode {
  return mode === 'overwrite' ? 'overwrite' : 'new'
}

/** 特征分析 DTO→Domain（time_domain → timeDomain；三组特征原值透传，后端已四舍五入） */
export function audioFeaturesFromDto(dto: AudioFeaturesDto): AudioFeatures {
  return {
    spectral: {
      fundamentalRangeLow: dto.spectral.fundamental_range_low,
      fundamentalRangeHigh: dto.spectral.fundamental_range_high,
      dominantFrequency: dto.spectral.dominant_frequency,
      harmonicDistortion: dto.spectral.harmonic_distortion,
    },
    energy: {
      averageEnergyDb: dto.energy.average_energy_db,
      peakEnergyDb: dto.energy.peak_energy_db,
      energyConcentration: dto.energy.energy_concentration,
    },
    timeDomain: {
      zeroCrossingRate: dto.time_domain.zero_crossing_rate,
      activeDurationRatio: dto.time_domain.active_duration_ratio,
      onsetTime: dto.time_domain.onset_time,
    },
    audioId: dto.audio_id,
    duration: dto.duration,
  }
}

/** 质量评估 DTO→Domain */
export function audioQualityFromDto(dto: AudioQualityDto): AudioQuality {
  return {
    snrDb: dto.snr_db,
    dynamicRangeDb: dto.dynamic_range_db,
    frequencyResponseScore: dto.frequency_response_score,
    qualityScore: dto.quality_score,
    audioId: dto.audio_id,
    duration: dto.duration,
  }
}

/** 处理结果 DTO→Domain（new_audio_id 仅 mode=new 有值） */
export function audioProcessResultFromDto(
  dto: AudioProcessResultDto
): AudioProcessResult {
  return {
    audioId: dto.audio_id,
    operation: toProcessOperation(dto.operation),
    mode: toProcessMode(dto.mode),
    format: dto.format,
    filePath: dto.file_path,
    duration: dto.duration,
    size: dto.size,
    newAudioId: dto.new_audio_id ?? null,
  }
}
