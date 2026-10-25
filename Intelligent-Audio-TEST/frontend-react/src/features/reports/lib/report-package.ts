/**
 * 报告包（ZIP）预检：只读包内 `manifest.json`，不落库、不解析业务数据。
 *
 * 为什么在前端读：D6（INT-1764）只交付 `POST /data-transfer/report/import` 与
 * `/export`，没有报告包预检端点（任务整包的 `/data-transfer/import/preview` 是另一
 * 种包格式，复用会误判）。预检展示「源任务 / 命中本地任务 / 将替换的现有报告」是
 * 卡面第 2 条的硬要求，故此处按 ZIP 规范（PKWARE APPNOTE 4.3.12）只解 manifest，
 * 业务校验与写入仍然全部由后端在导入时完成。
 *
 * 失败一律返回 null（包损坏 / 非报告包 / 无 manifest），由调用方降级为「无法读取
 * 包内清单，导入后以回执为准」，不阻断导入。
 */
import {
  toReportPackageManifest,
  type ReportPackageManifestDto,
} from '@/infrastructure/dto/report-studio.dto'
import type { ReportPackageManifestSummary } from '@/domain/models/report-studio'

const EOCD_SIGNATURE = 0x06054b50
const CENTRAL_SIGNATURE = 0x02014b50
const LOCAL_SIGNATURE = 0x04034b50
const MANIFEST_NAME = 'manifest.json'
const EOCD_MIN_BYTES = 22
const EOCD_MAX_SEARCH = 0xffff

function findEndOfCentralDirectory(view: DataView): number {
  const max = Math.min(view.byteLength, EOCD_MIN_BYTES + EOCD_MAX_SEARCH)
  for (let offset = EOCD_MIN_BYTES; offset <= max; offset += 1) {
    const pos = view.byteLength - offset
    if (view.getUint32(pos, true) === EOCD_SIGNATURE) return pos
  }
  return -1
}

function streamOf(bytes: Uint8Array): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(bytes)
      controller.close()
    },
  })
}

async function collect(stream: ReadableStream<Uint8Array>): Promise<Uint8Array> {
  const reader = stream.getReader()
  const chunks: Uint8Array[] = []
  let total = 0
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    if (value) {
      chunks.push(value)
      total += value.length
    }
  }
  const out = new Uint8Array(total)
  let offset = 0
  for (const chunk of chunks) {
    out.set(chunk, offset)
    offset += chunk.length
  }
  return out
}

async function inflateRaw(bytes: Uint8Array): Promise<Uint8Array> {
  const Decompression = (globalThis as { DecompressionStream?: unknown })
    .DecompressionStream as
    | (new (format: string) => TransformStream<Uint8Array, Uint8Array>)
    | undefined
  if (!Decompression) throw new Error('当前环境不支持解压')
  return collect(streamOf(bytes).pipeThrough(new Decompression('deflate-raw')))
}

/** 读取 ZIP 内 manifest.json 原始字节（仅支持单文件、deflate/stored 两种压缩） */
async function extractManifestBytes(buffer: ArrayBuffer): Promise<Uint8Array | null> {
  const view = new DataView(buffer)
  if (view.byteLength < EOCD_MIN_BYTES) return null
  const eocd = findEndOfCentralDirectory(view)
  if (eocd < 0) return null
  const entryCount = view.getUint16(eocd + 10, true)
  let pos = view.getUint32(eocd + 16, true)
  if (pos <= 0 || pos >= view.byteLength) return null

  for (let i = 0; i < entryCount; i += 1) {
    if (pos + 46 > view.byteLength) return null
    if (view.getUint32(pos, true) !== CENTRAL_SIGNATURE) return null
    const method = view.getUint16(pos + 10, true)
    const compressedSize = view.getUint32(pos + 20, true)
    const nameLen = view.getUint16(pos + 28, true)
    const extraLen = view.getUint16(pos + 30, true)
    const commentLen = view.getUint16(pos + 32, true)
    const localOffset = view.getUint32(pos + 42, true)
    const nameBytes = new Uint8Array(buffer, pos + 46, nameLen)
    const name = new TextDecoder().decode(nameBytes)

    if (name === MANIFEST_NAME) {
      if (localOffset + 30 > view.byteLength) return null
      if (view.getUint32(localOffset, true) !== LOCAL_SIGNATURE) return null
      const localNameLen = view.getUint16(localOffset + 26, true)
      const localExtraLen = view.getUint16(localOffset + 28, true)
      const dataStart = localOffset + 30 + localNameLen + localExtraLen
      if (dataStart + compressedSize > view.byteLength) return null
      const raw = new Uint8Array(buffer, dataStart, compressedSize)
      if (method === 0) return raw
      if (method === 8) return inflateRaw(raw)
      return null
    }
    pos += 46 + nameLen + extraLen + commentLen
  }
  return null
}

function isZipFile(file: File): boolean {
  return /\.zip$/i.test(file.name)
}

/** 读取报告包 manifest；不是 ZIP / 无 manifest / 解压失败均返回 null */
export async function readReportPackageManifest(
  file: File
): Promise<ReportPackageManifestSummary | null> {
  if (!isZipFile(file)) return null
  try {
    const buffer = await file.arrayBuffer()
    const bytes = await extractManifestBytes(buffer)
    if (!bytes) return null
    const json = JSON.parse(new TextDecoder().decode(bytes)) as ReportPackageManifestDto
    if (!json || typeof json !== 'object') return null
    return toReportPackageManifest(json)
  } catch {
    return null
  }
}
