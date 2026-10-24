/**
 * 评估策略领域模型（domain 层；11_用例域.md §5.1.3 评估策略节）。
 * 整体评估维度 + 全局背景噪声抽为可复用「评估策略」实体；用例引用策略 + 可选覆盖个别字段。
 * 用例承载契约 config.evaluationStrategy（前端建议，字段名/结构以主项目【后端】策略卡落定为准，
 * mock 阶段用本结构）：{ strategy_id?, overrides?: { dimensions?, background_noise? } }。
 * snake_case 仅存在于 infrastructure 层，前端 Domain 一律 camelCase。
 */

/** 用例维度配置项（TestCaseDimensionItem，schemas/testcase.py:85-90 实测 {id,name,weight,threshold,test_type}） */
export interface TestCaseDimensionItem {
  id: number | string
  name: string
  weight: number
  threshold: number
  /** 历史 LLM Judge 配置残留（旧数据原样透传，前端不再写新值；INT-1681） */
  llmJudgeConfig?: {
    model: string
    promptTemplate: string
  }
}

/** 全局背景噪声（TestCaseBackgroundNoiseItem，schemas/testcase.py:68-82 实测，extra='allow' 兼容文件名/设备名格式） */
export interface TestCaseBackgroundNoiseItem {
  audioId?: number | string | null
  audioName?: string | null
  /** 冗余音频简报（mock 侧携带 name/duration/tags；接线后由 audioId 解析或直接省略） */
  audio?: {
    id: number | string
    name: string
    duration?: number | null
    tags?: string[]
  } | null
  /** 声压级（dB） */
  spl?: number | null
  deviceIds?: Array<number | string>
  /** 播放设备名（旧配置残留名；未匹配到 ID 时黄色警示 chip） */
  playbackDeviceNames?: string[]
  playbackDeviceName?: string | null
  deviceNames?: string[]
  /** 循环播放 */
  loop?: boolean
}

/** 用例级覆盖区（strategy overrides 仅含覆盖字段；合并语义随后端定） */
export interface EvaluationStrategyOverrides {
  dimensions?: TestCaseDimensionItem[]
  backgroundNoise?: TestCaseBackgroundNoiseItem | null
}

/** 用例承载契约 config.evaluationStrategy（camelCase Domain 形态） */
export interface CaseEvaluationStrategy {
  strategyId?: string | null
  overrides?: EvaluationStrategyOverrides | null
}

/** 评估策略实体（GET /evaluation/strategies 选项；列表选项带摘要「{名} · 整体维度 {n} 项 · 噪声 {已配置|未配置}」） */
export interface EvaluationStrategy {
  id: number | string
  name: string
  description?: string | null
  dimensions: TestCaseDimensionItem[]
  backgroundNoise?: TestCaseBackgroundNoiseItem | null
}
