/**
 * Realtime frame 事件 DTO→Domain 适配器（infrastructure/adapters 层；10_测试执行.md §9）。
 * INT-646 返修：按后端 EventBus 载荷（realtime_stream_publisher.py）映射——
 * test_case_id → caseId、type → kind 枚举、payload.delta → textDelta、round_number → round。
 * 注：ai_audio_delta 后端仅推 payload.size（分片字节数），无 0-100 百分比——
 * 音频按 audioChunkBytes 累积展示，不做百分比换算（后端不提供总时长）。
 */
import type { RealtimeFrame, RealtimeFrameKind } from '@/domain/models/testExecution'
import type { FrameEventDto } from '@/infrastructure/dto/frame.dto'

const KIND_MAP: Record<string, RealtimeFrameKind> = {
  ai_text_delta: 'text_delta',
  ai_audio_delta: 'audio_delta',
  user_speech_started: 'speech_started',
  user_speech_stopped: 'speech_ended',
  round_started: 'round_started',
  round_completed: 'round_completed',
}

export function frameFromDto(dto: FrameEventDto): RealtimeFrame {
  const kind = KIND_MAP[dto.type] ?? 'text_delta'
  return {
    caseId: dto.test_case_id,
    kind,
    textDelta: typeof dto.payload?.delta === 'string' ? dto.payload.delta : undefined,
    audioChunkBytes:
      typeof dto.payload?.size === 'number' ? dto.payload.size : undefined,
    round: dto.round_number ?? undefined,
    timestamp: dto.ts,
  }
}
