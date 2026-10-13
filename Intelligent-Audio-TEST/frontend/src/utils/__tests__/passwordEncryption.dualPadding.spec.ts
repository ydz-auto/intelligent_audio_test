/**
 * 密码加密双 padding 降级契约测试（INT-245）
 * 覆盖：
 * - 安全上下文（subtle 可用）→ 恒走 OAEP 主路径（主 kid），不回退 jsencrypt
 * - 非安全上下文（subtle 缺失，如 http+LAN-IP）→ 动态 jsencrypt PKCS1v15
 *   + 降级 kid，密文可被服务端 RSA 私钥 PKCS1v15 解密还原（含中文 UTF-8）
 * - 非安全上下文且服务端未下发降级公钥 → UnavailableError（禁明文兜底）
 * - subtle 可用但 OAEP 失败（公钥非法）→ 不滑入 jsencrypt 降级（路径二选一）
 * - authApi.login 端到端：非安全上下文提交降级 kid 的密文字段（无明文）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { generateKeyPairSync, privateDecrypt, constants, webcrypto } from 'node:crypto'

import {
  encryptPassword, clearPasswordEncryptionCache,
  PasswordEncryptionUnavailableError,
} from '../passwordEncryption'

vi.mock('../../infrastructure/http/client', () => ({
  request: vi.fn(),
}))

import { request } from '../../infrastructure/http/client'
import { authApi } from '../../infrastructure/api/authApi'

const mockedRequest = vi.mocked(request)

function makeKeyPair() {
  const { publicKey, privateKey } = generateKeyPairSync('rsa', {
    modulusLength: 2048,
    publicExponent: 0x10001,
  })
  return { pem: publicKey.export({ type: 'spki', format: 'pem' }).toString(), privateKey }
}

function decryptOaep(privateKey: any, b64: string): string {
  return privateDecrypt(
    { key: privateKey, padding: constants.RSA_PKCS1_OAEP_PADDING, oaepHash: 'sha256' },
    Buffer.from(b64, 'base64'),
  ).toString('utf8')
}

function decryptPkcs1v15(privateKey: any, b64: string): string {
  return privateDecrypt(
    { key: privateKey, padding: constants.RSA_PKCS1_PADDING },
    Buffer.from(b64, 'base64'),
  ).toString('utf8')
}

// 环境操纵：WebCrypto subtle 是否存在即前端选路径的唯一依据（INT-245）
const realSubtle = globalThis.crypto?.subtle ?? webcrypto.subtle
const realGetRandomValues = webcrypto.getRandomValues.bind(webcrypto)

function stubSecureContext(): void {
  vi.stubGlobal('crypto', { subtle: realSubtle, getRandomValues: realGetRandomValues })
}

function stubInsecureContext(): void {
  // http+IP：subtle 为 undefined（getRandomValues 保留——jsencrypt 安全随机源）
  vi.stubGlobal('crypto', { getRandomValues: realGetRandomValues })
}

beforeEach(() => {
  mockedRequest.mockReset()
  clearPasswordEncryptionCache()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('encryptPassword 双 padding 路径选择（INT-245）', () => {
  it('安全上下文（subtle 可用）→ OAEP 主路径：主 kid + 密文可解', async () => {
    stubSecureContext()
    const primary = makeKeyPair()
    const fallback = makeKeyPair()
    const result = await encryptPassword('pw245', async () => ({
      kid: 'kid-primary', publicKey: primary.pem,
      fallback: { kid: 'kid-fallback', publicKey: fallback.pem },
    }))
    expect(result.encryptionKeyId).toBe('kid-primary')
    expect(decryptOaep(primary.privateKey, result.passwordEncrypted)).toBe('pw245')
  })

  it('非安全上下文（subtle 缺失）→ jsencrypt PKCS1v15：降级 kid + 密文可解', async () => {
    stubInsecureContext()
    const primary = makeKeyPair()
    const fallback = makeKeyPair()
    const result = await encryptPassword('S3cret-密码245!', async () => ({
      kid: 'kid-primary', publicKey: primary.pem,
      fallback: { kid: 'kid-fallback', publicKey: fallback.pem },
    }))
    expect(result.encryptionKeyId).toBe('kid-fallback')
    // jsencrypt（PKCS#1 v1.5）密文由服务端同 padding 私钥解密还原，UTF-8 对齐
    expect(decryptPkcs1v15(fallback.privateKey, result.passwordEncrypted))
      .toBe('S3cret-密码245!')
  })

  it('非安全上下文且未下发降级公钥 → UnavailableError（禁明文兜底）', async () => {
    stubInsecureContext()
    const primary = makeKeyPair()
    await expect(encryptPassword('pw245', async () => ({
      kid: 'kid-primary', publicKey: primary.pem,
    }))).rejects.toBeInstanceOf(PasswordEncryptionUnavailableError)
  })

  it('subtle 可用但 OAEP 失败（公钥非法）→ 不滑入 jsencrypt 降级', async () => {
    stubSecureContext()
    const fallback = makeKeyPair()
    await expect(encryptPassword('pw245', async () => ({
      kid: 'kid-primary', publicKey: 'not-a-pem',
      fallback: { kid: 'kid-fallback', publicKey: fallback.pem },
    }))).rejects.toBeInstanceOf(PasswordEncryptionUnavailableError)
  })
})

describe('authApi.login 非安全上下文端到端（INT-245）', () => {
  it('提交降级 kid 的 PKCS1v15 密文字段，请求体不含明文 password', async () => {
    stubInsecureContext()
    const primary = makeKeyPair()
    const fallback = makeKeyPair()
    mockedRequest.mockImplementation(async (method: string) => {
      if (method === 'GET') {
        return {
          enabled: true,
          kid: 'kid-primary', public_key: primary.pem,
          fallback: { kid: 'kid-fallback', public_key: fallback.pem },
        }
      }
      return { user: { username: 'u245' }, access_token: 'tk' }
    })
    const result = await authApi.login({ username: 'u245', password: 'p245' })
    expect(result.accessToken).toBe('tk')
    const posts = mockedRequest.mock.calls.filter(([m]) => m === 'POST')
    expect(posts).toHaveLength(1)
    const [, , body] = posts[0] as [string, string, URLSearchParams]
    expect(body).toBeInstanceOf(URLSearchParams)
    expect(body.get('encryption_key_id')).toBe('kid-fallback')
    expect(body.get('password_encrypted')).toBeTruthy()
    expect(decryptPkcs1v15(fallback.privateKey, body.get('password_encrypted')!))
      .toBe('p245')
    expect(body.get('password')).toBeNull()
  })
})
