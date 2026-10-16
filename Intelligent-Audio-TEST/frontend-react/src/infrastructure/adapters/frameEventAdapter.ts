/**
 * Realtime frame 事件 DTO→Domain 适配器（infrastructure/adapters 层；10_测试执行.md §9）。
 * §3.7/§5.3：frame 通道事件（ai_text_delta/ai_audio_delta 等 snake_case）→ camelCase
 * 枚举/增量负载；Presentation 层不感知 snake_case。
 */
import type { RealtimeFrame, RealtimeFrameKind } from '@/domain/models/testExecution'
import type { FrameEventDto } from '@/infrastructure/dto/frame.dto'

const KIND_MAP: Record<string, RealtimeFrameKind> = {
  ai_text_delta: 'text_delta',
  ai_audio_delta: 'audio_delta',
  user_speech_started: 'speech_started',
  user_speech_ended: 'speech_ended',
  round_started: 'round_started',
  round_completed: 'round_completed',
}

export function frameFromDto(dto: FrameEventDto): RealtimeFrame {
  const kind = KIND_MAP[dto.event_type] ?? 'text_delta'
  return {
    caseId: dto.case_id,
    kind,
    textDelta: typeof dto.data.text_delta === 'string' ? dto.data.text_delta : undefined,
    audioProgress:
      typeof dto.data.audio_progress === 'number' ? dto.data.audio_progress : undefined,
    round: typeof dto.data.round === 'number' ? dto.data.round : undefined,
    timestamp: dto.ts,
  }
}
