/**
 * run 失败原因 → 中文可操作说明：后端 run_finished.error 常是裸错误码，
 * 直接把 code 当正文会让人看不懂（EMPTY_MODEL_RESPONSE 等）。
 */
import { describe, expect, it } from 'vitest'

import { AGENT_ERROR_COPY, agentFailureText } from '@/domain/models/agent'

describe('agentFailureText', () => {
  it('已知错误码给可操作的中文指引', () => {
    const text = agentFailureText('EMPTY_MODEL_RESPONSE')
    expect(text).toContain('模型没有返回任何内容')
    expect(text).toContain('新建会话')
  })

  it('未知错误码原样保留，便于排查', () => {
    expect(agentFailureText('SOME_NEW_CODE')).toBe('SOME_NEW_CODE')
  })

  it('空错误退化为通用失败文案', () => {
    expect(agentFailureText(null)).toBe(AGENT_ERROR_COPY.runFailed)
    expect(agentFailureText('')).toBe(AGENT_ERROR_COPY.runFailed)
  })
})
