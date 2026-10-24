/**
 * INT-1777：API 编辑弹窗五页签骨架 + meta / audio_config 写入口径（母卡 INT-1750 §3.1）。
 * 覆盖：页签齐全与默认落基础、未选算法占位空态、请求模板按设备类型显隐、
 * 非法 JSON 拦截保存、未触碰 meta 不发 meta、清除 audio_config 传 {}。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ApiConfig } from '@/domain/models/apiConfig'

const { saveMock, fetchApiMock } = vi.hoisted(() => ({
  saveMock: vi.fn(async (_input: Record<string, unknown>) => undefined),
  fetchApiMock: vi.fn(async (_id: number): Promise<unknown> => null),
}))

vi.mock('@/application/test-execution/useApisCrud', () => ({
  useApisCrud: () => ({ save: saveMock }),
}))

vi.mock('@/infrastructure/api/test-execution-api', () => ({
  fetchApi: fetchApiMock,
}))

vi.mock('@/application/test-execution/useTestAlgorithmOptions', () => ({
  useTestAlgorithmOptions: () => ({ data: [] }),
}))

import { ApiEditDialog } from '../api-edit-dialog'

const API_FIXTURE: ApiConfig = {
  id: 11,
  name: '接线测试_API',
  vendor: null,
  description: null,
  status: 'online',
  algorithmType: 'voice_llm',
  defaultMaxProcess: 5,
  defaultMaxTimeout: 30,
  defaultMaxAudioDuration: 60,
  healthScore: 100,
  endpoints: [
    {
      id: 'ep-1',
      endpoint: 'https://api.example.com/v1/asr',
      name: null,
      maxProcess: 5,
      maxTimeout: 30,
      maxAudioDuration: 60,
      priority: 1,
      status: 'online',
      healthScore: 100,
      description: null,
      apiKeysSummary: null,
    },
  ],
  maxConcurrent: 5,
  deviceType: 'http_api',
  meta: { protocol: 'https', environment: 'production', appendix_test: 1 },
  audioConfig: { sample_rate: 16000, bit_depth: 's16', channels: 1, container: 'pcm' },
}

function renderDialog(api?: ApiConfig, fresh?: ApiConfig) {
  fetchApiMock.mockResolvedValue(fresh ?? null)
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <ApiEditDialog open onOpenChange={vi.fn()} api={api} />
    </QueryClientProvider>
  )
}

function openRequestTab() {
  fireEvent.click(screen.getByRole('tab', { name: '请求模板' }))
}

beforeEach(() => {
  saveMock.mockClear()
  fetchApiMock.mockClear()
})

describe('五页签骨架（INT-1777）', () => {
  it('五个页签齐全，默认落基础页签', () => {
    renderDialog(API_FIXTURE)
    const tabs = screen.getAllByRole('tab').map((tab) => tab.textContent)
    expect(tabs).toEqual(['基础', '请求模板', '响应解析', '输出字段', '映射'])
    expect(screen.getByRole('tab', { name: '基础' }).getAttribute('aria-selected')).toBe('true')
    expect(screen.getByLabelText('API 名称 *')).toHaveValue('接线测试_API')
  })

  it('未选算法时后三个页签显示占位空态', () => {
    renderDialog(undefined)
    fireEvent.click(screen.getByRole('tab', { name: '响应解析' }))
    expect(screen.getAllByText('未选择关联算法').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('tab', { name: '输出字段' }))
    expect(screen.getAllByText('未选择关联算法').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('tab', { name: '映射' }))
    expect(screen.getAllByText('未选择关联算法').length).toBeGreaterThan(0)
  })

  it('请求模板按目标设备类型显隐：http_api 只显示 method/headers/body_template', () => {
    renderDialog(API_FIXTURE)
    openRequestTab()
    expect(screen.getByText('请求方法（method）')).toBeInTheDocument()
    expect(screen.getByLabelText('请求体模板（body_template）')).toBeInTheDocument()
    expect(screen.queryByLabelText('会话配置（session_config）')).not.toBeInTheDocument()
  })

  it('请求模板按目标设备类型显隐：websocket_api 只显示 ws_headers/session_config/pacing', () => {
    renderDialog({ ...API_FIXTURE, deviceType: 'websocket_api' })
    openRequestTab()
    expect(screen.getByLabelText('会话配置（session_config）')).toBeInTheDocument()
    expect(screen.getByLabelText('节奏控制（pacing）')).toBeInTheDocument()
    expect(screen.queryByLabelText('请求体模板（body_template）')).not.toBeInTheDocument()
  })
})

describe('meta / audio_config 保存口径（INT-1777）', () => {
  it('非法 JSON 拦截保存，弹窗不关、保存请求不发出', async () => {
    renderDialog(API_FIXTURE)
    openRequestTab()
    fireEvent.change(screen.getByLabelText('请求体模板（body_template）'), {
      target: { value: '{bad json' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    expect(await screen.findByText('请求体模板 JSON 格式不正确')).toBeInTheDocument()
    expect(saveMock).not.toHaveBeenCalled()
  })

  it('只改基础字段保存 → 请求体不带 meta / audio_config（未触碰不发）', async () => {
    renderDialog(API_FIXTURE)
    fireEvent.change(screen.getByLabelText('API 名称 *'), {
      target: { value: '接线测试_API_改名' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1))
    const payload = saveMock.mock.calls[0][0]
    expect(payload.name).toBe('接线测试_API_改名')
    expect('meta' in payload).toBe(false)
    expect('audioConfig' in payload).toBe(false)
  })

  it('改 meta 字段保存 → 提交 base 合并后的整对象（未知键保留）', async () => {
    renderDialog(API_FIXTURE)
    openRequestTab()
    fireEvent.change(screen.getByLabelText('请求体模板（body_template）'), {
      target: { value: '{"text":"{{text}}"}' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1))
    const payload = saveMock.mock.calls[0][0]
    expect(payload.meta).toEqual({
      protocol: 'https',
      environment: 'production',
      appendix_test: 1,
      body_template: { text: '{{text}}' },
    })
    // audio_config 未触碰 → 不下发
    expect('audioConfig' in payload).toBe(false)
  })

  it('以打开时拉取的最新 meta 为合并 base（列表快照旧也不丢未知键）', async () => {
    const fresh: ApiConfig = {
      ...API_FIXTURE,
      meta: { ...API_FIXTURE.meta, appendix_test: 1, vendor_adapter: 'FreshAdapter' },
    }
    renderDialog(API_FIXTURE, fresh)
    await waitFor(() => expect(fetchApiMock).toHaveBeenCalledWith(API_FIXTURE.id))
    openRequestTab()
    await screen.findByDisplayValue('FreshAdapter')
    fireEvent.change(screen.getByLabelText('请求体模板（body_template）'), {
      target: { value: '{"text":"{{text}}"}' },
    })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1))
    const payload = saveMock.mock.calls[0][0]
    expect(payload.meta).toEqual({
      protocol: 'https',
      environment: 'production',
      appendix_test: 1,
      vendor_adapter: 'FreshAdapter',
      body_template: { text: '{{text}}' },
    })
  })

  it('仅「清除音频格式」→ audio_config 传 {}（顶层列清空）', async () => {
    renderDialog(API_FIXTURE)
    fireEvent.click(screen.getByRole('button', { name: '清除音频格式' }))
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1))
    const payload = saveMock.mock.calls[0][0]
    expect(payload.audioConfig).toEqual({})
    expect('meta' in payload).toBe(false)
  })

  it('编辑态回填 meta 请求模板（body_template 对象 → 结构化 JSON 文本）', () => {
    renderDialog({
      ...API_FIXTURE,
      meta: { ...API_FIXTURE.meta, method: 'POST', body_template: { text: '{{text}}' } },
    })
    openRequestTab()
    const body = screen.getByLabelText('请求体模板（body_template）') as HTMLTextAreaElement
    expect(JSON.parse(body.value)).toEqual({ text: '{{text}}' })
    const dialog = screen.getByRole('dialog')
    expect(within(dialog).getByText('HTTP API（http_api）')).toBeInTheDocument()
  })
})
