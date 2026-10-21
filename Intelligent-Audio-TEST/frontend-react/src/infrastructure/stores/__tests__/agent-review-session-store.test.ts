import { describe, expect, it, beforeEach } from 'vitest'

import { useAgentReviewSessionStore } from '@/infrastructure/stores/agentReviewSessionStore'

describe('agentReviewSessionStore', () => {
  beforeEach(() => {
    useAgentReviewSessionStore.setState({ sessions: {} })
  })

  it('updateConfig persists to the scope key', () => {
    useAgentReviewSessionStore.getState().updateConfig(1257, 'case-1', 'modelId', 'mock-model-1')
    const state = useAgentReviewSessionStore.getState()
    const session = state.sessions['iatp:ai-chat:v1:review:1257:case-1']
    expect(session).toBeDefined()
    expect(session?.config.modelId).toBe('mock-model-1')
  })

  it('updateMessages persists messages to the scope key', () => {
    useAgentReviewSessionStore.getState().updateMessages(1257, 'case-1', (prev) => [...prev, { key: 'a', from: 'user', versions: [{ id: 'a1', content: 'x' }] }])
    const session = useAgentReviewSessionStore.getState().sessions['iatp:ai-chat:v1:review:1257:case-1']
    expect(session?.messages.length).toBe(1)
  })

  it('resetSession clears the scope', () => {
    useAgentReviewSessionStore.getState().updateConfig(1257, 'case-1', 'modelId', 'm')
    useAgentReviewSessionStore.getState().resetSession(1257, 'case-1')
    expect(useAgentReviewSessionStore.getState().sessions).toEqual({})
  })
})
