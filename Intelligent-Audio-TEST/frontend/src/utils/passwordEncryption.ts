/**
 * 密码加密传输工具（INT-147 对齐旧库 V9.7.10 src/utils/passwordEncryption.ts）
 * 用 WebCrypto RSA-OAEP/SHA-256 加密密码，服务端 RSA 私钥解密。
 * 仅供 infrastructure 层（authApi）调用，不进 Domain 契约。
 *
 * INT-245 双 padding 降级：WebCrypto subtle 仅存在于安全上下文（https/
 * localhost）；http+LAN-IP 访问时 subtle 为 undefined → 动态 import
 * jsencrypt（纯 JS，不依赖 secure context）走 RSA-PKCS1v15 + 降级公钥
 * （服务端 /auth/login/encryption-key 下发 fallback 字段）。安全上下文
 * 恒走 OAEP 主路径不回退；降级路径失败收敛为 UnavailableError，明文
 * 兜底保持禁止（INT-188）。
 */
interface PasswordEncryptionKeyMaterial {
  kid: string
  publicKey: string
}

interface PasswordEncryptionKey extends PasswordEncryptionKeyMaterial {
  /** 降级密钥（PKCS1v15/jsencrypt 专用；服务端未下发时不可降级） */
  fallback?: PasswordEncryptionKeyMaterial
}

export interface EncryptedPassword {
  passwordEncrypted: string
  encryptionKeyId: string
}

/** 加密初始化/加密失败时的统一用户文案（INT-188：不回退明文，引导刷新重试） */
const PASSWORD_ENCRYPTION_UNAVAILABLE_MESSAGE = '登录加密初始化失败，请刷新页面重试'

/** 加密未启用（encryption-key 返回 enabled=false）→ 允许走明文字段路径 */
export class PasswordEncryptionDisabledError extends Error {
  constructor() {
    super('密码加密未启用')
    this.name = 'PasswordEncryptionDisabledError'
  }
}

/** 加密已启用但公钥获取/加密失败（网络抖动、环境不支持等）→ 禁止回退明文 */
export class PasswordEncryptionUnavailableError extends Error {
  constructor() {
    super(PASSWORD_ENCRYPTION_UNAVAILABLE_MESSAGE)
    this.name = 'PasswordEncryptionUnavailableError'
  }
}

const KEY_CACHE_TTL_MS = 5 * 60_000

let cachedKey: PasswordEncryptionKey | null = null
let cachedAt = 0

export function clearPasswordEncryptionCache(): void {
  cachedKey = null
  cachedAt = 0
}

export function getCachedEncryptionKey(): PasswordEncryptionKey | null {
  const now = Date.now()
  if (cachedKey && now - cachedAt < KEY_CACHE_TTL_MS) {
    return cachedKey
  }
  return null
}

export function cacheEncryptionKey(key: PasswordEncryptionKey): void {
  cachedKey = key
  cachedAt = Date.now()
}

/**
 * 加密密码（先取公钥——调用方注入取钥函数；公钥 5 分钟缓存）。
 * INT-188：公钥获取失败先重试一次（网络抖动容错），仍失败才收敛为
 * PasswordEncryptionUnavailableError；加密未启用抛
 * PasswordEncryptionDisabledError（由调用方决定是否走明文路径）。
 * INT-245：路径按上下文二选一——subtle 可用 → WebCrypto OAEP（主
 * kid）；不可用（http+IP 等非安全上下文）→ jsencrypt PKCS1v15（降级
 * kid，须服务端下发 fallback），两者失败均不回退明文。
 */
export async function encryptPassword(
  password: string,
  fetchKey: () => Promise<PasswordEncryptionKey>,
): Promise<EncryptedPassword> {
  let key: PasswordEncryptionKey
  try {
    key = await fetchKey()
  } catch (e) {
    if (e instanceof PasswordEncryptionDisabledError) throw e
    try {
      key = await fetchKey()
    } catch {
      throw new PasswordEncryptionUnavailableError()
    }
  }
  try {
    if (hasWebCryptoSubtle()) {
      const ciphertext = await rsaOaepEncrypt(password, key.publicKey)
      return {
        passwordEncrypted: ciphertext,
        encryptionKeyId: key.kid,
      }
    }
    const fallback = key.fallback
    if (!fallback?.kid || !fallback.publicKey) {
      throw new Error('服务端未下发降级加密公钥')
    }
    const ciphertext = await rsaPkcs1v15Encrypt(password, fallback.publicKey)
    return {
      passwordEncrypted: ciphertext,
      encryptionKeyId: fallback.kid,
    }
  } catch {
    throw new PasswordEncryptionUnavailableError()
  }
}

/** WebCrypto subtle 仅存在于安全上下文（https / localhost），据此选路径 */
function hasWebCryptoSubtle(): boolean {
  return typeof globalThis.crypto?.subtle !== 'undefined'
}

async function rsaOaepEncrypt(password: string, publicKeyPEM: string): Promise<string> {
  const publicKey = await globalThis.crypto.subtle.importKey(
    'spki',
    pemToDER(publicKeyPEM),
    { name: 'RSA-OAEP', hash: 'SHA-256' },
    false,
    ['encrypt']
  )
  const ciphertext = await globalThis.crypto.subtle.encrypt(
    { name: 'RSA-OAEP' },
    publicKey,
    new TextEncoder().encode(password)
  )
  return arrayBufferToBase64(ciphertext)
}

async function rsaPkcs1v15Encrypt(password: string, publicKeyPEM: string): Promise<string> {
  // 动态 import：jsencrypt 仅在非安全上下文降级路径加载（独立 chunk）
  const { JSEncrypt } = await import('jsencrypt')
  const jsencrypt = new JSEncrypt()
  jsencrypt.setPublicKey(publicKeyPEM)
  const ciphertext = jsencrypt.encrypt(password)
  if (!ciphertext) {
    throw new Error('jsencrypt 加密失败')
  }
  return ciphertext
}

function pemToDER(pem: string): ArrayBuffer {
  const body = pem
    .replace('-----BEGIN PUBLIC KEY-----', '')
    .replace('-----END PUBLIC KEY-----', '')
    .replace(/\s+/g, '')
  const binary = atob(body)
  const bytes = new Uint8Array(binary.length)
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index)
  }
  return bytes.buffer
}

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer)
  let binary = ''
  for (const byte of bytes) {
    binary += String.fromCharCode(byte)
  }
  return btoa(binary)
}
