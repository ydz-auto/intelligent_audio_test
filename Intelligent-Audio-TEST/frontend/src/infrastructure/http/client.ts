/**
 * Core HTTP request module and interceptor logic
 * Shared across all API domain modules
 */

import { API_CONFIG } from '../../utils/config';
import { AuthMode, getEffectiveAuthMode, HttpStatus } from '@/domain/enums';

const apiBaseUrl = API_CONFIG.baseUrl;

export interface RequestOptions extends RequestInit {
  isMultipart?: boolean;
  responseType?: 'json' | 'blob' | 'arraybuffer' | 'text';
  data?: any;
  unwrapResponse?: boolean;
  params?: Record<string, any>;
  /** 跳过 401 自动登出/跳转（用于 login 接口本身，避免密码错误触发登出循环） */
  skipAuthRedirect?: boolean;
  /** INT-1314：请求超时（毫秒）；fetch 分支经 AbortController 实现，IPC 分支透传给主进程 */
  timeout?: number;
  /** 静默失败（INT-1286：后台/尽力型请求失败不落控制台 SEVERE，调用方自处理错误） */
  silentError?: boolean;
}

/**
 * INT-1314：请求超时信号——调用方 signal 与超时信号合并。
 * 返回 cleanup 用于释放定时器/外部监听；超时或外部中止后由调用方在 finally 调用。
 */
function createAbortTimeoutSignal(externalSignal?: AbortSignal | null, timeout?: number): { signal?: AbortSignal; cleanup: () => void } {
  if (!timeout || typeof timeout !== 'number' || timeout <= 0) {
    return { signal: externalSignal || undefined, cleanup: () => {} };
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const onExternalAbort = () => controller.abort();
  if (externalSignal) {
    if (externalSignal.aborted) {
      controller.abort();
    } else {
      externalSignal.addEventListener('abort', onExternalAbort, { once: true });
    }
  }
  return {
    signal: controller.signal,
    cleanup: () => {
      clearTimeout(timer);
      externalSignal?.removeEventListener('abort', onExternalAbort);
    },
  };
}

const defaultRequestInterceptors: Array<(config: { method: string; url: string; data: any; options: RequestOptions }) => Promise<{ method: string; url: string; data: any; options: RequestOptions }>> = [];

const defaultResponseInterceptors: Array<(response: any) => any> = [];

export function addRequestInterceptor(interceptor: (config: { method: string; url: string; data: any; options: RequestOptions }) => Promise<{ method: string; url: string; data: any; options: RequestOptions }>) {
  defaultRequestInterceptors.push(interceptor);
}

export function addResponseInterceptor(interceptor: (response: any) => any) {
  defaultResponseInterceptors.push(interceptor);
}

async function applyRequestInterceptors(config: { method: string; url: string; data: any; options: RequestOptions }): Promise<{ method: string; url: string; data: any; options: RequestOptions }> {
  let currentConfig = config;
  for (const interceptor of defaultRequestInterceptors) {
    currentConfig = await interceptor(currentConfig);
  }
  return currentConfig;
}

function applyResponseInterceptors(response: any): any {
  let currentResponse = response;
  for (const interceptor of defaultResponseInterceptors) {
    currentResponse = interceptor(currentResponse);
  }
  return currentResponse;
}

// ===== JWT 认证拦截器 =====
// 自动在请求头注入 Authorization: Bearer <token>
addRequestInterceptor(async (config) => {
  const token = localStorage.getItem('auth_token')
  if (token) {
    if (!config.options.headers) {
      config.options.headers = {} as Record<string, string>
    }
    ;(config.options.headers as Record<string, string>)['Authorization'] = `Bearer ${token}`
  }
  return config
})

// ===== 401 自动登出拦截器 =====
addResponseInterceptor((response: any) => {
  return response
})

/**
 * Core Request function that bridges Electron IPC or Fetch
 */
export async function request<T = any>(
  method: string,
  url: string,
  data: any = null,
  options: RequestOptions = {}
): Promise<T> {
  const isMultipart = options.isMultipart || false;
  const signal = options.signal;
  const responseType = options.responseType || 'json';
  const unwrapResponse = options.unwrapResponse !== false;
  const normalizedUrl = url.startsWith('http') ? url : `${apiBaseUrl.replace(/\/$/, '')}/${url.replace(/^\//, '')}`;

  const interceptedConfig = await applyRequestInterceptors({ method, url: normalizedUrl, data, options });
  method = interceptedConfig.method;
  const requestData = interceptedConfig.data;
  const requestOptions = interceptedConfig.options;

  if (window.electronAPI && window.electronAPI.apiRequest) {
    try {
      let ipcData = requestData;
      const requestHeaders = {...(requestOptions.headers || {}) } as Record<string, string>;

      if (requestData instanceof FormData) {
        const obj : Record<string, any> = {};
        for (const [key, value] of (requestData as any).entries()) {
          let processedValue = value;

          if (value instanceof File) {
            processedValue = {isFilePath: true, path: window.webUtils ? window.webUtils.getPathForFile(value) : value.name, name: value.name, type: value.type, size: value.size};
          } else if (value instanceof Blob) {
            processedValue = await value.arrayBuffer();
          }

          if (obj[key] !== undefined) {
            if (Array.isArray(obj[key])) {
              obj[key].push(processedValue);
            } else {
              obj[key] = [obj[key], processedValue];
            }
          } else {
            obj[key] = processedValue;
          }
        }
        ipcData = obj;
      } else if (requestData && typeof requestData === 'object') {
        try {
          ipcData = JSON.parse(JSON.stringify(requestData));
        } catch (e) {
          console.warn('[API] Failed to deep clone data for IPC, using original', e);
        }

        if (!isMultipart && !requestHeaders['Content-Type']) {
          requestHeaders['Content-Type'] = 'application/json';
        }
      }

      const result = await window.electronAPI.apiRequest({
        method: method.toUpperCase() as any,
        url: normalizedUrl,
        data: ipcData,
        params: (requestOptions as any).params,
        isMultipart: isMultipart,
        headers: requestHeaders,
        options: {responseType: responseType as any, timeout: (requestOptions as any).timeout}
      });

      // IPC 返回的业务状态码非成功值（0 表示无业务错误，200/201 为 HTTP 成功）则抛错
      if (result && result.code !== undefined && result.code !== 0 && result.code !== HttpStatus.OK && result.code !== HttpStatus.CREATED) {
        const error : any = new Error(result.message || 'IPC Request failed');
        error.code = result.code;
        error.detail = result.detail || result.error;
        throw error;
      }

      if (responseType === 'blob' || responseType === 'arraybuffer') {
        if (result && result.isBinary) {
          const contentType = result.headers?.['content-type'] || 'application/octet-stream';
          const blob = new Blob([result.data], { type: contentType });
          const blobResult = responseType === 'blob' ? blob : await blob.arrayBuffer();
          return blobResult as unknown as T;
        }
        if (result instanceof ArrayBuffer || result instanceof Uint8Array) {
           const blob = new Blob([result as any]);
           const blobResult = responseType === 'blob' ? blob : await blob.arrayBuffer();
           return blobResult as unknown as T;
        }
        // 异常分支：期望二进制但实际返回非二进制（如 JSON 错误体），保留告警便于定位
        console.warn(`[API Response] ${method} ${normalizedUrl}: Expected binary response but got:`, typeof result, result);
      }

      if (unwrapResponse && result && result.data !== undefined && !result.isBinary) {
        const responseData = applyResponseInterceptors(result.data);
        return responseData as T;
      }

      const directResponse = applyResponseInterceptors(result);
      return directResponse as T;
    } catch (err) {
      console.error(`[IPC Error] ${method} ${normalizedUrl}:`, err);
      throw err;
    }
  }

  // INT-1314：请求超时控制（fetch 分支）——调用方 signal 与超时信号合并，finally 释放定时器
  const { signal: effectiveSignal, cleanup: cleanupTimeoutSignal } = createAbortTimeoutSignal(signal, requestOptions.timeout);

  const fetchOptions: RequestInit = { ...requestOptions, method, headers: requestOptions.headers || {}, signal: effectiveSignal };

  // FormData 与 URLSearchParams 均为非 JSON 通道：浏览器自动设置 Content-Type（含 boundary），不覆盖
  const isFormData = requestData instanceof FormData;
  const isUrlSearchParams = requestData instanceof URLSearchParams;
  if (!isFormData && !isUrlSearchParams) {
    (fetchOptions.headers as Record<string, string>)['Content-Type'] = 'application/json';
  }

  if (requestData && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
    fetchOptions.body = isFormData ? requestData : (isUrlSearchParams ? requestData : JSON.stringify(requestData));
  }

  let finalUrl = normalizedUrl;
  // query 参数对任意方法生效（DELETE ?cascade、POST presign 等均依赖此拼接）
  if (requestOptions.params) {
    const filteredParams = Object.fromEntries(
      Object.entries(requestOptions.params).filter(([_, value]) => value !== undefined && value !== null)
    );
    const query = new URLSearchParams(filteredParams).toString();
    if (query) {
      finalUrl = `${normalizedUrl}${normalizedUrl.includes('?') ? '&' : '?'}${query}`;
    }
  }

  try {
    const response = await fetch(finalUrl, fetchOptions);
    const result = await handleResponse(response, responseType, unwrapResponse, requestOptions.skipAuthRedirect);
    const responseData = applyResponseInterceptors(result);
    return responseData as T;
  } catch (err) {
    if (!options.silentError) console.error(`[API Fetch Error] ${method} ${finalUrl}:`, err);
    throw err;
  } finally {
    cleanupTimeoutSignal();
  }
}

async function handleResponse(response: Response, responseType: string = 'json', unwrapResponse: boolean = true, skipAuthRedirect: boolean = false): Promise<any> {
  // 二进制分支（blob / arraybuffer）：非 2xx 错误响应多为 JSON error body，
  // 必须先行判 response.ok——否则错误 JSON 会被当作成功二进制下载成损坏文件
  // （INT-1001 根因，本卡 INT-1005 修复：非 ok 时 clone 读 message/detail 抛给调用方）
  if (responseType === 'blob' || responseType === 'arraybuffer') {
    if (!response.ok) {
      let errorData: any = null;
      try {
        errorData = await response.clone().json();
      } catch {
        try {
          const text = await response.clone().text();
          if (text) errorData = { message: text };
        } catch {
          errorData = null;
        }
      }
      const error: any = new Error(errorData?.message || errorData?.detail || 'API Request failed');
      if (errorData) {
        error.code = errorData.code;
        error.detail = errorData.detail;
        error.errors = errorData.errors;
      }
      throw error;
    }
    return responseType === 'blob' ? await response.blob() : await response.arrayBuffer();
  }

  let data : any;
  try {
    try {
      const cloned = response.clone();
      data = await response.json();
    } catch (jsonErr: any) {
      console.warn(`[Handle Response] response.json() failed, trying text fallback:`, jsonErr.message);
      const text = await response.clone().text();

      if (text.trim().startsWith('<')) {
        throw new Error(`Server returned HTML instead of JSON: ${response.status} ${response.statusText}`);
      }

      data = JSON.parse(text);
    }
  } catch (err: any) {
    throw new Error(`Server returned invalid JSON: ${response.status} ${response.statusText} - ${err.message}`);
  }

  if (!response.ok) {
    // 401 未授权：清除登录态并跳转登录页（仅当后端开启认证模式且未显式跳过时）
    if (response.status === HttpStatus.UNAUTHORIZED && !skipAuthRedirect) {
      const authMode = getEffectiveAuthMode()
      if (authMode !== AuthMode.OFF) {
        import('../../store/authStore').then(async ({ useAuthStore }) => {
          const auth = useAuthStore()
          // authApi.logout 携带 skipAuthRedirect，登出请求自身 401 不会再进入本分支，
          // 故不会因 token 失效触发无限 POST /auth/logout 循环（INT-622 回归）。
          // 先 await 完成本地清理再跳转，避免跳转后残留登录态。
          await auth.logout()
          const current = window.location.hash.slice(1) || '/'
          // 已在登录页时不再叠加 redirect 参数（防嵌套膨胀：
          // #/login?redirect=/login?redirect=... 无界递归）
          if (current.split('?')[0] === '/login') {
            window.location.hash = '#/login'
          } else {
            window.location.hash = `#/login?redirect=${encodeURIComponent(current)}`
          }
        })
      }
    }
    const error : any = new Error(data.message || data.detail || 'API Request failed');
    error.code = data.code;
    error.detail = data.detail;
    error.errors = data.errors;
    throw error;
  }

  if (unwrapResponse && (data.code !== undefined || data.success !== undefined)) {
    if (data.code !== undefined) {
      const code = Number(data.code);
      // 允许更多的成功状态码，包括测试连接API的返回
      if (code !== 0 && code !== HttpStatus.OK && code !== HttpStatus.CREATED) {
        const error : any = new Error(data.message || 'API Request failed');
        error.code = data.code;
        error.detail = data.detail;
        error.errors = data.errors;
        throw error;
      }
      return data.data;
    } else if (data.success !== undefined) {
      if (!data.success) {
        const error : any = new Error(data.message || 'API Request failed');
        error.detail = data.detail;
        throw error;
      }
      return data.data;
    }
  }

  return data;
}

export { apiBaseUrl };
