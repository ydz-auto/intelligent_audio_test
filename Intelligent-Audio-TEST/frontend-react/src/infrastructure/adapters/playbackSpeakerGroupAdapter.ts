/**
 * 逻辑音箱组 DTO→Domain 适配器（infrastructure/adapters 层）。
 * 消费 dto/ 原始 snake_case，产出 domain 模型；Presentation 层不感知 snake_case。
 */
import type {
  PlaybackSpeakerGroup,
  PlaybackSpeakerGroupItem,
} from '@/domain/models/playbackSpeakerGroup'
import type {
  PlaybackSpeakerGroupDto,
  PlaybackSpeakerGroupItemDto,
} from '@/infrastructure/dto/playback-speaker-group.dto'

export function playbackSpeakerGroupItemFromDto(
  dto: PlaybackSpeakerGroupItemDto
): PlaybackSpeakerGroupItem {
  return {
    id: dto.id ?? null,
    groupId: dto.group_id,
    labId: dto.lab_id,
    playbackDeviceId: dto.playback_device_id,
  }
}

export function playbackSpeakerGroupFromDto(dto: PlaybackSpeakerGroupDto): PlaybackSpeakerGroup {
  return {
    id: dto.id,
    name: dto.name,
    description: dto.description,
    items: (dto.items ?? []).map(playbackSpeakerGroupItemFromDto),
    createdAt: dto.created_at,
    updatedAt: dto.updated_at,
  }
}
