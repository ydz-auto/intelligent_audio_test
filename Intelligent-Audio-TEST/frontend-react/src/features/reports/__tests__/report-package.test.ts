/**
 * 报告包预检 + Report Studio DTO 映射单测（INT-1766 D8）。
 * 覆盖：ZIP 只读 manifest（stored / deflate 两种压缩）、非 ZIP / 无 manifest 降级，
 * 以及 D5/D6 snake_case → camelCase 映射（source_type 默认、回执双拼写、列表分页字段）。
 */
import { describe, expect, it } from 'vitest'

import {
  toReportPackageImportReceipt,
  toStudioDocument,
  toStudioDocumentList,
} from '@/infrastructure/dto/report-studio.dto'
import { readReportPackageManifest } from '@/features/reports/lib/report-package'

const encoder = new TextEncoder()

interface ZipEntry {
  name: string
  data: Uint8Array
  /** 0 = stored，8 = deflate(raw) */
  method: 0 | 8
}

function streamOf(bytes: Uint8Array): ReadableStream<Uint8Array> {
  return new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(bytes)
      controller.close()
    },
  })
}

async function deflateRaw(bytes: Uint8Array): Promise<Uint8Array> {
  const stream = streamOf(bytes).pipeThrough(
    new CompressionStream('deflate-raw') as unknown as TransformStream<
      Uint8Array,
      Uint8Array
    >
  )
  const reader = stream.getReader()
  const chunks: Uint8Array[] = []
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    if (value) chunks.push(value)
  }
  return chunks.length === 1 ? chunks[0] : concat(chunks)
}

function concat(parts: Uint8Array[]): Uint8Array {
  const total = parts.reduce((sum, part) => sum + part.length, 0)
  const out = new Uint8Array(total)
  let offset = 0
  for (const part of parts) {
    out.set(part, offset)
    offset += part.length
  }
  return out
}

function u16(value: number): Uint8Array {
  const bytes = new Uint8Array(2)
  new DataView(bytes.buffer).setUint16(0, value, true)
  return bytes
}

function u32(value: number): Uint8Array {
  const bytes = new Uint8Array(4)
  new DataView(bytes.buffer).setUint32(0, value, true)
  return bytes
}

/** 构造最小合法 ZIP（单文件足够表达预检场景） */
async function buildZip(entries: ZipEntry[]): Promise<Blob> {
  const locals: Uint8Array[] = []
  const centrals: Uint8Array[] = []
  let offset = 0
  for (const entry of entries) {
    const nameBytes = encoder.encode(entry.name)
    const payload =
      entry.method === 8 ? await deflateRaw(entry.data) : entry.data
    const local = concat([
      u32(0x04034b50),
      u16(20),
      u16(0),
      u16(entry.method),
      u16(0),
      u16(0),
      u32(0), // crc32（预检不解压校验，置 0）
      u32(payload.length),
      u32(entry.data.length),
      u16(nameBytes.length),
      u16(0),
      nameBytes,
      payload,
    ])
    locals.push(local)
    centrals.push(
      concat([
        u32(0x02014b50),
        u16(20),
        u16(20),
        u16(0),
        u16(entry.method),
        u16(0),
        u16(0),
        u32(0),
        u32(payload.length),
        u32(entry.data.length),
        u16(nameBytes.length),
        u16(0),
        u16(0),
        u16(0),
        u16(0),
        u32(0),
        u32(offset),
        nameBytes,
      ])
    )
    offset += local.length
  }
  const centralDir = concat(centrals)
  const eocd = concat([
    u32(0x06054b50),
    u16(0),
    u16(0),
    u16(entries.length),
    u16(entries.length),
    u32(centralDir.length),
    u32(offset),
    u16(0),
  ])
  return new Blob([...locals, centralDir, eocd] as BlobPart[])
}

const MANIFEST = {
  kind: 'report_package',
  version: '1.0',
  exportedAt: '2026-10-25T12:00:00Z',
  sourceTask: { id: 301, name: '接线测试_源任务', caseSetHash: 'abc' },
  entities: ['platform_report', 'uploaded_file', 'agent_summary'],
  docVersionScope: 'full',
  stats: { documents: 3, versions: 4 },
}

function toFile(blob: Blob, name: string): File {
  return new File([blob], name, { type: 'application/zip' })
}

describe('report package manifest preflight', () => {
  it('读取 stored 压缩包内的 manifest', async () => {
    const zip = await buildZip([
      { name: 'manifest.json', data: encoder.encode(JSON.stringify(MANIFEST)), method: 0 },
      { name: 'db/test_reports.json', data: encoder.encode('[]'), method: 0 },
    ])
    const summary = await readReportPackageManifest(toFile(zip, 'pkg.zip'))
    expect(summary).not.toBeNull()
    expect(summary?.kind).toBe('report_package')
    expect(summary?.sourceTaskId).toBe(301)
    expect(summary?.sourceTaskName).toBe('接线测试_源任务')
    expect(summary?.docVersionScope).toBe('full')
    expect(summary?.stats).toEqual({ documents: 3, versions: 4 })
  })

  it('读取 deflate 压缩包内的 manifest', async () => {
    const zip = await buildZip([
      {
        name: 'manifest.json',
        data: encoder.encode(JSON.stringify(MANIFEST)),
        method: 8,
      },
    ])
    const summary = await readReportPackageManifest(toFile(zip, 'pkg.zip'))
    expect(summary?.sourceTaskId).toBe(301)
  })

  it('非 ZIP 扩展名直接降级为 null', async () => {
    const zip = await buildZip([])
    expect(await readReportPackageManifest(toFile(zip, 'pkg.tar'))).toBeNull()
  })

  it('ZIP 内没有 manifest 时降级为 null', async () => {
    const zip = await buildZip([
      { name: 'db/test_reports.json', data: encoder.encode('[]'), method: 0 },
    ])
    expect(await readReportPackageManifest(toFile(zip, 'pkg.zip'))).toBeNull()
  })

  it('损坏的 ZIP 不抛异常', async () => {
    const broken = new File([encoder.encode('not a zip at all')], 'x.zip')
    expect(await readReportPackageManifest(broken)).toBeNull()
  })
})

describe('report studio dto mapping', () => {
  it('文档字段 snake_case → camelCase，未知 source_type 回落平台报告', () => {
    const doc = toStudioDocument({
      doc_id: 'doc-1',
      report_id: 12,
      title: '总结',
      current_version: 3,
      chart_refs: ['chart:a'],
      source_type: 'agent_summary',
      agent_session_id: null,
      parent_doc_id: 'doc-0',
      source_format: null,
      source_download_ref: null,
    })
    expect(doc.docId).toBe('doc-1')
    expect(doc.reportId).toBe(12)
    expect(doc.currentVersion).toBe(3)
    expect(doc.sourceType).toBe('agent_summary')
    expect(doc.parentDocId).toBe('doc-0')
    expect(doc.chartRefs).toEqual(['chart:a'])

    expect(toStudioDocument({ doc_id: 'd2', source_type: 'unknown' }).sourceType).toBe(
      'platform_report'
    )
  })

  it('列表缺省字段回落为空数组与总数', () => {
    const list = toStudioDocumentList({ items: [{ doc_id: 'a' }], total: 7 })
    expect(list.items).toHaveLength(1)
    expect(list.total).toBe(7)
    expect(toStudioDocumentList(null).total).toBe(0)
  })

  it('导入回执兼容 camelCase 与 snake_case，缺省落空', () => {
    const receipt = toReportPackageImportReceipt({
      report_id: 88,
      target_resolved_by: 'latest_report',
      deleted_counts: { report_cases: 1 },
      inserted_counts: { report_cases: 2 },
      documentIdMapping: { 'old-doc': 'new-doc' },
      agent_session_dropped: 2,
      warnings: ['孤儿文档'],
      rollbackAvailable: true,
    })
    expect(receipt.reportId).toBe(88)
    expect(receipt.targetResolvedBy).toBe('latest_report')
    expect(receipt.deletedCounts).toEqual({ report_cases: 1 })
    expect(receipt.insertedCounts).toEqual({ report_cases: 2 })
    expect(receipt.documentIdMapping).toEqual({ 'old-doc': 'new-doc' })
    expect(receipt.agentSessionDropped).toBe(2)
    expect(receipt.warnings).toEqual(['孤儿文档'])
    expect(receipt.rollbackAvailable).toBe(true)

    const empty = toReportPackageImportReceipt(null)
    expect(empty.reportId).toBeNull()
    expect(empty.documentIdMapping).toEqual({})
    expect(empty.rollbackAvailable).toBe(false)
  })
})
