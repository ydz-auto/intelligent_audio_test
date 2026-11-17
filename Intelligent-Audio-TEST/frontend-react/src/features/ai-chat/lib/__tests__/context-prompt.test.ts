/**
 * 绑定上下文请求前缀（报告工作模式选 #420 却分析 #426 的回归保护）：
 * 选择器只写会话 config，发送时必须把 id 拼进本轮 message。
 */
import { describe, expect, it } from 'vitest'

import type { ChatConfig } from '@/domain/models/aiChat'
import { buildBoundContextPrefix } from '@/features/ai-chat/lib/context-prompt'

function config(partial: Partial<ChatConfig>): ChatConfig {
  return { chatMode: 'platform', ...partial }
}

describe('buildBoundContextPrefix', () => {
  it('未绑定上下文 → null，不改写用户输入', () => {
    expect(buildBoundContextPrefix(config({}))).toBeNull()
  })

  it('已解析名称的测试报告 → 前缀带类型、id 与名称', () => {
    const prefix = buildBoundContextPrefix(
      config({
        reportContextId: '420',
        reportContextLabel: '豆包-话筒接口测试',
        reportContextType: 'task',
      })
    )

    expect(prefix).toContain('【已绑定上下文】测试报告 #420')
    expect(prefix).toContain('「豆包-话筒接口测试」')
    expect(prefix).toContain('不要改用其他测试报告')
  })

  it('名称未解析（降级名已含 #id）→ 不重复拼名称', () => {
    const prefix = buildBoundContextPrefix(
      config({
        reportContextId: '420',
        reportContextLabel: '报告 #420',
        reportContextType: 'task',
      })
    )

    expect(prefix).toContain('测试报告 #420。')
    expect(prefix).not.toContain('「报告 #420」')
  })

  it('任务上下文 → 按「任务」口径声明来源', () => {
    const prefix = buildBoundContextPrefix(
      config({
        reportContextId: '460',
        reportContextLabel: '豆包-话筒接口测试',
        reportContextType: 'task_context',
      })
    )

    expect(prefix).toContain('【已绑定上下文】任务 #460')
    expect(prefix).toContain('不要改用其他任务')
  })

  it('对比报告 → 用对比报告口径，避免与测试报告混用', () => {
    const prefix = buildBoundContextPrefix(
      config({
        reportContextId: '512',
        reportContextType: 'comparison',
      })
    )

    expect(prefix).toContain('对比报告 #512')
  })
})
