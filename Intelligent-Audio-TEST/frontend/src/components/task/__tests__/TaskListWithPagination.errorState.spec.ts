/**
 * INT-288：TaskListWithPagination 错误态 / 空态区分回归。
 *
 * 缺陷：fetchTasks 失败仅 console.error，页面把「接口坏了」当成「没数据」，
 * 渲染「没有找到任务」空态。验收（issue 原文）：错误态（统一错误条组件 +
 * 重试）、错误与空态视觉区分、失败保留旧数据不清空。
 * 锁定契约：
 * 1. error 非空 → 渲染 LoadErrorState（.load-error-state）+ 重试按钮，点击 emit('retry')；
 * 2. 错误态压制空态（无数据 + 错误时不得渲染「没有找到任务」）；
 * 3. 有旧数据 + 错误 → 错误条悬于列表上方（数据不清空）；
 * 4. isLoading → .loading-state spinner。
 */
import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import TaskListWithPagination from '../TaskListWithPagination.vue'

function mountList(props: Record<string, unknown> = {}) {
  return mount(TaskListWithPagination, {
    props: {
      tasks: [],
      error: '',
      isLoading: false,
      currentPage: 1,
      totalPages: 1,
      pageSize: 10,
      totalItems: 0,
      ...props,
    },
    global: {
      stubs: {
        TaskCard: true,
        PaginationComponent: true,
      },
    },
  })
}

const OLD_TASK = { id: 1, name: '旧任务', status: 'completed', tags: [], deleted: false }

describe('TaskListWithPagination 错误态 / 空态（INT-288）', () => {
  it('error 非空：渲染错误条 + 重试按钮，点击 emit retry', async () => {
    const wrapper = mountList({ error: '加载任务失败，请稍后重试' })

    const bar = wrapper.find('.load-error-state')
    expect(bar.exists(), '失败后应渲染统一错误条（不再仅 console.error）').toBe(true)
    expect(bar.text()).toContain('加载任务失败')

    const retry = bar.find('button')
    expect(retry.exists(), '错误条应提供重试入口').toBe(true)
    await retry.trigger('click')
    expect(wrapper.emitted('retry'), '点击重试应 emit retry').toBeTruthy()
  })

  it('错误态压制空态：无数据 + 错误时不得渲染「没有找到任务」', () => {
    const wrapper = mountList({ error: '加载任务失败，请稍后重试' })
    expect(wrapper.find('.empty-state').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('没有找到任务')
  })

  it('无错误且无数据：渲染空态（错误与空态视觉区分）', () => {
    const wrapper = mountList()
    expect(wrapper.find('.empty-state').exists()).toBe(true)
    expect(wrapper.find('.load-error-state').exists()).toBe(false)
    expect(wrapper.text()).toContain('没有找到任务')
  })

  it('失败保留旧数据：有数据 + 错误 → 错误条悬于列表上方，空态不出现', () => {
    const wrapper = mountList({ tasks: [OLD_TASK], error: '加载任务失败，请稍后重试' })
    expect(wrapper.find('.load-error-state').exists()).toBe(true)
    expect(wrapper.find('.empty-state').exists()).toBe(false)
    // 旧数据 TaskCard 仍渲染（stub 占位存在）
    expect(wrapper.findAllComponents({ name: 'TaskCard' }).length).toBe(1)
  })

  it('加载态：isLoading 时渲染 spinner 加载中', () => {
    const wrapper = mountList({ isLoading: true })
    expect(wrapper.find('.loading-state').exists()).toBe(true)
    expect(wrapper.find('.spinner').exists()).toBe(true)
    expect(wrapper.text()).toContain('加载中')
  })
})
