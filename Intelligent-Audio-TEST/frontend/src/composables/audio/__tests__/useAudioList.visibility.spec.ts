/**
 * INT-467（代码审计 P1-1）：useAudioList.fetchAudios 展示层映射必须透传
 * visibility / createdByUserId——AudioListComponent 的 <VisibilityBadge> 与
 * useVisibility 的 owner 判定依赖这两个字段，此前在固定形状映射中被丢弃，
 * 导致音频列表私有徽标永不渲染。本用例即该缺陷的回归守卫（纯前端，不依赖后端）。
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
  audiosPort.getAllTags.mockResolvedValue({ success: true, data: [] })
})

describe('useAudioList 可见性字段透传（INT-467 P1-1 回归守卫）', () => {
  it('fetchAudios 保留私有音频的 visibility 与 createdByUserId（私有徽标渲染前提）', async () => {
    audiosPort.getAll.mockResolvedValue({
      items: [
        { id: 1, name: '私有音频', visibility: 'private', createdByUserId: 7 },
        { id: 2, name: '共享音频', visibility: 'shared', createdByUserId: 7 },
        { id: 3, name: '缺省音频' },
      ],
      total: 3,
    })
    const view = useAudioList()

    await view.fetchAudios()

    const byId = new Map(view.audioList.value.map(a => [a.id, a]))
    expect(byId.get(1)?.visibility).toBe('private')
    expect(byId.get(1)?.createdByUserId).toBe(7)
    expect(byId.get(2)?.visibility).toBe('shared')
    // 缺省字段：undefined 而非被构造为 shared/0（保持「未见即缺省」语义，徽标白名单外不误渲染）
    expect(byId.get(3)?.visibility).toBeUndefined()
    expect(byId.get(3)?.createdByUserId).toBeUndefined()
  })
})
