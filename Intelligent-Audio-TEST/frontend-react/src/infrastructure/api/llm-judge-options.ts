/**
 * LLM Judge 模型 / Prompt 模板可选值（11_用例域.md §5.1.3.1 已选维度参数卡）。
 *
 * 归属后端口径：可用模型池由评估服务的 LLM_JUDGE 配置决定，Prompt 模板同源；
 * 前端自持枚举即硬编码（INT-1658），必须由后端下发。
 *
 * 后端现状（2026-10-24 实测 15000 真实库栈）：无枚举端点；
 * `GET /api/v1/evaluation/dimensions` 读模型也不下发 llm_judge_config
 * （维度 result_type 仅 1 数值 / 2 布尔 / 3 文本，且全量 61 个维度无 llm_judge 口径）
 * → 按 §3.2 在本层留桩 `// 待接线`，取值沿用 V9.7.10
 * OverallEvaluationEditor.vue llmModelOptions/llmPromptOptions（Vue 基准）。
 * 待 FEAT INT-1671（LLM Judge 枚举端点 + 维度读模型 llm_judge 标识）落地后
 * 本函数改为 request 调用，调用方不变。
 */
export interface LlmJudgeOptions {
  /** 可选模型（后端 LLM_JUDGE 模型池） */
  models: string[]
  /** 可选 Prompt 模板名 */
  promptTemplates: string[]
}

/** 桩示例值（V9.7.10 口径；FEAT 端点落地后由后端下发，形态对齐 options 契约） */
const LLM_JUDGE_OPTIONS_STUB: LlmJudgeOptions = {
  models: ['gpt-4', 'gpt-4o', 'gpt-3.5-turbo', 'claude-3-opus', 'claude-3-sonnet'],
  promptTemplates: ['default', 'accuracy', 'fluency', 'relevance'],
}

/**
 * LLM Judge 可选值（待接线：后端枚举端点）。
 * 真实端点形态约定 `GET /api/v1/evaluation/llm-judge/options`
 * → `{ models: string[], prompt_templates: string[] }`，落库口径同
 * `config.dimensions[].llmJudgeConfig.{model,promptTemplate}`。
 */
export function getLlmJudgeOptions(): LlmJudgeOptions {
  // 待接线（FEAT INT-1671）：真实端点立项后改为
  //   const dto = await request<LlmJudgeOptionsDto>('GET', '/evaluation/llm-judge/options')
  //   return { models: dto.models, promptTemplates: dto.prompt_templates }
  return LLM_JUDGE_OPTIONS_STUB
}

/**
 * 当前值并入可选集：存量用例的 model/promptTemplate 可能是旧值或手填值，
 * 不在后端候选集里也必须能回显（否则 Select 显示空白）。
 */
export function withCurrentOption(
  options: string[],
  current: string | null | undefined
): string[] {
  if (!current || options.includes(current)) return options
  return [current, ...options]
}
