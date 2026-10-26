/**
 * INT-1983：导入「标签来源」三选一 + merge 载荷 tag_source
 *
 * 契约（语义表）：
 * - both（默认）：请求 tags = 手填标签 ∪ 该分组 JSON tags，tag_source=both
 * - path：请求 tags 只含手填标签（不并入 JSON tags），tag_source=path
 * - json：请求 tags = 手填标签 ∪ JSON tags，tag_source=json
 * - 任何模式都包含手填标签；fileTask.tags 为空回退 options.tags 的既有行为不回归
 * - 直传完成（completeDirectUpload）只下发组装后的 tags，不带 tag_source
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { ref } from 'vue';
import type { UploadProcessContext } from '../uploadProcess';
import type { UploadStatus } from '../../upload/useUploadState';
import { AudioTagSource } from '@/domain/enums';

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

import { uploadFileChunks, resolveRequestTags } from '../uploadProcess';

function makeCtx() {
  const abortController: AbortController | null = null;
  const ctx: UploadProcessContext = {
    uploadProgress: ref(0),
    currentTask: ref(null),
    currentUploadingFile: ref(null),
    uploadStatus: ref<UploadStatus>('uploading'),
    uploadTasks: ref([]),
    uploadOptions: { audioType: 'dry', createTestCase: false, tags: [], testTypes: ['e2e'] } as any,
    generatedTestCaseTotal: { value: 0 },
    getAbortController: () => abortController,
    setAbortController: vi.fn(),
    algorithmApi: {
      resolveAlgorithmParamsFromAnnotations: vi.fn().mockResolvedValue([]),
      dispatchParamsToRounds: vi.fn().mockResolvedValue(undefined),
    } as any,
  };
  return ctx;
}

function makeFileTask(name: string, tags: string[], groupTags: string[]) {
  const file = new File(['audio-content-bytes'], name, { type: 'audio/wav' });
  return {
    id: 'f_x',
    fileId: 'reg-1',
    file,
    name,
    size: file.size,
    totalChunks: 1,
    chunkSize: 10 * 1024 * 1024,
    progress: 0,
    uploadedSize: 0,
    status: 'pending',
    tags,
    groupTags,
  } as any;
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('resolveRequestTags 标签来源组装', () => {
  it('both：手填标签 ∪ 分组 JSON tags（去重保序）', () => {
    expect(
      resolveRequestTags({ tags: ['手填A'], groupTags: [] }, { tags: [] }, AudioTagSource.BOTH, ['J1', 'J2'])
    ).toEqual(['手填A', 'J1', 'J2']);
  });

  it('path：只含手填标签，不并入 JSON tags', () => {
    expect(
      resolveRequestTags({ tags: ['手填A'], groupTags: [] }, { tags: [] }, AudioTagSource.PATH, ['J1', 'J2'])
    ).toEqual(['手填A']);
  });

  it('json：手填标签 ∪ 分组 JSON tags', () => {
    expect(
      resolveRequestTags({ tags: ['手填A'], groupTags: [] }, { tags: [] }, AudioTagSource.JSON, ['J1'])
    ).toEqual(['手填A', 'J1']);
  });

  it('未选（undefined）按默认 both', () => {
    expect(
      resolveRequestTags({ tags: ['手填A'], groupTags: [] }, { tags: [] }, undefined, ['J1'])
    ).toEqual(['手填A', 'J1']);
  });

  it('手填与 JSON tags 重复时去重，手填在前', () => {
    expect(
      resolveRequestTags({ tags: ['A', 'B'], groupTags: [] }, { tags: [] }, AudioTagSource.BOTH, ['B', 'C'])
    ).toEqual(['A', 'B', 'C']);
  });

  it('fileTask.tags 为空回退 options.tags（既有行为不回归）', () => {
    expect(
      resolveRequestTags({ tags: [], groupTags: [] }, { tags: ['手填B'] }, AudioTagSource.BOTH, ['J1'])
    ).toEqual(['手填B', 'J1']);
    expect(
      resolveRequestTags({ tags: [], groupTags: [] }, { tags: ['手填B'] }, AudioTagSource.PATH, ['J1'])
    ).toEqual(['手填B']);
  });

  it('跨分组不串：不同分组 JSON tags 只落到各自文件', () => {
    const a = resolveRequestTags({ tags: ['手填'], groupTags: ['标签A'] }, { tags: [] }, AudioTagSource.JSON, ['标签A']);
    const b = resolveRequestTags({ tags: ['手填'], groupTags: ['标签B'] }, { tags: [] }, AudioTagSource.JSON, ['标签B']);
    expect(a).toEqual(['手填', '标签A']);
    expect(b).toEqual(['手填', '标签B']);
  });
});

describe('merge / 直传载荷携带标签来源', () => {
  it('网关分片 merge：tags 按来源组装，载荷带 tagSource（json）', async () => {
    const ctx = makeCtx();
    const fileTask = makeFileTask('case_json.wav', ['手填A'], ['J1']);
    const options = { ...ctx.uploadOptions, tagSource: AudioTagSource.JSON };

    // 预签名不可达 → 回退网关分片路径（merge 载荷走 buildMergePayload）
    audiosPort.presignUpload.mockRejectedValue(new Error('presign unavailable'));
    audiosPort.uploadChunk.mockResolvedValue({ code: 200, data: {} });
    audiosPort.mergeChunks.mockResolvedValue({ code: 200, data: { audioId: 1 } });

    await uploadFileChunks(ctx, 'task-1', fileTask, options);

    const payload = audiosPort.mergeChunks.mock.calls[0][2] as Record<string, any>;
    expect(payload.tags).toEqual(['手填A', 'J1']);
    expect(payload.tagSource).toBe(AudioTagSource.JSON);
  });

  it('网关分片 merge：path 模式只下发手填标签，tagSource=path', async () => {
    const ctx = makeCtx();
    const fileTask = makeFileTask('case_path.wav', ['手填A'], ['J1']);
    const options = { ...ctx.uploadOptions, tagSource: AudioTagSource.PATH };

    audiosPort.presignUpload.mockRejectedValue(new Error('presign unavailable'));
    audiosPort.uploadChunk.mockResolvedValue({ code: 200, data: {} });
    audiosPort.mergeChunks.mockResolvedValue({ code: 200, data: { audioId: 1 } });

    await uploadFileChunks(ctx, 'task-1', fileTask, options);

    const payload = audiosPort.mergeChunks.mock.calls[0][2] as Record<string, any>;
    expect(payload.tags).toEqual(['手填A']);
    expect(payload.tagSource).toBe(AudioTagSource.PATH);
  });

  it('未选标签来源：merge 载荷按默认 both 组装', async () => {
    const ctx = makeCtx();
    const fileTask = makeFileTask('case_default.wav', ['手填A'], ['J1']);

    audiosPort.presignUpload.mockRejectedValue(new Error('presign unavailable'));
    audiosPort.uploadChunk.mockResolvedValue({ code: 200, data: {} });
    audiosPort.mergeChunks.mockResolvedValue({ code: 200, data: { audioId: 1 } });

    await uploadFileChunks(ctx, 'task-1', fileTask, ctx.uploadOptions);

    const payload = audiosPort.mergeChunks.mock.calls[0][2] as Record<string, any>;
    expect(payload.tags).toEqual(['手填A', 'J1']);
    expect(payload.tagSource).toBe(AudioTagSource.BOTH);
  });

  it('直传完成（completeDirectUpload）只下发组装后的 tags，不带 tagSource', async () => {
    const ctx = makeCtx();
    const fileTask = makeFileTask('direct.wav', ['手填A'], ['J1']);
    const options = { ...ctx.uploadOptions, tagSource: AudioTagSource.JSON };

    audiosPort.presignUpload.mockResolvedValue({
      code: 200,
      data: {
        uploadId: 'up-1',
        ossKey: 'direct/test.wav',
        category: 'audios',
        chunkSize: 5 * 1024 * 1024,
        totalParts: 1,
        parts: [{ partNumber: 1, url: 'http://oss.example.com/audios/x' }],
        presignedRemaining: false,
      },
    });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, headers: { get: () => 'etag-1' } }));
    audiosPort.completeDirectUpload.mockResolvedValue({ code: 200, data: { audioId: 9 } });

    await uploadFileChunks(ctx, 'task-1', fileTask, options);

    const payload = audiosPort.completeDirectUpload.mock.calls[0][0] as Record<string, any>;
    expect(payload.tags).toEqual(['手填A', 'J1']);
    expect(payload).not.toHaveProperty('tagSource');
    expect(payload).not.toHaveProperty('tag_source');
    vi.unstubAllGlobals();
  });
});
