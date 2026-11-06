/**
 * 挑选树测试（18_挑选合并交互重设计.md §3.8.3，INT-1127 / INT-1694 三次口径）。
 * 组织层：result_type 之下、用例卡之上的 caseOrg 分支行（名称 + 计数 + 三态 Checkbox + 展开）；
 * 用例节点统一渲染为 CaseCard compact（PickCaseCard），卡内子树继续走 PickTree。
 */
import { fireEvent, render, screen } from '@testing-library/react'
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
  deviceId: 1,
  deviceName: '设备-01',
  apiId: null,
  apiName: null,
  resultType: 'real-time',
  executionStatus: 'completed',
  evaluationStatus: 'completed',
  createdAt: '2026-10-15T09:00:00',
  added: false,
}

/** 设备视图树（设备→result_type→组织层→用例→叶，buildPickDeviceView 形态） */
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
            key: 'dv-org:device:1:real-time:group:g1',
            level: 'caseOrg',
            orgKind: 'group',
            name: '拒识',
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
    ],
  },
]

function setup() {
  const onToggleLeaf = vi.fn()
  const onToggleBranch = vi.fn()
  render(
    <PickTree
      items={DEVICE_VIEW as PickTreeItem[]}
      selectedIds={new Set()}
      onToggleLeaf={onToggleLeaf}
      onToggleBranch={onToggleBranch}
      expandSignal={{ all: true, tick: 1 }}
    />
  )
  return { onToggleLeaf, onToggleBranch }
}

describe('PickTree 组织层与用例卡（INT-1694：result_type → 组织层 → 用例卡）', () => {
  it('顶/二层仍为分支行，组织层第三层为组头分支行（名称 + 计数）', () => {
    setup()
    expect(screen.getByTestId('pick-branch-dv-device:device:1')).toBeInTheDocument()
    expect(
      screen.getByTestId('pick-branch-dv-resultType:device:1:real-time')
    ).toBeInTheDocument()
    expect(
      screen.getByTestId('pick-branch-dv-org:device:1:real-time:group:g1')
    ).toBeInTheDocument()
    expect(screen.getByText('拒识')).toBeInTheDocument()
    expect(screen.getAllByText('1 条').length).toBeGreaterThan(0)
  })

  it('组织组头可三态勾选：点击组头 Checkbox → onToggleBranch(组头, true)', () => {
    const { onToggleBranch } = setup()
    fireEvent.click(screen.getByLabelText('拒识（1 条）'))
    expect(onToggleBranch).toHaveBeenCalledWith(
      expect.objectContaining({ level: 'caseOrg', name: '拒识' }),
      true
    )
  })

  it('组织组头下是用例卡（PickCaseCard），展开后叶行照常渲染', () => {
    setup()
    // 用例卡显示用例名与用例 ID 徽章（CaseCard compact）
    expect(screen.getAllByText('用例001').length).toBeGreaterThan(0)
    // 全部展开 signal 打到底：叶行 data-testid 出现（任务层 → 叶）
    expect(screen.getByTestId('pick-leaf-1')).toBeInTheDocument()
  })
})
