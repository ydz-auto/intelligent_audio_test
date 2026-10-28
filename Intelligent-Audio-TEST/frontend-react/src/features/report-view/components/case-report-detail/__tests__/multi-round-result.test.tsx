/**
 * 多轮对话结果块（INT-2120）：判定对齐 V9.7.10 `parseMultiRoundResult`——只有真正的
 * rounds 源才渲染整块；`round_details@round:N` 这类按轮展开的 json 数组不判多轮。
 * 真有 rounds 源时聚合卡只渲染有值项、每轮字段按 v-if 语义有值才渲染（无「—」占位）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ReportCaseItem } from '@/domain/models/report'

import { MultiRoundResult } from '../multi-round-result'

function makeCase(algorithmResults: ReportCaseItem['algorithmResults']): ReportCaseItem {
  return {
    id: 'case-1',
    name: '用例',
    metrics: [{ resource: 'dev1', metrics: [] }],
    algorithmResults,
  } as unknown as ReportCaseItem
}

describe('多轮对话结果：rounds 源判定（INT-2120）', () => {
  it('report 420 真实形态：round_details@round:N 的数组 value 不是 rounds 源，整块不渲染', () => {
    const { container } = render(
      <MultiRoundResult
        caseItem={makeCase([
          {
            paramCode: 'round_details@round:1',
            paramType: 'json',
            value: [{ role: 'interruption', round: 0, reply_latency_ms: 1410.2 }],
          },
          {
            paramCode: 'llm_round_evaluations@round:1',
            paramType: 'json',
            value: [{ wer: 0.1 }],
          },
          {
            // 真实库同一条用例还有 param_code=rounds 的扁平项（value 即 2 轮数组），
            // V9.7.10 同样不认（只认 rounds 字段）→ 整块仍不渲染
            paramCode: 'rounds',
            paramType: 'json',
            value: [
              { round: 0, input: { audio_name: 'silence_1.wav' }, latency: null, evaluation: {} },
              { round: 1, input: { audio_name: 'response_2.wav' }, latency: null, evaluation: {} },
            ],
          },
        ])}
      />
    )
    expect(screen.queryByText(/多轮对话结果/)).toBeNull()
    expect(container.textContent).toBe('')
  })

  it('没有 algorithmResults → 不渲染', () => {
    const { container } = render(<MultiRoundResult caseItem={makeCase([])} />)
    expect(container.textContent).toBe('')
  })

  it('项自身 rounds 数组（V9.7.10 主口径）→ 渲染并按轮展开', () => {
    render(
      <MultiRoundResult
        caseItem={makeCase([
          {
            paramCode: 'rounds',
            roundNumber: 1,
            rounds: [
              { latency: 1200, input: { audio_name: 'round1.wav' } },
              { latency: 1300 },
            ],
          },
        ])}
      />
    )
    expect(screen.getByText('多轮对话结果 (2 轮)')).toBeInTheDocument()
  })

  it('value 对象内含 rounds 数组（快照嵌套形态）→ 渲染', () => {
    render(
      <MultiRoundResult
        caseItem={makeCase([
          { paramCode: 'multi_round_result', value: { rounds: [{}, {}] } },
        ])}
      />
    )
    expect(screen.getByText('多轮对话结果 (2 轮)')).toBeInTheDocument()
  })

  it('param_code=rounds 但 value 是数组（report 420 真实扁平形态）→ 不渲染：V9.7.10 只认 rounds 字段', () => {
    const { container } = render(
      <MultiRoundResult
        caseItem={makeCase([
          {
            paramCode: 'rounds',
            paramType: 'json',
            value: [
              { round: 0, input: { audio_name: 'silence_1.wav' }, latency: null, evaluation: {} },
              { round: 1, input: { audio_name: 'response_2.wav' }, latency: null, evaluation: {} },
            ],
          },
        ])}
      />
    )
    // 数组 value 不是 rounds 源：不把「扁平 rounds 项」反推成多轮块（不合成口径）
    expect(container.textContent).toBe('')
  })

  it('rounds 为空数组 → 不渲染（无轮可展开）', () => {
    const { container } = render(
      <MultiRoundResult caseItem={makeCase([{ paramCode: 'rounds', value: [] }])} />
    )
    expect(container.textContent).toBe('')
  })
})

describe('多轮对话结果：聚合卡与每轮字段不出现「—」占位（INT-2120）', () => {
  it('聚合卡只渲染有值字段（无 avg_wer / 打断次数 卡片）', () => {
    render(
      <MultiRoundResult
        caseItem={makeCase([{ paramCode: 'multi_round_result', value: { rounds: [{ latency: 1200 }, { latency: 1300 }] } }])}
      />
    )
    expect(screen.getByText('平均延迟')).toBeInTheDocument()
    expect(screen.getByText('1250ms')).toBeInTheDocument()
    expect(screen.queryByText('平均 WER')).toBeNull()
    expect(screen.queryByText('平均 LLM 评分')).toBeNull()
    expect(screen.queryByText('打断次数')).toBeNull()
  })

  it('后端 aggregated 有值字段照常展示（含 0 值打断次数）', () => {
    render(
      <MultiRoundResult
        caseItem={makeCase([
          {
            paramCode: 'rounds',
            value: {
              rounds: [{}],
              aggregated: { avg_wer: 1.234, interruption_count: 0 },
            },
          },
        ])}
      />
    )
    expect(screen.getByText('1.23%')).toBeInTheDocument()
    expect(screen.getByText('打断次数')).toBeInTheDocument()
    expect(screen.getByText('0')).toBeInTheDocument()
    expect(screen.queryByText('平均延迟')).toBeNull()
  })

  it('每轮展开只渲染有值字段：第 2 轮无输入音频 / ASR 输出，也无「—」', () => {
    render(
      <MultiRoundResult
        caseItem={makeCase([
          {
            paramCode: 'multi_round_result',
            value: {
              rounds: [
                {
                  latency: 1200,
                  input: { audio_name: 'round1.wav' },
                  output: { asr_text: '你好' },
                },
                { latency: 1300 },
              ],
            },
          },
        ])}
      />
    )
    fireEvent.click(screen.getByText('第 2 轮'))
    expect(screen.queryByText('输入音频')).toBeNull()
    expect(screen.queryByText('ASR 输出')).toBeNull()
    // 延迟有值照常渲染；展开体里没有任何「—」占位
    expect(screen.getAllByText('延迟').length).toBeGreaterThan(0)
    expect(document.body.textContent).not.toContain('—')
  })

  it('第 1 轮有值字段照常渲染（输入音频 / ASR 输出 / 延迟 / 维度评分徽章）', () => {
    render(
      <MultiRoundResult
        caseItem={makeCase([
          {
            paramCode: 'multi_round_result',
            value: {
              rounds: [
                {
                  latency: 1200,
                  input: { audio_name: 'round1.wav' },
                  output: { asr_text: '你好' },
                  evaluation: { wer: 2.5, llm_judge: 4 },
                },
              ],
            },
          },
        ])}
      />
    )
    fireEvent.click(screen.getAllByText('第 1 轮')[0])
    expect(screen.getByText('输入音频')).toBeInTheDocument()
    expect(screen.getByText('round1.wav')).toBeInTheDocument()
    expect(screen.getByText('ASR 输出')).toBeInTheDocument()
    expect(screen.getByText('WER 2.50%')).toBeInTheDocument()
    expect(screen.getByText('LLM 评分 4.0')).toBeInTheDocument()
  })
})
