/**
 * LLM 供应商 Demo API（infrastructure 层；08_AI对话页.md §3.8/§3.11）。
 * Demo 可先行：用户自配 Base URL/API Key（localStorage iatp:ai-chat:v1:providers），
 * OpenAI 兼容 /chat/completions 直连 + GET {baseUrl}/models 试探。
 * 2026-10-17 审计返修（P1/P2-1）：测试连接/自动获取模型/发送对话均换**真实请求**
 * （fetch 直连用户供应商），删除恒成功的 mock 结果与杜撰数据回显；失败回语义化错误。
 * 红线④：不接平台后端；用户密钥仅随浏览器直连供应商，不上传平台。
 */
import type { LlmProvider } from '@/domain/models/aiChat'

export type LlmConnectionTestResult = {
  ok: boolean
  /** 探测到的模型 id 列表（自动获取模型列表 / 测试连接回填用） */
  models: string[]
  /** 失败原因（ok=false 时，§6 中文文案） */
  error?: string
}

/** 对话消息（OpenAI 兼容 roles：system/user/assistant） */
export type ChatCompletionMessage = {
  role: 'system' | 'user' | 'assistant'
  content: string
}

/** 归一 Base URL：去尾部斜杠，保证 `${base}/models`、`${base}/chat/completions` 拼接正确 */
function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.replace(/\/+$/, '')
}

/** fetch 公共头：OpenAI 兼容 Bearer 鉴权 */
function authHeaders(apiKey: string): Record<string, string> {
  return { Authorization: `Bearer ${apiKey}` }
}

function toErrorMessage(status: number | null, fallback: string): string {
  if (status === null) return '无法连接该供应商'
  if (status === 401 || status === 403) return '认证失败：请检查 API Key 是否有效'
  if (status === 404) return '接口地址不存在：请检查 Base URL 是否包含 /v1 等路径'
  if (status >= 500) return '供应商服务异常，请稍后重试'
  return fallback
}

/**
 * 测试连接：GET {baseUrl}/models 试探成功回填模型列表（§3.11 表单「测试连接」）。
 * 真实网络请求（P2-1 返修）；失败返回 ok=false + 中文原因（表单 toast 呈现）。
 */
export async function testProviderConnection(
  provider: Pick<LlmProvider, 'baseUrl' | 'apiKey'>
): Promise<LlmConnectionTestResult> {
  if (!provider.baseUrl || !provider.apiKey) {
    return { ok: false, models: [], error: '请先填写 Base URL 与 API Key' }
  }
  const url = `${normalizeBaseUrl(provider.baseUrl)}/models`
  try {
    const res = await fetch(url, { headers: authHeaders(provider.apiKey) })
    if (!res.ok) {
      return { ok: false, models: [], error: toErrorMessage(res.status, `连接失败（HTTP ${res.status}）`) }
    }
    const data = await res.json()
    const items = Array.isArray(data?.data) ? (data.data as unknown[]) : []
    const models = items
      .map((item) => (typeof item === 'object' && item !== null ? (item as { id?: unknown }).id : undefined))
      .filter((id): id is string => typeof id === 'string' && id.length > 0)
    return { ok: true, models }
  } catch {
    return { ok: false, models: [], error: '无法连接该供应商' }
  }
}

/**
 * 自动获取模型列表：同 GET {baseUrl}/models（§3.11 表单「自动获取模型列表」）。
 * 真实请求；失败返回 []（表单侧按 testProviderConnection 语义呈现）。
 */
export async function fetchProviderModels(
  provider: Pick<LlmProvider, 'baseUrl' | 'apiKey'>
): Promise<string[]> {
  const result = await testProviderConnection(provider)
  return result.ok ? result.models : []
}

/**
 * 发送对话（Demo 态直连用户供应商 /chat/completions；§3.8「Demo 可先行」）。
 * P1 返修：真实 POST（OpenAI 兼容 body { model, messages, stream:false }），
 * 返回模型正文；流式视觉由 use-chat-handler 本地逐块渲染承担（stream:false + 打字机）。
 * 失败抛中文 ApiError 语义消息（use-chat-handler 落 error 消息态）。
 */
export async function sendChatCompletion(request: {
  baseUrl: string
  apiKey: string
  model: string
  messages: ChatCompletionMessage[]
  signal?: AbortSignal
}): Promise<string> {
  const { baseUrl, apiKey, model, messages, signal } = request
  const url = `${normalizeBaseUrl(baseUrl)}/chat/completions`
  let res: Response
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...authHeaders(apiKey),
      },
      body: JSON.stringify({ model, messages, stream: false }),
      signal,
    })
  } catch (err) {
    if (signal?.aborted) throw new Error('生成已中断')
    throw new Error('网络连接失败或服务无响应')
  }
  if (!res.ok) {
    throw new Error(toErrorMessage(res.status, `对话请求失败（HTTP ${res.status}）`))
  }
  const data = (await res.json()) as {
    choices?: Array<{ message?: { content?: unknown } }>
  }
  const content = data?.choices?.[0]?.message?.content
  if (typeof content !== 'string' || content.length === 0) {
    throw new Error('模型返回为空，请重试或更换模型')
  }
  return content
}
