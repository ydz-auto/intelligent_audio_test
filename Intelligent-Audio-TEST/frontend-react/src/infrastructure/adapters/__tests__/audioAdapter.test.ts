/**
 * 音频 DTO→Domain 适配器单测（infrastructure/adapters）。
 * 覆盖 snake_case→camelCase 字段映射与 audio_type 归一（16_设备域.md §10 契约）。
 */
import { describe, expect, it } from 'vitest'

import {
  audioFromDto,
  audioStatsFromDto,
  toAudioType,
} from '@/infrastructure/adapters/audioAdapter'
import type {
  AudioItemDto,
  AudioListStatsDto,
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
