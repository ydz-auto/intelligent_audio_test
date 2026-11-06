/**
 * 评估分类保存 API 单测（INT-1552）：POST /evaluation/categories 返回的真实分类 id
 * 必须透传给调用方（维度抽屉内联新建分类回填 category_id，不再用临时负 id）。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { saveEvaluationCategory } from '@/infrastructure/api/evaluation-api'

const requestMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/client', () => ({ request: requestMock }))

describe('saveEvaluationCategory', () => {
  beforeEach(() => {
    requestMock.mockReset()
  })

  it('新增分类 POST /evaluation/categories，透传后端返回的真实 id', async () => {
    requestMock.mockResolvedValue({ id: 42 })
    const result = await saveEvaluationCategory({ name: '接线测试_分类' })
    expect(requestMock).toHaveBeenCalledWith('POST', '/evaluation/categories', {
      name: '接线测试_分类',
    })
    expect(result).toEqual({ success: true, id: 42 })
  })

  it('后端未下发 id 时 id 为 null（调用方据此提示失败）', async () => {
    requestMock.mockResolvedValue(null)
    await expect(saveEvaluationCategory({ name: '接线测试_分类' })).resolves.toEqual({
      success: true,
      id: null,
    })
  })

  it('编辑分类走 PUT /evaluation/categories/{id}', async () => {
    requestMock.mockResolvedValue(undefined)
    await expect(saveEvaluationCategory({ id: 7, name: '接线测试_分类' })).resolves.toEqual({
      success: true,
      id: 7,
    })
    expect(requestMock).toHaveBeenCalledWith('PUT', '/evaluation/categories/7', {
      name: '接线测试_分类',
    })
  })
})
