/**
 * Access Token API module —— 契约桩（INT-1155）
 *
 * 端点（INT-1140 定稿，挂网关 /api/v1/auth 前缀，鉴权 = 当前登录用户本人）：
 *   POST   /auth/access-tokens            创建（明文仅返回一次）
 *   GET    /auth/access-tokens            列表（token_hint 掩码末 4 位）
 *   PATCH  /auth/access-tokens/{id}       重命名 / 换 scopes / 改 expires / 启停
 *   DELETE /auth/access-tokens/{id}       删除
 *
 * // 待接线（INT-1149）：后端 api_gateway「网关鉴权扩展 + Access Token CRUD 路由」未合栈。
 * 本文件先按后端 schema 维护会话级内存桩（种子示例数据 + 增删改查就地更新），
 * 供前端完整走创建→列表→编辑→启停→删除流程；页面渲染层零 mock。
 * 合栈后把各函数内的示例分支整体替换为 request(...) 真实调用（上方注释已给真实端点形态），
 * 不留双口径。
 */
import type {
  AccessToken,
  AccessTokenCreatePayload,
  AccessTokenCreated,
  AccessTokenUpdatePayload,
} from '../../domain/model/accessToken'
import type { AccessTokenItemDto, AccessTokenCreateResultDto } from '../dto/accessTokenDto'
import { toAccessToken, toAccessTokenCreated } from '../adapters/accessTokenAdapter'

/** 明文令牌前缀（对齐 INT-1140：at_ + 32 hex） */
const TOKEN_PREFIX = 'at_'

/** 桩内随机 hex 生成（仅内存桩用；真实令牌由后端生成） */
function randomHex(length: number): string {
  let s = ''
  for (let i = 0; i < length; i++) {
    s += Math.floor(Math.random() * 16).toString(16)
  }
  return s
}

/** 种子示例数据（符合后端 schema；未创建前列表展示用） */
const seedTokens: AccessTokenItemDto[] = [
  {
    id: 1,
    name: 'CI 集成令牌',
    token_hint: 'a3f2',
    scopes: ['task:read', 'task:create', 'task:execute', 'testcase:read', 'report:read'],
    expires_at: '2026-12-31T23:59:59Z',
    status: 'enabled',
    last_used_at: '2026-10-21T05:30:00Z',
    created_at: '2026-10-20T02:00:00Z',
  },
  {
    id: 2,
    name: '外部 Agent 只读令牌',
    token_hint: '7c1e',
    scopes: null,
    expires_at: 0,
    status: 'disabled',
    last_used_at: null,
    created_at: '2026-10-18T09:00:00Z',
  },
]

/** 会话级内存表（// 待接线：合栈后删除，改由后端持久化） */
let tokenSeq = seedTokens.length
const memoryTokens: AccessTokenItemDto[] = [...seedTokens]

/** 创建（POST /auth/access-tokens）——返回明文 token 仅此一次 */
export async function createAccessToken(
  payload: AccessTokenCreatePayload,
): Promise<AccessTokenCreated> {
  // 待接线（INT-1149）：真实请求
  //   const dto = await request<AccessTokenCreateResultDto>('POST', '/auth/access-tokens', {
  //     name: payload.name,
  //     scopes: payload.scopes.length > 0 ? payload.scopes : null,
  //     expires_at: payload.expiresAt ?? 0,
  //   })
  //   return toAccessTokenCreated(dto)
  const plain = `${TOKEN_PREFIX}${randomHex(32)}`
  const item: AccessTokenItemDto = {
    id: ++tokenSeq,
    name: payload.name,
    token_hint: plain.slice(-4),
    scopes: payload.scopes.length > 0 ? payload.scopes : null,
    expires_at: payload.expiresAt ?? 0,
    status: 'enabled',
    last_used_at: null,
    created_at: new Date().toISOString(),
  }
  memoryTokens.unshift(item)
  return toAccessTokenCreated({ access_token: plain, token: item })
}

/** 列表（GET /auth/access-tokens）——每行 token_hint 掩码末 4 位 */
export async function listAccessTokens(): Promise<AccessToken[]> {
  // 待接线（INT-1149）：真实请求
  //   const dto = await request<{ items: AccessTokenItemDto[] }>('GET', '/auth/access-tokens')
  //   return (dto?.items ?? []).map(toAccessToken)
  return memoryTokens.map(toAccessToken)
}

/** 更新（PATCH /auth/access-tokens/{id}）——重命名 / 换 scopes / 改 expires / 启停 */
export async function updateAccessToken(
  id: number,
  payload: AccessTokenUpdatePayload,
): Promise<AccessToken> {
  // 待接线（INT-1149）：真实请求
  //   const dto = await request<AccessTokenItemDto>('PATCH', `/auth/access-tokens/${id}`, {
  //     name: payload.name,
  //     scopes: payload.scopes !== undefined ? (payload.scopes.length > 0 ? payload.scopes : null) : undefined,
  //     expires_at: payload.expiresAt !== undefined ? (payload.expiresAt ?? 0) : undefined,
  //     status: payload.status,
  //   })
  //   return toAccessToken(dto)
  const item = memoryTokens.find((t) => t.id === id)
  if (!item) throw new Error('令牌不存在')
  if (payload.name !== undefined) item.name = payload.name
  if (payload.scopes !== undefined) item.scopes = payload.scopes.length > 0 ? payload.scopes : null
  if (payload.expiresAt !== undefined) item.expires_at = payload.expiresAt ?? 0
  if (payload.status !== undefined) item.status = payload.status
  return toAccessToken(item)
}

/** 删除（DELETE /auth/access-tokens/{id}） */
export async function deleteAccessToken(id: number): Promise<void> {
  // 待接线（INT-1149）：真实请求
  //   await request('DELETE', `/auth/access-tokens/${id}`)
  const idx = memoryTokens.findIndex((t) => t.id === id)
  if (idx >= 0) memoryTokens.splice(idx, 1)
}

/** 命名导出对象（供 api/index.ts 桶引用） */
export const accessTokenApi = {
  createAccessToken,
  listAccessTokens,
  updateAccessToken,
  deleteAccessToken,
}
