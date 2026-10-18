/**
 * Realtime frame 事件 DTO（infrastructure/dto 层——snake_case 唯一出现层；10_测试执行.md §9）。
 * INT-646 返修：按后端 EventBus 载荷实测对齐（api_test_service/infrastructure/messaging/
 * realtime_stream_publisher.py：publish_frame 载荷 task_id/test_case_id/session_id/
 * round_number/seq/channel/type/payload/ts；经 api_gateway sse_bp REPORT_EVENTS →
 * realtime_frame 事件名转发）。原始字段经 frameEventAdapter 转 camelCase 枚举消费，
 * Presentation 层不感知 snake_case。
 */

/** frame 事件原始类型（RealtimeEventType 归一化枚举；shared/models/common_enums.py） */
export type FrameEventTypeDto =
  | 'ai_text_delta'
  | 'ai_audio_delta'
  | 'ai_text_done'
  | 'ai_audio_done'
  | 'user_speech_started'
  | 'user_speech_stopped'
  | 'response_cancelled'
  | 'error'
  | 'session.created'
  | 'session.updated'
  | 'connection_closed'

/** frame 通道事件原始载荷（snake_case；后端 publish_frame 实测） */
export interface FrameEventDto {
  task_id: string
  test_case_id: string
  session_id?: string | null
  round_number?: number
  seq: number
  /** 通道枚举值（RealtimeChannel.FRAME = 'frame'） */
  channel: string
  /** 归一化事件类型 */
  type: FrameEventTypeDto
  payload?: {
    /** 文字流增量（ai_text_delta） */
    text_delta?: string
    /**
     * ai_audio_delta 载荷实测仅推分片字节数（size），后端不推 0-100 百分比；
     * contract 缺口：前端音频进度条暂缺该值，见 frameEventAdapter 注释（不动后端口径）。
     */
    size?: number
    [key: string]: unknown
  }
  ts: string
}
