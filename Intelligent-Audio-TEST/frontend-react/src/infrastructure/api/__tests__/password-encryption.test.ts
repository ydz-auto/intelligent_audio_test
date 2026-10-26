/**
 * 密码加密原语单测（INT-1990 双 padding）：
 * - 安全上下文（crypto.subtle 可用）→ WebCrypto RSA-OAEP，encryption_key_id 用主 kid，
 *   且不加载 jsencrypt；
 * - 非安全上下文（http+IP，subtle 为 undefined）→ jsencrypt RSA-PKCS1v15，keyId 用降级 kid，
 *   服务端未下发 fallback 时收敛为 PasswordEncryptionUnavailableError；
 * - 取钥失败重试一次、两次失败收敛、DisabledError 直接上抛（不回退明文，INT-188）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { jsencryptLoadSpy, jsencryptSetPublicKeySpy } = vi.hoisted(() => ({
  jsencryptLoadSpy: vi.fn(),
  jsencryptSetPublicKeySpy: vi.fn(),
}))

vi.mock('jsencrypt', () => {
  jsencryptLoadSpy()
  class JSEncrypt {
    setPublicKey(publicKey: string): void {
      jsencryptSetPublicKeySpy(publicKey)
    }
    encrypt(password: string): string | false {
      return password === 'jsencrypt-fail' ? false : `pkcs1:${password}`
    }
  }
  return { JSEncrypt }
})

import {
  PasswordEncryptionDisabledError,
  PasswordEncryptionUnavailableError,
  encryptPassword,
  type PasswordEncryptionKey,
} from '@/infrastructure/api/password-encryption'

/** 合法 base64（atob 可解），OAEP 路径的 pemToDER 用 */
const PUBLIC_KEY_PEM = 'TWFu'
const FALLBACK_PEM = '-----BEGIN PUBLIC KEY-----\nRkFMTEJBQ0s=\n-----END PUBLIC KEY-----'

const MAIN_KEY: PasswordEncryptionKey = {
  kid: 'kid-main',
  publicKey: PUBLIC_KEY_PEM,
  fallback: { kid: 'kid-fb', publicKey: FALLBACK_PEM },
}

/** 模拟安全上下文：crypto.subtle 存在（OAEP 走桩实现） */
function stubSecureContext(): void {
  vi.stubGlobal('crypto', {
    subtle: {
      importKey: vi.fn(async () => 'imported-key'),
      encrypt: vi.fn(async () => new Uint8Array([1, 2, 3]).buffer),
    },
  })
}

/** 模拟非安全上下文：http + IP 下 crypto.subtle 为 undefined */
function stubInsecureContext(): void {
  vi.stubGlobal('crypto', { subtle: undefined })
}

describe('encryptPassword', () => {
  beforeEach(() => {
    jsencryptSetPublicKeySpy.mockClear()
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  // 必须排在降级用例之前：jsencrypt 模块一旦被动态 import 就留在模块缓存里
  describe('安全上下文（subtle 可用）', () => {
    it('走 WebCrypto RSA-OAEP，encryption_key_id 为主 kid，且不加载 jsencrypt', async () => {
      stubSecureContext()
      const result = await encryptPassword('secret', async () => MAIN_KEY)

      expect(result.encryptionKeyId).toBe('kid-main')
      expect(result.passwordEncrypted).toBe('AQID')
      expect(jsencryptLoadSpy).not.toHaveBeenCalled()
      expect(jsencryptSetPublicKeySpy).not.toHaveBeenCalled()
    })

    it('OAEP 加密失败收敛为 UnavailableError（不回退明文/降级）', async () => {
      vi.stubGlobal('crypto', {
        subtle: {
          importKey: vi.fn(async () => {
            throw new Error('importKey 失败')
          }),
          encrypt: vi.fn(),
        },
      })
      await expect(
        encryptPassword('secret', async () => MAIN_KEY)
      ).rejects.toBeInstanceOf(PasswordEncryptionUnavailableError)
      expect(jsencryptSetPublicKeySpy).not.toHaveBeenCalled()
    })
  })

  describe('非安全上下文（subtle 不可用）', () => {
    it('走 jsencrypt PKCS1v15 + 降级公钥，encryption_key_id 为降级 kid', async () => {
      stubInsecureContext()
      const result = await encryptPassword('secret', async () => MAIN_KEY)

      expect(result.encryptionKeyId).toBe('kid-fb')
      expect(result.passwordEncrypted).toBe('pkcs1:secret')
      expect(jsencryptLoadSpy).toHaveBeenCalledTimes(1)
      expect(jsencryptSetPublicKeySpy).toHaveBeenCalledWith(FALLBACK_PEM)
    })

    it('服务端未下发 fallback：收敛为 UnavailableError，不加载 jsencrypt、不回退明文', async () => {
      stubInsecureContext()
      await expect(
        encryptPassword('secret', async () => ({
          kid: 'kid-main',
          publicKey: PUBLIC_KEY_PEM,
        }))
      ).rejects.toBeInstanceOf(PasswordEncryptionUnavailableError)
      expect(jsencryptSetPublicKeySpy).not.toHaveBeenCalled()
    })

    it('jsencrypt 返回空密文：收敛为 UnavailableError', async () => {
      stubInsecureContext()
      await expect(
        encryptPassword('jsencrypt-fail', async () => MAIN_KEY)
      ).rejects.toBeInstanceOf(PasswordEncryptionUnavailableError)
    })
  })

  describe('取钥失败重试', () => {
    it('首次取钥失败、重试成功：正常返回密文', async () => {
      stubSecureContext()
      const fetchKey = vi
        .fn<() => Promise<PasswordEncryptionKey>>()
        .mockRejectedValueOnce(new Error('网络抖动'))
        .mockResolvedValueOnce(MAIN_KEY)

      const result = await encryptPassword('secret', fetchKey)
      expect(fetchKey).toHaveBeenCalledTimes(2)
      expect(result.encryptionKeyId).toBe('kid-main')
    })

    it('两次取钥均失败：收敛为 UnavailableError', async () => {
      stubSecureContext()
      const fetchKey = vi.fn(async () => {
        throw new Error('网络失败')
      })
      await expect(encryptPassword('secret', fetchKey)).rejects.toBeInstanceOf(
        PasswordEncryptionUnavailableError
      )
      expect(fetchKey).toHaveBeenCalledTimes(2)
    })

    it('加密未启用（DisabledError）：直接上抛且不重试（调用方走明文路径）', async () => {
      stubSecureContext()
      const fetchKey = vi.fn(async () => {
        throw new PasswordEncryptionDisabledError()
      })
      await expect(encryptPassword('secret', fetchKey)).rejects.toBeInstanceOf(
        PasswordEncryptionDisabledError
      )
      expect(fetchKey).toHaveBeenCalledTimes(1)
    })
  })
})
