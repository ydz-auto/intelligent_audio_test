/**
 * 评估策略 API（infrastructure 层；11_用例域.md §5.1.3 评估策略节）。
 * 后端实体由主项目 INT-590【后端】卡落定——本卡已探测常驻网关 GET /api/v1/evaluation/strategies
 * → 404 Not Found（端点未交付），按契约 mock 先行（红线④），接口接线随后端策略卡 done。
 * 契约：GET  /api/v1/evaluation/strategies          策略列表（选项带摘要）
 *       POST /api/v1/evaluation/strategies          新建策略（入库后全局可复用）
 */
import type { EvaluationStrategy } from '@/domain/models/evaluationStrategy'
import { MOCK_EVALUATION_STRATEGIES } from '../mock/evaluation-strategies-mock'

/** 模拟网络延迟（视觉稿演示用；接线后删除） */
function mockLatency<T>(value: T, ms = 160): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms))
}

/** 策略列表（GET /evaluation/strategies；mock 内存库运行时可变，新建后追加） */
let strategiesStore: EvaluationStrategy[] = [...MOCK_EVALUATION_STRATEGIES]
let nextStrategyId = 1000

/** 供测试清理内存库 */
export function __resetStrategyMock(): void {
  strategiesStore = [...MOCK_EVALUATION_STRATEGIES]
  nextStrategyId = 1000
}

export function peekStrategies(): EvaluationStrategy[] {
  return strategiesStore
}

/** 策略列表（选项带摘要「{名} · 整体维度 {n} 项 · 噪声 {已配置|未配置}」） */
export async function fetchEvaluationStrategies(): Promise<EvaluationStrategy[]> {
  // TODO(API 接线): GET /api/v1/evaluation/strategies（INT-590 后端策略卡 done 后替换）
  return mockLatency([...strategiesStore])
}

/** 新建策略（POST /evaluation/strategies；入库后进入 Select 列表全局可复用） */
export async function createEvaluationStrategy(
  input: Pick<EvaluationStrategy, 'name' | 'description'> &
    Partial<Pick<EvaluationStrategy, 'dimensions' | 'backgroundNoise'>>
): Promise<EvaluationStrategy> {
  // TODO(API 接线): POST /api/v1/evaluation/strategies（INT-590 后端策略卡 done 后替换）
  nextStrategyId += 1
  const strategy: EvaluationStrategy = {
    id: `str-${nextStrategyId}`,
    name: input.name,
    description: input.description ?? null,
    dimensions: input.dimensions ?? [],
    backgroundNoise: input.backgroundNoise ?? null,
  }
  strategiesStore = [strategy, ...strategiesStore]
  return mockLatency(strategy, 220)
}
