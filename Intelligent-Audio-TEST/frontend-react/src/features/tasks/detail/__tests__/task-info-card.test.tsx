/**
 * 任务信息卡渲染测试（INT-2446）：
 * - 头行「创建人」取真实 created_by_user_id 解析出的显示名，未解析到回退「用户 #id」，
 *   无创建人时为「—」；不得再出现硬编码假名（mock 残留）。
 * - 标签行带「标签」标签名，空态是一个有归属的「—」，不是裸露短横线。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { TaskDetailData } from '@/domain/models/task'

import { TaskInfoCard } from '../task-info-card'

function makeDetail(overrides: Partial<TaskDetailData> = {}): TaskDetailData {
  return {
    id: 588,
    name: '测试任务_2026-11-02 09:35',
    description: null,
    status: 'completed',
    executionStatus: 'completed',
    evaluationStatus: 'completed',
    deviceTypes: [],
    config: {},
    algorithmType: null,
    algorithmParams: null,
    startedAt: null,
    completedAt: null,
    expectedTotalTime: null,
    expectedCompleteTime: null,
    usedTime: null,
    totalCases: 0,
    caseCount: 0,
    deviceCount: null,
    completedCases: 0,
    failedCases: 0,
    tags: [],
    cases: [],
    devices: [],
    apis: [],
    createdAt: '2026-11-02T01:35:41',
    updatedAt: null,
    createdByUserId: 1,
    apiCount: null,
    concurrency: null,
    reviewCount: 0,
    ...overrides,
  }
}

describe('TaskInfoCard 创建人', () => {
  it('解析到显示名时头行显示真实创建人', () => {
    render(<TaskInfoCard detail={makeDetail()} createdByName='dev_user' />)

    expect(screen.getByText(/创建人 dev_user/)).toBeInTheDocument()
    // 旧硬编码假名必须消失
    expect(screen.queryByText(/张测试/)).toBeNull()
  })

  it('未解析到显示名时回退「用户 #id」而不是留空或写假名', () => {
    render(<TaskInfoCard detail={makeDetail({ createdByUserId: 4 })} />)

    expect(screen.getByText(/创建人 用户 #4/)).toBeInTheDocument()
  })

  it('无创建人 id 时显示「—」', () => {
    render(<TaskInfoCard detail={makeDetail({ createdByUserId: null })} />)

    expect(screen.getByText(/创建人 —/)).toBeInTheDocument()
  })
})

describe('TaskInfoCard 标签行', () => {
  it('空标签行带「标签」标签名，并显示空态「—」', () => {
    render(<TaskInfoCard detail={makeDetail({ tags: [] })} />)

    const label = screen.getByText('标签')
    // 「标签」标签名与它的空态值同属一个分组，避免裸露无归属的短横线
    expect(label.parentElement).toHaveTextContent('标签—')
  })

  it('有标签时逐个渲染 Badge', () => {
    render(<TaskInfoCard detail={makeDetail({ tags: ['旗舰回归', '远场'] })} />)

    expect(screen.getByText('标签')).toBeInTheDocument()
    expect(screen.getByText('旗舰回归')).toBeInTheDocument()
    expect(screen.getByText('远场')).toBeInTheDocument()
  })
})
