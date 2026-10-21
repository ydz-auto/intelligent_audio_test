/**
 * 挑选树测试（18_挑选合并交互重设计.md §3.8.3，INT-1127 实施）。
 * renderCaseLayer：设备/结果类型视图 result_type/设备 节点下用例层改由组织列表渲染
 * （替代默认内联用例分支行），顶/二层分支行仍为 PickTree 层级行。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type {
  PickTreeBranch,
  PickTreeItem,
  PickTreeLeaf,
} from '@/domain/models/cherryPick'
import { PickTree } from '@/features/tasks/cherry-pick/components/pick-tree'

const LEAF: PickTreeLeaf = {
  kind: 'leaf',
  key: 'leaf:1',
  resultId: 1,
  taskName: '任务A',
  caseName: '用例001',
  deviceName: '设备-01',
  apiName: null,
  resultType: 'real-time',
  executionStatus: 'completed',
  evaluationStatus: 'completed',
  createdAt: '2026-10-15T09:00:00',
  added: false,
}

/** 设备视图树（设备→result_type→用例→叶，INT-1047 buildPickDeviceView 形态） */
const DEVICE_VIEW: PickTreeBranch[] = [
  {
    kind: 'branch',
    key: 'dv-device:device:1',
    level: 'device',
    name: '设备-01',
    count: 1,
    resultIds: [1],
    children: [
      {
        kind: 'branch',
        key: 'dv-resultType:device:1:real-time',
        level: 'resultType',
        name: 'real-time',
        count: 1,
        resultIds: [1],
        children: [
          {
            kind: 'branch',
            key: 'dv-case:device:1:real-time:c1',
            level: 'case',
            name: '用例001',
            caseId: 'c1',
            algorithmType: null,
            count: 1,
            resultIds: [1],
            children: [LEAF],
          },
        ],
      },
    ],
  },
]

function setup(renderCaseLayer?: (caseBranches: PickTreeBranch[]) => React.ReactNode) {
  const onToggleLeaf = vi.fn()
  const onToggleBranch = vi.fn()
  render(
    <PickTree
      items={DEVICE_VIEW as PickTreeItem[]}
      selectedIds={new Set()}
      onToggleLeaf={onToggleLeaf}
      onToggleBranch={onToggleBranch}
      expandSignal={{ all: true, tick: 1 }}
      showLeafTask
      renderCaseLayer={renderCaseLayer}
    />
  )
  return { onToggleLeaf, onToggleBranch }
}

describe('PickTree renderCaseLayer（§3.8.3 用例层组织作用层，INT-1127）', () => {
  it('不传 renderCaseLayer：result_type 下用例层为默认分支行（回归）', () => {
    setup()
    // 设备-01 同时出现于设备分支行与叶行设备名，real-time 出现于分支行与叶徽章
    expect(screen.getAllByText('设备-01').length).toBeGreaterThan(0)
    expect(screen.getAllByText('real-time').length).toBeGreaterThan(0)
    expect(screen.getAllByText('用例001').length).toBeGreaterThan(0) // 分支行
  })

  it('传 renderCaseLayer：result_type 下用例层改由组织列表渲染（顶/二层仍为分支行）', () => {
    setup((caseBranches) => (
      <div data-testid='case-layer'>
        {caseBranches.map((b) => (
          <div key={b.key}>org:{b.name}</div>
        ))}
      </div>
    ))
    expect(screen.getByTestId('case-layer')).toBeInTheDocument()
    expect(screen.getByText('org:用例001')).toBeInTheDocument()
    // 顶/二层仍为分支行（设备/result_type）
    expect(screen.getByText('设备-01')).toBeInTheDocument()
    expect(screen.getByText('real-time')).toBeInTheDocument()
  })

  it('renderCaseLayer 不影响叶行渲染（用例卡展开后叶行照常）', () => {
    setup((caseBranches) => (
      <div data-testid='case-layer'>
        {caseBranches.map((b) => (
          <div key={b.key}>org:{b.name}</div>
        ))}
      </div>
    ))
    // 用例卡由 renderCaseLayer 接管，叶行不再以默认行出现在 result_type 下
    expect(screen.queryByText('任务A')).not.toBeInTheDocument()
  })
})
