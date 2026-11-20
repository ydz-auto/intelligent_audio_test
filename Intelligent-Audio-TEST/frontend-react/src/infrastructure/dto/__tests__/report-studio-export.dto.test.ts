/**
 * Report Studio 版本 / 导出 DTO 转换（INT-2473）。
 * 契约来源：report_service `_version_dict` / `_export_job_dict`（INT-673 + INT-2471）。
 */
import { describe, expect, it } from 'vitest'

import { StudioExportStatus } from '@/domain/models/report-studio'
import {
  toStudioDocumentVersion,
  toStudioExportJob,
} from '@/infrastructure/dto/report-studio.dto'

describe('toStudioExportJob', () => {
  it('映射真实作业字段（snake_case → camelCase）', () => {
    const job = toStudioExportJob({
      export_id: 'e-1',
      doc_id: 'd-1',
      version: 3,
      format: 'pdf',
      theme: 'default',
      status: 'running',
      progress: 42,
      error: null,
      created_at: '2026-11-14T00:00:00',
      updated_at: '2026-11-14T00:00:01',
      download_ref: '/api/v1/report-studio/exports/e-1/download',
    })
    expect(job).toMatchObject({
      exportId: 'e-1',
      docId: 'd-1',
      version: 3,
      format: 'pdf',
      status: StudioExportStatus.RUNNING,
      progress: 42,
      downloadRef: '/api/v1/report-studio/exports/e-1/download',
    })
  })

  it('失败作业保留后端原因', () => {
    const job = toStudioExportJob({
      export_id: 'e-2',
      status: 'failed',
      progress: 100,
      error: '格式 pdf 渲染为后续增强（S3），当前支持 html/md',
    })
    expect(job.status).toBe(StudioExportStatus.FAILED)
    expect(job.error).toContain('当前支持 html/md')
  })

  it('未知状态按失败收口（不把页面卡在轮询里）', () => {
    expect(toStudioExportJob({ status: 'weird' }).status).toBe(
      StudioExportStatus.FAILED
    )
  })

  it('空载荷给安全默认值', () => {
    expect(toStudioExportJob(null)).toMatchObject({
      exportId: '',
      version: 0,
      progress: 0,
      downloadRef: null,
    })
  })
})

describe('toStudioDocumentVersion', () => {
  it('映射版本链字段；后端不返回正文时正文为空串', () => {
    const version = toStudioDocumentVersion({
      id: 1,
      doc_id: 'd-1',
      version: 2,
      parent_version: 1,
      snapshot_reason: 'manual_edit',
      created_at: '2026-11-14T00:00:00',
      created_by: 1,
    })
    expect(version).toMatchObject({
      docId: 'd-1',
      version: 2,
      parentVersion: 1,
      snapshotReason: 'manual_edit',
      createdBy: 1,
      markdownContent: '',
    })
  })
})
