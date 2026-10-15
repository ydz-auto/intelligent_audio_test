/**
 * Agent 会话 API 占位桩（infrastructure 层；08_AI对话页.md §3.8）。
 * DSH Agent 后端未实施：会话/Run/SSE 契约全部待后端立项，这里只留接口形状，
 * 前端先行版式（use-chat-handler 本地 mock 流式回显骨架）。
 *
 * TODO(API 接线): 接 DSH Bridge 后实现——
 *   POST /api/v1/agent/sessions / GET /api/v1/agent/sessions/{id}
 *   POST /api/v1/agent/sessions/{id}/runs
 *   GET  /api/v1/agent/runs/{rid}/events（SSE，复用基座 taskChannelPort）
 */
export const agentApi = {
  /** 创建/恢复会话 */
  createSession: null as unknown,
  /** 发起 Run */
  createRun: null as unknown,
  /** 订阅 Run 事件流（SSE） */
  subscribeRunEvents: null as unknown,
}
