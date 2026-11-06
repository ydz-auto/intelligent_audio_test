/**
 * AI 复核结论卡（interfaces 层 features/ai-review；19 规范 §5.4）。
 * 灵犀Agent 分析完成后的结构化结论卡：Agent 分析摘要 + 快捷追问 chips +
 * 「保存复核结论」说明（保存后由后端复检链路落位 ai_reviews 记录，§5.5 方案 A）。
 * 保存/稍后处理动作在会话底栏（§5.2）；本卡负责结论呈现与追问入口。
 */
import { Sparkles } from 'lucide-react'

import { cn } from '@/lib/utils'

export function AiReviewVerdictCard({
  analysis,
  onAskQuick,
  saving = false,
}: {
  /** Agent 最新分析文本（最后一条 assistant 完整回复） */
  analysis: string
  /** 快捷追问 chips（§5.4：照 08 §3.4 Suggestion 语义，点击即发送） */
  onAskQuick?: (text: string) => void
  saving?: boolean
}) {
  const chips = ['哪个维度失分最多？', '对比其他设备的表现', '给出逐设备复核意见']

  return (
    <div className='rounded-xl border px-3 py-2.5'>
      <div className='flex flex-wrap items-center gap-2'>
        <Sparkles aria-hidden='true' className='text-primary size-4' />
        <span className='text-sm font-medium'>AI 复核结论</span>
        {saving && (
          <span className='text-muted-foreground animate-pulse text-xs'>
            AI 复核中…
          </span>
        )}
      </div>
      <p className='text-muted-foreground mt-2 line-clamp-3 text-xs leading-5'>
        {analysis || '灵犀Agent 已完成分析，可保存复核结论交由后端复检落位。'}
      </p>
      <div className='mt-2 flex flex-wrap gap-1.5'>
        {chips.map((chip) => (
          <button
            key={chip}
            type='button'
            disabled={saving}
            onClick={() => onAskQuick?.(chip)}
            className={cn(
              'text-muted-foreground hover:text-foreground hover:bg-accent disabled:opacity-50 h-6 cursor-pointer rounded-md border px-2 text-[11px] transition-colors'
            )}
          >
            {chip}
          </button>
        ))}
      </div>
      <p className='text-muted-foreground/70 mt-2 border-t pt-1.5 text-[11px]'>
        保存后由后端复检链路落位 AI 复核记录（真实端点），供采纳为人工复核结果或驳回。
      </p>
    </div>
  )
}
