/**
 * 认证 API module
 * 登录（POST /auth/login）与当前用户信息（GET /auth/me）
 *
 * 出口契约：camelCase Domain（domain/model/auth.ts）。
 * DTO（snake_case，dto/authDto.ts）→ Domain 转换由 authAdapter 承担，
 * 业务层只消费领域类型。
 *
 * 说明：
 * - 后端 /auth/login 通过 FastAPI Form(...) 接收表单字段（username +
 *   password_encrypted/encryption_key_id，INT-147 RSA 加密传输），
 *   请求体须为 application/x-www-form-urlencoded，不能走默认 JSON 通道
 * - /auth/me 需要 JWT，token 由 http/client.ts 认证拦截器自动注入
 * - 密码加密：登录前取公钥（5 分钟缓存），WebCrypto RSA-OAEP/SHA-256；
 *   INT-188 加密启用时不再回退明文——加密初始化失败直接报错引导刷新，
 *   仅后端返回 enabled=false 时走明文字段路径
 */
import { request, type RequestOptions } from '../http/client';
import {
  encryptPassword, getCachedEncryptionKey, cacheEncryptionKey,
  PasswordEncryptionDisabledError, PasswordEncryptionUnavailableError,
} from '../../utils/passwordEncryption';
import type { AuthLoginResultDto, AuthMeResultDto } from '../dto/authDto';
import type { OAuthProviderDto, OAuthProviderPublicDto } from '../dto/authDto';
import type { PasswordEncryptionKeyDto, OAuthBindingDto, OAuthDiscoveryResultDto, AuthModeResultDto } from '../dto/authDto';
import type { AuthLoginResult, CurrentUserInfo } from '../../domain/model/auth';
import type { OAuthProvider, OAuthProviderDetail, OAuthBinding, OAuthDiscoveryResult } from '../../domain/model/auth';
import {
  toAuthLoginResult, toCurrentUserInfo, toAuthMode,
  toOAuthProviderPublicList, toOAuthProvider, toOAuthProviderList,
  toOAuthBinding, toOAuthBindingList, toOAuthDiscoveryResult,
} from '../adapters/authAdapter';

/** 登录/注册共用的 RSA 公钥获取（enabled=false 抛 DisabledError 走明文路径） */
async function fetchEncryptionKey(options: RequestOptions = {}): Promise<{ kid: string; publicKey: string }> {
  const cached = getCachedEncryptionKey();
  if (cached) return cached;
  const dto = await request<PasswordEncryptionKeyDto>(
    'GET', '/auth/login/encryption-key', undefined, {
      ...options,
      skipAuthRedirect: true,
    });
  if (!dto?.enabled) {
    throw new PasswordEncryptionDisabledError();
  }
  if (!dto.kid || !dto.public_key) {
    throw new PasswordEncryptionUnavailableError();
  }
  const key = { kid: dto.kid, publicKey: dto.public_key };
  cacheEncryptionKey(key);
  return key;
}

export const authApi = {
  /**
   * 开发模式用户名/密码登录（INT-147：密码 RSA 加密传输 + 邮箱登录）
   * body 以 URLSearchParams 提交，强制表单编码以匹配后端 Form(...) 契约。
   * 跳过 401 自动登出（密码错误返回 401 时不应触发登出跳转循环）。
   */
  async login(credentials: { username: string; password: string }, options: RequestOptions = {}): Promise<AuthLoginResult> {
    const body = new URLSearchParams({ username: credentials.username });
    try {
      const enc = await encryptPassword(credentials.password, () => fetchEncryptionKey(options));
      body.append('password_encrypted', enc.passwordEncrypted);
      body.append('encryption_key_id', enc.encryptionKeyId);
    } catch (e) {
      // INT-188：加密已启用时禁止明文兜底（后端开启加密时明文必被拒，
      // 形成"必然失败且无解释"陷阱）——初始化失败直接抛错引导刷新，
      // 不发起登录请求；仅加密未启用（enabled=false）走明文字段路径
      if (!(e instanceof PasswordEncryptionDisabledError)) {
        throw e;
      }
      body.append('password', credentials.password);
    }
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
   * INT-147：密码走 RSA 加密字段（password_encrypted/encryption_key_id）。
   * 成功后调用方引导用户走登录 Tab 完成登录。
   */
  async register(
    payload: { username: string; password: string; email?: string },
    options: RequestOptions = {},
  ): Promise<{ userId: number }> {
    const body: Record<string, unknown> = {
      username: payload.username,
      email: payload.email,
    };
    try {
      const enc = await encryptPassword(payload.password, () => fetchEncryptionKey(options));
      body.password_encrypted = enc.passwordEncrypted;
      body.encryption_key_id = enc.encryptionKeyId;
    } catch (e) {
      // INT-188：与 login 同语义——加密启用时不回退明文（后端注册端点
      // 加密开启时也只接受密文字段）
      if (!(e instanceof PasswordEncryptionDisabledError)) {
        throw e;
      }
      body.password = payload.password;
    }
    const dto = await request<{ user_id: number }>(
      'POST', '/auth/register', body, {
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

  /** 当前生效认证模式（INT-180 启动自检，公开端点；仅回枚举 mode 值） */
  async getAuthMode(options: RequestOptions = {}): Promise<string> {
    const dto = await request<AuthModeResultDto>('GET', '/auth/mode', undefined, {
      ...options,
      skipAuthRedirect: true,
    });
    return toAuthMode(dto ?? {});
  },

  /** OAuth 授权跳转地址（整页跳转由调用方 window.location.href 拼接；intent=bind 走绑定流程） */
  getOAuthAuthorizeUrl(slug: string, intent: 'login' | 'bind' = 'login'): string {
    const base = `/api/v1/auth/oauth/${encodeURIComponent(slug)}/authorize`;
    return intent === 'bind' ? `${base}?intent=bind` : base;
  },

  // ===== 第三方账号绑定（INT-147）=====

  /** 当前用户绑定列表（GET /auth/oauth/bindings，JWT 由拦截器注入） */
  async listOAuthBindings(options: RequestOptions = {}): Promise<OAuthBinding[]> {
    const dto = await request<{ bindings: OAuthBindingDto[] }>(
      'GET', '/auth/oauth/bindings', undefined, options);
    return toOAuthBindingList(dto?.bindings ?? []);
  },

  /** 携绑定票据完成绑定（POST /auth/oauth/bindings；票据来自 OAuth 回调回传） */
  async completeOAuthBinding(bindTicket: string, options: RequestOptions = {}): Promise<OAuthBinding> {
    const dto = await request<OAuthBindingDto>(
      'POST', '/auth/oauth/bindings', { bind_ticket: bindTicket }, options);
    return toOAuthBinding(dto as OAuthBindingDto);
  },

  /** 解绑指定提供方（DELETE /auth/oauth/bindings/{id}，幂等） */
  async unbindOAuthProvider(providerId: number, options: RequestOptions = {}): Promise<void> {
    await request('DELETE', `/auth/oauth/bindings/${providerId}`, undefined, options);
  },

  /** 管理端：OIDC Discovery 拉取（POST /auth/oauth/admin/discovery，admin） */
  async fetchOAuthDiscovery(
    payload: { issuer_url?: string; well_known_url?: string },
    options: RequestOptions = {},
  ): Promise<OAuthDiscoveryResult> {
    const dto = await request<OAuthDiscoveryResultDto>(
      'POST', '/auth/oauth/admin/discovery', payload, options);
    return toOAuthDiscoveryResult(dto);
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