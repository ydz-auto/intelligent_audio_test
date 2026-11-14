/**
 * 审批变更预览（interfaces 层 ai-chat/approval）。
 *
 * 后端 `agent_approval.diff` 由 ToolGateway.proposal_diff 生成，REST 写工具的形态是
 * `{kind:'rest_request', method, path, arguments}`；M2 各域写工具可覆盖成字段级 diff。
 * 前端不解读业务语义，只按已知形态渲染，未知形态原样 JSON 展示 —— 不伪造 diff。
 */
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible'
import { ChevronDown } from 'lucide-react'

import { AGENT_APPROVAL_COPY } from '@/domain/models/agent'

const REST_DIFF_KIND = 'rest_request'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function toJsonText(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

/** 参数 / diff 的只读代码块（长内容折叠，不截断数据） */
export function ApprovalJsonBlock({
  label,
  value,
  testId,
}: {
  label: string
  value: unknown
  testId?: string
}) {
  if (value === undefined || value === null) return null
  if (isRecord(value) && Object.keys(value).length === 0) return null
  return (
    <Collapsible>
      <CollapsibleTrigger className='group text-muted-foreground hover:text-foreground flex w-full items-center gap-1 text-xs'>
        <ChevronDown className='size-3.5 transition-transform group-data-[panel-open]:rotate-180' />
        <span>{label}</span>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <pre
          className='bg-muted/40 text-foreground/90 mt-1 max-h-56 overflow-auto rounded-md p-2 font-mono text-[11px] leading-5'
          data-approval-json={testId}
        >
          {toJsonText(value)}
        </pre>
      </CollapsibleContent>
    </Collapsible>
  )
}

type ApprovalDiffProps = {
  diff: unknown
  /** 无 diff 时回退展示脱敏参数 */
  argumentsValue?: Record<string, unknown>
}

/** 变更预览：REST 请求（方法 + 路径 + 参数）优先，其余形态原样展示 */
export function ApprovalDiffPreview({
  diff,
  argumentsValue,
}: ApprovalDiffProps) {
  const isRest = isRecord(diff) && diff['kind'] === REST_DIFF_KIND
  const method = isRest ? diff['method'] : undefined
  const path = isRest ? diff['path'] : undefined
  const restArguments = isRest ? diff['arguments'] : undefined

  return (
    <div className='space-y-1.5' data-approval-diff>
      {isRest && (
        <div className='flex flex-wrap items-center gap-2'>
          <span className='text-muted-foreground text-xs'>
            {AGENT_APPROVAL_COPY.diffRequest}
          </span>
          {typeof method === 'string' && (
            <span className='bg-secondary text-secondary-foreground rounded px-1.5 py-0.5 font-mono text-[11px]'>
              {method}
            </span>
          )}
          {typeof path === 'string' && (
            <code className='text-foreground/90 break-all font-mono text-[11px]'>
              {path}
            </code>
          )}
        </div>
      )}
      {isRest ? (
        <ApprovalJsonBlock
          label={AGENT_APPROVAL_COPY.arguments}
          testId='rest-arguments'
          value={restArguments}
        />
      ) : (
        <ApprovalJsonBlock
          label={AGENT_APPROVAL_COPY.diff}
          testId='diff'
          value={diff}
        />
      )}
      {!isRest && (
        <ApprovalJsonBlock
          label={AGENT_APPROVAL_COPY.arguments}
          testId='arguments'
          value={argumentsValue}
        />
      )}
    </div>
  )
}
