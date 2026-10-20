/**
 * AI 复核会话 Dialog（interfaces 层 features/ai-review；19 规范 §5.2，INT-1064）。
 * 内嵌灵犀Agent 复核会话（Dialog sm:max-w-2xl，h-[min(70dvh,640px)] 内滚）：
 * 头行 Sparkles +「AI 复核」+ Demo 徽标 +「展开到 /ai-chat」+ 关闭；
 * 头行下复核上下文摘要条（§5.3）；会话区复用 AiChat compact（有界会话 scope，
 * 独立 localStorage 键 iatp:ai-chat:v1:review:{taskId}:{caseId}，不污染主会话）；
 * 结论卡（§5.4）/ AI 复核记录卡（§5.5）+ 底栏「稍后处理」「保存复核结论」。
 * 对话走用户自配 LLM 供应商（Demo）；「保存复核结论」落位走真实后端端点
 * （POST /tasks/results/ai-review，INT-800 done）——两者分离（§3.10/§5.6）。
 */
import { Maximize2, Sparkles, X } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Alert, AlertDescription } from '@/components/ui/alert'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { AiChat } from '@/features/ai-chat/components/chat/ai-chat'
import { AiChatInput } from '@/features/ai-chat/components/input/ai-chat-input'
import { ProviderManager } from '@/features/ai-chat/components/input/provider-manager'
import { DEMO_COPY } from '@/features/ai-chat/constants'

import { useAiReviewSession } from '@/application/ai-review/use-ai-review-session'
import { AiReviewContextCard } from '@/features/ai-review/ai-review-context-card'
import { AiReviewVerdictCard } from '@/features/ai-review/ai-review-verdict-card'
import { AiReviewRecordCard } from '@/features/ai-review/ai-review-record-card'

export function AiReviewSessionDialog({
  open,
  onOpenChange,
  taskId,
  caseId,
  caseName,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  taskId: number
  caseId: string
  caseName?: string
}) {
  const s = useAiReviewSession({ taskId, caseId, open })
  const context = s.contextQuery.context

  /** 最后一条完整 assistant 回复（Agent 分析文本；结论卡摘要源） */
  const latestAssistantText = [...s.messages]
    .reverse()
    .find(
      (m) =>
        m.from === 'assistant' &&
        (m.status === 'complete' || m.status === 'streaming') &&
        (m.versions[0]?.content ?? '').trim().length > 0
    )?.versions[0]?.content

  const handleAdopt = async () => {
    const ok = await s.ai.adopt()
    if (ok) onOpenChange(false)
  }
  const handleReject = async () => {
    await s.ai.reject()
    onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className='sm:max-w-2xl'
        data-slot='ai-review-session-dialog'
        aria-describedby={undefined}
      >
        <div className='flex h-[min(70dvh,640px)] flex-col overflow-hidden'>
          <DialogHeader className='text-start'>
            <div className='flex flex-wrap items-center gap-2'>
              <DialogTitle className='flex items-center gap-1.5 text-base font-semibold'>
                <Sparkles aria-hidden='true' className='text-primary size-4' />
                AI 复核
                {caseName && (
                  <span className='text-muted-foreground max-w-56 truncate text-sm font-normal'>
                    — {caseName}
                  </span>
                )}
              </DialogTitle>
              <Tooltip>
                <TooltipTrigger
                  render={
                    <Badge variant='warning' className='cursor-help'>
                      {DEMO_COPY.badge}
                    </Badge>
                  }
                />
                <TooltipContent>
                  <p>对话为 Demo 预览，使用你配置的 LLM 供应商；「保存复核结论」为真实 AI 复核记录</p>
                </TooltipContent>
              </Tooltip>
              <div className='ms-auto flex items-center gap-0.5'>
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Button
                        aria-label='展开到 /ai-chat'
                        className='text-muted-foreground hover:text-foreground size-7'
                        onClick={s.expandToAiChat}
                        type='button'
                        variant='ghost'
                        disabled={!context}
                      >
                        <Maximize2 className='size-4' />
                      </Button>
                    }
                  />
                  <TooltipContent>展开到 /ai-chat 带入主会话继续追问</TooltipContent>
                </Tooltip>
                <Button
                  aria-label='关闭'
                  className='text-muted-foreground hover:text-foreground size-7'
                  onClick={() => onOpenChange(false)}
                  type='button'
                  variant='ghost'
                >
                  <X className='size-4' />
                </Button>
              </div>
            </div>
            <p className='text-muted-foreground text-xs'>
              由灵犀Agent 对当前评估结果进行复核，可追问；结论供人工确认，不直接修改统计
            </p>
          </DialogHeader>

          {/* 复核上下文摘要条（§5.3；加载态 Skeleton / 失败 Alert 重试） */}
          <div className='shrink-0 px-4 pb-2'>
            {!open || s.contextQuery.isLoading ? (
              <Skeleton className='h-16 w-full rounded-xl' />
            ) : s.contextQuery.isError || !context ? (
              <Alert variant='destructive'>
                <AlertDescription className='text-xs'>
                  复核上下文加载失败，请重试
                  <Button
                    variant='outline'
                    size='sm'
                    className='ms-2 h-6 px-2 text-xs'
                    onClick={s.contextQuery.refetch}
                  >
                    重试
                  </Button>
                </AlertDescription>
              </Alert>
            ) : (
              <AiReviewContextCard context={context} />
            )}
          </div>

          {/* 会话区（AiChat compact，有界会话 scope；粘底滚动由 Conversation 承担） */}
          <div className='flex min-h-0 flex-1 flex-col overflow-hidden px-3'>
            <AiChat
              compact
              editingKey={s.editingMessageKey}
              isGenerating={s.isGenerating}
              isLoadingMessages={false}
              messages={s.messages}
              onCancelEdit={s.handleEditOpenChange}
              onDeleteMessage={s.handleDeleteMessage}
              onEditMessage={s.handleEditMessage}
              onEditPromptMessage={s.handleEditPromptMessage}
              onRegenerateMessage={s.handleRegenerateMessage}
              onSaveEdit={(content) => s.applyEdit(content, false)}
              onSaveEditAndSubmit={(content) => s.applyEdit(content, true)}
              onUndoMessage={s.handleUndoMessage}
            />

            {/* 结论/记录卡（§5.4/§5.5）：Agent 分析完成 → 结论卡；保存落位 → AI 复核记录卡 */}
            <div className='shrink-0 space-y-2 px-3 pb-2'>
              {s.ai.error && (
                <Alert variant='destructive'>
                  <AlertDescription className='flex items-center gap-2 text-xs'>
                    AI 复核失败：{s.ai.error}
                    <Button
                      variant='outline'
                      size='sm'
                      className='ms-auto h-6 px-2 text-xs'
                      onClick={() => s.ai.reset()}
                    >
                      重试
                    </Button>
                  </AlertDescription>
                </Alert>
              )}
              {s.ai.record &&
                (s.ai.phase === 'completed' ||
                  s.ai.phase === 'adopted' ||
                  s.ai.phase === 'rejected') && (
                  <AiReviewRecordCard
                    record={s.ai.record}
                    originalEvaluationStatus={context?.evaluationStatus}
                    onAdopt={() => void handleAdopt()}
                    onReject={() => void handleReject()}
                    disposition={
                      s.ai.phase === 'adopted'
                        ? 'adopted'
                        : s.ai.phase === 'rejected'
                          ? 'rejected'
                          : undefined
                    }
                    disabled={s.ai.phase !== 'completed'}
                  />
                )}
              {s.ai.phase === 'running' && (
                <p className='text-muted-foreground animate-pulse text-xs'>
                  AI 复核中…（后端复检链路执行中，完成后展示记录卡）
                </p>
              )}
              {s.ai.phase === 'idle' && latestAssistantText && s.canSave && (
                <AiReviewVerdictCard
                  analysis={latestAssistantText}
                  onAskQuick={s.handleAskQuick}
                />
              )}
            </div>
          </div>

          {/* 输入区（AiChatInput compact；模型/供应商切换复用，无参数面板） */}
          <div className='shrink-0 px-1 pb-1'>
            <AiChatInput
              compact
              config={s.config}
              disabled={s.isGenerating}
              hasMessages={s.messages.length > 0}
              isGenerating={s.isGenerating}
              onClearMessages={s.handleClearMessages}
              onManageProviders={() => s.setProviderManagerOpen(true)}
              onSelectModel={s.handleSelectModel}
              onSelectProvider={s.handleSelectProvider}
              onStop={s.stopGeneration}
              onSubmit={s.handleSendMessage}
              onValueChange={s.setDraftText}
              providers={s.providers}
              value={s.draftText}
            />
          </div>

          {/* 底栏（§5.2：［稍后处理］［保存复核结论］→ POST /ai-review 落位） */}
          <DialogFooter className='border-t px-4 py-2.5'>
            <Button
              variant='ghost'
              size='sm'
              onClick={() => onOpenChange(false)}
              disabled={s.ai.phase === 'running'}
            >
              稍后处理
            </Button>
            {s.ai.phase === 'running' ? (
              <Button size='sm' disabled>
                保存中…
              </Button>
            ) : s.ai.phase === 'completed' ||
              s.ai.phase === 'adopted' ||
              s.ai.phase === 'rejected' ? (
              <Button size='sm' variant='outline' onClick={() => onOpenChange(false)}>
                关闭
              </Button>
            ) : (
              <Button size='sm' disabled={!s.canSave} onClick={s.handleSave}>
                <Sparkles aria-hidden='true' className='size-3.5' />
                保存复核结论
              </Button>
            )}
          </DialogFooter>
        </div>

        {/* LLM 供应商管理（§3.11；复核会话与主会话共用同一供应商清单） */}
        <ProviderManager
          onAdd={s.addProvider}
          onFetchModels={s.fetchModels}
          onOpenChange={s.setProviderManagerOpen}
          onRemove={s.removeProvider}
          onSetDefault={s.setDefaultProvider}
          onTestConnection={s.testConnection}
          onUpdate={s.updateProvider}
          open={s.providerManagerOpen}
          providers={s.providers}
        />
      </DialogContent>
    </Dialog>
  )
}
