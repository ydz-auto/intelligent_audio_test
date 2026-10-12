/**
 * authApi 登录加密回退语义契约测试（INT-188）
 * 覆盖：
 * - 加密启用（enabled=true）且公钥获取失败 → 重试一次后报错，不发起
 *   明文登录请求（取消静默明文兜底）
 * - 加密未启用（enabled=false）→ 保持明文字段路径（兼容旧语义）
 * - 加密启用 + 加密成功 → 提交 password_encrypted/encryption_key_id，
 *   请求体不含明文 password
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}));

import { request } from '../../http/client';
import { authApi } from '../authApi';
import {
  clearPasswordEncryptionCache,
  PasswordEncryptionUnavailableError,
} from '../../../utils/passwordEncryption';

const mockedRequest = vi.mocked(request);

// 加密成功链路依赖 WebCrypto subtle（jsdom 环境缺失时跳过该组）
const hasSubtle = typeof globalThis.crypto?.subtle !== 'undefined';
const itIfSubtle = hasSubtle ? it : it.skip;

beforeEach(() => {
  mockedRequest.mockReset();
  clearPasswordEncryptionCache();
});

function callsByMethod(method: string) {
  return mockedRequest.mock.calls.filter(([m]) => m === method);
}

describe('authApi login 加密回退语义（INT-188）', () => {
  it('加密启用且公钥获取失败：重试一次后报错，不发明文登录请求', async () => {
    mockedRequest.mockRejectedValue(new Error('network down'));
    await expect(
      authApi.login({ username: 'u1', password: 'p1' }),
    ).rejects.toThrow('登录加密初始化失败，请刷新页面重试');
    // 公钥获取恰好两次（首发 + 重试一次），且全程无 POST /auth/login
    const gets = callsByMethod('GET');
    expect(gets).toHaveLength(2);
    for (const [method, url] of gets) {
      expect(method).toBe('GET');
      expect(url).toBe('/auth/login/encryption-key');
    }
    expect(callsByMethod('POST')).toHaveLength(0);
  });

  it('加密未启用（enabled=false）：保持明文字段路径（兼容）', async () => {
    mockedRequest.mockImplementation(async (method: string) => {
      if (method === 'GET') {
        return { enabled: false };
      }
      return { user: { username: 'u1' }, access_token: 'tk' };
    });
    const result = await authApi.login({ username: 'u1', password: 'p1' });
    expect(result.accessToken).toBe('tk');
    const posts = callsByMethod('POST');
    expect(posts).toHaveLength(1);
    const [, , body] = posts[0] as [string, string, URLSearchParams];
    expect(body).toBeInstanceOf(URLSearchParams);
    expect(body.get('password')).toBe('p1');
    expect(body.get('password_encrypted')).toBeNull();
  });

  itIfSubtle('加密启用且加密成功：提交密文字段，不含明文 password', async () => {
    // 生成真实 RSA-OAEP 密钥对，SPKI DER → PEM 下发
    const pair = await globalThis.crypto.subtle.generateKey(
      { name: 'RSA-OAEP', modulusLength: 2048, publicExponent: new Uint8Array([1, 0, 1]), hash: 'SHA-256' },
      true,
      ['encrypt', 'decrypt'],
    );
    const der = await globalThis.crypto.subtle.exportKey('spki', pair.publicKey);
    const b64 = btoa(String.fromCharCode(...new Uint8Array(der)));
    const pem = `-----BEGIN PUBLIC KEY-----\n${b64}\n-----END PUBLIC KEY-----`;
    mockedRequest.mockImplementation(async (method: string) => {
      if (method === 'GET') {
        return { enabled: true, kid: 'kid-188', public_key: pem };
      }
      return { user: { username: 'u1' }, access_token: 'tk' };
    });
    const result = await authApi.login({ username: 'u1', password: 'p1' });
    expect(result.accessToken).toBe('tk');
    const posts = callsByMethod('POST');
    expect(posts).toHaveLength(1);
    const [, , body] = posts[0] as [string, string, URLSearchParams];
    expect(body.get('username')).toBe('u1');
    expect(body.get('encryption_key_id')).toBe('kid-188');
    expect(body.get('password_encrypted')).toBeTruthy();
    expect(body.get('password')).toBeNull();
  });

  it('抛错类型为 PasswordEncryptionUnavailableError（LoginPage 据此呈现文案）', async () => {
    mockedRequest.mockRejectedValue(new Error('503'));
    await expect(
      authApi.login({ username: 'u1', password: 'p1' }),
    ).rejects.toBeInstanceOf(PasswordEncryptionUnavailableError);
  });
});

describe('authApi register 加密回退语义（INT-188）', () => {
  it('加密启用且公钥获取失败：报错且不发明文注册请求', async () => {
    mockedRequest.mockRejectedValue(new Error('network down'));
    await expect(
      authApi.register({ username: 'u1', password: 'p1' }),
    ).rejects.toThrow('登录加密初始化失败，请刷新页面重试');
    expect(callsByMethod('POST')).toHaveLength(0);
  });

  it('加密未启用（enabled=false）：保持明文字段路径（兼容）', async () => {
    mockedRequest.mockImplementation(async (method: string) => {
      if (method === 'GET') {
        return { enabled: false };
      }
      return { user_id: 7 };
    });
    const result = await authApi.register({ username: 'u1', password: 'p1' });
    expect(result.userId).toBe(7);
    const posts = callsByMethod('POST');
    expect(posts).toHaveLength(1);
    const body = posts[0][2] as Record<string, unknown>;
    expect(body.password).toBe('p1');
    expect(body.password_encrypted).toBeUndefined();
  });
});
