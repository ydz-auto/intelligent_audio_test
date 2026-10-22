/**
 * INT-1329（P1）：上传直传 OSS 失败/不可达时回退网关分片路径。
 *
 * 契约：uploadFileChunks 先走预签名直传 OSS；当 PUT 预签名 URL 失败
 * （本环境 rustfs:9000 不可解析 / SigV2 403）时，自动回退到
 * /upload/chunk 网关分片路径（复用同批注册 file_id），再 /upload/merge
 * 创建音频记录 + 测试用例，不留双口径。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';
import type { UploadProcessContext } from '../uploadProcess';
import type { UploadStatus } from '../../upload/useUploadState';

// jsdom（vitest 环境）的 Blob 原型仅实现 constructor/slice/size/type，缺 arrayBuffer()；
// uploadProcess 直传 OSS 路径依赖 chunk.arrayBuffer() 读取分片字节，用 FileReader 补齐，
// 让契约测试走真实代码路径（浏览器原生 Blob 即按此语义实现）。
if (typeof Blob !== 'undefined' && !(Blob.prototype as any).arrayBuffer) {
  Blob.prototype.arrayBuffer = function arrayBuffer(): Promise<ArrayBuffer> {
    return new Promise<ArrayBuffer>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result as ArrayBuffer);
      reader.onerror = () => reject(reader.error);
      reader.readAsArrayBuffer(this);
    });
  };
}

const audiosPort = vi.hoisted(() => ({
  presignUpload: vi.fn(),
  presignPart: vi.fn(),
  uploadChunk: vi.fn(),
  mergeChunks: vi.fn(),
  completeDirectUpload: vi.fn(),
}));

vi.mock('@/composables/audio/audiosPort', () => ({ audiosPort }));

import { uploadFileChunks } from '../uploadProcess';

function makeFile(name: string): File {
  return new File(['audio-content-bytes'], name, { type: 'audio/wav' });
}

function makeCtx() {
  const uploadProgress = ref(0);
  const uploadStatus = ref<UploadStatus>('uploading');
  const generatedTestCaseTotal = { value: 0 };
  let abortController: AbortController | null = null;
  const ctx: UploadProcessContext = {
    uploadProgress,
    currentTask: ref(null),
    currentUploadingFile: ref(null),
    uploadStatus,
    uploadTasks: ref([]),
    uploadOptions: { audioType: 'dry', createTestCase: false, tags: [], testTypes: ['e2e'] } as any,
    generatedTestCaseTotal,
    getAbortController: () => abortController,
    setAbortController: (c) => { abortController = c; },
    algorithmApi: {
      resolveAlgorithmParamsFromAnnotations: vi.fn().mockResolvedValue([]),
      dispatchParamsToRounds: vi.fn().mockResolvedValue(undefined),
    } as any,
  };
  return ctx;
}

function makeFileTask(file: File, fileId = 'reg-123', totalChunks = 1, chunkSize = 10 * 1024 * 1024) {
  return {
    id: `f_${fileId}`,
    fileId,
    file,
    name: file.name,
    size: file.size,
    totalChunks,
    chunkSize,
    progress: 0,
    uploadedSize: 0,
    status: 'pending',
    tags: [],
  } as any;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('INT-1329 直传 OSS 失败 → 回退网关分片路径', () => {
  it('PUT 预签名 URL 不可达时：改走 uploadChunk 网关分片 + merge，文件完成且回填 audioId', async () => {
    const file = makeFile('int1261_fallback_a.wav');
    const fileTask = makeFileTask(file);
    const ctx = makeCtx();

    // 预签名返回成功（含不可达的 rustfs:9000 URL），但浏览器 PUT 失败
    audiosPort.presignUpload.mockResolvedValue({
      code: 200,
      data: {
        uploadId: 'up-1',
        ossKey: 'direct/test.wav',
        category: 'audios',
        chunkSize: 5 * 1024 * 1024,
        totalParts: 1,
        parts: [{ partNumber: 1, url: 'http://rustfs:9000/audios/direct/test.wav?X-Amz-Signature=x' }],
        presignedRemaining: false,
      },
    });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')));
    audiosPort.uploadChunk.mockResolvedValue({ code: 200, data: { chunk_index: 0 } });
    audiosPort.mergeChunks.mockResolvedValue({ code: 200, data: { audioId: 101, name: 'int1261_fallback_a.wav', testCaseCount: 0 } });

    await uploadFileChunks(ctx, 'task-1', fileTask, ctx.uploadOptions);

    // 直传 PUT 确实失败过（触发回退的证据）
    expect(fetch).toHaveBeenCalledTimes(1);
    // 网关分片路径：逐分片经 /upload/chunk 上传（复用注册 file_id）
    expect(audiosPort.uploadChunk).toHaveBeenCalledTimes(1);
    const form: FormData = audiosPort.uploadChunk.mock.calls[0][0];
    expect(form.get('file_id')).toBe('reg-123');
    expect(form.get('task_id')).toBe('task-1');
    expect(form.get('chunk_index')).toBe('0');
    expect(form.get('total_chunks')).toBe('1');
    expect(form.has('chunk')).toBe(true);
    // merge 不带直传 OSS 字段（不留双口径）
    const mergeArgs = audiosPort.mergeChunks.mock.calls[0];
    expect(mergeArgs[0]).toBe('reg-123');
    expect(mergeArgs[1]).toBe('task-1');
    expect(mergeArgs[2]).not.toHaveProperty('isDirectOss');
    expect(mergeArgs[2]).not.toHaveProperty('ossKey');
    // 文件落地（status=completed 由调用方 startUploadProcess 负责，此处核验本单元实际落地的字段）
    expect(fileTask.audioId).toBe(101);
    expect(fileTask.progress).toBe(100);
    expect(fileTask.uploadedSize).toBe(file.size);
  });

  it('预签名成功 + 直传 PUT 成功：仍走直传路径，不触发网关回退', async () => {
    const file = makeFile('int1261_direct_b.wav');
    const fileTask = makeFileTask(file);
    const ctx = makeCtx();

    audiosPort.presignUpload.mockResolvedValue({
      code: 200,
      data: {
        uploadId: 'up-2',
        ossKey: 'direct/test.wav',
        category: 'audios',
        chunkSize: 5 * 1024 * 1024,
        totalParts: 1,
        parts: [{ partNumber: 1, url: 'http://oss.example.com/audios/x' }],
        presignedRemaining: false,
      },
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, headers: { get: () => 'etag-1' } }));
    audiosPort.completeDirectUpload.mockResolvedValue({ code: 200, data: { audioId: 202 } });

    await uploadFileChunks(ctx, 'task-1', fileTask, ctx.uploadOptions);

    expect(audiosPort.uploadChunk).not.toHaveBeenCalled();
    expect(audiosPort.completeDirectUpload).toHaveBeenCalledTimes(1);
    expect(fileTask.audioId).toBe(202);
    expect(fileTask.progress).toBe(100);
    expect(fileTask.uploadedSize).toBe(file.size);
  });

  it('预签名命中秒传：直接完成并走 processMergeForExistingFile，不触发网关回退', async () => {
    const file = makeFile('int1261_instant_c.wav');
    const fileTask = makeFileTask(file);
    const ctx = makeCtx();

    audiosPort.presignUpload.mockResolvedValue({
      code: 200,
      data: { instantUpload: true, audioId: 303, name: 'int1261_instant_c.wav' },
    });
    audiosPort.mergeChunks.mockResolvedValue({ code: 200, data: { audioId: 303, name: 'int1261_instant_c.wav', testCaseCount: 0 } });

    await uploadFileChunks(ctx, 'task-1', fileTask, ctx.uploadOptions);

    expect(audiosPort.uploadChunk).not.toHaveBeenCalled();
    expect(audiosPort.mergeChunks).toHaveBeenCalledTimes(1);
    expect(fileTask.status).toBe('completed');
    expect(fileTask.audioId).toBe(303);
  });
});
