/**
 * 会话存档：产物索引 + 消息字节预算（回归「关闭页面再打开产物卡消失」）。
 *
 * 根因：messages 只按条数裁剪，长报告一轮就能超过 1MB，localStorage 写入
 * 静默失败后刷新只剩服务端纯文本历史；产物是前端投影，toolCalls 不在服务端，
 * 因而必须单独落一份小索引。
 */
import { beforeEach, describe, expect, it } from 'vitest'

import type { ChatMessage } from '@/domain/models/aiChat'
import type { StudioExportArtifact } from '@/domain/models/report-studio'

import { MAX_STORED_MESSAGES_BYTES, aiChatPrefs } from '../aiChatPrefs'

function makeMessage(key: string, content: string): ChatMessage {
  return {
    key,
    from: 'assistant',
    versions: [{ id: `${key}-v1`, content }],
    status: 'complete',
  }
}

function makeArtifact(exportId: string): StudioExportArtifact {
  return {
    exportId,
    docId: 'doc-1',
    reportId: 420,
    version: 1,
    format: 'pptx',
    theme: 'default',
    status: 'done',
    progress: 100,
    error: null,
    downloadRef: `/api/v1/report-studio/exports/${exportId}/download`,
  }
}

beforeEach(() => {
  window.localStorage.clear()
})

describe('aiChatPrefs 产物索引', () => {
  it('按 session id 存取，其他会话读不到', () => {
    aiChatPrefs.saveArtifacts('s-1', [makeArtifact('e-1')])

    expect(aiChatPrefs.loadArtifacts('s-1')).toEqual([makeArtifact('e-1')])
    expect(aiChatPrefs.loadArtifacts('s-2')).toEqual([])
    expect(aiChatPrefs.loadArtifacts(null)).toEqual([])
  })

  it('同一会话重复保存按传入顺序保留（去重由 store 负责）', () => {
    aiChatPrefs.saveArtifacts('s-1', [makeArtifact('e-1')])
    aiChatPrefs.saveArtifacts('s-1', [
      makeArtifact('e-1'),
      makeArtifact('e-2'),
    ])

    expect(aiChatPrefs.loadArtifacts('s-1').map((item) => item.exportId)).toEqual([
      'e-1',
      'e-2',
    ])
  })
})

describe('aiChatPrefs 消息字节预算', () => {
  it('总量超预算时保留最新消息，不因整份写失败丢失产物卡', () => {
    // 'x' 在 UTF-8 下 1 字节：两条各约 0.5MB，合计超过 1MB 预算
    const content = 'x'.repeat(MAX_STORED_MESSAGES_BYTES / 2)
    aiChatPrefs.saveMessages([
      makeMessage('old', content),
      makeMessage('new', content),
    ])

    const loaded = aiChatPrefs.loadMessages()
    expect(loaded).toHaveLength(1)
    expect(loaded?.[0]?.key).toBe('new')
  })

  it('未超预算时全部保留（消息与产物卡一起恢复）', () => {
    const artifact = makeArtifact('e-1')
    aiChatPrefs.saveMessages([
      {
        ...makeMessage('new', '短报告'),
        toolCalls: [
          {
            id: 'tc-1',
            tool: 'report_export',
            label: '导出报告',
            status: 'completed',
            exportArtifact: artifact,
          },
        ],
      },
    ])

    const loaded = aiChatPrefs.loadMessages()
    expect(loaded?.[0]?.toolCalls?.[0]?.exportArtifact?.exportId).toBe('e-1')
  })
})
