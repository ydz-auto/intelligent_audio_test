/**
 * client.ts handleResponse 二进制分支（blob/arraybuffer）response.ok 判定契约测试（INT-1005 回归）。
 *
 * 回归背景：INT-1001 实测任务导出——POST /api/v1/data-transfer/export 返回非 2xx
 * （HTTP 400，body 为错误 JSON）时，blob 分支直接 return await response.blob()，
 * 把错误 JSON 当作成功 Blob 下载成损坏 zip、emit exported 并关闭弹窗，页面无
 * .dt-error。本卡修复：非 2xx 先判 response.ok，clone 读 JSON error 并抛
 * message/detail/code/errors 给调用方；非 JSON body 降级为响应文本。
 *
 * 覆盖：
 * - 非 2xx + JSON error body → reject，message = 后端 message，且携带 code/detail/errors
 * - 非 2xx + 非 JSON 错误体 → reject，message 降级为响应文本
 * - 2xx → 正常返回 Blob
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { request } from '../client';

function jsonResponse(status: number, body: Record<string, unknown>): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => {
  localStorage.clear();
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('client 二进制分支 response.ok 判定（INT-1005）', () => {
  it('非 2xx + JSON error body：reject，message 为后端 message，且携带 code/detail/errors', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse(400, {
        code: 'EXPORT_FAILED',
        message: '导出任务失败：服务暂不可用',
        detail: 'export service error',
        errors: ['task not found'],
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      request<Blob>('POST', '/data-transfer/export', { task_ids: [1] }, { responseType: 'blob' }),
    ).rejects.toMatchObject({
      message: '导出任务失败：服务暂不可用',
      code: 'EXPORT_FAILED',
      detail: 'export service error',
      errors: ['task not found'],
    });
  });

  it('非 2xx + 非 JSON 错误体：reject，message 降级为响应文本', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response('upstream timeout', { status: 502 }),
    );
    vi.stubGlobal('fetch', fetchMock);

    await expect(
      request<Blob>('GET', '/reports/1/export', null, { responseType: 'blob' }),
    ).rejects.toThrow('upstream timeout');
  });

  it('2xx：正常返回 Blob', async () => {
    // jsdom 环境下真实 Response 包装 Blob 存在跨 realm 字节丢失（undici vs jsdom Blob），
    // 故用 Response-like 桩直接验证 ok 路径契约：handleResponse 原样透传 response.blob()
    const blob = new Blob(['zip-bytes'], { type: 'application/zip' });
    const responseStub = {
      ok: true,
      status: 200,
      blob: () => Promise.resolve(blob),
      arrayBuffer: () => blob.arrayBuffer(),
    };
    const fetchMock = vi.fn().mockResolvedValue(responseStub as unknown as Response);
    vi.stubGlobal('fetch', fetchMock);

    const result = await request<Blob>('POST', '/data-transfer/export', { task_ids: [1] }, { responseType: 'blob' });
    expect(result).toBe(blob); // 同一引用：二进制 ok 分支直接返回 response.blob()
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
