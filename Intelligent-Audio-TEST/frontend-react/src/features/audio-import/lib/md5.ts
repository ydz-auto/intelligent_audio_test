/**
 * 浏览器端 MD5（RFC 1321；INT-1582 批量更新标注按内容 MD5 匹配音频）。
 *
 * V9.7.10 BatchAnnotationModal 用 spark-md5 分块算音频 MD5；本项目不引入该依赖，
 * 这里给等价的分块增量实现：`Md5` 可多次 append（大文件按切片流式读，不整只入内存），
 * `md5OfFile` 按 FILE_CHUNK_SIZE 切片读取 File 后出 32 位小写十六进制摘要。
 * 摘要口径与后端 audios.md5 列（标准 MD5 hex）一致，供 POST /audios/by-md5 查库。
 */

const ROTATE = [
  7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 7, 12, 17, 22, 5, 9, 14, 20, 5, 9, 14, 20, 5, 9,
  14, 20, 5, 9, 14, 20, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 4, 11, 16, 23, 6, 10, 15,
  21, 6, 10, 15, 21, 6, 10, 15, 21, 6, 10, 15, 21,
]

/** K[i] = floor(abs(sin(i + 1)) * 2^32)（RFC 1321 常量表，模块加载时算一次） */
const SINE_TABLE = (() => {
  const table = new Uint32Array(64)
  for (let i = 0; i < 64; i += 1) {
    table[i] = Math.floor(Math.abs(Math.sin(i + 1)) * 0x100000000) >>> 0
  }
  return table
})()

const BLOCK_SIZE = 64
/** 单次读取切片（10MB，与 V9.7.10 calculateMd5 的 chunkSize 同档） */
export const FILE_CHUNK_SIZE = 10 * 1024 * 1024

function rotateLeft(value: number, bits: number): number {
  return ((value << bits) | (value >>> (32 - bits))) >>> 0
}

/** 增量 MD5（append 可任意切分，结果只取决于字节序列） */
export class Md5 {
  private readonly state = new Uint32Array([0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476])
  private readonly tail = new Uint8Array(BLOCK_SIZE)
  private readonly words = new Uint32Array(16)
  private tailLength = 0
  private byteLength = 0

  append(chunk: Uint8Array): void {
    this.byteLength += chunk.length
    let offset = 0

    if (this.tailLength > 0) {
      const take = Math.min(BLOCK_SIZE - this.tailLength, chunk.length)
      this.tail.set(chunk.subarray(0, take), this.tailLength)
      this.tailLength += take
      offset = take
      if (this.tailLength === BLOCK_SIZE) {
        this.processBlock(this.tail, 0)
        this.tailLength = 0
      }
    }

    while (offset + BLOCK_SIZE <= chunk.length) {
      this.processBlock(chunk, offset)
      offset += BLOCK_SIZE
    }

    if (offset < chunk.length) {
      this.tail.set(chunk.subarray(offset), 0)
      this.tailLength = chunk.length - offset
    }
  }

  /** 收尾（补位 + 长度）并返回 32 位小写 hex */
  digest(): string {
    const bitLength = this.byteLength * 8
    const paddingLength = this.tailLength < 56 ? 56 - this.tailLength : 120 - this.tailLength
    const padding = new Uint8Array(paddingLength + 8)
    padding[0] = 0x80
    const view = new DataView(padding.buffer)
    view.setUint32(paddingLength, bitLength >>> 0, true)
    view.setUint32(paddingLength + 4, Math.floor(bitLength / 0x100000000), true)
    // append 会计入 byteLength，但摘要已在补位前取长度，无副作用
    this.append(padding)

    let hex = ''
    for (let i = 0; i < 4; i += 1) {
      for (let j = 0; j < 4; j += 1) {
        const byte = (this.state[i] >>> (j * 8)) & 0xff
        hex += byte.toString(16).padStart(2, '0')
      }
    }
    return hex
  }

  private processBlock(bytes: Uint8Array, offset: number): void {
    const x = this.words
    for (let i = 0; i < 16; i += 1) {
      const at = offset + i * 4
      x[i] =
        (bytes[at] |
          (bytes[at + 1] << 8) |
          (bytes[at + 2] << 16) |
          (bytes[at + 3] << 24)) >>>
        0
    }

    let a = this.state[0]
    let b = this.state[1]
    let c = this.state[2]
    let d = this.state[3]

    for (let i = 0; i < 64; i += 1) {
      let f: number
      let g: number
      if (i < 16) {
        f = (b & c) | (~b & d)
        g = i
      } else if (i < 32) {
        f = (d & b) | (~d & c)
        g = (5 * i + 1) % 16
      } else if (i < 48) {
        f = b ^ c ^ d
        g = (3 * i + 5) % 16
      } else {
        f = c ^ (b | ~d)
        g = (7 * i) % 16
      }
      const sum = (a + f + SINE_TABLE[i] + x[g]) | 0
      const rotated = (b + rotateLeft(sum >>> 0, ROTATE[i])) >>> 0
      a = d
      d = c
      c = b
      b = rotated
    }

    this.state[0] = (this.state[0] + a) >>> 0
    this.state[1] = (this.state[1] + b) >>> 0
    this.state[2] = (this.state[2] + c) >>> 0
    this.state[3] = (this.state[3] + d) >>> 0
  }
}

/** 字节数组 MD5（32 位小写 hex） */
export function md5Hex(bytes: Uint8Array): string {
  const hasher = new Md5()
  hasher.append(bytes)
  return hasher.digest()
}

/** 浏览器 File/Blob 的 MD5（分块流式读取，大文件不整只入内存） */
export async function md5OfFile(
  file: Blob,
  onProgress?: (loaded: number, total: number) => void
): Promise<string> {
  const hasher = new Md5()
  const total = file.size
  let loaded = 0
  while (loaded < total) {
    const slice = file.slice(loaded, Math.min(loaded + FILE_CHUNK_SIZE, total))
    const buffer = await slice.arrayBuffer()
    hasher.append(new Uint8Array(buffer))
    loaded += buffer.byteLength
    onProgress?.(loaded, total)
  }
  return hasher.digest()
}
