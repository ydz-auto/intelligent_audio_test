/**
 * authApi 登出契约测试（INT-406：POST /auth/logout 服务端审计旁路）。
 * 对照 React 基准 frontend-react/src/infrastructure/api/authApi.ts logout：
 * - POST /auth/logout，无请求体，成功返回 void
 * - Vue 侧安全偏离（INT-622 回归）：skipAuthRedirect=true——Vue client.ts 的 401
 *   拦截器会重入 authStore.logout()，登出请求自身 401（token 已失效）若不带跳过
 *   标记将触发拦截器再登出 → 无限 POST /auth/logout 循环。React client 的 401
 *   处理不重入登出 API（仅清本地），故 React 基准无该标记、Vue 必须有。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}));

import { request } from '../../http/client';
import { authApi } from '../authApi';

const mockedRequest = vi.mocked(request);

beforeEach(() => {
  mockedRequest.mockReset();
});

describe('authApi logout（POST /auth/logout）', () => {
  it('登出：POST /auth/logout，无请求体，成功返回 void，携带 skipAuthRedirect', async () => {
    mockedRequest.mockResolvedValue({ message: '已登出' });
    await expect(authApi.logout()).resolves.toBeUndefined();
    expect(mockedRequest).toHaveBeenCalledTimes(1);
    const [method, url, body, options] = mockedRequest.mock.calls[0] as [
      string, string, unknown, Record<string, unknown>,
    ];
    expect(method).toBe('POST');
    expect(url).toBe('/auth/logout');
    expect(body).toBeUndefined();
    // INT-622：登出请求自身 401 不得触发 401 拦截器重入（Vue 侧安全偏离）
    expect(options.skipAuthRedirect).toBe(true);
  });

  it('登出接口失败：请求错误上抛（由 store 层 best-effort 兜底）', async () => {
    mockedRequest.mockRejectedValue(new Error('network down'));
    await expect(authApi.logout()).rejects.toThrow('network down');
  });
});
