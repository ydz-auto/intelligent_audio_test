/**
 * INT-736：算法卡片网格——definitions 加载 + display_order 排序 + 全局 store 读写 + 参数摘要。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'
import { getAlgorithmParamSummary, useAlgorithmCards } from '../useAlgorithmCards'

const mocks = vi.hoisted(() => ({
  getDefinitions: vi.fn(),
}))

vi.mock('@/composables/algorithm/algorithmPort', () => ({
  algorithmPort: { getDefinitions: mocks.getDefinitions },
}))

import type { AlgorithmDefinition } from '../../../domain/model/algorithm'

function makeAlgo(overrides: Partial<AlgorithmDefinition>): AlgorithmDefinition {
  return {
    id: 1,
    type: 'asr',
    name: 'ASR 识别',
    displayOrder: 0,
    status: 'online',
    ...overrides,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  setActivePinia(createPinia())
})

describe('useAlgorithmCards', () => {
  it('load 拉取 definitions 并按 display_order 排序', async () => {
    mocks.getDefinitions.mockResolvedValue({
      data: [
        makeAlgo({ id: 1, type: 'tts', name: 'TTS', displayOrder: 3 }),
        makeAlgo({ id: 2, type: 'asr', name: 'ASR', displayOrder: 1 }),
        makeAlgo({ id: 3, type: 'translation', name: '翻译', displayOrder: 2 }),
      ],
    })
    const cards = useAlgorithmCards()
    await cards.load()
    expect(cards.definitions.value.map(a => a.type)).toEqual(['asr', 'translation', 'tts'])
    expect(cards.error.value).toBeNull()
  })

  it('load 失败收敛为 error（不抛出），供视图层降级条渲染', async () => {
    mocks.getDefinitions.mockRejectedValue(new Error('403'))
    const cards = useAlgorithmCards()
    await cards.load()
    expect(cards.definitions.value).toHaveLength(0)
    expect(cards.error.value).toBeTruthy()
  })

  it('select(null) 写回「全部算法」，select(type) 写回具体算法并持久化 localStorage', async () => {
    const cards = useAlgorithmCards()
    cards.select('asr')
    expect(cards.selectedType.value).toBe('asr')
    expect(localStorage.getItem('iatp:algorithm:v1')).toBe('asr')

    cards.select(null)
    expect(cards.selectedType.value).toBeNull()
    expect(localStorage.getItem('iatp:algorithm:v1')).toBeNull()
  })
})

describe('getAlgorithmParamSummary', () => {
  it('设备/API/用例参数按长度派生摘要', () => {
    const algo = makeAlgo({
      deviceParams: [{ id: 1, algorithmType: 'asr', paramCode: 'a', paramType: 'string' }],
      apiParams: [{ id: 2, algorithmType: 'asr', paramCode: 'b', paramType: 'string' }],
      caseParams: [{ id: 3, algorithmType: 'asr', paramCode: 'c' }],
    })
    expect(getAlgorithmParamSummary(algo)).toBe('设备参数 1 · API 参数 1 · 用例参数 1')
  })

  it('三项全 0/缺失时返回空字符串（隐藏摘要行）', () => {
    expect(getAlgorithmParamSummary(makeAlgo({}))).toBe('')
  })
})
