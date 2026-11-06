/**
 * 健康测试弹窗空态回归（INT-1816 P3-3）：无端点维度后端返回 results=[] +
 * overall_status='online'，弹窗此前显示「总状态 在线」+ 只有表头的空表，
 * 把「没有可探测端点」表达成「在线」。改为走空态文案，且不渲染总状态徽章。
 */
import type { UseMutationResult } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'

import type {
  Dimension,
  HealthCheckResultItem,
} from '@/domain/models/evaluationDimension'
import { HealthTestDialog } from '@/features/evaluation/modals/health-test-dialog'

const DIMENSION: Dimension = { id: 121, name: '拒识准确率' }

type HealthMutation = UseMutationResult<
  { results: HealthCheckResultItem[]; overallStatus: string },
  unknown,
  Dimension
>

/** 探测结果桩（mutate 不真正请求，保持传入 data 不变） */
function makeHealthTest(
  data: { results: HealthCheckResultItem[]; overallStatus: string }
): HealthMutation {
  return {
    data,
    isPending: false,
    mutate: vi.fn(),
  } as unknown as HealthMutation
}

/** 复刻评估维度页的受控用法：点按钮打开弹窗。 */
function Harness({ healthTest }: { healthTest: HealthMutation }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type='button' onClick={() => setOpen(true)}>
        测试 API
      </button>
      <HealthTestDialog
        open={open}
        onOpenChange={setOpen}
        dimension={DIMENSION}
        healthTest={healthTest}
      />
    </>
  )
}

describe('HealthTestDialog 无端点空态', () => {
  it('results 为空时显示未配置端点空态，不显示「总状态 在线」', async () => {
    render(
      <Harness
        healthTest={makeHealthTest({ results: [], overallStatus: 'online' })}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: '测试 API' }))

    expect(
      await screen.findByText('该维度未配置 API 端点，无可探测端点')
    ).toBeTruthy()
    expect(screen.queryByText('总状态')).toBeNull()
    expect(screen.queryByText('在线')).toBeNull()
    expect(screen.queryByText('暂无健康探测数据')).toBeNull()
  })

  it('有端点结果时仍显示总状态与端点明细', async () => {
    render(
      <Harness
        healthTest={makeHealthTest({
          results: [
            {
              url: 'http://example.test/predict',
              status: 'online',
              responseTime: '128ms',
              message: 'OK',
            },
          ],
          overallStatus: 'online',
        })}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: '测试 API' }))

    expect(await screen.findByText('总状态')).toBeTruthy()
    // 总状态徽章 + 端点行状态徽章各一个
    expect(screen.getAllByText('在线')).toHaveLength(2)
    expect(screen.getByText('http://example.test/predict')).toBeTruthy()
    expect(
      screen.queryByText('该维度未配置 API 端点，无可探测端点')
    ).toBeNull()
  })
})
