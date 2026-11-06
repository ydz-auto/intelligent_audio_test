/**
 * 音频 DTO→Domain 适配器单测（infrastructure/adapters）。
 * 覆盖 snake_case→camelCase 字段映射与 audio_type 归一（16_设备域.md §10 契约）。
 */
import { describe, expect, it } from 'vitest'

import {
  audioFeaturesFromDto,
  audioFromDto,
  audioProcessResultFromDto,
  audioQualityFromDto,
  audioStatsFromDto,
  toAudioType,
  toProcessMode,
  toProcessOperation,
} from '@/infrastructure/adapters/audioAdapter'
import type {
  AudioFeaturesDto,
  AudioItemDto,
  AudioListStatsDto,
  AudioProcessResultDto,
  AudioQualityDto,
} from '@/infrastructure/dto/audio.dto'

const AUDIO_DTO: AudioItemDto = {
  id: 1,
  name: '客厅_中文_命令集.wav',
  original_filename: '客厅_中文_命令集.wav',
  file_path: 'test_data/dry/客厅_中文_命令集.wav',
  duration: 42.5,
  size: 3_352_064,
  sample_rate: 48_000,
  channels: 2,
  bitrate: 768,
  format: 'WAV',
  audio_type: 'dry',
  asr_text: null,
  description: '客厅环境中文命令词语料',
  source_language: 'zh-CN',
  tags: ['客厅', '中文'],
  annotations: [],
  created_at: '2026-10-12T09:18:00Z',
  updated_at: '2026-10-14T11:02:00Z',
}

describe('audioAdapter toAudioType', () => {
  it('dry/noise/prompt/mixed 四值归一保留', () => {
    expect(toAudioType('dry')).toBe('dry')
    expect(toAudioType('noise')).toBe('noise')
    expect(toAudioType('prompt')).toBe('prompt')
    expect(toAudioType('mixed')).toBe('mixed')
  })

  it('非四值/空返回 null', () => {
    expect(toAudioType('unknown')).toBeNull()
    expect(toAudioType(null)).toBeNull()
  })
})

describe('audioAdapter audioFromDto', () => {
  it('snake_case 字段映射为 camelCase Domain', () => {
    const audio = audioFromDto(AUDIO_DTO)
    expect(audio.id).toBe(1)
    expect(audio.name).toBe('客厅_中文_命令集.wav')
    expect(audio.originalFilename).toBe(AUDIO_DTO.original_filename)
    expect(audio.filePath).toBe(AUDIO_DTO.file_path)
    expect(audio.sampleRate).toBe(48_000)
    expect(audio.audioType).toBe('dry')
    expect(audio.sourceLanguage).toBe('zh-CN')
    expect(audio.createdAt).toBe('2026-10-12T09:18:00Z')
  })

  it('audio_type 非四值时 audioType 归一为 null', () => {
    const audio = audioFromDto({ ...AUDIO_DTO, audio_type: 'weird' })
    expect(audio.audioType).toBeNull()
  })
})

describe('audioAdapter audioStatsFromDto', () => {
  it('统计字段映射为 camelCase', () => {
    const statsDto: AudioListStatsDto = {
      total_files: 142,
      total_size: '3.2 GB',
      total_duration: '18 h 26 min',
      today_uploads: 6,
    }
    const stats = audioStatsFromDto(statsDto)
    expect(stats.totalFiles).toBe(142)
    expect(stats.totalSize).toBe('3.2 GB')
    expect(stats.totalDuration).toBe('18 h 26 min')
    expect(stats.todayUploads).toBe(6)
  })
})

/** 特征分析响应（GET /audios/{id}/features 200 的 data；字段对照 audio_service compute_features） */
const FEATURES_DTO: AudioFeaturesDto = {
  spectral: {
    fundamental_range_low: 118.6,
    fundamental_range_high: 402.31,
    dominant_frequency: 196.0,
    harmonic_distortion: 24.17,
  },
  energy: {
    average_energy_db: -22.4,
    peak_energy_db: -1.2,
    energy_concentration: 0.8531,
  },
  time_domain: {
    zero_crossing_rate: 0.0412,
    active_duration_ratio: 0.62,
    onset_time: 0.128,
  },
  audio_id: 2071,
  duration: 1.606,
}

describe('audioAdapter audioFeaturesFromDto', () => {
  it('三组特征 snake_case → camelCase，time_domain 归一为 timeDomain', () => {
    const features = audioFeaturesFromDto(FEATURES_DTO)
    expect(features.spectral.fundamentalRangeLow).toBe(118.6)
    expect(features.spectral.fundamentalRangeHigh).toBe(402.31)
    expect(features.spectral.dominantFrequency).toBe(196.0)
    expect(features.spectral.harmonicDistortion).toBe(24.17)
    expect(features.energy.averageEnergyDb).toBe(-22.4)
    expect(features.energy.peakEnergyDb).toBe(-1.2)
    expect(features.energy.energyConcentration).toBe(0.8531)
    expect(features.timeDomain.zeroCrossingRate).toBe(0.0412)
    expect(features.timeDomain.activeDurationRatio).toBe(0.62)
    expect(features.timeDomain.onsetTime).toBe(0.128)
    expect(features.audioId).toBe(2071)
    expect(features.duration).toBe(1.606)
  })
})

describe('audioAdapter audioQualityFromDto', () => {
  it('质量指标 snake_case → camelCase（docker 15000 实测 200 同字段）', () => {
    const dto: AudioQualityDto = {
      snr_db: 22.38,
      dynamic_range_db: 40.7,
      frequency_response_score: 6.69,
      quality_score: 30,
      audio_id: 2071,
      duration: 1.606,
    }
    const quality = audioQualityFromDto(dto)
    expect(quality.snrDb).toBe(22.38)
    expect(quality.dynamicRangeDb).toBe(40.7)
    expect(quality.frequencyResponseScore).toBe(6.69)
    expect(quality.qualityScore).toBe(30)
    expect(quality.audioId).toBe(2071)
    expect(quality.duration).toBe(1.606)
  })
})

describe('audioAdapter audioProcessResultFromDto', () => {
  it('mode=new 映射 new_audio_id → newAudioId', () => {
    const dto: AudioProcessResultDto = {
      audio_id: 2071,
      operation: 'gain',
      mode: 'new',
      format: 'wav',
      file_path: 'oss://audios/processed/abc.wav',
      duration: 1.606,
      size: 154_188,
      new_audio_id: 2549,
    }
    const result = audioProcessResultFromDto(dto)
    expect(result.audioId).toBe(2071)
    expect(result.operation).toBe('gain')
    expect(result.mode).toBe('new')
    expect(result.format).toBe('wav')
    expect(result.filePath).toBe('oss://audios/processed/abc.wav')
    expect(result.duration).toBe(1.606)
    expect(result.size).toBe(154_188)
    expect(result.newAudioId).toBe(2549)
  })

  it('mode=overwrite 无 new_audio_id → newAudioId 归一为 null', () => {
    const result = audioProcessResultFromDto({
      audio_id: 2071,
      operation: 'denoise',
      mode: 'overwrite',
      format: 'wav',
      file_path: 'oss://audios/processed/def.wav',
      duration: 1.606,
      size: 100_000,
    })
    expect(result.mode).toBe('overwrite')
    expect(result.newAudioId).toBeNull()
  })
})

describe('audioAdapter 处理操作归一', () => {
  it('operation 仅保留 denoise/gain/trim，其余回落 denoise', () => {
    expect(toProcessOperation('denoise')).toBe('denoise')
    expect(toProcessOperation('gain')).toBe('gain')
    expect(toProcessOperation('trim')).toBe('trim')
    expect(toProcessOperation('unknown')).toBe('denoise')
  })

  it('mode 仅 overwrite 视为覆盖，其余回落 new', () => {
    expect(toProcessMode('overwrite')).toBe('overwrite')
    expect(toProcessMode('new')).toBe('new')
    expect(toProcessMode('')).toBe('new')
  })
})
