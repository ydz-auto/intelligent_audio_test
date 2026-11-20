/**
 * 导出产物卡：Agent 导出结果的可用性（PPT/PDF 可下载、MD/HTML 可预览）。
 *
 * 回归背景：旧实现只把后端返回的 `/api/v1/report-studio/exports/{id}/download`
 * 写进回复正文；该路径需要 Bearer token，浏览器直接点 401。产物卡必须替用户
 * 发起鉴权下载，且给出「查看文档」入口。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { StudioExportArtifact } from '@/domain/models/report-studio'

import { ExportArtifactCard } from '../export-artifact-card'

const state = vi.hoisted(() => ({
  job: null as Record<string, unknown> | null,
  jobError: null as unknown,
  openStudioDocument: vi.fn(),
  downloadBlob: vi.fn(),
  downloadBlobImpl: async (): Promise<Blob> => new Blob(['artifact']),
}))

vi.mock('@/application/reports/use-report-studio', () => ({
  useStudioExportJob: () => ({
    data: state.job,
    error: state.jobError,
    isLoading: false,
    isError: state.jobError != null,
    refetch: vi.fn(),
  }),
}))

vi.mock('@/infrastructure/stores/aiChatSessionStore', () => ({
  useAiChatSession: (
    selector: (store: { openStudioDocument: typeof state.openStudioDocument }) => unknown
  ) => selector({ openStudioDocument: state.openStudioDocument }),
}))

vi.mock('@/infrastructure/api/reportStudioApi', () => ({
  downloadStudioExportBlob: () => state.downloadBlobImpl(),
}))

vi.mock('@/lib/download-blob', () => ({
  downloadBlob: (...args: unknown[]) => state.downloadBlob(...args),
}))

vi.mock('@/components/ai-elements/response', () => ({
  Response: ({ children }: { children: string }) => <div>{children}</div>,
}))

function makeArtifact(
  overrides: Partial<StudioExportArtifact> = {}
): StudioExportArtifact {
  return {
    exportId: 'e-1',
    docId: 'doc-1',
    reportId: 420,
    version: 2,
    format: 'pptx',
    theme: 'default',
    status: 'done',
    progress: 100,
    error: null,
    downloadRef: '/api/v1/report-studio/exports/e-1/download',
    ...overrides,
  }
}

beforeEach(() => {
  state.job = null
  state.jobError = null
  state.openStudioDocument = vi.fn()
  state.downloadBlob = vi.fn()
  state.downloadBlobImpl = async () => new Blob(['artifact'])
})

describe('ExportArtifactCard', () => {
  it('PPTX 完成态 → 下载走鉴权接口并给出可读文件名', async () => {
    render(<ExportArtifactCard artifact={makeArtifact()} />)

    expect(screen.queryByTestId('studio-export-artifact-preview')).not.toBeInTheDocument()
    fireEvent.click(screen.getByTestId('studio-export-artifact-download'))

    await waitFor(() => expect(state.downloadBlob).toHaveBeenCalledTimes(1))
    expect(state.downloadBlob.mock.calls[0][1]).toBe('报告-420-v2.pptx')
  })

  it('「查看文档」→ 把文档焦点交给页面（自动展开文档面板）', () => {
    render(<ExportArtifactCard artifact={makeArtifact()} />)

    fireEvent.click(screen.getByTestId('studio-export-artifact-open-doc'))

    expect(state.openStudioDocument).toHaveBeenCalledWith({
      docId: 'doc-1',
      reportId: 420,
    })
  })

  it('失败态 → 展示后端原因，不出现下载 / 预览按钮', () => {
    render(
      <ExportArtifactCard
        artifact={makeArtifact({ status: 'failed', progress: 0, error: '渲染器未部署' })}
      />
    )

    expect(screen.getByTestId('studio-export-artifact-error')).toHaveTextContent(
      '渲染器未部署'
    )
    expect(screen.queryByTestId('studio-export-artifact-download')).not.toBeInTheDocument()
    expect(screen.queryByTestId('studio-export-artifact-preview')).not.toBeInTheDocument()
  })

  it('Markdown 完成态 → 侧边预览面板内渲染正文', async () => {
    state.downloadBlobImpl = async () => new Blob(['# 报告正文'])
    render(<ExportArtifactCard artifact={makeArtifact({ format: 'md' })} />)

    fireEvent.click(screen.getByTestId('studio-export-artifact-preview'))

    expect(await screen.findByText('# 报告正文')).toBeInTheDocument()
  })

  it('在途作业 → 展示进度，不提供下载', () => {
    render(
      <ExportArtifactCard
        artifact={makeArtifact({ status: 'running', progress: 40 })}
      />
    )

    expect(screen.getByTestId('studio-export-artifact-progress')).toHaveTextContent('40%')
    expect(screen.queryByTestId('studio-export-artifact-download')).not.toBeInTheDocument()
  })
})
