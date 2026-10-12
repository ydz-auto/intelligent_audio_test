/**
 * audiosApi.download 契约测试（INT-146 缺陷1）
 * stream 接口返回 JSON 预签名 URL 后，下载须二次取字节流：
 * - OSS 预签名 URL（绝对 http/https）→ 直接 fetch（URL 自带签名）
 * - 网关回退路径（/api/v1/audios/download?path=...）→ 剥前缀走 request 注入 JWT
 * - 未返回 url → 抛错
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}));

import { request } from '../../http/client';
import { audiosApi } from '../audiosApi';

const mockedRequest = vi.mocked(request);

beforeEach(() => {
  mockedRequest.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('audiosApi.download 预签名适配', () => {
  it('先调 stream 取 JSON URL，再 fetch 绝对预签名地址', async () => {
    mockedRequest.mockResolvedValueOnce({ url: 'https://oss.example.com/audios/a.wav?sig=1' });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('RIFF', { status: 200 })));

    const result = await audiosApi.download(1);

    expect(mockedRequest).toHaveBeenCalledWith('GET', '/audios/1/stream', null, expect.anything());
    expect(fetch).toHaveBeenCalledWith('https://oss.example.com/audios/a.wav?sig=1', expect.anything());
    // jsdom/undici Blob 非同一 realm，仅断言字节内容
    expect(await result.text()).toBe('RIFF');
  });

  it('网关回退路径剥掉 /api/v1/ 前缀后经 request 以 blob 拉取', async () => {
    mockedRequest
      .mockResolvedValueOnce({ url: '/api/v1/audios/download?path=local://audios/a.wav' })
      .mockResolvedValueOnce('RIFFlocal');

    const result = await audiosApi.download(2);

    expect(mockedRequest).toHaveBeenNthCalledWith(2, 'GET', 'audios/download?path=local://audios/a.wav', null,
      expect.objectContaining({ responseType: 'blob' }));
    // jsdom Blob 无 text()（与 undici Blob 非.realm），仅断言返回包装成功
    expect(result).toBeTruthy();
  });

  it('兼容 data.url 包装形态', async () => {
    mockedRequest.mockResolvedValueOnce({ data: { url: 'https://oss.example.com/b.mp3?sig=2' } });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(new Blob(['x']), { status: 200 })));

    await audiosApi.download(3);
    expect(fetch).toHaveBeenCalledWith('https://oss.example.com/b.mp3?sig=2', expect.anything());
  });

  it('未返回 url 时抛错', async () => {
    mockedRequest.mockResolvedValueOnce({ url: null, message: '音频不存在' });
    await expect(audiosApi.download(4)).rejects.toThrow('音频不存在');
  });

  it('预签名 fetch 非 200 时抛错', async () => {
    mockedRequest.mockResolvedValueOnce({ url: 'https://oss.example.com/c.wav?sig=3' });
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('forbidden', { status: 403 })));
    await expect(audiosApi.download(5)).rejects.toThrow('403');
  });
});
