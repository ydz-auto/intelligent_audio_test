/**
 * 写操作失败必须有可见反馈（INT-2473 返工 P2-1）。
 *
 * 根因：`ApiError` 在网络层失败 / 错误体只有 detail 时 `message` 恒为空串，
 * 旧实现五处写操作都取 `error.message`，空串被条件渲染吞掉 → 保存 / 起草 /
 * 恢复 / 导出的失败「毫无提示」。这里把「空 message 的 ApiError 仍出现文案」
 * 逐个钉成断言，防止有人改回 `error.message`。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { NETWORK_FAILED_COPY } from '@/domain/models/auth'
import { ApiError } from '@/infrastructure/api/api-error'

import { DocumentPanel } from '../document-panel'
import { ExportPanel } from '../export-panel'
import { VersionList } from '../version-list'

/** 网络层失败（client.ts 构造的真实形状：message 为空、isNetworkError=true） */
function networkError() {
  return new ApiError({
    httpStatus: null,
    message: '',
    detail: 'Failed to fetch',
    isNetworkError: true,
  })
}

const state = vi.hoisted(() => ({
  docs: [] as Record<string, unknown>[],
  createImpl: async (): Promise<Record<string, unknown>> => ({}),
  saveImpl: async (): Promise<void> => {},
  restoreImpl: async (): Promise<unknown> => ({}),
  exportCreateImpl: async (): Promise<Record<string, unknown>> => ({}),
  exportJob: null as Record<string, unknown> | null,
  exportJobError: null as unknown,
  exportRefetch: vi.fn(),
}))

vi.mock('@/application/hooks/use-permissions', () => ({
  usePermissions: () => ({ hasPermission: () => true }),
}))

vi.mock('@/application/reports/use-report-studio', async () => {
  const React = await import('react')
  /** 模拟 react-query：mutation 失败后把 error 写回 hook 状态并触发重渲染 */
  const useMutationMock = (impl: () => Promise<unknown>) => {
    const [error, setError] = React.useState<unknown>(null)
    return {
      error,
      isPending: false,
      mutateAsync: async () => {
        try {
          return await impl()
        } catch (err) {
          setError(err)
          throw err
        }
      },
    }
  }
  return {
    useStudioDocuments: () => ({
      data: { items: state.docs },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    }),
    useStudioDocument: (docId: string | null) => ({
      data: state.docs.find((doc) => doc.docId === docId) ?? null,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    }),
    useCreateStudioDocument: () => useMutationMock(state.createImpl),
    useUpdateStudioDocument: () => useMutationMock(state.saveImpl),
    useStudioDocumentVersions: () => ({
      data: [
        { id: 2, docId: 'd-1', version: 2, snapshotReason: 'manual_edit', createdAt: null },
        { id: 1, docId: 'd-1', version: 1, snapshotReason: 'ai_edit', createdAt: null },
      ],
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    }),
    useRestoreStudioDocumentVersion: () => useMutationMock(state.restoreImpl),
    useCreateStudioExportJob: () => useMutationMock(state.exportCreateImpl),
    useStudioExportJob: () => ({
      data: state.exportJob,
      error: state.exportJobError,
      isLoading: false,
      isError: state.exportJobError != null,
      refetch: state.exportRefetch,
    }),
  }
})

vi.mock('@/features/ai-chat/hooks/use-pending-approvals', () => ({
  usePendingApprovals: () => ({ pendingCount: 0, isLoading: false, isError: false }),
}))

vi.mock('@/components/ai-elements/response', () => ({
  Response: ({ children }: { children: string }) => <div>{children}</div>,
}))

vi.mock('@/infrastructure/api/reportStudioApi', () => ({
  downloadStudioExportBlob: vi.fn(),
}))

const doc = {
  createdAt: '2026-11-14T06:00:00',
  currentVersion: 1,
  docId: 'd-1',
  markdownContent: '# 草稿正文',
  sourceFormat: null,
  title: '接线测试 草稿',
  updatedAt: '2026-11-14T06:00:00',
}

beforeEach(() => {
  state.docs = [doc]
  state.createImpl = async () => ({})
  state.saveImpl = async () => {}
  state.restoreImpl = async () => ({})
  state.exportCreateImpl = async () => ({})
  state.exportJob = null
  state.exportJobError = null
  state.exportRefetch = vi.fn()
})

describe('DocumentPanel 保存失败（P2-1）', () => {
  it('空 message 的 ApiError 也要出文案，不能点完保存什么都看不到', async () => {
    state.saveImpl = async () => {
      throw networkError()
    }
    render(
      <DocumentPanel
        onClose={() => {}}
        reportId={426}
        sourceId='426'
        sourceKind='report'
      />
    )

    fireEvent.click(screen.getByRole('button', { name: '编辑文档' }))
    fireEvent.change(screen.getByTestId('studio-document-editor'), {
      target: { value: '# 改过的正文' },
    })
    fireEvent.click(screen.getByTestId('studio-document-save'))

    expect(await screen.findByText(NETWORK_FAILED_COPY)).toBeInTheDocument()
  })
})

describe('DocumentPanel 起草失败（P2-1）', () => {
  it('空 message 的 ApiError 也要出文案', async () => {
    state.docs = []
    state.createImpl = async () => {
      throw networkError()
    }
    render(
      <DocumentPanel
        onClose={() => {}}
        reportId={426}
        sourceId='426'
        sourceKind='report'
      />
    )

    fireEvent.click(screen.getByTestId('studio-draft-button'))
    expect(await screen.findByText(NETWORK_FAILED_COPY)).toBeInTheDocument()
  })
})

describe('VersionList 恢复失败（P2-1）', () => {
  it('空 message 的 ApiError 也要出文案，弹窗不能停在原样', async () => {
    state.restoreImpl = async () => {
      throw networkError()
    }
    render(
      <VersionList
        canRestore
        currentVersion={2}
        docId='d-1'
        onOpenChange={() => {}}
        open
      />
    )

    fireEvent.click(screen.getByRole('button', { name: '恢复版本 v1' }))
    expect(await screen.findByText(NETWORK_FAILED_COPY)).toBeInTheDocument()
  })
})

describe('ExportPanel 创建作业失败（P2-1）', () => {
  it('空 message 的 ApiError 也要出文案', async () => {
    state.exportCreateImpl = async () => {
      throw networkError()
    }
    render(
      <ExportPanel
        canExport
        docId='d-1'
        docTitle='接线测试 草稿'
        onOpenChange={() => {}}
        open
        version={1}
      />
    )

    fireEvent.click(screen.getByTestId('studio-export-start'))
    expect(await screen.findByText(NETWORK_FAILED_COPY)).toBeInTheDocument()
  })
})

describe('ExportPanel 进度查询失败（P3-1）', () => {
  it('查询失败时保留作业、给重试查询入口，并禁止再建第二个作业', async () => {
    state.exportCreateImpl = async () => ({ exportId: 'e-1' })
    state.exportJobError = networkError()
    render(
      <ExportPanel
        canExport
        docId='d-1'
        docTitle='接线测试 草稿'
        onOpenChange={() => {}}
        open
        version={1}
      />
    )

    fireEvent.click(screen.getByTestId('studio-export-start'))

    expect(await screen.findByTestId('studio-export-query-error')).toBeInTheDocument()
    expect(screen.getByTestId('studio-export-start')).toBeDisabled()

    fireEvent.click(screen.getByTestId('studio-export-requery'))
    expect(state.exportRefetch).toHaveBeenCalledTimes(1)
  })
})
