/**
 * API client 桩（infrastructure 层）。
 * 红线④：当前一律 mock 常量，不接真实后端、不起后端服务。
 * TODO(API 接线): 在此实现统一 fetch 封装（baseURL / 错误码映射 / SSE 订阅），
 * 形态对照 api_gateway/schemas/；替换 infrastructure/stores 与 mock 常量数据源。
 */

export const apiClient = {
  async get<T>(_path: string): Promise<T> {
    throw new Error('TODO(API 接线): 未接真实后端，当前页面全部使用 mock 数据')
  },
  async post<T>(_path: string, _body?: unknown): Promise<T> {
    throw new Error('TODO(API 接线): 未接真实后端，当前页面全部使用 mock 数据')
  },
}
