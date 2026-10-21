/**
 * Access Token API module（INT-1140 联接你的 agent）
 *
 * 个人 Access Token CRUD：经网关转发 auth_service（/api/v1/auth/access-tokens），
 * 鉴权 = 当前登录用户本人（JWT 由 http/client.ts 拦截器注入）。
 * skill 包下载见 agentSkillApi（agent 域）。
 *
 * 出口契约：camelCase Domain（domain/model/accessToken.ts）。
 * DTO（snake_case，dto/accessTokenDto.ts）→ Domain 转换由
 * accessTokenAdapter 承担，业务层只消费领域类型。
 */
import { request, type RequestOptions } from '../http/client';
import type {
  AccessTokenListResultDto,
  AccessTokenCreatedDto,
  AccessTokenDto,
} from '../dto/accessTokenDto';
import type {
  AccessToken,
  AccessTokenCreated,
  AccessTokenCreatePayload,
  AccessTokenUpdatePayload,
} from '../../domain/model/accessToken';
import {
  toAccessToken,
  toAccessTokenCreated,
  toAccessTokenList,
} from '../adapters/accessTokenAdapter';

export const accessTokenApi = {
  /**
   * 当前用户 Access Token 列表（掩码：token_hint，无明文/哈希）
   * GET /auth/access-tokens
   */
  async list(options: RequestOptions = {}): Promise<AccessToken[]> {
    const dto = await request<AccessTokenListResultDto>(
      'GET', '/auth/access-tokens', undefined, options);
    return toAccessTokenList(dto?.items ?? []);
  },

  /**
   * 创建 Access Token（明文仅本响应返回一次，库中只存哈希）
   * POST /auth/access-tokens
   *  - expiresAt 缺省 → 后端默认有效期；0 → 永不过期；ISO → 显式过期
   *  - scopes 缺省/空 → 继承用户全部权限
   */
  async create(
    payload: AccessTokenCreatePayload,
    options: RequestOptions = {},
  ): Promise<AccessTokenCreated> {
    const dto = await request<AccessTokenCreatedDto>(
      'POST', '/auth/access-tokens', {
        name: payload.name,
        ...(payload.scopes !== undefined ? { scopes: payload.scopes } : {}),
        ...(payload.expiresAt !== undefined ? { expires_at: payload.expiresAt } : {}),
      }, options);
    return toAccessTokenCreated(dto as AccessTokenCreatedDto);
  },

  /** 当前用户单个 Access Token 详情（掩码） GET /auth/access-tokens/{id} */
  async get(id: number, options: RequestOptions = {}): Promise<AccessToken> {
    const dto = await request<AccessTokenDto>(
      'GET', `/auth/access-tokens/${id}`, undefined, options);
    return toAccessToken(dto as AccessTokenDto);
  },

  /**
   * 更新当前用户 Access Token（键缺省 = 不修改；scopes 空数组 = 清空继承全部）
   * PATCH /auth/access-tokens/{id}
   */
  async update(
    id: number,
    payload: AccessTokenUpdatePayload,
    options: RequestOptions = {},
  ): Promise<void> {
    const body: Record<string, unknown> = {};
    if (payload.name !== undefined) body.name = payload.name;
    if (payload.scopes !== undefined) body.scopes = payload.scopes;
    if (payload.status !== undefined) body.status = payload.status;
    if (payload.expiresAt !== undefined) body.expires_at = payload.expiresAt;
    await request('PATCH', `/auth/access-tokens/${id}`, body, options);
  },

  /** 软删除当前用户 Access Token（保留行供审计） DELETE /auth/access-tokens/{id} */
  async remove(id: number, options: RequestOptions = {}): Promise<void> {
    await request('DELETE', `/auth/access-tokens/${id}`, undefined, options);
  },
}
