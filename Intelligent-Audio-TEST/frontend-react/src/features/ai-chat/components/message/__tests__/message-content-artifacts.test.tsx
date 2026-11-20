/**
 * 服务端历史回填的产物卡：messages 从 getAgentSession 恢复时没有 toolCalls，
 * 产物挂在 message.exportArtifacts 上；消息编排必须把它渲染出来，
 * 且与 toolCalls[].exportArtifact 按 exportId 去重。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { ChatMessage } from '@/domain/models/aiChat'
import type { StudioExportArtifact } from '@/domain/models/report-studio'
import { AiChatMessageContent } from '@/features/ai-chat/components/message/message-content'

vi.mock('@/features/ai-chat/components/message/export-artifact-card', () => ({
  ExportArtifactCard: ({
    artifact,
  }: {
    artifact: StudioExportArtifact
  }) => <div data-testid='export-artifact-card'>{artifact.exportId}</div>,
}))

function makeArtifact(exportId: string): StudioExportArtifact {
  return {
    exportId,
    docId: 'doc-1',
    reportId: 420,
    version: 1,
    format: 'html',
    theme: 'default',
    status: 'done',
    progress: 100,
    error: null,
    downloadRef: `/api/v1/report-studio/exports/${exportId}/download`,
  }
}

function renderMessage(message: ChatMessage) {
  return render(
    <AiChatMessageContent
      alignment='left'
      message={message}
      versionContent={message.versions[0]?.content ?? ''}
    />
  )
}

describe('AiChatMessageContent 产物卡', () => {
  it('服务端回填消息的 exportArtifacts 仍渲染产物卡', () => {
    renderMessage({
      key: 'restored-1',
      from: 'assistant',
      versions: [{ id: 'restored-1-v1', content: '之前的回答' }],
      status: 'complete',
      exportArtifacts: [makeArtifact('e-1')],
    })

    expect(screen.getByTestId('export-artifact-card')).toHaveTextContent('e-1')
  })

  it('exportArtifacts 与 toolCalls 指向同一导出作业时只渲染一张卡', () => {
    renderMessage({
      key: 'assistant-1',
      from: 'assistant',
      versions: [{ id: 'assistant-1-v1', content: '导出完成' }],
      status: 'complete',
      exportArtifacts: [makeArtifact('e-1')],
      toolCalls: [
        {
          id: 'tc-1',
          tool: 'report_export',
          label: '导出报告',
          status: 'completed',
          exportArtifact: makeArtifact('e-1'),
        },
      ],
    })

    expect(screen.getAllByTestId('export-artifact-card')).toHaveLength(1)
  })
})
