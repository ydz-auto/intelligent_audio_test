/**
 * INT-289：AudioImport 主列表获取失败可见错误提示（失败不清空列表现状）。
 *
 * 旧实现：useAudioList.fetchAudios 失败仅 console.error，页面落「没有找到匹配的音频文件」空态，
 *   用户把「接口坏了」当成「没数据」。
 *
 * 锁定契约：
 * 1. fetchAudios 失败走 useNotification.error，且 audioList 保留旧数据、loading 复位；
 * 2. fetchAllTags 失败走 useNotification.error；
 * 3. 成功路径不弹错误提示。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

const audiosPort = vi.hoisted(() => ({
  getAll: vi.fn(),
  getAllTags: vi.fn(),
  getAllIds: vi.fn(),
}))
const notifications = vi.hoisted(() => ({ error: vi.fn(), show: vi.fn(), warning: vi.fn(), success: vi.fn(), info: vi.fn() }))

vi.mock('@/composables/audio/audiosPort', () => ({ audiosPort }))
vi.mock('@/composables/shared/useTagFilter', () => ({
  useTagFilter: () => ({
    selectedTags: ref([]),
    tagModes: ref(new Map()),
    tagModesObject: {},
    handleTagClick: vi.fn(),
    toggleTag: vi.fn(),
    clearTags: vi.fn(),
    setTagsFromProps: vi.fn(),
  }),
}))
vi.mock('@/composables/shared/useFolderSelection', () => ({
  useFolderSelection: () => ({
    toggleFolderSelection: vi.fn(),
    isFolderAllSelected: vi.fn(() => false),
    isFolderPartialSelected: vi.fn(() => false),
  }),
}))
vi.mock('@/composables/modal/useNotification', () => ({ useNotification: () => notifications }))

import { useAudioList } from '../useAudioList'

beforeEach(() => {
  vi.clearAllMocks()
  audiosPort.getAll.mockResolvedValue({ items: [], total: 0 })
  audiosPort.getAllTags.mockResolvedValue({ success: true, data: [] })
})

describe('useAudioList 失败可见（INT-289）', () => {
  it('fetchAudios 失败：notification.error 提示，audioList 保留旧数据，loading 复位', async () => {
    audiosPort.getAll.mockRejectedValue(new Error('后端停服'))
    const view = useAudioList()
    view.audioList.value = [{ id: 1, name: '旧音频' }] as any

    await view.fetchAudios()

    expect(notifications.error).toHaveBeenCalledTimes(1)
    expect(notifications.error).toHaveBeenCalledWith('加载音频列表失败: 后端停服')
    expect(view.loading.value).toBe(false)
    expect(view.audioList.value.length).toBe(1)
  })

  it('fetchAudios 成功：不弹错误提示，列表正常填充', async () => {
    audiosPort.getAll.mockResolvedValue({ items: [{ id: 1, name: 'a1' }], total: 1 })
    const view = useAudioList()

    await view.fetchAudios()

    expect(notifications.error).not.toHaveBeenCalled()
    expect(view.audioList.value.length).toBe(1)
  })

  it('fetchAllTags 失败：notification.error 提示', async () => {
    audiosPort.getAllTags.mockRejectedValue(new Error('标签接口超时'))
    const view = useAudioList()

    await view.fetchAllTags()

    expect(notifications.error).toHaveBeenCalledWith('加载标签列表失败: 标签接口超时')
  })
})
