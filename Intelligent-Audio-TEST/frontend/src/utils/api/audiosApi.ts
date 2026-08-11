/**
 * Audios API module
 */
import { request, type RequestOptions } from './http';

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

  async urlImport(importData: any) {
    return request('POST', '/audios/url-import', importData);
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

  // 前端直传 OSS 相关接口（生产环境多实例部署）
  async presignUpload(data: { filename: string; fileSize: number; md5?: string; chunkSize?: number; isWav: boolean; relativePath?: string }, options: RequestOptions = {}) {
    return request('POST', '/audios/upload/presign', data, options);
  },

  async presignPart(data: { uploadId: string; partNumber: number }, ossKey: string, category: string = 'raw_chunks', options: RequestOptions = {}) {
    return request('POST', '/audios/upload/presign-part', data, { ...options, params: { oss_key: ossKey, category } });
  },

  async completeDirectUpload(data: any, options: RequestOptions = {}) {
    return request('POST', '/audios/upload/complete-direct', data, options);
  },

  async getFolderTree(params: any = {}, options: RequestOptions = {}) {
    return request('POST', '/audios/folder-tree', params, options);
  }
};
