/**
 * Realtime frame 事件 DTO（infrastructure/dto 层——snake_case 唯一出现层；10_测试执行.md §9）。
 * §3.7：frame 通道事件不落库，Socket.IO room=task_id 推送；原始字段经 frameEventAdapter
 * 转 camelCase 枚举消费，Presentation 层不感知 snake_case（对齐五层对称模板 §5.3）。
 */

/** frame 事件原始类型（API测试功能设计文档 §5.3 实测） */
export type FrameEventTypeDto =
  | 'ai_text_delta'
  | 'ai_audio_delta'
  | 'user_speech_started'
  | 'user_speech_ended'
  | 'round_started'
  | 'round_completed'

/** frame 通道事件原始载荷（snake_case） */
export interface FrameEventDto {
  case_id: string
  event_type: FrameEventTypeDto
  data: {
    text_delta?: string
    audio_progress?: number
    round?: number
    [key: string]: unknown
  }
  ts: string
}
