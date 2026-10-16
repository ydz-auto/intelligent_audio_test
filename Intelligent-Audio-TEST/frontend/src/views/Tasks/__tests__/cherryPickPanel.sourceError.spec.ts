/**
 * INT-552：挑选合并页签「源结果溯源」加载失败错误态（审计 P2-2）。
 *
 * 缺陷：CherryPickPanel loadSource catch 静默置 sourcesByTask[taskId]=[]，
 * 溯源接口失败时展开区显示「该挑选合并任务暂无来源记录」，与真无来源混淆。
 * 修复：per-task error ref + 重试，v-if 三分（loading / 分组 / 错误 / 空态）。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

const api = vi.hoisted(() => ({ getSource: vi.fn() }))

vi.mock('../../../infrastructure/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../infrastructure/api')>()
  return {
    ...actual,
    cherryPickApi: { getSource: api.getSource },
  }
})

import CherryPickPanel from '../CherryPickPanel.vue'

const CT = (id: number) => ({ id, name: `挑选合并任务${id}`, status: 'completed' })

const cherryPickProp = () => ({
  loading: false,
  items: [CT(1), CT(2)],
  total: 2,
  page: 1,
  perPage: 10,
  pages: 1,
  setPage: vi.fn(),
  setPageSize: vi.fn(),
  fetchList: vi.fn(),
})

beforeEach(() => {
  vi.clearAllMocks()
  api.getSource.mockResolvedValue({ groups: [] })
})

async function mountPanel() {
  const w = mount(CherryPickPanel, {
    props: {
      cherryPick: cherryPickProp(),
      taskActions: [],
      isFavorite: () => false,
    },
    global: {
      stubs: { TaskCard: true, PaginationComponent: true },
    },
  })
  await flushPromises()
  return w
}

describe('INT-552：溯源加载失败错误态（审计 P2-2）', () => {
  it('getSource reject → 展开区显示错误+重试，不显示「暂无来源」误导文案', async () => {
    api.getSource.mockRejectedValue(new Error('溯源服务不可用'))
    const w = await mountPanel()
    await w.findAll('.merged-source-list-title')[0].trigger('click')
    await flushPromises()

    const err = w.find('.merged-source-error')
    expect(err.exists()).toBe(true)
    expect(err.text()).toContain('溯源加载失败')
    expect(err.text()).toContain('溯源服务不可用')
    expect(w.text()).not.toContain('该挑选合并任务暂无来源记录')
  })

  it('错误后点重试成功 → 错误消失、溯源分组展示', async () => {
    api.getSource
      .mockRejectedValueOnce(new Error('网络抖动'))
      .mockResolvedValueOnce({
        groups: [{ sourceTaskId: 5, sourceTaskName: '源任务5', results: [{ caseId: 'C1' }] }],
      })
    const w = await mountPanel()
    await w.findAll('.merged-source-list-title')[0].trigger('click')
    await flushPromises()
    expect(w.find('.merged-source-error').exists()).toBe(true)

    await w.find('.merged-source-retry').trigger('click')
    await flushPromises()
    expect(w.find('.merged-source-error').exists()).toBe(false)
    expect(w.text()).toContain('源任务5')
  })

  it('多卡独立错误态：卡1 失败不影响卡2 正常展开', async () => {
    api.getSource
      .mockRejectedValueOnce(new Error('网络抖动'))
      .mockResolvedValueOnce({
        groups: [{ sourceTaskId: 6, sourceTaskName: '源任务6', results: [{ caseId: 'C2' }] }],
      })
    const w = await mountPanel()
    // 先展开卡1（失败），再展开卡2（成功）
    const titles = w.findAll('.merged-source-list-title')
    await titles[0].trigger('click')
    await flushPromises()
    await titles[1].trigger('click')
    await flushPromises()

    const errors = w.findAll('.merged-source-error')
    expect(errors.length).toBe(1)
    expect(w.text()).toContain('源任务6')
  })
})
