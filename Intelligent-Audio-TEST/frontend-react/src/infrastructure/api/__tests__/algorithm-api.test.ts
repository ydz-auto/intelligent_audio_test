/**
 * 算法选项 API 单测（接线壳 INT-607）：GET /algorithm/options → snake_case DTO
 * → camelCase Domain（value=算法类型码，与 useAlgorithmStore.algorithmId 同源）。
 * mock client 层按真实端点响应形态（data.algorithms）验证转换链。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchAlgorithmOptions } from '@/infrastructure/api/algorithm-api'

const getMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/client', () => ({
  apiClient: { get: getMock },
}))

describe('fetchAlgorithmOptions', () => {
  beforeEach(() => {
    getMock.mockReset()
  })

  it('真实 data.algorithms 形态 snake→camel 转换（value=算法类型码）', async () => {
    getMock.mockResolvedValue({
      algorithms: [
        {
          value: 'voice_llm',
          name: '小艺语音大模型',
          group_id: null,
          group_name: null,
          icon: null,
        },
        {
          value: 'asr-stream',
          name: '流式识别引擎',
          group_id: 2,
          group_name: '流式',
          icon: 'stream',
        },
      ],
    })
    const options = await fetchAlgorithmOptions()
    expect(getMock).toHaveBeenCalledWith('/algorithm/options')
    expect(options).toEqual([
      { value: 'voice_llm', name: '小艺语音大模型' },
      { value: 'asr-stream', name: '流式识别引擎' },
    ])
  })

  it('空 algorithms 回空数组（不抛错）', async () => {
    getMock.mockResolvedValue({ algorithms: [] })
    await expect(fetchAlgorithmOptions()).resolves.toEqual([])
  })
})
