/**
 * 上传流程单测（INT-1979）：
 * - register 请求带 relative_path（文件夹导入 = 含子目录相对路径，单文件 = 文件名）；
 * - merge 载荷 tags 按「标签来源」组装：手填标签任何档位都保留，JSON 顶层 tags 仅
 *   「仅路径解析」档不并入；tag_source 逐档透传。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { runAudioUpload } from '@/application/audio/useAudioUploadProcess'
import type {
  AudioTagSource,
  UploadTestCaseConfig,
} from '@/infrastructure/api/audio-upload-api'

const postMock = vi.hoisted(() => vi.fn())

vi.mock('@/infrastructure/api/client', () => ({
  apiClient: { post: postMock },
}))

function makeFile(name: string, relativePath: string): File {
  const file = new File([new Uint8Array([1, 2, 3])], name, {
    type: 'application/octet-stream',
  })
  Object.defineProperty(file, 'webkitRelativePath', { value: relativePath })
  return file
}

function baseConfig(overrides: Partial<UploadTestCaseConfig> = {}): UploadTestCaseConfig {
  return {
    createTestCase: true,
    algorithmType: 'voice_llm',
    algorithmParams: [],
    dimensions: [],
    playbackDeviceId: null,
    spl: 65,
    noiseAudioId: null,
    noiseSpl: 60,
    inheritTags: true,
    groupName: undefined,
    tags: ['手填A'],
    tagSource: 'both',
    audioType: 'dry',
    ...overrides,
  }
}

/** 按 URL 分发真实上传四步的响应（分片一次传完） */
function mockUploadChain() {
  postMock.mockImplementation((url: string) => {
    if (url === '/audios/upload/init') return Promise.resolve({ task_id: 'task-1' })
    if (url === '/audios/upload/register') {
      return Promise.resolve({
        files: [{ file_id: 'file-1', total_chunks: 1, chunk_size: 5 * 1024 * 1024 }],
      })
    }
    if (url === '/audios/upload/chunk') return Promise.resolve({})
    if (url === '/audios/upload/merge') {
      return Promise.resolve({ audio_id: 11, name: 'a.wav', test_case_id: null, test_case_count: 0 })
    }
    throw new Error(`未预期的请求：${url}`)
  })
}

function callOf(url: string): Record<string, unknown> | undefined {
  const hit = postMock.mock.calls.find((call) => call[0] === url)
  return hit?.[1] as Record<string, unknown> | undefined
}

async function uploadOne(
  tagSource: AudioTagSource,
  perFileTags: string[] | undefined,
  relativePath = '根/组1/子目录/a.wav'
) {
  mockUploadChain()
  const file = makeFile('a.wav', relativePath)
  const result = await runAudioUpload([file], baseConfig({ tagSource }), undefined, [
    { rounds: [{ round_number: 1, audios: [{ audio_name: 'a.wav', play_order: 1 }] }], tags: perFileTags },
  ])
  expect(result.failedCount).toBe(0)
  return callOf('/audios/upload/merge') as Record<string, unknown>
}

describe('runAudioUpload（INT-1979 标签来源与 relative_path）', () => {
  beforeEach(() => {
    postMock.mockReset()
  })

  it('register 请求带 relative_path（含子目录的相对路径）', async () => {
    mockUploadChain()
    await runAudioUpload([makeFile('a.wav', '根/组1/子目录/a.wav')], baseConfig())
    const register = callOf('/audios/upload/register') as {
      files: Array<Record<string, unknown>>
    }
    expect(register.files[0]).toMatchObject({
      name: 'a.wav',
      relative_path: '根/组1/子目录/a.wav',
    })
  })

  it('单文件无目录结构时 relative_path = 文件名', async () => {
    mockUploadChain()
    await runAudioUpload([makeFile('b.wav', '')], baseConfig())
    const register = callOf('/audios/upload/register') as {
      files: Array<Record<string, unknown>>
    }
    expect(register.files[0].relative_path).toBe('b.wav')
  })

  it('both（默认）：tags = 手填 ∪ 分组 JSON tags，tag_source=both', async () => {
    const payload = await uploadOne('both', ['JSON标签'])
    expect(payload.tags).toEqual(['手填A', 'JSON标签'])
    expect(payload.tag_source).toBe('both')
  })

  it('json：tags = 手填 ∪ 分组 JSON tags，tag_source=json', async () => {
    const payload = await uploadOne('json', ['JSON标签'])
    expect(payload.tags).toEqual(['手填A', 'JSON标签'])
    expect(payload.tag_source).toBe('json')
  })

  it('path：tags 只含手填标签（不并入 JSON tags），tag_source=path', async () => {
    const payload = await uploadOne('path', ['JSON标签'])
    expect(payload.tags).toEqual(['手填A'])
    expect(payload.tag_source).toBe('path')
  })

  it('无分组 JSON tags 时三档都保留手填标签', async () => {
    for (const source of ['both', 'json', 'path'] as const) {
      postMock.mockReset()
      const payload = await uploadOne(source, undefined)
      expect(payload.tags).toEqual(['手填A'])
      expect(payload.tag_source).toBe(source)
    }
  })

  it('手填为空 + 无 JSON tags → 请求 tags 为空数组（不静默报错）', async () => {
    mockUploadChain()
    const file = makeFile('a.wav', '根/组1/a.wav')
    const result = await runAudioUpload([file], baseConfig({ tags: [], tagSource: 'json' }))
    expect(result.failedCount).toBe(0)
    expect((callOf('/audios/upload/merge') as { tags: string[] }).tags).toEqual([])
  })
})
