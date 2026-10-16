/**
 * 音频管理 API 桩（infrastructure 层；16_设备域.md §10 组件树落位）。
 * 红线④：全部返回 mock 常量（audio-mock），接线时替换为真实请求：
 *   GET    /api/v1/audios                          列表（含 data.stats）+ 分页/facet/跨页 ids
 *   GET    /api/v1/audios/tags                     标签列表（facet 选项）
 *   POST   /api/v1/audios/folder-tree              文件夹树（depth 1/10 增量）
 *   GET    /api/v1/audios/{id}                     详情（下载二次取流）
 *   DELETE /api/v1/audios/{id}                     删除（引用四路拦截）
 *   PUT    /api/v1/audios/{id}                     编辑元数据（§6.13）
 *   POST   /api/v1/audios/{id}/convert             格式转换（§6.15）
 *   POST   /api/v1/audios/url-import               URL 导入（§6.18）
 *   POST   /api/v1/audios/batch-action             批量 action（§5.6）
 *   POST   /api/v1/audios/batch/annotations        批量更新标注（§6.19）
 */
import type {
  AudioAsset,
  AudioFolderNode,
  AudioListStats,
} from '@/domain/models/audio'
import {
  MOCK_AUDIOS,
  MOCK_AUDIO_STATS,
  MOCK_AUDIO_TAGS,
  MOCK_FOLDER_TREE,
} from '../mock/audio-mock'

/** 模拟网络延迟（视觉稿演示用；接线后删除） */
function mockLatency<T>(value: T, ms = 180): Promise<T> {
  return new Promise((resolve) => setTimeout(() => resolve(value), ms))
}

/** mock 内存库（页面内增删改操作在运行时可变） */
let audiosStore: AudioAsset[] = [...MOCK_AUDIOS]

/** 新 id（mock 阶段自增；接线后走后端自增） */
let nextAudioId = 1000
function freshId(): number {
  nextAudioId += 1
  return nextAudioId
}

/** 当前 mock 内存库（供 feature 内读取；接线后删除） */
export function peekAudios(): AudioAsset[] {
  return audiosStore
}

export type AudioListResult = {
  items: AudioAsset[]
  stats: AudioListStats
}

/** 音频列表（§5.3；GET /audios，响应含 data.stats） */
export async function fetchAudios(): Promise<AudioListResult> {
  // TODO(API 接线): GET /api/v1/audios
  return mockLatency({ items: audiosStore, stats: MOCK_AUDIO_STATS })
}

/** 标签列表（§5.3.2 标签 facet 选项；GET /audios/tags） */
export async function fetchAudioTags(): Promise<string[]> {
  // TODO(API 接线): GET /api/v1/audios/tags
  return mockLatency(MOCK_AUDIO_TAGS)
}

/** 文件夹树（§5.5；POST /audios/folder-tree，depth 1 根节点） */
export async function fetchFolderTree(): Promise<AudioFolderNode[]> {
  // TODO(API 接线): POST /api/v1/audios/folder-tree
  return mockLatency(MOCK_FOLDER_TREE)
}

/** 删除音频（§5.3.1；DELETE /audios/{id}，引用四路拦截文案见 §9） */
export async function deleteAudio(
  id: number
): Promise<{ success: boolean; message?: string }> {
  // TODO(API 接线): DELETE /api/v1/audios/{id}
  const target = audiosStore.find((a) => a.id === id)
  if (!target) return mockLatency({ success: false, message: '音频不存在' }, 80)
  audiosStore = audiosStore.filter((a) => a.id !== id)
  return mockLatency({ success: true }, 120)
}

/** 编辑元数据（§6.13；PUT /audios/{id}） */
export async function updateAudioMetadata(
  id: number,
  patch: Partial<AudioAsset>
): Promise<AudioAsset | undefined> {
  // TODO(API 接线): PUT /api/v1/audios/{id}
  const target = audiosStore.find((a) => a.id === id)
  if (!target) return mockLatency(undefined, 80)
  const updated: AudioAsset = {
    ...target,
    ...patch,
    updatedAt: new Date().toISOString(),
  }
  audiosStore = audiosStore.map((a) => (a.id === id ? updated : a))
  return mockLatency(updated, 120)
}

/** 格式转换（§6.15；POST /audios/{id}/convert{format}） */
export async function convertAudio(
  _id: number,
  format: string
): Promise<{ success: boolean; message?: string }> {
  // TODO(API 接线): POST /api/v1/audios/{id}/convert
  return mockLatency({ success: true, message: `已提交转换为 ${format}` }, 200)
}

/** URL 导入（§6.18；POST /audios/url-import） */
export async function urlImportAudios(
  urls: string[]
): Promise<{ successCount: number; failedCount: number }> {
  // TODO(API 接线): POST /api/v1/audios/url-import
  let successCount = 0
  let failedCount = 0
  for (const url of urls) {
    if (!/^https?:\/\//i.test(url)) {
      failedCount += 1
      continue
    }
    const name = url.split('/').filter(Boolean).pop() ?? 'url-audio'
    audiosStore = [
      {
        id: freshId(),
        name,
        originalFilename: name,
        filePath: url,
        duration: null,
        size: null,
        sampleRate: null,
        channels: null,
        bitrate: null,
        format: null,
        audioType: 'dry',
        asrText: null,
        description: null,
        sourceLanguage: null,
        tags: [],
        annotations: [],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      },
      ...audiosStore,
    ]
    successCount += 1
  }
  return mockLatency({ successCount, failedCount }, 200)
}

/** 批量更新标注（§6.19；POST /audios/batch/annotations） */
export async function batchUpdateAnnotations(): Promise<{
  success: number
  failed: number
  refreshed: number
}> {
  // TODO(API 接线): POST /api/v1/audios/batch/annotations
  return mockLatency({ success: 4, failed: 1, refreshed: 3 }, 220)
}

/** 批量 action（§5.6；POST /audios/batch-action） */
export type AudioBatchAction =
  | 'delete'
  | 'export'
  | 'tags'
  | 'move'
  | 'copy'
  | 'rename'
  | 'modify-properties'

export async function batchActionAudios(
  _action: AudioBatchAction,
  ids: number[]
): Promise<{ action: AudioBatchAction; total: number; successCount: number }> {
  // TODO(API 接线): POST /api/v1/audios/batch-action
  if (_action === 'delete') {
    audiosStore = audiosStore.filter((a) => !ids.includes(a.id))
  }
  return mockLatency(
    { action: _action, total: ids.length, successCount: ids.length },
    160
  )
}

/** 供测试清理内存库（vitest 用例内独立初始化） */
export function __resetAudioMock(): void {
  audiosStore = [...MOCK_AUDIOS]
  nextAudioId = 1000
}
