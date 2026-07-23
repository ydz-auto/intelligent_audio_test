/**
 * Backend API Integration Service
 * Base URL is usually http://localhost:5000/api/v1
 */

export interface AlgorithmDefinition {
  id?: number;
  type: string;
  name: string;
  group_id?: number;
  group_name?: string;
  description?: string;
  status: string;
  icon?: string;
  display_order: number;
  params?: AlgorithmParam[];
  mappings?: {
    device: ParamMapping[];
    api: ParamMapping[];
    evaluation: ParamMapping[];
  };
  created_at?: string;
  updated_at?: string;
}

export interface AlgorithmParam {
  id?: number;
  algorithm_type: string;
  param_code: string;
  param_name?: string;
  param_type: string;
  required: boolean;
  default_value?: string;
  validation_rules?: string;
  help_text?: string;
  component?: string;
  ui_order: number;
  ui_group: string;
  hidden: boolean;
}

export interface AlgorithmGroup {
  id?: number;
  name: string;
  description?: string;
  icon?: string;
  display_order: number;
  deleted?: boolean;
  created_at?: string;
  updated_at?: string;
  algorithm_count?: number;
}

export interface ParamMapping {
  id?: number;
  algorithm_type: string;
  component_type: 'device' | 'api' | 'evaluation';
  direction?: 'input' | 'output';
  field_type?: 'text' | 'audio' | 'number' | 'boolean' | 'json';
  source_param: string;
  target_key: string;
  mapped_from?: string;
  transform_type?: 'none' | 'uppercase' | 'lowercase' | 'json_parse' | 'base64' | 'rttm_to_obj' | 'stm_to_obj';
}

export interface FormSchema {
  algorithmType: string;
  algorithmName: string;
  group_id?: number;
  group_name?: string;
  description?: string;
  groups: {
    name: string;
    label: string;
    fields: FormField[];
  }[];
  fields: FormField[];
}

export interface FormField {
  fieldCode: string;
  fieldName: string;
  fieldType: string;
  required: boolean;
  defaultValue?: any;
  component?: string;
  options?: { value: string; label: string }[];
  validation?: string;
  helpText?: string;
  hidden: boolean;
  uiOrder: number;
  uiGroup: string;
  scope?: string;
}

import { API_CONFIG } from './config';
import type {
  AudioInfo, 
  AudioUploadTask, 
  AudioUploadFile, 
  APIResponse,
  Device, 
  TestCase, 
  TestCaseGroup,
  TestCaseFormData,
  GroupFormData,
  Task, 
  Log, 
  Report, 
  ReportListParams,
  PaginatedResponse,
  EvaluationDimension,
  EvaluationCategory,
  LogQueryParams,
  SPLQueryParams,
  SPLMapping,
  CalibrationData,
  PaginationInfo
} from '../shared/types';

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
async function request<T = any>(
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

export const tasksApi = {
  async getAll(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request('GET', '/tasks', null, { ...options, params });
  },

  async getOne(id: string | number) {
    return request('GET', `/tasks/${id}`);
  },

  async getProgress(id: string | number) {
    return request('GET', `/tasks/${id}/progress`);
  },

  async getCaseDetail(taskId: string | number, caseId: string | number) {
    return request('GET', `/tasks/${taskId}/cases/${caseId}/detail`);
  },

  async getCaseResults(taskId: string | number, caseId: string | number) {
    return request('GET', `/tasks/${taskId}/cases/${caseId}/results`);
  },

  async create(taskData: any) {
    return request('POST', '/tasks', taskData);
  },

  async start(id: string | number) {
    return request('POST', `/tasks/${id}/start`);
  },

  async stop(id: string | number) {
    return request('POST', `/tasks/${id}/stop`);
  },

  async control(id: string | number, action: string) {
    return request('POST', `/tasks/${id}/control`, { action });
  },

  async delete(id: string | number) {
    return request('DELETE', `/tasks/${id}`);
  },

  async getStats(id: string | number) {
    return request('GET', `/tasks/${id}/stats`);
  },

  async batchAction(action: string, ids: (string | number)[]) {
    return request('POST', '/tasks/batch-action', { action, taskIds: ids });
  },

  async mergeTasks(ids: (string | number)[]) {
    return request('POST', '/tasks/merge', { taskIds: ids });
  },

  async updateCases(id: string | number, action: string, caseIds: (string | number)[]) {
    return request('PATCH', `/tasks/${id}/cases`, { action, caseIds: caseIds });
  },

  async retry(id: string | number) {
    return request('POST', `/tasks/${id}/retry`);
  },

  async reevaluate(id: string | number, reevaluateType: string = 'all', reextractDeviceOutput: boolean = false) {
    return request('POST', `/evaluation/task/reevaluate`, { taskId: id, reevaluateType, reextractDeviceOutput });
  },

  async update(id: string | number, taskData: { name?: string; description?: string }) {
    return request('PUT', `/tasks/${id}`, taskData);
  }
};

export const logsApi = {
  async getAll(params: LogQueryParams = {}, options: RequestOptions = {}) {
    return request<PaginatedResponse<Log>>('GET', '/logs', null, { ...options, params });
  },

  async getStats(params: LogQueryParams = {}, options: RequestOptions = {}) {
    return request<Record<string, number>>('GET', '/logs/stats', null, { ...options, params });
  },

  async mark(logIds: (string | number)[], mark: string = 'flagged') {
    return request('PUT', '/logs/mark', { logIds: logIds, mark });
  },

  async export(params: LogQueryParams = {}) {
    return request('GET', '/logs/export', params);
  },

  async clear(params: LogQueryParams = {}) {
    return request('POST', '/logs/clear', params);
  },

  async delete(id: string | number) {
    return request('DELETE', `/logs/${id}`);
  },

  async batchDelete(ids: (string | number)[]) {
    return request('POST', '/logs/batch-delete', { logIds: ids });
  },

  async refresh(lastId: string | number) {
    return request('POST', '/logs/refresh', { lastId: lastId });
  }
};

export const devicesApi = {
  async getAll(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request('GET', '/test-devices', null, { ...options, params });
  },

  async getOne(id: string | number) {
    return request('GET', `/test-devices/${id}`);
  },

  async create(deviceData: any, options: RequestOptions = {}) {
    return request('POST', '/test-devices', deviceData, options);
  },

  async update(id: string | number, deviceData: any, options: RequestOptions = {}) {
    return request('PUT', `/test-devices/${id}`, deviceData, options);
  },

  async delete(id: string | number) {
    return request('DELETE', `/test-devices/${id}`);
  },

  async healthCheck(deviceIds: (string | number)[] = []) {
    return request('POST', '/test-devices/health-check', { deviceIds: deviceIds });
  },

  async getStatuses() {
    return request('GET', '/test-devices/status');
  },

  async scan() {
    return request('POST', '/test-devices/scan');
  },

  async test(id: string | number) {
    return request('POST', `/test-devices/${id}/test`);
  },

  async stopTest(id: string | number) {
    return request('POST', `/test-devices/${id}/stop-test`);
  },

  async getAvailableSerials() {
    return request('GET', '/test-devices/serials');
  },

  async getDriverKeywords() {
    return request('GET', '/test-devices/driver-keywords');
  },

  async getPlaybackDevices(options: RequestOptions = {}) {
    return request('GET', '/playback-devices', null, options);
  }
};

export const playbackApi = {
  async getAll(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request('GET', '/playback-devices', null, { ...options, params });
  },

  async getOne(id: string | number) {
    return request('GET', `/playback-devices/${id}`);
  },

  async create(deviceData: any, options: RequestOptions = {}) {
    return request('POST', '/playback-devices', deviceData, options);
  },

  async update(id: string | number, deviceData: any, options: RequestOptions = {}) {
    return request('PUT', `/playback-devices/${id}`, deviceData, options);
  },

  async delete(id: string | number) {
    return request('DELETE', `/playback-devices/${id}`);
  },

  async getStatuses() {
    return request('GET', '/playback-devices/status');
  },

  async scan() {
    return request('POST', '/playback-devices/scan');
  },

  async associateSpl(id: string | number, splMappingId: string | number) {
    return request('POST', `/playback-devices/${id}/associate-spl`, { splMappingId: splMappingId });
  },

  async test(id: string | number) {
    return request('POST', `/playback-devices/${id}/test`);
  },

  async stopTest(id: string | number) {
    return request('POST', `/playback-devices/${id}/stop-test`);
  },
  
  async checkStatus() {
    return request('GET', '/playback-devices/check-status');
  }
};

export const apisApi = {
  async getAll(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request('GET', '/apis', null, { ...options, params });
  },

  async getOne(id: string | number) {
    return request('GET', `/apis/${id}`);
  },

  async create(apiData: any, options: RequestOptions = {}) {
    return request('POST', '/apis', apiData, options);
  },

  async update(id: string | number, apiData: any, options: RequestOptions = {}) {
    return request('PUT', `/apis/${id}`, apiData, options);
  },

  async delete(id: string | number) {
    return request('DELETE', `/apis/${id}`);
  },

  async healthCheck(id: string | number) {
    return request('POST', `/apis/${id}/health`);
  },

  async testConnection(id: string | number) {
    return request('POST', `/apis/${id}/health`);
  },

  async stopTest(id: string | number) {
    return request('POST', `/apis/${id}/stop-test`);
  }
};

export const audiosApi = {
  async getAll(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request('POST', '/audios', params, { ...options });
  },

  async getAllIds(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request('POST', '/audios/ids', params, { ...options });
  },

  async getOne(id: string | number, options: RequestOptions = {}) {
    return request('GET', `/audios/${id}`, null, options);
  },

  async getByIds(ids: (string | number)[], options: RequestOptions = {}) {
    return request('POST', '/audios/by-ids', { ids }, options);
  },

  async getByMd5(md5List: string[], options: RequestOptions = {}) {
    return request('POST', '/audios/by-md5', { md5_list: md5List }, options);
  },

  async getAllTags(options: RequestOptions = {}) {
    return request('GET', '/audios/tags', null, options);
  },

  async upload(uploadData: any, options: RequestOptions = {}) {
    return request('POST', '/audios/upload', uploadData, { isMultipart: true, ...options });
  },

  async urlImport(importData: any) {
    return request('POST', '/audios/url-import', importData);
  },

  async record(recordData: any) {
    return request('POST', '/audios/record', recordData);
  },

  async convert(id: string | number, convertData: any) {
    return request('POST', `/audios/${id}/convert`, convertData);
  },

  async updateMetadata(id: string | number, metadata: any, options: RequestOptions = {}) {
    return request('PUT', `/audios/${id}/metadata`, metadata, options);
  },

  async batchUpdateAnnotations(data: any, options: RequestOptions = {}) {
    return request('POST', '/audios/batch/annotations', data, options);
  },

  async preview(id: string | number, previewData: any = {}, options: RequestOptions = {}) {
    return request('POST', `/audios/${id}/preview`, previewData, options);
  },

  async stopPreview(id: string | number, options: RequestOptions = {}) {
    return request('POST', `/audios/${id}/stop-preview`, null, options);
  },

  async stream(id: string | number, options: RequestOptions = {}) {
    return request('GET', `/audios/${id}/stream`, null, options);
  },

  async delete(id: string | number, options: RequestOptions = {}) {
    return request('DELETE', `/audios/${id}`, null, options);
  },

  async batchAction(action: string, ids: (string | number)[], extraParams: any = {}, options: RequestOptions = {}) {
    return request('POST', '/audios/batch-action', { action, audioIds: ids, ...extraParams }, options);
  },

  async getStats() {
    return request('GET', '/audios/stats');
  },

  async createUploadTask(taskData: any) {
    return request('POST', '/audios/upload-tasks', taskData);
  },

  async uploadTaskChunk(taskId: string, fileId: string, chunkIndex: number, chunk: Blob) {
    const formData = new FormData();
    formData.append('chunk', chunk);
    formData.append('task_id', taskId);
    formData.append('file_id', fileId);
    formData.append('chunk_index', chunkIndex.toString());
    return request('POST', `/audios/upload-tasks/${taskId}/chunks`, formData, { isMultipart: true });
  },

  async mergeTaskChunks(taskId: string, fileId: string, mergeData: any) {
    return request('POST', `/audios/upload-tasks/${taskId}/files/${fileId}/merge`, mergeData);
  },

  async checkChunkStatus(taskId: string, fileId: string) {
    return request('GET', `/audios/upload-tasks/${taskId}/files/${fileId}/chunks`);
  },

  async folderImport(folderData: any, options: RequestOptions = {}) {
    return request('POST', '/audios/folder-import', folderData, options);
  },

  async initUpload(options: RequestOptions = {}) {
    return request('POST', '/audios/upload/init', {}, options);
  },

  async registerUploadFiles(taskId: string | number, files: any[], options: RequestOptions = {}) {
    return request('POST', '/audios/upload/register', { taskId: taskId, files }, options);
  },

  async uploadChunk(chunkData: any, options: RequestOptions = {}) {
    return request('POST', '/audios/upload/chunk', chunkData, { isMultipart: true, ...options });
  },

  async mergeChunks(fileId: string | number, taskId: string | number, mergeData: any = {}, options: RequestOptions = {}) {
    const normalizedData = { ...mergeData };
    const intFields = ['playbackDeviceId', 'noiseAudioId', 'promptDeviceId'];
    for (const field of intFields) {
      if (normalizedData[field] === '' || normalizedData[field] === undefined) {
        normalizedData[field] = null;
      }
    }
    return request('POST', '/audios/upload/merge', { fileId: fileId, taskId: taskId, ...normalizedData }, options);
  },

  async getUploadProgress(taskId: string | number, options: RequestOptions = {}) {
    return request('GET', '/audios/upload/progress', null, { ...options, params: { task_id: taskId } });
  },

  async getFolderTree(params: any = {}, options: RequestOptions = {}) {
    return request('POST', '/audios/folder-tree', params, options);
  }
};

export const groupsApi = {
  async getAll(params: { page?: number; perPage?: number; algorithmType?: string } = {}) {
    const query = new URLSearchParams();
    if (params.page) query.append('page', String(params.page));
    if (params.perPage) query.append('per_page', String(params.perPage));
    if (params.algorithmType) query.append('algorithm_type', params.algorithmType);
    const queryString = query.toString();
    return request('get', `/groups${queryString ? '?' + queryString : ''}`);
  },

  async create(groupData: any) {
    return request('POST', '/groups', groupData);
  },

  async update(id: string | number, groupData: any) {
    return request('PUT', `/groups/${id}`, groupData);
  },

  async delete(id: string | number) {
    return request('DELETE', `/groups/${id}`);
  },

  async moveCases(sourceId: string | number, targetId: string | number, caseIds: (string | number)[]) {
    return request('POST', '/groups/move-cases', { sourceId: sourceId, targetId: targetId, caseIds: caseIds });
  }
};

export const testcasesApi = {
  async getAll(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request<PaginatedResponse<TestCase>>('GET', '/testcases', null, { ...options, params });
  },

  async getOne(id: string | number) {
    return request<TestCase>('GET', `/testcases/${id}`);
  },

  async create(tcData: TestCaseFormData | FormData | Record<string, any>) {
    return request<TestCase>('POST', '/testcases', tcData);
  },

  async update(id: string | number, tcData: TestCaseFormData | FormData | Record<string, any>) {
    return request<void>('PUT', `/testcases/${id}`, tcData);
  },

  async delete(id: string | number) {
    return request<void>('DELETE', `/testcases/${id}`);
  },

  async copy(id: string | number) {
    return request<TestCase>('POST', `/testcases/${id}/copy`);
  },

  async preview(id: string | number, previewData: any = {}) {
    return request<any>('POST', `/testcases/${id}/preview`, previewData);
  },

  async stopPreview(id: string | number) {
    return request<void>('POST', `/testcases/${id}/stop_preview`);
  },

  async batchAction(action: string, ids: (string | number)[], extraParams: Record<string, any> = {}) {
    return request<any>('POST', '/testcases/batch', { action, ids, ...extraParams });
  },

  async getStats() {
    return request<any>('GET', '/testcases/stats');
  },

  async getGroups(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request<PaginatedResponse<TestCaseGroup>>('GET', '/groups', null, { ...options, params });
  },

  async getTags() {
    return request<string[]>('GET', '/testcases/tags');
  },

  async export(ids: (string | number)[], format: string = 'json', includeDeleted: boolean = false) {
    const options: RequestOptions = {};
    if (format === 'xlsx') {
      options.responseType = 'blob';
    }
    return request<any>('POST', '/testcases/export', { ids, format, include_deleted: includeDeleted }, options);
  },

  async importCases(fileData: FormData) {
    return request<any>('POST', '/testcases/import', fileData, { isMultipart: true });
  },

  async downloadTemplate() {
    const options: RequestOptions = {
      responseType: 'blob'
    };
    return request<any>('GET', '/testcases/template/download', null, options);
  },

  async previewImport(fileData: FormData) {
    return request<any>('POST', '/testcases/import/preview', fileData, { isMultipart: true });
  },

  async createGroup(groupData: GroupFormData) {
    return request<TestCaseGroup>('POST', '/groups', groupData);
  },

  async updateGroup(id: string | number, groupData: GroupFormData) {
    return request<void>('PUT', `/groups/${id}`, groupData);
  },

  async deleteGroup(id: string | number, cascade: boolean = true) {
    return request<void>('DELETE', `/groups/${id}?cascade=${cascade}`);
  },

  async getRefreshTaskStatus(taskId: string) {
    return request<any>('GET', `/testcases/refresh_task/${taskId}`);
  }
};

export const evaluationApi = {
  async getAll(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request<PaginatedResponse<EvaluationDimension>>('GET', '/evaluation/dimensions', null, { ...options, params });
  },

  async getOptions(params: { algorithm_type?: string } = {}) {
    return request<{ dimensions: EvaluationDimension[] }>('GET', '/evaluation/dimensions/options', null, { params });
  },

  async getOne(id: string | number) {
    return request<EvaluationDimension>('GET', `/evaluation/dimensions/${id}`);
  },

  async create(dimData: Partial<EvaluationDimension>) {
    return request<EvaluationDimension>('POST', '/evaluation/dimensions', dimData);
  },

  async update(id: string | number, dimData: Partial<EvaluationDimension>) {
    return request<void>('PUT', `/evaluation/dimensions/${id}`, dimData);
  },

  async delete(id: string | number) {
    return request<void>('DELETE', `/evaluation/dimensions/${id}`);
  },

  async healthCheck(id: string | number) {
    return request<any>('GET', `/evaluation/dimensions/${id}/health`);
  },

  async batchAction(action: string, ids: (string | number)[]) {
    return request<any>('POST', '/evaluation/dimensions/batch', { action, itemIds: ids });
  },

  async calculateScore(id: string | number, value: any) {
    return request<{ score: number }>('POST', `/evaluation/dimensions/${id}/calculate`, { value });
  },

  async import(formData: FormData, updateExisting: boolean = false) {
    formData.append('update_existing', updateExisting.toString());
    return request<any>('POST', '/evaluation/dimensions/import', formData, { isMultipart: true });
  },

  async export(format: 'json' | 'excel' = 'json', ids?: (string | number)[], options: RequestOptions = {}) {
    const params: any = { format };
    if (ids && ids.length > 0) {
      params.ids = ids.join(',');
    }
    return request<any>('GET', '/evaluation/dimensions/export', null, { ...options, params, responseType: 'blob' });
  },

  async getCategories() {
    return request<PaginatedResponse<EvaluationCategory>>('GET', '/evaluation/categories');
  },

  async createCategory(catData: Partial<EvaluationCategory>) {
    return request<EvaluationCategory>('POST', '/evaluation/categories', catData);
  },

  async updateCategory(id: string | number, catData: Partial<EvaluationCategory>) {
    return request<void>('PUT', `/evaluation/categories/${id}`, catData);
  },

  async deleteCategory(id: string | number) {
    return request<void>('DELETE', `/evaluation/categories/${id}`);
  }
};

export const reportsApi = {
  async getAll(params: Partial<ReportListParams> = {}, options: RequestOptions = {}): Promise<PaginatedResponse<Report>> {
    const defaultParams : ReportListParams = {page: 1, perPage: 10, sortBy: 'created_at', order: 'desc' as const};
    const mergedParams = {...defaultParams, ...params};
    return request<PaginatedResponse<Report>>('GET', '/reports', null, { ...options, params: mergedParams });
  },

  async getOne(id: string | number) {
    return request('GET', `/reports/${id}`);
  },

  async delete(id: string | number): Promise<void> {
    return request<void>('DELETE', `/reports/${id}`);
  },

  async batchDelete(ids: (string | number)[]): Promise<void> {
    return request<void>('POST', '/reports/batch-delete', { reportIds: ids });
  },

  async getProgress(id: string | number): Promise<any> {
    return request<any>('GET', `/reports/${id}/progress`);
  },

  async compare(taskIds: (string | number)[], name: string | null = null): Promise<{ id?: string | number; reportId?: string | number }> {
    return request<{ id?: string | number; reportId?: string | number }>('POST', '/reports/compare', { taskIds: taskIds, name });
  },

  async secondaryCompare(reportIds: (string | number)[]): Promise<{ reportKey: (string | number)[]; status: string }> {
    return request<{ reportKey: (string | number)[]; status: string }>('POST', '/reports/secondary-compare', { reportIds: reportIds });
  },

  async export(reportIds: (string | number)[], format: string = 'excel'): Promise<Blob> {
    return request<Blob>('POST', '/reports/export', { ids: reportIds, format }, { responseType: 'blob' });
  },

  async generateTaskReport(taskId: string | number, name: string | null = null) {
    return request('POST', '/reports/generate-task', { taskId: taskId, name });
  },

  async getTrendData(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request('GET', '/reports/trend', null, { ...options, params });
  },

  async getCaseAveragesByFilters(
    taskId: string | number,
    filters: Record<string, any> = {},
    options: RequestOptions = {}
  ) {
    return request('POST', '/reports/case-averages', { taskId, ...filters }, options);
  },

  async create(reportData: any) {
    return request('POST', '/reports', reportData);
  },

  async update(id: string | number, reportData: any) {
    return request('PUT', `/reports/${id}`, reportData);
  },

  async publish(id: string | number) {
    return request('POST', `/reports/${id}/publish`);
  },
  
  async getCases(id: string | number, params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request('GET', `/reports/${id}/cases`, null, { ...options, params });
  },

  async searchCases(id: string | number, body: Record<string, any> = {}, options: RequestOptions = {}) {
    return request('POST', `/reports/${id}/cases/search`, body, options);
  },

  async downloadCaseLogs(reportId: string | number, caseId: string | number): Promise<Blob> {
    return request<Blob>('GET', `/reports/${reportId}/cases/${caseId}/logs/download`, null, { responseType: 'blob' });
  },

  getCaseLogsDownloadUrl(reportId: string | number, caseId: string | number): string {
    const base = apiBaseUrl.replace(/\/$/, '');
    return `${base}/reports/${reportId}/cases/${caseId}/logs/download`;
  }
};

export const splApi = {
  async getAll(params: SPLQueryParams = {}, options: RequestOptions = {}) {
    return request<PaginatedResponse<SPLMapping>>('GET', '/spl', null, { ...options, params });
  },

  async getOne(id: string | number) {
    return request<SPLMapping>('GET', `/spl/${id}`);
  },

  async getByDevice(deviceId: string | number, options: RequestOptions = {}) {
    return request<{items: SPLMapping[], total: number}>('GET', `/spl/by-device/${deviceId}`, null, options);
  },

  async create(splData: Partial<SPLMapping>) {
    return request<SPLMapping>('POST', '/spl', splData);
  },

  async update(id: string | number, splData: Partial<SPLMapping>) {
    return request<void>('PUT', `/spl/${id}`, splData);
  },

  async delete(id: string | number) {
    return request<void>('DELETE', `/spl/${id}`);
  },

  async calibrate(id: string | number, calibrationData: any) {
    return request<CalibrationData>('POST', `/spl/${id}/calibrate`, calibrationData);
  },

  async getHistory(id: string | number) {
    return request<PaginatedResponse<any>>('GET', `/spl/${id}/history`);
  },

  async getCalibrationData(id: string | number) {
    return request<any>('GET', `/spl/${id}/calibration-data`);
  },

  async getStats() {
    return request<{
      total: number;
      calibrated: number;
      uncalibrated: number;
      associatedDevices: number;
    }>('GET', '/spl/stats');
  },

  async stopTestTone(uniqueId?: string | null) {
    return request<any>('POST', '/spl/test-tone/stop', { unique_id: uniqueId ?? undefined });
  }
};

export const statsApi = {
  async getStats() {
    return request<{
      testCases: number;
      tasks: number;
      devices: number;
      audioFiles: number;
    }>('GET', '/home/stats');
  },

  async getStatsDetails() {
    return request<{
      testCases: {
        total: number;
        groups: number;
      };
      tasks: {
        total: number;
        completed: number;
        running: number;
        failed: number;
      };
      devices: {
        online: number;
        offline: number;
        total: number;
      };
      audioFiles: {
        total: number;
        dry: number;
        noise: number;
        prompt: number;
        duration: {
          total: number;
          dry: number;
          noise: number;
          prompt: number;
        };
      };
      playbackDevices: number;
      apis: {
        online: number;
        offline: number;
        total: number;
      };
      reports: number;
      dimensions: {
        total: number;
        withEndpoints: number;
        endpoints: number;
      };
      updatedAt?: string;
    }>('GET', '/home/stats/details');
  },

  async getStatsSummary() {
    return request<{
      recentTasks: Array<{
        id: number;
        name: string;
        type: string;
        status: string;
        total_cases: number;
        completed_cases: number;
        created_at: string;
      }>;
      topGroups: Array<{
        id: string;
        name: string;
        case_count: number;
      }>;
      deviceStatus: {
        online: number;
        offline: number;
      };
    }>('GET', '/home/stats/summary');
  }
};

export const algorithmApi = {
  async getDefinitions(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request<{ data: AlgorithmDefinition[]; total: number }>('GET', '/algorithm/definitions', null, { ...options, params });
  },

  async getDefinition(algoType: string) {
    return request<AlgorithmDefinition>('GET', `/algorithm/definitions/${algoType}`);
  },

  async createDefinition(data: Partial<AlgorithmDefinition>) {
    return request<AlgorithmDefinition>('POST', '/algorithm/definitions', data);
  },

  async updateDefinition(algoType: string, data: Partial<AlgorithmDefinition>) {
    return request<AlgorithmDefinition>('PUT', `/algorithm/definitions/${algoType}`, data);
  },

  async deleteDefinition(algoType: string) {
    return request<void>('DELETE', `/algorithm/definitions/${algoType}`);
  },

  async getGroups(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request<{ data: AlgorithmGroup[]; total: number }>('GET', '/algorithm/groups', null, { ...options, params });
  },

  async getGroup(groupId: number) {
    return request<AlgorithmGroup>('GET', `/algorithm/groups/${groupId}`);
  },

  async createGroup(data: Partial<AlgorithmGroup>) {
    return request<AlgorithmGroup>('POST', '/algorithm/groups', data);
  },

  async updateGroup(groupId: number, data: Partial<AlgorithmGroup>) {
    return request<AlgorithmGroup>('PUT', `/algorithm/groups/${groupId}`, data);
  },

  async deleteGroup(groupId: number) {
    return request<void>('DELETE', `/algorithm/groups/${groupId}`);
  },

  async getParams(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request<{ parameters: AlgorithmParam[]; total: number }>('GET', '/algorithm/params', null, { ...options, params });
  },

  async getParam(paramId: number) {
    return request<AlgorithmParam>('GET', `/algorithm/params/${paramId}`);
  },

  async createParam(data: Partial<AlgorithmParam>) {
    return request<AlgorithmParam>('POST', '/algorithm/params', data);
  },

  async updateParam(paramId: number, data: Partial<AlgorithmParam>) {
    return request<AlgorithmParam>('PUT', `/algorithm/params/${paramId}`, data);
  },

  async deleteParam(paramId: number) {
    return request<void>('DELETE', `/algorithm/params/${paramId}`);
  },

  async getMappings(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request<{ mappings: ParamMapping[]; total: number }>('GET', '/algorithm/mappings', null, { ...options, params });
  },

  async createMapping(data: Partial<ParamMapping>) {
    return request<ParamMapping>('POST', '/algorithm/mappings', data);
  },

  async updateMapping(mappingId: number, data: Partial<ParamMapping>) {
    return request<ParamMapping>('PUT', `/algorithm/mappings/${mappingId}`, data);
  },

  async deleteMapping(mappingId: number) {
    return request<void>('DELETE', `/algorithm/mappings/${mappingId}`);
  },

  async getOptions() {
    return request<{ algorithms: { value: string; name: string; group_id?: number; group_name?: string; icon?: string }[] }>('GET', '/algorithm/options');
  },

  async getFormSchema(algoType: string) {
    return request<FormSchema>('GET', `/algorithm/form-schema/${algoType}`);
  },

  async getDimensions(algoType: string) {
    return request<{
      dimensions: Array<{ id: number; name: string; description?: string; type?: string; weight: number; is_default: boolean }>;
      dimension_ids: number[];
      default_dimension_id: number | null;
      weights: Record<number, number>;
    }>('GET', `/algorithm/dimensions/${algoType}`);
  },

  async associateDimensions(algoType: string, dimensions: Array<{ dimension_id: number; weight?: number; is_default?: boolean }>) {
    return request<void>('POST', `/algorithm/dimensions/${algoType}`, { dimensions });
  },

  async createDimensionRelation(data: { algorithm_type: string; dimension_id: number; weight?: number; is_default?: boolean }) {
    return request<{ id: number; algorithm_type: string; dimension_id: number; weight: number; is_default: boolean }>('POST', '/algorithm/dimension-relations', data);
  },

  async updateDimensionRelation(relationId: number, data: { weight?: number; is_default?: boolean; dimension_id?: number }) {
    return request<{ id: number; algorithm_type: string; dimension_id: number; weight: number; is_default: boolean }>('PUT', `/algorithm/dimension-relations/${relationId}`, data);
  },

  async deleteDimensionRelation(relationId: number) {
    return request<void>('DELETE', `/algorithm/dimension-relations/${relationId}`);
  },

  async reloadConfig() {
    return request<{ success: boolean; message: string; reload_time: string }>('POST', '/algorithm/reload');
  },

  async importAlgorithms(data: { algorithms: any[] }) {
    return request<{ imported: string[] }>('POST', '/algorithm/import', data);
  },

  async bulkDelete(algorithmTypes: string[]) {
    return request<{ deleted_types: string[] }>('POST', '/algorithm/bulk-delete', { algorithm_types: algorithmTypes });
  },

  async extractParams(caseConfig: Record<string, any>) {
    return request<Record<string, any>>('POST', '/algorithm/extract-params', { case_config: caseConfig });
  },

  async getDimensionParams(dimensionId: number) {
    return request<{ params: Array<{ id: number; code: string; name: string; label: string; field_type: string; required: boolean; default_value: any }> }>('GET', `/algorithm/dimension-params/${dimensionId}`);
  },

  async getCaseParams(algorithmType: string, scope?: string, options: RequestOptions = {}) {
    const params: Record<string, any> = {};
    if (algorithmType) params.algorithm_type = algorithmType;
    if (scope) params.scope = scope;
    return request<{ parameters: any[]; total: number }>('GET', '/algorithm/case-params', null, { ...options, params });
  },

  async getCaseParam(paramId: number) {
    return request<any>('GET', `/algorithm/case-params/${paramId}`);
  },

  async createCaseParam(data: Partial<any>) {
    return request<any>('POST', '/algorithm/case-params', data);
  },

  async updateCaseParam(paramId: number, data: Partial<any>) {
    return request<any>('PUT', `/algorithm/case-params/${paramId}`, data);
  },

  async deleteCaseParam(paramId: number) {
    return request<void>('DELETE', `/algorithm/case-params/${paramId}`);
  },

  async getReferenceParams(algoType: string, options: RequestOptions = {}) {
    return request<{ data: any[]; total: number }>('GET', '/algorithm/reference-params', null, { ...options, params: { algorithm_type: algoType } });
  },

  async getReferenceParam(paramId: number, algoType: string) {
    return request<any>('GET', `/algorithm/reference-params/${paramId}`, null, { params: { algorithm_type: algoType } });
  },

  async createReferenceParam(data: Partial<any>) {
    return request<any>('POST', '/algorithm/reference-params', data);
  },

  async updateReferenceParam(paramId: number, algoType: string, data: Partial<any>) {
    const bodyData = { ...data, algorithm_type: algoType };
    return request<any>('PUT', `/algorithm/reference-params/${paramId}`, bodyData);
  },

  async deleteReferenceParam(paramId: number, algoType: string) {
    return request<void>('DELETE', `/algorithm/reference-params/${paramId}`, null, { params: { algorithm_type: algoType } });
  }
};

export interface TagCategory {
  id: number;
  name: string;
  description?: string;
  color?: string;
  sortOrder: number;
  tagCount: number;
  createdAt?: string;
  updatedAt?: string;
}

export interface TagItem {
  id: number;
  name: string;
  description?: string;
  color?: string;
  categoryId?: number;
  categoryName?: string;
  createdAt?: string;
  updatedAt?: string;
}

export const tagsApi = {
  async getCategories(params: Record<string, any> = {}) {
    return request<{ items: TagCategory[]; total: number }>('GET', '/tags/categories', null, { params });
  },

  async getCategory(id: number) {
    return request<TagCategory>('GET', `/tags/categories/${id}`);
  },

  async createCategory(data: Partial<TagCategory>) {
    return request<TagCategory>('POST', '/tags/categories', data);
  },

  async updateCategory(id: number, data: Partial<TagCategory>) {
    return request<TagCategory>('PUT', `/tags/categories/${id}`, data);
  },

  async deleteCategory(id: number) {
    return request<void>('DELETE', `/tags/categories/${id}`);
  },

  async getTags(params: Record<string, any> = {}) {
    return request<{ items: TagItem[]; total: number }>('GET', '/tags', null, { params });
  },

  async getTagNames(params: Record<string, any> = {}) {
    return request<{ items: string[]; total: number }>('GET', '/tags/names', null, { params });
  },

  async getTagsByCategory() {
    return request<{ items: Array<{ category: TagCategory | null; tags: TagItem[] }>; total: number }>('GET', '/tags/by-category');
  },

  async getTag(id: number) {
    return request<TagItem>('GET', `/tags/${id}`);
  },

  async createTag(data: Partial<TagItem>) {
    return request<TagItem>('POST', '/tags', data);
  },

  async updateTag(id: number, data: Partial<TagItem>) {
    return request<TagItem>('PUT', `/tags/${id}`, data);
  },

  async deleteTag(id: number) {
    return request<void>('DELETE', `/tags/${id}`);
  },

  async batchUpdateCategory(tagIds: number[], categoryId: number | null) {
    return request<void>('PUT', '/tags/batch-category', { tag_ids: tagIds, category_id: categoryId });
  }
};

export default {
  tasks: tasksApi,
  logs: logsApi,
  devices: devicesApi,
  playback: playbackApi,
  apis: apisApi,
  audios: audiosApi,
  groups: groupsApi,
  testcases: testcasesApi,
  reports: reportsApi,
  spl: splApi,
  evaluation: evaluationApi,
  stats: statsApi,
  algorithm: algorithmApi,
  tags: tagsApi
};
