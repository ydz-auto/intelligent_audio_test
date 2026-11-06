/**
 * 消息元数据（interfaces 层 ai-chat/message；08_AI对话页.md §3.4 照 newAPI message-metadata）：
 * 时:分:秒 + 「响应时间：{n}」 text-[11px] text-muted-foreground。
 */
import { Clock } from 'lucide-react'

import {
  formatDuration,
  formatMessageTime,
} from '@/features/ai-chat/lib/message'

type MessageMetadataProps = {
  timestamp?: number
  durationMs?: number
}

export function MessageMetadata({
  timestamp,
  durationMs,
}: MessageMetadataProps) {
  return (
    <div className='text-muted-foreground mt-1 flex items-center gap-1.5 text-[11px] leading-none'>
      {timestamp && <span>{formatMessageTime(timestamp)}</span>}
      {durationMs !== undefined && durationMs > 0 && (
        <>
          <span aria-hidden='true'>·</span>
          <span className='inline-flex items-center gap-1'>
            <Clock className='size-3' />
            响应时间：{formatDuration(durationMs)}
          </span>
        </>
      )}
    </div>
  )
}
