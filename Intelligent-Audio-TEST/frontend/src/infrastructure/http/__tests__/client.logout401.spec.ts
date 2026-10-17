/**
 * client.ts 401 拦截器循环防护契约测试（INT-622 回归）。
 *
 * 回归背景：authStore.logout() 改 async 后调用 POST /auth/logout，登出请求自身
 * 401（token 已失效）若不带 skipAuthRedirect，会经 401 拦截器再次重入登出 → 无限
 * POST /auth/logout 401 循环（真实浏览器实测 657 次/5s）。
 *
 * 本测试直接建模拦截器时序（真实拦截器经动态 import().then 异步执行，in-flight
 * 窗口关闭后才落地，store 层 in-flight 防护无法覆盖）：
 * - skipAuthRedirect=true 的 401 → 拦截器整体跳过：无跳登录页、无二次请求
 * - 非跳过 401 → 拦截器触发：清登录态 + 跳登录页；登出请求自身携带跳过标记，
 *   共恰好 1 次 POST /auth/logout，不再递归
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

// 强制 AUTH_MODE=dev，让 401 拦截器分支真实生效（默认读取 import.meta.env 在
// vitest 下为 undefined → off，分支会被跳过，无法验证跳过语义）
vi.mock('@/domain/enums', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/domain/enums')>();
  return { ...actual, getEffectiveAuthMode: () => 'dev' };
});

import { request } from '../client';
import { useAuthStore } from '../../../store/authStore';

function jsonResponse(status: number, body: Record<string, unknown>): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => {
  setActivePinia(createPinia());
  localStorage.clear();
  window.location.hash = '';
  vi.stubGlobal('fetch', vi.fn());
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('client 401 拦截器循环防护（INT-622）', () => {
  it('skipAuthRedirect 请求自身 401：拦截器整体跳过——无跳转、无重入请求', async () => {
    // 每次调用返回新 Response（避免 body 被首读消费后二次 .json() 失败）
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(jsonResponse(401, { message: '缺少认证凭据' })),
    );
    vi.stubGlobal('fetch', fetchMock);

    // authApi.logout 的底层语义：skipAuthRedirect=true
    await expect(
      request('POST', '/auth/logout', undefined, { skipAuthRedirect: true }),
    ).rejects.toThrow('缺少认证凭据');

    expect(fetchMock).toHaveBeenCalledTimes(1); // 仅登出请求本身，无二次请求
    expect(window.location.hash).toBe(''); // 未触发跳登录页（拦截器被跳过）
  });

  it('非跳过 401 触发拦截器：清登录态 + 跳登录页，登出请求恰好 1 次 POST 不再递归', async () => {
    // 每次调用返回新 Response（避免 body 被首读消费后二次 .json() 失败）
    const fetchMock = vi.fn().mockImplementation(() =>
      Promise.resolve(jsonResponse(401, { message: '缺少认证凭据' })),
    );
    vi.stubGlobal('fetch', fetchMock);
    const store = useAuthStore();
    store.setAuth('tk-1', {
      id: 1, username: 'dev_user', roleId: 1, roleName: 'admin', permissions: [],
    });

    await expect(request('GET', '/auth/me', undefined)).rejects.toThrow('缺少认证凭据');

    // 拦截器经动态 import().then 异步执行，等待其完成（登出 + 跳转）
    await vi.waitFor(() => {
      expect(window.location.hash).toContain('#/login');
    });

    // 登出请求（POST /auth/logout，skipAuthRedirect）自身 401 不再触发拦截器
    // → 恰 1 次 POST；总请求 2 次（原始 401 + 登出）
    const calls = fetchMock.mock.calls.map((c) => ({
      url: String(c[0]),
      init: c[1] as RequestInit,
    }));
    expect(calls).toHaveLength(2);
    expect(calls[1].init.method).toBe('POST');
    expect(calls[1].url).toContain('/auth/logout');

    // 本地登录态已清除
    expect(store.token).toBe('');
    expect(store.user).toBeNull();
    expect(localStorage.getItem('auth_token')).toBeNull();
  });
});
