/**
 * audiosApi.mergeChunks 契约测试（INT-1417 根因）
 * 选「关联算法」后上传走到 merge 阶段返回 400：
 * audio_service create_audio_algorithm_relation 按 snake_case 读键
 * （algorithm_type / is_primary），而前端 Domain 侧 algorithmRelations 子项为
 * camelCase（algorithmType / isPrimary），merge 链路无键转换 →
 * algorithm_type=null 违约 NOT NULL。
 * 本测试锁定 mergeChunks 出口已对 algorithmRelations 逐项归一为后端
 * wire 格式（algorithm_type / is_primary），与 annotations/dimensions 归一一致。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}));

import { request } from '../../http/client';
import { audiosApi } from '../audiosApi';

const mockedRequest = vi.mocked(request);

beforeEach(() => {
  mockedRequest.mockReset();
  mockedRequest.mockResolvedValue({ success: true });
});

describe('audiosApi.mergeChunks 载荷归一', () => {
  it('algorithmRelations 子项 camelCase → snake_case（algorithmType→algorithm_type / isPrimary→is_primary）', async () => {
    await audiosApi.mergeChunks(100, 200, {
      audioType: 'dry',
      algorithmType: 'voice_llm',
      algorithmRelations: [
        { algorithmType: 'voice_llm', isPrimary: true, weight: 1 },
      ],
      annotations: [],
      dimensions: [],
    });

    expect(mockedRequest).toHaveBeenCalledWith(
      'POST',
      '/audios/upload/merge',
      expect.objectContaining({
        fileId: 100,
        taskId: 200,
        // 顶层键原样透传（audioType/algorithmType 后端有 camelCase 兜底），
        // 仅 algorithmRelations 子项归一为 snake_case（INT-1417 根因）
        audioType: 'dry',
        algorithmType: 'voice_llm',
        algorithmRelations: [
          { algorithm_type: 'voice_llm', is_primary: true, weight: 1 },
        ],
      }),
      expect.anything(),
    );
  });

  it('algorithmRelations 为空数组 / 未携带时不额外注入', async () => {
    await audiosApi.mergeChunks(101, 201, { audioType: 'dry' });

    const body = mockedRequest.mock.calls[0][2] as Record<string, unknown>;
    expect(body.algorithmRelations).toBeUndefined();
    expect(body.algorithm_type).toBeUndefined();
  });

  it('params 字段原样透传（不深度 snakify），weight 数值保留', async () => {
    await audiosApi.mergeChunks(102, 202, {
      algorithmRelations: [
        { algorithmType: 'voice_llm', isPrimary: false, weight: 2, params: { model: 'x' } },
      ],
    });

    const body = mockedRequest.mock.calls[0][2] as Record<string, unknown>;
    expect(body.algorithmRelations).toEqual([
      { algorithm_type: 'voice_llm', is_primary: false, weight: 2, params: { model: 'x' } },
    ]);
  });

  it('annotations/dimensions 归一仍生效，与 algorithmRelations 归一共存', async () => {
    await audiosApi.mergeChunks(103, 203, {
      algorithmRelations: [{ algorithmType: 'asr', isPrimary: true, weight: 1 }],
      annotations: [{ sourceLanguage: 'zh', targetLanguage: 'en' }],
      dimensions: [{ testType: 'api', roundScope: 'single' }],
    });

    const body = mockedRequest.mock.calls[0][2] as Record<string, unknown>;
    expect(body.algorithmRelations).toEqual([{ algorithm_type: 'asr', is_primary: true, weight: 1 }]);
    expect(body.annotations).toEqual([{ source_language: 'zh', target_language: 'en' }]);
    expect(body.dimensions).toEqual([{ test_type: 'api', round_scope: 'single' }]);
  });
});
