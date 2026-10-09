/**
 * 认证 API module
 * 登录（POST /auth/login）与当前用户信息（GET /auth/me）
 *
 * 出口契约：camelCase Domain（domain/model/auth.ts）。
 * DTO（snake_case，dto/authDto.ts）→ Domain 转换由 authAdapter 承担，
 * 业务层只消费领域类型。
 *
 * 说明：
 * - 后端 /auth/login 通过 FastAPI Form(...) 接收表单字段（username/password），
 *   请求体须为 application/x-www-form-urlencoded，不能走默认 JSON 通道
 * - /auth/me 需要 JWT，token 由 http/client.ts 认证拦截器自动注入
 */
import { request, type RequestOptions } from '../http/client';
import type { AuthLoginResultDto, AuthMeResultDto } from '../dto/authDto';
import type { OAuthProviderDto, OAuthProviderPublicDto } from '../dto/authDto';
import type { AuthLoginResult, CurrentUserInfo } from '../../domain/model/auth';
import type { OAuthProvider, OAuthProviderDetail } from '../../domain/model/auth';
import {
  toAuthLoginResult, toCurrentUserInfo,
  toOAuthProviderPublicList, toOAuthProvider, toOAuthProviderList,
} from '../adapters/authAdapter';

export const authApi = {
  /**
   * 开发模式用户名/密码登录
   * body 以 URLSearchParams 提交，强制表单编码以匹配后端 Form(...) 契约。
   * 跳过 401 自动登出（密码错误返回 401 时不应触发登出跳转循环）。
   */
  async login(credentials: { username: string; password: string }, options: RequestOptions = {}): Promise<AuthLoginResult> {
    const body = new URLSearchParams({
      username: credentials.username,
      password: credentials.password,
    });
    const dto = await request<AuthLoginResultDto>('POST', '/auth/login', body, {
      ...options,
      skipAuthRedirect: true,
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        ...(options.headers as Record<string, string> | undefined),
      },
    });
    return toAuthLoginResult(dto);
  },

  /** 获取当前登录用户信息（JWT 由 client.ts 拦截器注入） */
  async getMe(options: RequestOptions = {}): Promise<CurrentUserInfo> {
    const dto = await request<AuthMeResultDto>('GET', '/auth/me', undefined, options);
    return toCurrentUserInfo(dto);
  },

  // ===== 登录体系改造（INT-51）=====

  /**
   * 自助注册（POST /auth/register；后端注册开关关闭时 403）
   * 成功后调用方引导用户走登录 Tab 完成登录。
   */
  async register(
    payload: { username: string; password: string; email?: string },
    options: RequestOptions = {},
  ): Promise<{ userId: number }> {
    const dto = await request<{ user_id: number }>(
      'POST', '/auth/register', payload, {
        ...options,
        skipAuthRedirect: true,
      });
    return { userId: dto?.user_id ?? 0 };
  },

  /** 已启用 OAuth 提供方（登录页动态渲染，公开端点无凭证字段） */
  async listPublicOAuthProviders(options: RequestOptions = {}): Promise<OAuthProvider[]> {
    const dto = await request<{ providers: OAuthProviderPublicDto[] }>(
      'GET', '/auth/oauth/providers', undefined, {
        ...options,
        skipAuthRedirect: true,
      });
    return toOAuthProviderPublicList(dto?.providers ?? []);
  },

  /** OAuth 授权跳转地址（整页跳转由调用方 window.location.href 拼接） */
  getOAuthAuthorizeUrl(slug: string): string {
    return `/api/v1/auth/oauth/${encodeURIComponent(slug)}/authorize`;
  },

  /** 管理端：全部提供方（含禁用；clientSecret 掩去） */
  async listOAuthProviders(options: RequestOptions = {}): Promise<OAuthProviderDetail[]> {
    const dto = await request<{ providers: OAuthProviderDto[] }>(
      'GET', '/auth/oauth-providers', undefined, options);
    return toOAuthProviderList(dto?.providers ?? []);
  },

  /** 管理端：提供方详情 */
  async getOAuthProvider(id: number, options: RequestOptions = {}): Promise<OAuthProviderDetail> {
    const dto = await request<OAuthProviderDto>(
      'GET', `/auth/oauth-providers/${id}`, undefined, options);
    return toOAuthProvider(dto);
  },

  /** 管理端：创建提供方（clientSecret 必填；缺省键走后端默认值） */
  async createOAuthProvider(
    payload: Partial<Record<string, unknown>> & {
      name: string; slug: string; client_id: string; client_secret: string;
      authorize_url: string; token_url: string; userinfo_url: string;
    },
    options: RequestOptions = {},
  ): Promise<{ providerId: number }> {
    const dto = await request<{ provider_id: number }>(
      'POST', '/auth/oauth-providers', payload, options);
    return { providerId: dto?.provider_id ?? 0 };
  },

  /** 管理端：更新提供方（body 键缺省=不修改；client_secret 空串=保留原值） */
  async updateOAuthProvider(
    id: number,
    payload: Record<string, unknown>,
    options: RequestOptions = {},
  ): Promise<void> {
    await request('PUT', `/auth/oauth-providers/${id}`, payload, options);
  },

  /** 管理端：删除提供方 */
  async deleteOAuthProvider(id: number, options: RequestOptions = {}): Promise<void> {
    await request('DELETE', `/auth/oauth-providers/${id}`, undefined, options);
  },
}