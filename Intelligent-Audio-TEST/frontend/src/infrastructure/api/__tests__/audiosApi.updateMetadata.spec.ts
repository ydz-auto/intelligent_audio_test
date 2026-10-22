/**
 * audiosApi.updateMetadata 契约测试（INT-1354 观察1 根因）
 * DetailViewModal 的 editableData 以 UI 键承载（fileName/audioType/asrText/sourceLanguage），
 * 后端 update_metadata 读 name/audio_type/asr_text/source_language（INT-1261 遗留），
 * 本测试锁定 updateMetadata 出口已归一为后端 UpdateMetadataRequest（snake_case）：
 *  - fileName → name（改名真正落库，列表「文件名」列刷新后反映新名）
 *  - camelCase → snake_case（audioType/asrText/sourceLanguage）
 *  - tags 数组统一为逗号分隔字符串；annotations 原样透传
 *  - 仅后端契约字段上行，UI 专属键（category/format/duration/size/translations）不下发
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

describe('audiosApi.updateMetadata 载荷归一', () => {
  it('UI 键 fileName 映射为后端契约 name，改名落库', async () => {
    await audiosApi.updateMetadata(1, {
      id: 1,
      fileName: '改名后.wav',
      audioType: 'dry',
      asrText: '你好',
      sourceLanguage: 'zh',
      tags: 'a,b',
      annotations: [{ format: 'text', code: 'x', data: { text: 'hello' } }],
    });

    expect(mockedRequest).toHaveBeenCalledWith(
      'PUT',
      '/audios/1/metadata',
      expect.objectContaining({
        name: '改名后.wav',
        audio_type: 'dry',
        asr_text: '你好',
        source_language: 'zh',
        tags: 'a,b',
        annotations: [{ format: 'text', code: 'x', data: { text: 'hello' } }],
      }),
      expect.anything(),
    );
  });

  it('camelCase 域键（name/audioType/asrText/sourceLanguage）同样归一为 snake_case', async () => {
    await audiosApi.updateMetadata(2, {
      name: 'a.wav',
      audioType: 'noise',
      asrText: '文本',
      sourceLanguage: 'en',
    });

    expect(mockedRequest).toHaveBeenCalledWith(
      'PUT',
      '/audios/2/metadata',
      expect.objectContaining({ name: 'a.wav', audio_type: 'noise', asr_text: '文本', source_language: 'en' }),
      expect.anything(),
    );
  });

  it('tags 数组统一为逗号分隔字符串，annotations 原样透传', async () => {
    await audiosApi.updateMetadata(3, {
      name: 'b.wav',
      tags: ['甲', '乙'],
      annotations: [{ format: 'json', code: 'c', data: { segments: [] } }],
    });

    expect(mockedRequest).toHaveBeenCalledWith(
      'PUT',
      '/audios/3/metadata',
      expect.objectContaining({
        tags: '甲, 乙',
        annotations: [{ format: 'json', code: 'c', data: { segments: [] } }],
      }),
      expect.anything(),
    );
  });

  it('仅下发后端契约字段，UI 专属键（category/format/duration/size/translations）不下发', async () => {
    await audiosApi.updateMetadata(4, {
      id: 4,
      fileName: 'c.wav',
      category: 'folder/',
      format: 'wav',
      duration: 12,
      size: 1234,
      translations: [{ direction: 'zh-en', text: '' }],
    });

    const body = mockedRequest.mock.calls[0][2] as Record<string, unknown>;
    expect(body).toEqual({ name: 'c.wav' });
    expect(body.category).toBeUndefined();
    expect(body.format).toBeUndefined();
    expect(body.duration).toBeUndefined();
    expect(body.size).toBeUndefined();
    expect(body.translations).toBeUndefined();
    expect(body.id).toBeUndefined();
  });
});
