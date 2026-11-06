/**
 * 购物车树用例层组织层渲染（18 §3.8.3 A 组第 3 层，INT-1740；接线侧 INT-1694 起一直有该层）。
 * 设备视图在 result_type 之下、用例卡之上渲染组织层分支（组头 / 兜底桶 + 计数）。
 * 接线侧口径：org 缺省 'group'（容器组成区 / 购物车共用同一份会话态，恒定渲染组织层），
 * 所以「不传 org」= 按分组组织，不回到无组织层的旧形状。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { PickCartGroup } from '@/domain/models/cherryPick'
import { CartTree } from '@/features/tasks/cherry-pick/components/cart-tree'

const GROUPS: PickCartGroup[] = [
  {
    taskId: 420,
    taskName: '任务420',
    entries: [
      {
        itemId: 'o1', resultId: 11, sourceTaskId: 420, sourceTaskName: '任务420',
        sourceCaseId: 'c1', sourceCaseName: '用例001',
        sourceDeviceId: 1, sourceDeviceName: '设备-01', sourceApiId: null, sourceApiName: null,
        sourceResultType: 'real-time', executionStatus: 'completed', evaluationStatus: 'completed',
        invalid: false, sourceGroupId: 'g1', sourceGroupName: '会议', sourceTags: ['冒烟'],
      },
      {
        itemId: 'o2', resultId: 12, sourceTaskId: 420, sourceTaskName: '任务420',
        sourceCaseId: 'c2', sourceCaseName: '用例002',
        sourceDeviceId: 1, sourceDeviceName: '设备-01', sourceApiId: null, sourceApiName: null,
        sourceResultType: 'real-time', executionStatus: 'completed', evaluationStatus: 'completed',
        invalid: false, sourceGroupId: null, sourceGroupName: null, sourceTags: [],
      },
    ],
  },
]

const EMPTY = new Set<string>()
const noop = () => {}

function renderTree(org?: 'group' | 'tag') {
  return render(
    <CartTree
      groups={GROUPS}
      view='device'
      readOnly
      org={org}
      subView='flat'
      selectedEntryIds={EMPTY}
      onToggleLeaf={noop}
      onToggleBranch={noop}
      onRemoveEntry={noop}
      onRemoveNode={noop}
      onRemoveTask={noop}
      expandSignal={{ all: true, tick: 1 }}
    />
  )
}

describe('CartTree 设备视图用例层组织（INT-1740）', () => {
  it('传 org：result_type 下渲染组织层组头 + 兜底桶，用例卡挂在组头下', () => {
    renderTree('group')
    expect(screen.getByText('会议')).toBeInTheDocument()
    expect(screen.getByText('未分组')).toBeInTheDocument()
    expect(screen.getAllByText('用例001').length).toBeGreaterThan(0)
    expect(screen.getAllByText('用例002').length).toBeGreaterThan(0)
  })

  it('传 org=tag：按标签分桶，无标签入「未设置标签」', () => {
    renderTree('tag')
    // 组头与用例卡上的标签 chip 同名，取「至少出现一次」即可
    expect(screen.getAllByText('冒烟').length).toBeGreaterThan(0)
    expect(screen.getAllByText('未设置标签').length).toBeGreaterThan(0)
  })

  it('不传 org：按接线侧缺省 group 组织（不是无组织层旧形状）', () => {
    renderTree()
    expect(screen.getByText('会议')).toBeInTheDocument()
    expect(screen.getByText('未分组')).toBeInTheDocument()
    expect(screen.getAllByText('用例001').length).toBeGreaterThan(0)
  })
})
