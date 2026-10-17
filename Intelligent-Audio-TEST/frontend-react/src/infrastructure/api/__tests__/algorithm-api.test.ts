/**
 * 算法选项 API 单测（接线壳 INT-607）：GET /algorithm/options → snake_case DTO
 * → camelCase Domain（value=type 算法类型码）。mock client 层验证转换链。
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

  it('options 列表 snake→camel 转换（value=type）', async () => {
    getMock.mockResolvedValue({
      options: [
        { id: 1, name: '通用识别引擎', type: 'asr-v3' },
        { id: 2, name: '流式识别引擎', type: 'asr-stream' },
      ],
    })
    const options = await fetchAlgorithmOptions()
    expect(getMock).toHaveBeenCalledWith('/algorithm/options')
    expect(options).toEqual([
      { value: 'asr-v3', name: '通用识别引擎' },
      { value: 'asr-stream', name: '流式识别引擎' },
    ])
  })

  it('空 options 回空数组（不抛错）', async () => {
    getMock.mockResolvedValue({ options: [] })
    await expect(fetchAlgorithmOptions()).resolves.toEqual([])
  })
})
