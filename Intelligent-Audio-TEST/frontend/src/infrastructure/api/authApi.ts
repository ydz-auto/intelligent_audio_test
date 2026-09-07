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
import type { AuthLoginResult, CurrentUserInfo } from '../../domain/model/auth';
import { toAuthLoginResult, toCurrentUserInfo } from '../adapters/authAdapter';

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
  }
}