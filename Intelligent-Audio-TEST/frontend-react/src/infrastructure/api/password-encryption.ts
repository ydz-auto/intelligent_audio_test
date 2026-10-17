/**
 * 密码加密传输工具（infrastructure/api 层；对照旧 Vue utils/passwordEncryption.ts 平移）。
 * WebCrypto RSA-OAEP/SHA-256 加密密码，服务端 RSA 私钥解密（INT-147）。
 * INT-188：加密初始化/加密失败不回退明文，收敛为 PasswordEncryptionUnavailableError
 * 引导刷新重试；后端加密未启用（encryption-key 返回 enabled=false）抛
 * PasswordEncryptionDisabledError，由调用方决定是否走明文字段路径。
 * jsencrypt PKCS1v15 降级公钥路径（http+LAN-IP 非安全上下文）随【接线·认证】卡补装。
 */

export interface PasswordEncryptionKey {
  kid: string
  publicKey: string
  /** 降级公钥（PKCS1v15/jsencrypt 专用；服务端未下发时不可降级） */
  fallback?: { kid: string; publicKey: string }
}

export interface EncryptedPassword {
  passwordEncrypted: string
  encryptionKeyId: string
}

/** 加密初始化/加密失败时的统一用户文案（INT-188：不回退明文，引导刷新重试） */
export const PASSWORD_ENCRYPTION_UNAVAILABLE_MESSAGE =
  '登录加密初始化失败，请刷新页面重试'

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

/**
 * 加密密码（先取公钥——调用方注入取钥函数）。
 * 公钥获取失败先重试一次（网络抖动容错），仍失败收敛为
 * PasswordEncryptionUnavailableError；加密未启用抛 DisabledError 由调用方
 * 决定是否走明文路径。非安全上下文（WebCrypto subtle 不可用）当前收敛为
 * 不可用（降级路径待认证卡补装），均不回退明文（INT-188）。
 */
export async function encryptPassword(
  password: string,
  fetchKey: () => Promise<PasswordEncryptionKey>
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
    if (!hasWebCryptoSubtle()) {
      throw new Error('非安全上下文暂不支持加密登录')
    }
    const ciphertext = await rsaOaepEncrypt(password, key.publicKey)
    return {
      passwordEncrypted: ciphertext,
      encryptionKeyId: key.kid,
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
