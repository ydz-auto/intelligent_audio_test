/**
 * Core HTTP request module and interceptor logic
 * Shared across all API domain modules
 */

import { API_CONFIG } from '../config';

const apiBaseUrl = API_CONFIG.baseUrl;

export interface RequestOptions extends RequestInit {
  isMultipart?: boolean;
  responseType?: 'json' | 'blob' | 'arraybuffer' | 'text';
  data?: any;
  unwrapResponse?: boolean;
  params?: Record<string, any>;
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

  console.log(`[API Request] ${method} ${url}`, data || '');

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

      console.log(`[IPC Response] ${method} ${normalizedUrl}:`, result);

      if (result && result.code !== undefined && result.code !== 0 && result.code !== 200 && result.code !== 201) {
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
          console.log(`[API Response] ${method} ${normalizedUrl}: Binary response (${blobResult instanceof Blob ? 'Blob' : 'ArrayBuffer'}, ${blobResult instanceof Blob ? blobResult.size : 'N/A'} bytes)`);
          return blobResult as unknown as T;
        }
        if (result instanceof ArrayBuffer || result instanceof Uint8Array) {
           const blob = new Blob([result as any]);
           const blobResult = responseType === 'blob' ? blob : await blob.arrayBuffer();
           console.log(`[API Response] ${method} ${normalizedUrl}: Binary response (${blobResult instanceof Blob ? 'Blob' : 'ArrayBuffer'}, ${blobResult instanceof Blob ? blobResult.size : 'N/A'} bytes)`);
           return blobResult as unknown as T;
        }
        console.log(`[API Response] ${method} ${normalizedUrl}: Expected binary response but got:`, typeof result, result);
      }

      if (unwrapResponse && result && result.data !== undefined && !result.isBinary) {
        const responseData = applyResponseInterceptors(result.data);
        console.log(`[API Response] ${method} ${normalizedUrl}: Success`, responseData);
        return responseData as T;
      }

      const directResponse = applyResponseInterceptors(result);
      console.log(`[API Response] ${method} ${normalizedUrl}: Success (direct format)`, directResponse);
      return directResponse as T;
    } catch (err) {
      console.error(`[IPC Error] ${method} ${normalizedUrl}:`, err);
      throw err;
    }
  }

  const fetchOptions: RequestInit = {method, headers: requestOptions.headers || {},
    signal,
    ...requestOptions
  };

  if (!isMultipart && !(requestData instanceof FormData)) {
    (fetchOptions.headers as Record<string, string>)['Content-Type'] = 'application/json';
  }

  if (requestData && (method === 'POST' || method === 'PUT' || method === 'PATCH')) {
    fetchOptions.body = requestData instanceof FormData ? requestData : JSON.stringify(requestData);
  }

  let finalUrl = normalizedUrl;
  if (method === 'GET' && requestOptions.params) {
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
    const result = await handleResponse(response, responseType, unwrapResponse);
    const responseData = applyResponseInterceptors(result);
    console.log(`[API Response] ${method} ${finalUrl}: Success`, responseData);
    return responseData as T;
  } catch (err) {
    console.error(`[API Fetch Error] ${method} ${finalUrl}:`, err);
    throw err;
  }
}

async function handleResponse(response: Response, responseType: string = 'json', unwrapResponse: boolean = true): Promise<any> {
  if (responseType === 'blob') {
    return await response.blob();
  }

  if (responseType === 'arraybuffer') {
    return await response.arrayBuffer();
  }

  let data : any;
  try {
    console.log(`[Handle Response] status: ${response.status} ${response.statusText}`);

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
    const error : any = new Error(data.message || 'API Request failed');
    error.code = data.code;
    error.detail = data.detail;
    error.errors = data.errors;
    throw error;
  }

  if (unwrapResponse && (data.code !== undefined || data.success !== undefined)) {
    if (data.code !== undefined) {
      const code = Number(data.code);
      // 允许更多的成功状态码，包括测试连接API的返回
      if (code !== 0 && code !== 200 && code !== 201) {
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
