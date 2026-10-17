/**
 * LLM 供应商 Demo API（infrastructure 层；08_AI对话页.md §3.8/§3.11）。
 * Demo 可先行：用户自配 Base URL/API Key（localStorage iatp:ai-chat:v1:providers），
 * OpenAI 兼容 /chat/completions 直连 + GET {baseUrl}/models 试探。
 * 红线④：本桩不接真实后端——测试连接/自动获取模型返回 mock 结果（不发网络请求），
 * TODO(API 接线)：正式 Demo 直连时换 fetch(baseUrl + 路径)，OpenAI 兼容协议。
 */
import type { LlmProvider } from '@/domain/models/aiChat'

export type LlmConnectionTestResult = {
  ok: boolean
  /** 探测到的模型 id 列表（自动获取模型列表 / 测试连接回填用） */
  models: string[]
  /** 失败原因（ok=false 时） */
  error?: string
}

/** mock 探测模型清单（红线④ 不接真实后端；TODO(API 接线) 换 GET {baseUrl}/models） */
const MOCK_MODEL_LIST = ['gpt-4o', 'gpt-4o-mini', 'deepseek-chat', 'deepseek-reasoner', 'glm-4-plus']

/**
 * 测试连接：GET {baseUrl}/models 试探成功回填模型列表（§3.11 表单「测试连接」）。
 * Demo 态返回 mock 成功（字段齐全即通过），不发真实网络请求（红线④）。
 * TODO(API 接线)：换 fetch(`${provider.baseUrl}/models`, { headers: { Authorization: `Bearer ${provider.apiKey}` } })。
 */
export async function testProviderConnection(provider: Pick<LlmProvider, 'baseUrl' | 'apiKey'>): Promise<LlmConnectionTestResult> {
  // 表单校验前置已保证 baseUrl/apiKey 非空；此处仍兜底返回失败语义
  if (!provider.baseUrl || !provider.apiKey) {
    return { ok: false, models: [], error: '请先填写 Base URL 与 API Key' }
  }
  return { ok: true, models: MOCK_MODEL_LIST }
}

/**
 * 自动获取模型列表：同 GET {baseUrl}/models（§3.11 表单「自动获取模型列表」）。
 * Demo 态返回 mock 模型清单；TODO(API 接线)：换真实请求。
 */
export async function fetchProviderModels(provider: Pick<LlmProvider, 'baseUrl' | 'apiKey'>): Promise<string[]> {
  const result = await testProviderConnection(provider)
  return result.ok ? result.models : []
}

/**
 * 发送对话（Demo 态直连用户供应商 /chat/completions；§3.8 占位）。
 * 红线④：当前 mock 流式由 use-chat-handler 承担，本桩仅声明契约。
 * TODO(API 接线)：换 POST {baseUrl}/chat/completions，OpenAI 兼容 body
 * { model, messages, stream } 并经 SSE/分块读取流式回复。
 */
export async function sendChatCompletion(_request: {
  baseUrl: string
  apiKey: string
  model: string
  messages: Array<{ role: 'system' | 'user' | 'assistant'; content: string }>
}): Promise<never> {
  throw new Error('TODO(API 接线): Demo 直连 /chat/completions 未接线')
}
