/**
 * 逻辑音箱组 DTO（infrastructure/dto 层——snake_case 唯一出现层）。
 * 形态对照 api_gateway/schemas/playback.py：PlaybackSpeakerGroupData / PlaybackSpeakerGroupItem。
 */

/** 组内某实验室的对应设备（PlaybackSpeakerGroupItem） */
export interface PlaybackSpeakerGroupItemDto {
  id: number | null
  group_id: number
  lab_id: number
  playback_device_id: number
}

/** 逻辑音箱组（PlaybackSpeakerGroupData） */
export interface PlaybackSpeakerGroupDto {
  id: number
  name: string
  description: string | null
  items: PlaybackSpeakerGroupItemDto[]
  created_at: string | null
  updated_at: string | null
}
