/**
 * LLM 供应商 API（infrastructure 层；08_AI对话页 §3.11 Demo 可先行）。
 * 用户自管 LLM API 供应商直连（chatbox 式，本地 localStorage），
 * 不走平台 request()（避免注入平台 auth header 泄漏给外部供应商）——直接 fetch。
 * 密钥仅存用户本地，不上传平台后端；正式版密钥管理待后端立项。
 */
export interface ChatCompletionMessage {
  role: 'system' | 'user' | 'assistant'
  content: string
}

export interface SendChatCompletionParams {
  baseUrl: string
  apiKey: string
  model: string
  messages: ChatCompletionMessage[]
  signal?: AbortSignal
}

/** OpenAI 兼容 /chat/completions（Demo 直连；返回 assistant 正文） */
async function sendChatCompletion(
  params: SendChatCompletionParams
): Promise<string> {
  const { baseUrl, apiKey, model, messages, signal } = params
  const url = `${baseUrl.replace(/\/+$/, '')}/chat/completions`
  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      model,
      messages,
      stream: false,
    }),
    signal,
  })
  if (!response.ok) {
    throw new Error(`AI 服务响应异常（HTTP ${response.status}）`)
  }
  const data = await response.json()
  const content: unknown = data?.choices?.[0]?.message?.content
  if (typeof content !== 'string') {
    throw new Error('AI 服务返回格式无法解析')
  }
  return content
}

/** 自动获取供应商模型列表：GET {baseUrl}/models（试探连接 + 回填模型） */
async function fetchProviderModels(
  baseUrl: string,
  apiKey: string,
  signal?: AbortSignal
): Promise<string[]> {
  const url = `${baseUrl.replace(/\/+$/, '')}/models`
  const response = await fetch(url, {
    method: 'GET',
    headers: {
      Authorization: `Bearer ${apiKey}`,
    },
    signal,
  })
  if (!response.ok) {
    throw new Error(`无法连接该供应商（HTTP ${response.status}）`)
  }
  const data = await response.json()
  const models: unknown = data?.data
  if (!Array.isArray(models)) {
    throw new Error('该供应商未返回模型列表')
  }
  return models
    .map((m) => (typeof m === 'string' ? m : (m as { id?: unknown })?.id))
    .filter((m): m is string => typeof m === 'string' && m.length > 0)
}

/** LLM 供应商 API（Demo 直连，用户自管 Base URL/Key） */
export const llmProviderApi = {
  sendChatCompletion,
  fetchProviderModels,
}
