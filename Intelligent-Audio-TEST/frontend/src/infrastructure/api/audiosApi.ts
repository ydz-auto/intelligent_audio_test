/**
 * Audios API module
 */
import { request, type RequestOptions } from '../http/client';
import type { AudioItemDto, AudioListDto } from '../dto/audioDto';
import { toAudioInfo, toAudioInfoList, toAudioPage, toFolderNode } from '../adapters/audioAdapter';
import type { AudioInfo } from '../../domain/model/audio';
import { camelizeKeys } from '../../utils/keyTransform';

/**
 * 将 upload 系列接口响应归一为 camelCase 出口：
 * 兼容 unwrapResponse: false 的完整包装（{ code, message, data }）与裸数据两种形态，
 * 保证 Port 出口只暴露 camelCase key。
 */
function camelizeUploadResult<T>(result: T): T {
  if (result && typeof result === 'object' && 'data' in (result as Record<string, unknown>)) {
    const wrapped = result as Record<string, unknown>;
    return { ...wrapped, data: wrapped.data != null ? camelizeKeys(wrapped.data) : wrapped.data } as T;
  }
  return camelizeKeys(result);
}

/**
 * 标注载荷条目 → 后端 wire 格式（snake_case）：
 * 仅转换已知顶层传输 key（sourceLanguage/targetLanguage→source_language/target_language），
 * data/segments 等内容原样透传，避免深度 snakify 误伤自定义字段名。
 */
function toAnnotationDto(ann: unknown): unknown {
  if (!ann || typeof ann !== 'object' || Array.isArray(ann)) return ann;
  const rec = ann as Record<string, unknown>;
  const { sourceLanguage, targetLanguage, ...rest } = rec;
  return {
    ...rest,
    source_language: sourceLanguage ?? rec.source_language ?? '',
    target_language: targetLanguage ?? rec.target_language ?? '',
  };
}

/**
 * 评估维度条目 → 后端用例配置协议原文（snake_case）：
 * audio_service 的 _build_config_and_apply_dimensions 以 d.get('test_type') / d.get('round_scope')
 * 解析且无 camelCase 兜底，merge 链路无键转换，故必须在出口显式转换；其余字段（id/name/weight/threshold）原样透传。
 */
function toEvaluationDimensionDto(dim: unknown): unknown {
  if (!dim || typeof dim !== 'object' || Array.isArray(dim)) return dim;
  const rec = dim as Record<string, unknown>;
  const { testType, roundScope, roundNumber, ...rest } = rec;
  return {
    ...rest,
    test_type: testType ?? rec.test_type,
    round_scope: roundScope ?? rec.round_scope,
    ...(roundNumber !== undefined ? { round_number: roundNumber } : {}),
  };
}

/**
 * 元数据编辑载荷 → 后端 UpdateMetadataRequest（snake_case，INT-1354）：
 * DetailViewModal 的 editableData 以 UI 键承载（fileName/audioType/asrText/sourceLanguage），
 * 而后端 update_metadata 读 name/audio_type/asr_text/source_language（INT-1261 遗留），
 * 此处显式归一，保证改名（name）真正落库；tags 统一为逗号分隔字符串。
 */
function toUpdateMetadataDto(metadata: Record<string, unknown>): Record<string, unknown> {
  const body: Record<string, unknown> = {};
  const firstDefined = (camel: string, snake: string) =>
    metadata[camel] !== undefined ? metadata[camel] : metadata[snake];
  if (firstDefined('name', 'fileName') !== undefined) {
    body.name = firstDefined('name', 'fileName');
  }
  if (firstDefined('audioType', 'audio_type') !== undefined) {
    body.audio_type = firstDefined('audioType', 'audio_type');
  }
  if (firstDefined('asrText', 'asr_text') !== undefined) {
    body.asr_text = firstDefined('asrText', 'asr_text');
  }
  if (metadata.description !== undefined) {
    body.description = metadata.description;
  }
  if (firstDefined('sourceLanguage', 'source_language') !== undefined) {
    body.source_language = firstDefined('sourceLanguage', 'source_language');
  }
  if (metadata.tags !== undefined) {
    body.tags = Array.isArray(metadata.tags) ? metadata.tags.join(', ') : String(metadata.tags);
  }
  if (metadata.annotations !== undefined) {
    body.annotations = metadata.annotations;
  }
  return body;
}

/** 批量更新标注请求条目（camelCase 域契约；annotations 为标注内容协议，原样透传） */
export interface BatchAnnotationItem {
  audioId: string | number;
  annotations: unknown[];
}

/** 批量更新标注请求（camelCase 域契约；snake_case 化在 Infrastructure 内部完成） */
export interface BatchUpdateAnnotationsData {
  items: BatchAnnotationItem[];
  algorithmType?: string;
  refreshTestCases?: boolean;
}

/** camelCase 批量更新标注请求 → snake_case 请求体（annotations 内容协议仅归一顶层语言 key） */
function toBatchUpdateAnnotationsDto(data: BatchUpdateAnnotationsData): Record<string, unknown> {
  return {
    items: data.items.map(item => ({
      audio_id: item.audioId,
      annotations: Array.isArray(item.annotations) ? item.annotations.map(toAnnotationDto) : item.annotations,
    })),
    algorithm_type: data.algorithmType,
    refresh_test_cases: data.refreshTestCases,
  };
}

export const audiosApi = {
  async getAll(params: Record<string, any> = {}, options: RequestOptions = {}) {
    const dto = await request<AudioListDto>('POST', '/audios', params, { ...options });
    return toAudioPage(dto);
  },

  async getAllIds(params: Record<string, any> = {}, options: RequestOptions = {}) {
    return request('POST', '/audios/ids', params, { ...options });
  },

  async getOne(id: string | number, options: RequestOptions = {}): Promise<AudioInfo> {
    const dto = await request<AudioItemDto>('GET', `/audios/${id}`, null, options);
    return toAudioInfo(dto);
  },

  async getByIds(ids: (string | number)[], options: RequestOptions = {}): Promise<AudioInfo[]> {
    const res = await request<AudioItemDto[] | { data?: AudioItemDto[] } | null>('POST', '/audios/by-ids', { ids }, options);
    const dtos = Array.isArray(res) ? res : (res?.data ?? []);
    return toAudioInfoList(dtos);
  },

  async getByMd5(md5List: string[], options: RequestOptions = {}) {
    return request('POST', '/audios/by-md5', { md5_list: md5List }, options);
  },

  async getAllTags(options: RequestOptions = {}) {
    return request('GET', '/audios/tags', null, options);
  },

  async urlImport(importData: any) {
    return request('POST', '/audios/url-import', importData);
  },

  async convert(id: string | number, convertData: any) {
    return request('POST', `/audios/${id}/convert`, convertData);
  },

  async updateMetadata(id: string | number, metadata: any, options: RequestOptions = {}) {
    return request('PUT', `/audios/${id}/metadata`, toUpdateMetadataDto(metadata ?? {}), options);
  },

  async batchUpdateAnnotations(data: BatchUpdateAnnotationsData, options: RequestOptions = {}) {
    const raw = await request<any>('POST', '/audios/batch/annotations', toBatchUpdateAnnotationsDto(data), options);
    return {
      ...raw,
      updatedCount: raw?.updatedCount ?? raw?.updated_count ?? 0,
      failedCount: raw?.failedCount ?? raw?.failed_count ?? 0,
      refreshedTestCaseIds: raw?.refreshedTestCaseIds ?? raw?.refreshed_test_case_ids ?? [],
    };
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

  /** 按路径获取音频流（返回 OSS 预签名 URL 的 JSON） */
  async streamByPath(path: string, options: RequestOptions = {}) {
    return request('GET', '/audios/stream-by-path', null, { ...options, params: { path } });
  },

  /**
   * 下载音频（INT-146 缺陷1）：stream 已改为返回 JSON 预签名 URL，
   * 下载需二次请求取字节流，不能再按 blob 消费 stream 响应。
   * - OSS 预签名 URL（绝对 http/https）：URL 自带签名，直接 fetch（无需 JWT）
   * - 网关回退路径（/api/v1/audios/download?path=...）：走 HTTP 客户端注入 JWT
   */
  async download(id: string | number, options: RequestOptions = {}): Promise<Blob> {
    const result = await request<any>('GET', `/audios/${id}/stream`, null, options);
    const url: string | undefined = result?.url ?? result?.data?.url;
    if (!url) {
      throw new Error(result?.message || '获取音频下载地址失败');
    }
    if (/^https?:\/\//i.test(url)) {
      const resp = await fetch(url, { signal: options.signal });
      if (!resp.ok) {
        throw new Error(`下载音频失败: ${resp.status} ${resp.statusText}`);
      }
      return await resp.blob();
    }
    // 网关相对路径：剥掉 baseUrl 前缀后经 request 注入 JWT（request 会重新拼接 baseUrl）
    const relative = url.replace(/^\/api\/v1\//i, '');
    const data = await request<Blob>('GET', relative, null, { ...options, responseType: 'blob' });
    return data instanceof Blob ? data : new Blob([data as unknown as BlobPart]);
  },

  async delete(id: string | number, options: RequestOptions = {}) {
    return request('DELETE', `/audios/${id}`, null, options);
  },

  async batchAction(action: string, ids: (string | number)[], extraParams: any = {}, options: RequestOptions = {}) {
    return request('POST', '/audios/batch-action', { action, audioIds: ids, ...extraParams }, options);
  },

  async initUpload(options: RequestOptions = {}) {
    return camelizeUploadResult(await request('POST', '/audios/upload/init', {}, options));
  },

  async registerUploadFiles(taskId: string | number, files: any[], options: RequestOptions = {}) {
    return camelizeUploadResult(await request('POST', '/audios/upload/register', { taskId: taskId, files }, options));
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
    // 标注载荷上行归一：Modal/Domain 侧 camelCase → 后端 wire snake_case（仅顶层语言 key）
    if (Array.isArray(normalizedData.annotations)) {
      normalizedData.annotations = normalizedData.annotations.map(toAnnotationDto);
    }
    // 评估维度上行归一：Domain 侧 camelCase（testType/roundScope）→ 后端用例配置协议原文（test_type/round_scope）
    if (Array.isArray(normalizedData.dimensions)) {
      normalizedData.dimensions = normalizedData.dimensions.map(toEvaluationDimensionDto);
    }
    return camelizeUploadResult(await request('POST', '/audios/upload/merge', { fileId: fileId, taskId: taskId, ...normalizedData }, options));
  },

  async getUploadProgress(taskId: string | number, options: RequestOptions = {}) {
    return request('GET', '/audios/upload/progress', null, { ...options, params: { task_id: taskId } });
  },

  // 前端直传 OSS 相关接口（生产环境多实例部署）
  async presignUpload(data: { filename: string; fileSize: number; md5?: string; chunkSize?: number; isWav: boolean; relativePath?: string }, options: RequestOptions = {}) {
    return camelizeUploadResult(await request('POST', '/audios/upload/presign', data, options));
  },

  async presignPart(data: { uploadId: string; partNumber: number }, ossKey: string, category: string = 'raw_chunks', options: RequestOptions = {}) {
    return camelizeUploadResult(await request('POST', '/audios/upload/presign-part', data, { ...options, params: { oss_key: ossKey, category } }));
  },

  async completeDirectUpload(data: any, options: RequestOptions = {}) {
    return camelizeUploadResult(await request('POST', '/audios/upload/complete-direct', data, options));
  },

  async getFolderTree(params: any = {}, options: RequestOptions = {}) {
    // INT-1331：后端 folder-tree 处理器读取原始 JSON key（不经 Pydantic alias_generator），
    // 域参数为 camelCase，此处把 sampleRate 映射为后端读取的 sample_rate；
    // apply_folder_tree_filters 用 between(sample_rate ± 100) 匹配，须下发 Hz 数值（44100）
    const body: Record<string, any> = { ...params };
    if (body.sampleRate !== undefined && body.sampleRate !== null && body.sampleRate !== '') {
      const hz = Number(body.sampleRate);
      if (Number.isFinite(hz) && hz > 0) {
        body.sample_rate = hz;
      }
      delete body.sampleRate;
    }
    const response = await request<any>('POST', '/audios/folder-tree', body, options);
    // 兼容 unwrapResponse: false 时返回的 { success, data: { tree } } 包装
    if (response && response.data && response.data.tree) {
      response.data.tree = toFolderNode(response.data.tree);
    } else if (response && response.tree) {
      response.tree = toFolderNode(response.tree);
    }
    return response;
  }
};
