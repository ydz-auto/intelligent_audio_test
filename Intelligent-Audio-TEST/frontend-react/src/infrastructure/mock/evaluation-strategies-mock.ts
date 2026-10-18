/**
 * 评估策略 mock 数据（infrastructure 层；11_用例域.md §5.1.3）。
 * 后端 /evaluation/strategies 实体由主项目 INT-590【后端】卡落定——当前常驻网关无该端点
 * （探测 GET /api/v1/evaluation/strategies → 404），按契约 mock 先行、接口接线随后端交付。
 * 策略列表选项带摘要「{名} · 整体维度 {n} 项 · 噪声 {已配置|未配置}」。
 * 维度项形态对照 TestCaseDimensionItem；backgroundNoise 对照 TestCaseBackgroundNoiseItem。
 */
import type { EvaluationStrategy } from '@/domain/models/evaluationStrategy'

export const MOCK_EVALUATION_STRATEGIES: EvaluationStrategy[] = [
  {
    id: 'str-1',
    name: '全链路智能音箱回归',
    description: '智能音箱核心指令的跨轮次综合评估，含识别准确率与语义理解。',
    dimensions: [
      { id: 1, name: '识别准确率', weight: 50, threshold: 80 },
      { id: 2, name: '语义理解', weight: 50, threshold: 80, llmJudgeConfig: { model: 'claude-3-sonnet', promptTemplate: 'accuracy' } },
    ],
    backgroundNoise: {
      audioId: 'au-n1',
      audioName: '粉红噪声_94dB.wav',
      audio: { id: 'au-n1', name: '粉红噪声_94dB.wav', duration: 180, tags: ['粉红噪声'] },
      spl: 60,
      deviceIds: ['dev-1', 'dev-3'],
      deviceNames: ['音频接口 A', '功放 左声道'],
      loop: true,
    },
  },
  {
    id: 'str-2',
    name: '车载导航专项评估',
    description: '车载场景导航指令整体评估，关注响应时延与唤醒成功率。',
    dimensions: [
      { id: 3, name: '唤醒成功率', weight: 60, threshold: 85 },
      { id: 4, name: '响应时延', weight: 40, threshold: 75 },
    ],
    backgroundNoise: null,
  },
  {
    id: 'str-3',
    name: '会议转写综合策略',
    description: '多人会议转写的跨轮次一致性评估，整体维度含对话连贯性（LLM Judge）。',
    dimensions: [
      { id: 5, name: '对话连贯性', weight: 50, threshold: 80, llmJudgeConfig: { model: 'claude-3-opus', promptTemplate: 'fluency' } },
      { id: 11, name: '字准率', weight: 50, threshold: 80 },
    ],
    backgroundNoise: {
      audioId: 'au-n2',
      audioName: '白噪声_85dB.wav',
      audio: { id: 'au-n2', name: '白噪声_85dB.wav', duration: 120, tags: ['白噪声'] },
      spl: 45,
      deviceIds: ['dev-2'],
      deviceNames: ['音频接口 B'],
      loop: true,
    },
  },
]
