/**
 * authStore 登出契约测试（INT-406：POST /auth/logout 服务端审计旁路 best-effort，
 * 失败不阻断本地清理；INT-622：in-flight 归并，并发 401 拦截器重入只发一次登出）。
 * 对照 React 基准 frontend-react auth-store.ts logout：
 * - 先 await authPort.logout()（best-effort），再清 token/user + localStorage
 * - 登出请求自身 401 的循环防护由 authApi.logout 的 skipAuthRedirect 保证
 *   （见 authApi.logout.spec / client.logout401.spec），store 层以 in-flight
 *   promise 归并 in-flight 窗口内的并发重入
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

vi.mock('../../composables/auth/authPort', () => ({
  authPort: {
    login: vi.fn(),
    register: vi.fn(),
    getMe: vi.fn(),
    logout: vi.fn(),
  },
}));

import { authPort } from '../../composables/auth/authPort';
import { useAuthStore } from '../authStore';

const mockedLogout = vi.mocked(authPort.logout);
const TOKEN_KEY = 'auth_token';
const USER_KEY = 'auth_user';

function seedLoggedInStore() {
  const store = useAuthStore();
  store.setAuth('tk-1', {
    id: 1,
    username: 'dev_user',
    roleId: 1,
    roleName: 'admin',
    permissions: ['*'],
  });
  return store;
}

beforeEach(() => {
  setActivePinia(createPinia());
  mockedLogout.mockReset();
  localStorage.clear();
});

describe('authStore logout（best-effort POST /auth/logout + 本地清理）', () => {
  it('登出成功：先调 authPort.logout()，再清 token/user（内存 + localStorage）', async () => {
    mockedLogout.mockResolvedValue();
    const store = seedLoggedInStore();
    expect(store.isLoggedIn).toBe(true);
    expect(localStorage.getItem(TOKEN_KEY)).toBe('tk-1');

    await store.logout();

    expect(mockedLogout).toHaveBeenCalledTimes(1);
    expect(store.token).toBe('');
    expect(store.user).toBeNull();
    expect(store.isLoggedIn).toBe(false);
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(localStorage.getItem(USER_KEY)).toBeNull();
  });

  it('登出接口失败（含 token 失效 401）：不阻断本地清理（审计旁路 INT-406）', async () => {
    mockedLogout.mockRejectedValue(new Error('401 缺少认证凭据'));
    const store = seedLoggedInStore();

    await expect(store.logout()).resolves.toBeUndefined();

    expect(mockedLogout).toHaveBeenCalledTimes(1);
    expect(store.token).toBe('');
    expect(store.user).toBeNull();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
    expect(localStorage.getItem(USER_KEY)).toBeNull();
  });

  it('in-flight 归并：in-flight 期间重入 await 同一 promise，authPort.logout 仅发一次', async () => {
    const store = seedLoggedInStore();
    let calls = 0;
    let resolveFirst!: () => void;
    mockedLogout.mockImplementation(() => {
      calls += 1;
      return new Promise<void>((resolve) => { resolveFirst = resolve; });
    });

    const first = store.logout();
    // 模拟并发 401 请求的拦截器在 in-flight 窗口内重入登出
    // （pinia 对 action 返回做 .then 包装，两次调用不可能是同一 Promise 对象，
    // 以行为断言：authPort.logout 仅发一次、两个调用都随同一 in-flight 任务完成）
    const reentrant = store.logout();
    void reentrant;

    resolveFirst();
    await Promise.all([first, reentrant]);

    expect(calls).toBe(1);
    expect(store.token).toBe('');
    expect(store.user).toBeNull();
    expect(localStorage.getItem(TOKEN_KEY)).toBeNull();
  });
});
