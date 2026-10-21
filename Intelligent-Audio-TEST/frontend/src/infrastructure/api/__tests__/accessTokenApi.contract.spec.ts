/**
 * accessTokenApi / agentSkillApi 契约测试（INT-1140 联接你的 agent）
 *
 * 锁定与后端 auth_service access_tokens CRUD + 网关 skill 下载端点的
 * 请求路径 / snake_case 载荷 / query 参数；防前端 adapter 改动破坏契约。
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../http/client', () => ({
  request: vi.fn(),
}));

import { request } from '../../http/client';
import { accessTokenApi } from '../accessTokenApi';
import { agentSkillApi } from '../agentSkillApi';

const mockedRequest = vi.mocked(request);

beforeEach(() => {
  mockedRequest.mockReset();
});

const baseTokenDto = {
  id: 3,
  user_id: 2,
  name: 'Claude Code',
  token_hint: 'abcd',
  scopes: ['task:read', 'audio:read'],
  status: 'enabled',
  expires_at: 0,
  last_used_at: null,
  last_used_ip: null,
  created_at: '2026-10-21T10:00:00',
};

describe('accessTokenApi.list', () => {
  it('GET /auth/access-tokens，响应 items 转 Domain（camelCase 掩码）', async () => {
    mockedRequest.mockResolvedValue({
      total: 1,
      items: [baseTokenDto],
    });

    const tokens = await accessTokenApi.list();

    expect(mockedRequest).toHaveBeenCalledWith(
      'GET', '/auth/access-tokens', undefined, expect.anything());
    expect(tokens[0]).toEqual({
      id: 3,
      userId: 2,
      name: 'Claude Code',
      tokenHint: 'abcd',
      scopes: ['task:read', 'audio:read'],
      status: 'enabled',
      expiresAt: 0,
      lastUsedAt: null,
      lastUsedIp: null,
      createdAt: '2026-10-21T10:00:00',
    });
    expect('token' in tokens[0]).toBe(false); // 列表绝不返回明文
  });
});

describe('accessTokenApi.create', () => {
  it('POST /auth/access-tokens，载荷 snake_case；缺省 scopes/expires_at 不上送', async () => {
    mockedRequest.mockResolvedValue({ ...baseTokenDto, token: 'at_abcd1234' });

    const created = await accessTokenApi.create({ name: '新 token' });

    expect(mockedRequest).toHaveBeenCalledWith(
      'POST', '/auth/access-tokens', { name: '新 token' }, expect.anything());
    expect(created.token).toBe('at_abcd1234');
  });

  it('expiresAt=0 映射 expires_at=0（永不过期）；scopes 透传数组', async () => {
    mockedRequest.mockResolvedValue({ ...baseTokenDto, token: 'at_x' });

    await accessTokenApi.create({
      name: 't',
      scopes: ['task:read'],
      expiresAt: 0,
    });

    expect(mockedRequest).toHaveBeenCalledWith(
      'POST', '/auth/access-tokens',
      { name: 't', scopes: ['task:read'], expires_at: 0 },
      expect.anything());
  });

  it('expiresAt=ISO 字符串映射 expires_at=ISO', async () => {
    mockedRequest.mockResolvedValue({ ...baseTokenDto, token: 'at_x' });

    await accessTokenApi.create({
      name: 't',
      expiresAt: '2026-11-20T10:00:00',
    });

    expect(mockedRequest).toHaveBeenCalledWith(
      'POST', '/auth/access-tokens',
      { name: 't', expires_at: '2026-11-20T10:00:00' },
      expect.anything());
  });
});

describe('accessTokenApi.update', () => {
  it('PATCH /auth/access-tokens/{id}；缺省键不发送，null 保留', async () => {
    mockedRequest.mockResolvedValue({});

    await accessTokenApi.update(3, { status: 'disabled' });

    expect(mockedRequest).toHaveBeenCalledWith(
      'PATCH', '/auth/access-tokens/3', { status: 'disabled' }, expect.anything());
  });

  it('scopes 空数组 = 清空继承全部（发送 []）', async () => {
    mockedRequest.mockResolvedValue({});

    await accessTokenApi.update(3, { scopes: [] });

    expect(mockedRequest).toHaveBeenCalledWith(
      'PATCH', '/auth/access-tokens/3', { scopes: [] }, expect.anything());
  });
});

describe('accessTokenApi.remove', () => {
  it('DELETE /auth/access-tokens/{id}', async () => {
    mockedRequest.mockResolvedValue({});

    await accessTokenApi.remove(7);

    expect(mockedRequest).toHaveBeenCalledWith(
      'DELETE', '/auth/access-tokens/7', undefined, expect.anything());
  });
});

describe('agentSkillApi.downloadSkill', () => {
  it('GET /agent/skill?base_url=<地址栏>，responseType=blob', async () => {
    mockedRequest.mockResolvedValue(new Blob(['zip']));

    await agentSkillApi.downloadSkill('http://127.0.0.1:5400');

    expect(mockedRequest).toHaveBeenCalledWith(
      'GET', '/agent/skill', null,
      expect.objectContaining({
        params: { base_url: 'http://127.0.0.1:5400' },
        responseType: 'blob',
      }),
    );
  });

  it('后端错误 JSON Blob（401/404 时 request blob 分支不抛错）转异常', async () => {
    const errBlob = Object.create(Blob.prototype) as Blob
    Object.defineProperties(errBlob, {
      type: { value: 'application/json' },
      size: { value: 40 },
      text: { value: async () => JSON.stringify({ detail: 'skill 端点不可用' }) },
    })
    mockedRequest.mockResolvedValue(errBlob);

    await expect(agentSkillApi.downloadSkill('http://127.0.0.1:5400'))
      .rejects.toThrow('skill 端点不可用');
  });
});
