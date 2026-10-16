/**
 * 灵犀Agent生成报告入口（15_报告域.md §3.2.1；08_AI对话页卡 INT-415 契约）。
 * 报告详情页报告头操作组按钮：文案「灵犀Agent生成报告」（lucide Sparkles），
 * 点击 → `/ai-chat?report={reportId}` 带当前报告 ID 进入对话式报告工作台
 * （对话式报告工作台功能设计文档.md:85 实测；工作台本体由 08 卡落位，本卡只挂按钮与传参）。
 */
import { useNavigate } from '@tanstack/react-router'
import { Sparkles } from 'lucide-react'

import { Button } from '@/components/ui/button'

interface AiChatEntryProps {
  /** 当前报告 ID（URL 契约：/ai-chat?report={id}） */
  reportId: number
  /** 是否渲染（report:read 持有者渲染；默认 true） */
  enabled?: boolean
}

export function AiChatEntry({ reportId, enabled = true }: AiChatEntryProps) {
  const navigate = useNavigate()

  if (!enabled) return null

  return (
    <Button
      variant='secondary'
      size='sm'
      onClick={() =>
        void navigate({ to: '/ai-chat', search: { report: String(reportId) } })
      }
      title='进入对话式报告工作台，生成可交付报告'
    >
      <Sparkles data-icon='inline-start' />
      灵犀Agent生成报告
    </Button>
  )
}
