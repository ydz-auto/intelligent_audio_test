/**
 * 导出包条目读取（features/testcases/lib，INT-2196「包含音频文件」）。
 *
 * 只读 ZIP 中央目录的**条目名**，不解压、不校验 CRC：用于导出后核对「勾选了包含音频
 * 文件，包内到底有没有 `audios/` 条目」。不复用不存在的 zip 依赖——条目名在中央目录里
 * 以明文存放，按 EOCD → 中央目录逐个读文件名即可（导出包由后端 zipfile 顺序写出，
 * 单文件 < 4GB，不涉及 ZIP64）。
 */
const EOCD_SIG = 0x06054b50
const CENTRAL_HEADER_SIG = 0x02014b50
const EOCD_MIN_SIZE = 22
/** ZIP 注释最长 0xffff 字节，EOCD 只可能落在文件尾部这一段内 */
const MAX_COMMENT_SIZE = 0xffff

/** 音频条目所在目录（后端数据包口径：`audios/<audio_id>.<ext>`） */
export const AUDIO_ENTRY_DIR = 'audios/'

function findEocd(view: DataView, length: number): number {
  if (length < EOCD_MIN_SIZE) return -1
  const stop = Math.max(0, length - EOCD_MIN_SIZE - MAX_COMMENT_SIZE)
  for (let offset = length - EOCD_MIN_SIZE; offset >= stop; offset -= 1) {
    if (view.getUint32(offset, true) === EOCD_SIG) return offset
  }
  return -1
}

/** 读取 ZIP 内全部条目名；不是合法 ZIP（找不到 EOCD / 中央目录）时返回空数组 */
export function zipEntryNames(bytes: Uint8Array): string[] {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  const eocd = findEocd(view, bytes.byteLength)
  if (eocd < 0) return []

  const count = view.getUint16(eocd + 10, true)
  let offset = view.getUint32(eocd + 16, true)
  const decoder = new TextDecoder()
  const names: string[] = []
  for (let index = 0; index < count; index += 1) {
    if (offset + 46 > bytes.byteLength) break
    if (view.getUint32(offset, true) !== CENTRAL_HEADER_SIG) break
    const nameLength = view.getUint16(offset + 28, true)
    const extraLength = view.getUint16(offset + 30, true)
    const commentLength = view.getUint16(offset + 32, true)
    const nameStart = offset + 46
    if (nameStart + nameLength > bytes.byteLength) break
    names.push(decoder.decode(bytes.subarray(nameStart, nameStart + nameLength)))
    offset = nameStart + nameLength + extraLength + commentLength
  }
  return names
}

/** 包内音频条目数（`audios/` 下的文件，不含目录条目自身） */
export function countAudioEntries(names: string[]): number {
  return names.filter(
    (name) => name.startsWith(AUDIO_ENTRY_DIR) && !name.endsWith('/')
  ).length
}

/**
 * 导出的 ZIP Blob 里有多少个音频条目。
 * 读不出内容（环境不支持 arrayBuffer / 读取抛错）时返回 `null`——调用方据此不提示，
 * 免得把「读不了」误报成「没打包音频」；包体不是 ZIP 时按 0 个音频处理。
 */
export async function countZipAudioEntries(blob: Blob): Promise<number | null> {
  if (typeof blob.arrayBuffer !== 'function') return null
  try {
    return countAudioEntries(zipEntryNames(new Uint8Array(await blob.arrayBuffer())))
  } catch {
    return null
  }
}
