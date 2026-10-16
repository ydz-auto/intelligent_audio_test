/**
 * 算法配置 API 桩单测（infrastructure/api；mock 内存库 CRUD 行为）。
 * 覆盖列表/分组读取、新建/编辑、删除引用中算法拦截、批量删除、分组删除含算法拦截。
 */
import { beforeEach, describe, expect, it } from 'vitest'

import {
  __resetAlgorithmMock,
  bulkDeleteAlgorithms,
  createAlgorithm,
  createAlgorithmGroup,
  deleteAlgorithm,
  deleteAlgorithmGroup,
  fetchAlgorithmDefinitions,
  fetchAlgorithmGroups,
  updateAlgorithm,
} from '@/infrastructure/api/algorithm-config-api'
import type { SaveAlgorithmInput } from '@/infrastructure/api/algorithm-config-api'

function saveInput(type: string): SaveAlgorithmInput {
  return {
    type,
    name: `${type} 名称`,
    groupId: 1,
    displayOrder: 1,
    status: 'online',
    description: '',
    deviceParams: [],
    apiParams: [],
    caseParams: [],
    referenceParams: [],
    mappings: { device: [], api: [], evaluation: [] },
    associatedDimensions: [],
  }
}

describe('algorithm-config-api（mock 桩）', () => {
  beforeEach(() => {
    __resetAlgorithmMock()
  })

  it('列表返回全量定义与分组（§3.2 全量返回语义）', async () => {
    const definitions = await fetchAlgorithmDefinitions()
    expect(definitions.length).toBeGreaterThan(0)
    expect(definitions[0].type).toBeTruthy()
    const groups = await fetchAlgorithmGroups()
    expect(groups.some((g) => g.algorithmCount > 0)).toBe(true)
  })

  it('新建算法追加到列表并联动分组计数', async () => {
    const created = await createAlgorithm(saveInput('tts-new'))
    expect(created.type).toBe('tts-new')
    expect(created.groupName).toBe('语音识别')
    const definitions = await fetchAlgorithmDefinitions()
    expect(definitions.some((d) => d.type === 'tts-new')).toBe(true)
  })

  it('编辑算法更新显示名称', async () => {
    const input = saveInput('asr-v3')
    input.name = '改名后的识别引擎'
    const updated = await updateAlgorithm('asr-v3', input)
    expect(updated.name).toBe('改名后的识别引擎')
  })

  it('删除被引用算法被拦截（caseCount>0 语义，§6.7 删除失败路径）', async () => {
    // asr-v3 关联用例数 50，删除应失败
    const result = await deleteAlgorithm('asr-v3')
    expect(result.success).toBe(false)
    const definitions = await fetchAlgorithmDefinitions()
    expect(definitions.some((d) => d.type === 'asr-v3')).toBe(true)
  })

  it('批量删除跳过被引用算法并返回成功/失败计数（§7.8）', async () => {
    // 先新建一个未引用算法（caseCount=0），保证批量删除有成功项
    await createAlgorithm(saveInput('tts-brand-new'))
    const result = await bulkDeleteAlgorithms(['asr-v3', 'tts-brand-new'])
    // asr-v3 被引用失败，tts-brand-new 成功
    expect(result.failedCount).toBeGreaterThan(0)
    expect(result.successCount).toBe(1)
    const definitions = await fetchAlgorithmDefinitions()
    expect(definitions.some((d) => d.type === 'tts-brand-new')).toBe(false)
    expect(definitions.some((d) => d.type === 'asr-v3')).toBe(true)
  })

  it('分组 CRUD：新建计数为 0，删除含算法分组被拦截（§7.1 cascade 语义）', async () => {
    const created = await createAlgorithmGroup({
      name: '新分组',
      description: '',
      icon: '',
      displayOrder: 9,
    })
    expect(created.algorithmCount).toBe(0)

    const deleted = await deleteAlgorithmGroup(1) // 语音识别组含算法
    expect(deleted.success).toBe(false)
    expect(deleted.message).toContain('包含')

    const emptyDeleted = await deleteAlgorithmGroup(created.id)
    expect(emptyDeleted.success).toBe(true)
  })
})
