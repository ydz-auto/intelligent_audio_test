/**
 * 容器组成区组件测试（18_挑选合并功能交互重设计.md §5.5.3 ①/②、§5.5.6，INT-1717）。
 * 覆盖本卡新增/依赖的难复现态：落点① 组成区滚动 + 高亮 1.2s 消退；
 * 「容器无来源记录」空态、「结果全部失效」失效 Alert（真实库无可写入关系行的端点，
 * 这两态以组件测试覆盖，交付评论已说明）。
 */
import { act, render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  summarizeComposition,
  toCompositionEntries,
  type CompositionEntry,
} from '@/domain/lib/container-composition'
import type { ContainerSourceTrace } from '@/domain/models/cherryPick'
import type { TaskCaseBrief } from '@/domain/models/task'

vi.mock('@tanstack/react-router', () => ({
  Link: ({ children }: { children: ReactNode }) => <a>{children}</a>,
}))

vi.mock('@/application/tasks/cherry-pick/use-pick-org', () => ({
  usePickOrg: () => ({
    org: 'group',
    subView: 'flat',
    setOrg: vi.fn(),
    setSubView: vi.fn(),
  }),
}))

vi.mock('@/features/tasks/cherry-pick/components/cart-tree', () => ({
  CartTree: ({ groups }: { groups: unknown[] }) => (
    <div data-testid='cart-tree' data-groups={groups.length} />
  ),
}))

vi.mock('@/features/tasks/detail/container-view-switcher', () => ({
  ContainerCompositionToolbar: () => <div data-testid='composition-toolbar' />,
}))

vi.mock('@/features/testcases/components/case-sub-group-header', () => ({
  CaseSubGroupHeader: () => <div />,
}))

import { ContainerComposition } from '@/features/tasks/detail/container-composition'

const CASE_A = '11111111-1111-1111-1111-111111111111'

const CASE_BRIEF: TaskCaseBrief = {
  case_id: CASE_A,
  name: '用例 A',
  status: 'completed',
  execution_status: 'completed',
  evaluation_status: 'completed',
  started_at: null,
  completed_at: null,
  duration: null,
  error_message: null,
  group_name: '分组一',
  tags: ['标签一'],
  evaluation_dimensions: [],
  reviewed: false,
}

function traceWith(missing: boolean): ContainerSourceTrace {
  return {
    taskId: 611,
    isCherryPick: true,
    total: 1,
    groups: [
      {
        sourceTaskId: 419,
        sourceTaskName: '任务419',
        sourceTaskStatus: null,
        results: [
          {
            resultId: 5714,
            sourceCaseId: CASE_A,
            sourceDeviceId: null,
            sourceApiId: null,
            missing,
            resultType: null,
            executionStatus: null,
            evaluated: null,
            caseName: null,
            deviceName: null,
            apiName: null,
            resultCreatedAt: null,
          },
        ],
      },
    ],
  }
}

function renderComposition(trace: ContainerSourceTrace | null, entries: CompositionEntry[]) {
  return render(
    <ContainerComposition
      trace={trace}
      entries={entries}
      summary={summarizeComposition(entries)}
    />
  )
}

function entriesFor(trace: ContainerSourceTrace) {
  return toCompositionEntries(trace, [CASE_BRIEF], [], [])
}

describe('ContainerComposition 空态 / 失效（§5.5.6）', () => {
  it('容器无来源记录（groups = []）→ 虚线空态文案，不白屏', () => {
    const emptyTrace: ContainerSourceTrace = { taskId: 611, isCherryPick: true, total: 0, groups: [] }
    renderComposition(emptyTrace, [])

    expect(screen.getByText('该任务没有合并来源记录')).toBeInTheDocument()
    expect(
      screen.getByText('若它是历史合并任务，来源关系可能在合并功能上线前生成')
    ).toBeInTheDocument()
    expect(screen.queryByTestId('cart-tree')).not.toBeInTheDocument()
  })

  it('结果全部失效 → 失效 Alert（条数正确）+ 仍渲染树', () => {
    const trace = traceWith(true)
    renderComposition(trace, entriesFor(trace))

    expect(
      screen.getByText('1 条源结果已失效（源任务或结果已被删除），仅保留溯源记录')
    ).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '只看失效' })).toBeInTheDocument()
    expect(screen.getByTestId('cart-tree')).toBeInTheDocument()
  })

  it('无失效条目不显示失效 Alert', () => {
    const trace = traceWith(false)
    renderComposition(trace, entriesFor(trace))

    expect(screen.queryByText(/条源结果已失效/)).not.toBeInTheDocument()
  })
})

describe('ContainerComposition 落点①高亮（§5.5.3 ①）', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    window.location.hash = '#composition'
  })
  afterEach(() => {
    vi.useRealTimers()
    window.location.hash = ''
  })

  it('带 #composition 进入 → 出现高亮层，1.2s 后消退', () => {
    const trace = traceWith(false)
    renderComposition(trace, entriesFor(trace))

    expect(screen.getByTestId('composition-landing-highlight')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(1300)
    })
    expect(screen.queryByTestId('composition-landing-highlight')).not.toBeInTheDocument()
  })

  it('无锚点进入（页签行展开 sectionId=null）→ 不高亮', () => {
    const trace = traceWith(false)
    render(
      <ContainerComposition
        trace={trace}
        entries={entriesFor(trace)}
        summary={summarizeComposition(entriesFor(trace))}
        sectionId={null}
      />
    )
    expect(screen.queryByTestId('composition-landing-highlight')).not.toBeInTheDocument()
  })
})
