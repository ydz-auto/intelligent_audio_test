/**
 * INT-289：AudioListComponent 消费 loading prop——首载渲染骨架屏，空数据时不再仅显示空态误导。
 *
 * 旧实现：AudioImport.vue 传 :loading，但组件模板零消费——主数据获取期间无任何指示，
 *   失败/加载中被「没有找到匹配的音频文件」空态文案误导。
 *
 * 锁定契约：
 * 1. loading=true 且无数据：渲染骨架屏（SKELETON_ROWS 行），不渲染表格与空态；
 * 2. loading=true 且已有数据：保留表格（刷新不清空视觉）；
 * 3. loading=false 且无数据：渲染空态文案；
 * 4. folderLoading=true 且树无内容：渲染文件夹树加载指示。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import AudioListComponent from '../AudioListComponent.vue'

vi.mock('../misc/FolderNodeComponent.vue', () => ({ default: { template: '<div class="folder-node-stub" />' } }))
vi.mock('../data/PaginationComponent.vue', () => ({ default: { template: '<div class="pagination-stub" />' } }))
vi.mock('../BadgeFilter.vue', () => ({ default: { template: '<div class="badge-filter-stub" />' } }))

const baseProps = {
  audios: [] as any[],
  enableSelection: true,
  showStatus: true,
  audioType: 'all',
  selectedAudios: [] as (string | number)[],
  totalAudios: 0,
  currentPage: 1,
  pageSize: 20,
  allTags: [] as string[],
  selectedTags: [] as string[],
  tagModes: {},
}

function mountComponent(overrides: Record<string, unknown> = {}) {
  return mount(AudioListComponent, {
    props: { ...baseProps, ...overrides },
  })
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('AudioListComponent loading prop 消费（INT-289）', () => {
  it('loading=true 且无数据：渲染骨架屏，不渲染表格与空态', () => {
    const wrapper = mountComponent({ loading: true, viewMode: 'list' })

    expect(wrapper.find('.audio-list-skeleton').exists()).toBe(true)
    expect(wrapper.findAll('.skeleton-row')).toHaveLength(5)
    expect(wrapper.find('table.data-table').exists()).toBe(false)
    expect(wrapper.find('.empty-state').exists()).toBe(false)
  })

  it('loading=true 且已有数据：不渲染骨架屏，保留表格（刷新不清空视觉）', () => {
    const wrapper = mountComponent({
      loading: true,
      viewMode: 'list',
      audios: [{ id: 1, filename: 'a.wav' }],
      totalAudios: 1,
    })

    expect(wrapper.find('.audio-list-skeleton').exists()).toBe(false)
    expect(wrapper.find('table.data-table').exists()).toBe(true)
  })

  it('loading=false 且无数据：渲染空态文案，不渲染骨架屏', () => {
    const wrapper = mountComponent({ loading: false, viewMode: 'list' })

    expect(wrapper.find('.audio-list-skeleton').exists()).toBe(false)
    expect(wrapper.find('.empty-state').exists()).toBe(true)
  })

  it('folderLoading=true 且树无内容：渲染文件夹树加载指示', () => {
    const wrapper = mountComponent({ loading: false, viewMode: 'folder', folderLoading: true })

    expect(wrapper.find('.folder-tree-loading').exists()).toBe(true)
  })

  it('folderLoading=false：不渲染文件夹树加载指示', () => {
    const wrapper = mountComponent({ loading: false, viewMode: 'folder', folderLoading: false })

    expect(wrapper.find('.folder-tree-loading').exists()).toBe(false)
  })
})
