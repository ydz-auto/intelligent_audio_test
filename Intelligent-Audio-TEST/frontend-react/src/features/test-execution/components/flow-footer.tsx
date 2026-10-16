/**
 * FlowFooter 底部动作条（interfaces/features/test-execution/components；10_测试执行.md §3.1）。
 * 照 StepNavigation + PromptInputFooter 语义：`border-t bg-background/95 dark:bg-background/80
 * backdrop-blur px-4 py-2.5 flex items-center justify-between gap-3`。
 * 左=上下文提示区（voice_llm 提示/校验错误摘要）；右=随步骤按钮组：
 * 步骤0 仅「下一步」/ 步骤1「上一步+下一步」/ 步骤2「上一步+开始测试→任务名称弹窗」/
 * 步骤3 无按钮（执行控制在内容区）/ 步骤4 报告动作组（上一步隐藏）；
 * 只读观察态（§3.1.1）：仅 info 文案「当前为只读观察模式，不可执行测试」，无任何按钮。
 */
import { ChevronLeft, FileBarChart, Rocket } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import type { FlowStep } from '@/application/test-execution/useFlowSteps'

interface FlowFooterProps {
  step: FlowStep
  readOnly: boolean
  /** 左区上下文提示 */
  hint?: string
  onPrev: () => void
  /** 步骤 0-1：下一步 */
  onNext: () => void
  /** 步骤 2：开始测试（打开任务名称弹窗） */
  onStart: () => void
  startPending?: boolean
  /** 步骤 4 报告动作组 */
  canSaveReport: boolean
  onSaveReport: () => void
  savingReport?: boolean
  onExportReport: () => void
  canPublishReport: boolean
  onPublishReport: () => void
  onGoReportCenter: () => void
  onNewTest: () => void
}

export function FlowFooter({
  step,
  readOnly,
  hint,
  onPrev,
  onNext,
  onStart,
  startPending,
  canSaveReport,
  onSaveReport,
  savingReport,
  onExportReport,
  canPublishReport,
  onPublishReport,
  onGoReportCenter,
  onNewTest,
}: FlowFooterProps) {
  const showPrev = step === 1 || step === 2

  return (
    <div className='bg-background/95 supports-[backdrop-filter]:bg-background/80 shrink-0 border-t px-4 py-2.5 backdrop-blur'>
      <div className='mx-auto flex w-full max-w-5xl items-center justify-between gap-3'>
        <div className='text-muted-foreground min-w-0 flex-1 text-xs'>
          {readOnly ? (
            <span className='text-info flex items-center gap-1.5'>
              <span className='bg-info/15 text-info inline-flex h-4 items-center rounded-full px-2 text-[11px] font-medium'>
                只读
              </span>
              当前为只读观察模式，不可执行测试
            </span>
          ) : (
            hint
          )}
        </div>

        {!readOnly && (
          <div className='flex shrink-0 items-center gap-2'>
            {showPrev && (
              <Button variant='outline' size='sm' onClick={onPrev}>
                <ChevronLeft aria-hidden='true' className='size-3.5' />
                上一步
              </Button>
            )}
            {(step === 0 || step === 1) && (
              <Button size='sm' onClick={onNext}>
                下一步
              </Button>
            )}
            {step === 2 && (
              <Button size='sm' disabled={startPending} onClick={onStart}>
                {startPending ? (
                  <>
                    <Spinner className='size-3.5' />
                    正在启动…
                  </>
                ) : (
                  <>
                    <Rocket aria-hidden='true' className='size-3.5' />
                    开始测试
                  </>
                )}
              </Button>
            )}
            {step === 4 && (
              <>
                {canSaveReport && (
                  <Button variant='outline' size='sm' disabled={savingReport} onClick={onSaveReport}>
                    {savingReport ? (
                      <>
                        <Spinner className='size-3.5' />
                        保存中…
                      </>
                    ) : (
                      '保存报告'
                    )}
                  </Button>
                )}
                <Button variant='outline' size='sm' onClick={onExportReport}>
                  导出报告
                </Button>
                {canPublishReport && (
                  <Button size='sm' onClick={onPublishReport}>
                    <Rocket aria-hidden='true' className='size-3.5' />
                    发布报告
                  </Button>
                )}
                <Button variant='ghost' size='sm' onClick={onGoReportCenter}>
                  <FileBarChart aria-hidden='true' className='size-3.5' />
                  前往报告中心
                </Button>
                <Button variant='outline' size='sm' onClick={onNewTest}>
                  开始新测试
                </Button>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
