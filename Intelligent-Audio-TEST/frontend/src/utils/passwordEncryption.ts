/**
 * 密码加密传输工具（INT-147 对齐旧库 V9.7.10 src/utils/passwordEncryption.ts）
 * 用 WebCrypto RSA-OAEP/SHA-256 加密密码，服务端 RSA 私钥解密。
 * 仅供 infrastructure 层（authApi）调用，不进 Domain 契约。
 */
interface PasswordEncryptionKey {
  kid: string
  publicKey: string
}

export interface EncryptedPassword {
  passwordEncrypted: string
  encryptionKeyId: string
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

/** 加密密码（先取公钥——调用方注入取钥函数；公钥 5 分钟缓存） */
export async function encryptPassword(
  password: string,
  fetchKey: () => Promise<PasswordEncryptionKey>,
): Promise<EncryptedPassword> {
  const key = await fetchKey()
  const ciphertext = await rsaOaepEncrypt(password, key.publicKey)
  return {
    passwordEncrypted: ciphertext,
    encryptionKeyId: key.kid,
  }
}

async function rsaOaepEncrypt(password: string, publicKeyPEM: string): Promise<string> {
  if (typeof globalThis.crypto?.subtle !== 'undefined') {
    try {
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
    } catch {
      // 继续尝试 fallback
    }
  }
  throw new Error('当前环境不支持密码加密，请关闭加密传输后重试')
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
