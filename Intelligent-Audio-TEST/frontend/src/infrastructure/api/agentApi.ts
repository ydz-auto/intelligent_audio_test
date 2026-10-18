/**
 * Agent 后端 API 占位（infrastructure 层；08_AI对话页 §3.8 数据交互面占位表）。
 * F6（DeepSeek Harness：对话/流式/工具链后端 + 会话持久化）尚未立项，
 * 本模块仅登记契约（§3.8 / Studio §15.5 在册），不发起任何请求、不造数据兜底。
 * FEAT 落地后由【接线·新Vue】卡替换为真实接口。
 *
 * 契约占位（全部「待后端立项」）：
 * - 会话创建/恢复：POST /api/v1/agent/sessions、GET /api/v1/agent/sessions/{id}
 * - 发送消息→流式回复：POST /api/v1/agent/sessions/{id}/runs + GET /api/v1/agent/runs/{rid}/events（SSE）
 * - 停止生成：取消 Run API
 * - 文档创建/读取/人工编辑：POST/GET/PUT /api/v1/report-studio/documents（expected_version 乐观锁）
 * - 版本列表/恢复：GET /documents/{id}/versions、POST /documents/{id}/restore
 * - 图表数据：GET /documents/{id}/charts/{chartId}
 * - 导出作业/下载：POST /exports、GET /exports/{id}、GET /exports/{id}/download
 * - Agent 工具装配（9 个，§3.4 表）：DSH Report Studio Tool Plugin
 */

/** 待后端立项标记（供 UI 标注数据交互面状态） */
export const AGENT_BACKEND_STATUS = '待后端立项' as const

/**
 * 创建/恢复 Agent 会话（占位；待后端立项）。
 * 不发起请求：后端无端点，调用方应展示「待后端立项」提示而非等待失败。
 */
export async function createAgentSession(): Promise<never> {
  throw new Error(
    `Agent 会话接口${AGENT_BACKEND_STATUS}（F6：DeepSeek Harness 未实施）`
  )
}

/**
 * 发起 Run + 订阅流式事件（占位；待后端立项）。
 * 不发起请求：后端无端点，调用方应展示「待后端立项」提示而非等待失败。
 */
export async function runAgentTurn(): Promise<never> {
  throw new Error(
    `Agent Run/SSE 接口${AGENT_BACKEND_STATUS}（F6：DeepSeek Harness 未实施）`
  )
}

/** Agent 后端 API 占位出口（契约登记；所有方法待后端立项，不发起请求） */
export const agentApi = {
  status: AGENT_BACKEND_STATUS,
  createSession: createAgentSession,
  runTurn: runAgentTurn,
}
