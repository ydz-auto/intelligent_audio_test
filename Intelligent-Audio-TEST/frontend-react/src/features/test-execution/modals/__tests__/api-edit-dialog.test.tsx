/**
 * INT-1777：API 编辑弹窗五页签骨架 + meta / audio_config 写入口径（母卡 INT-1750 §3.1）。
 * 覆盖：页签齐全与默认落基础、未选算法占位空态、请求模板按设备类型显隐、
 * 非法 JSON 拦截保存、未触碰 meta 不发 meta、清除 audio_config 传 {}。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import type { ApiConfig } from '@/domain/models/apiConfig'

const { saveMock, fetchApiMock, algorithmOptions } = vi.hoisted(() => ({
  saveMock: vi.fn(async (_input: Record<string, unknown>) => undefined),
  fetchApiMock: vi.fn(async (_id: number): Promise<unknown> => null),
  algorithmOptions: { list: [] as Array<{ id: string; name: string }> },
}))

vi.mock('@/application/test-execution/useApisCrud', () => ({
  useApisCrud: () => ({ save: saveMock }),
}))

vi.mock('@/infrastructure/api/test-execution-api', () => ({
  fetchApi: fetchApiMock,
}))

vi.mock('@/application/test-execution/useTestAlgorithmOptions', () => ({
  useTestAlgorithmOptions: () => ({ data: algorithmOptions.list }),
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

/** 可开合的宿主：复测 P2-1「取消 / 关闭后重开不残留上次输入」 */
function renderReopenable(api?: ApiConfig) {
  fetchApiMock.mockResolvedValue(null)
  function Harness() {
    const [open, setOpen] = useState(true)
    return (
      <>
        <button type='button' onClick={() => setOpen(true)}>
          重新打开
        </button>
        <ApiEditDialog open={open} onOpenChange={setOpen} api={api} />
      </>
    )
  }
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>
  )
}

function cancelAndReopen() {
  fireEvent.click(screen.getByRole('button', { name: '取消' }))
  fireEvent.click(screen.getByRole('button', { name: '重新打开' }))
}

beforeEach(() => {
  saveMock.mockClear()
  fetchApiMock.mockClear()
  algorithmOptions.list = []
})

describe('五页签骨架（INT-1777）', () => {
  it('五个页签齐全，默认落基础页签', () => {
    renderDialog(API_FIXTURE)
    const tabs = screen.getAllByRole('tab').map((tab) => tab.textContent)
    expect(tabs).toEqual(['基础', '请求模板', '响应解析', '输出字段', '映射'])
    expect(screen.getByRole('tab', { name: '基础' }).getAttribute('aria-selected')).toBe('true')
    expect(screen.getByLabelText('API 名称 *')).toHaveValue('接线测试_API')
  })

  it('未选算法时两个只读页签显示占位空态（响应解析是写 meta 的页签，仍可填）', () => {
    renderDialog(undefined)
    fireEvent.click(screen.getByRole('tab', { name: '响应解析' }))
    expect(screen.queryByText('未选择关联算法')).not.toBeInTheDocument()
    expect(screen.getByLabelText('响应解析器（result_parser）')).toBeInTheDocument()
    expect(screen.getByText('未选择关联算法，无法判定')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('tab', { name: '输出字段' }))
    expect(screen.getAllByText('未选择关联算法').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByRole('tab', { name: '映射' }))
    expect(screen.getAllByText('未选择关联算法').length).toBeGreaterThan(1)
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

describe('关联算法存类型码（INT-1778 修：原实现存的是显示名）', () => {
  it('下拉显示算法名称，提交的 algorithmType 是算法类型码', async () => {
    const user = userEvent.setup()
    algorithmOptions.list = [{ id: 'voice_llm', name: '小艺语音大模型' }]
    renderDialog(undefined)
    fireEvent.change(screen.getByLabelText('API 名称 *'), { target: { value: '接线测试_算法码' } })
    // 打开关联算法下拉，选唯一选项（显示名 = 小艺语音大模型）
    await user.click(screen.getAllByRole('combobox')[0])
    await user.click(await screen.findByRole('option', { name: '小艺语音大模型' }))
    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1))
    const payload = saveMock.mock.calls[0][0] as { algorithmType?: string }
    expect(payload.algorithmType).toBe('voice_llm')
  })

  // 返工 P2-1：base-ui Select 收起态靠 items 取 label，漏传会直接回显类型码
  it('收起态显示算法名：编辑态回填不出现类型码', () => {
    algorithmOptions.list = [{ id: 'voice_llm', name: '小艺语音大模型' }]
    renderDialog(API_FIXTURE)
    const editTrigger = screen.getAllByRole('combobox')[0]
    expect(editTrigger).toHaveTextContent('小艺语音大模型')
    expect(editTrigger).not.toHaveTextContent('voice_llm')
  })

  it('收起态显示算法名：新增态刚选中就显示名称', async () => {
    const user = userEvent.setup()
    algorithmOptions.list = [{ id: 'voice_llm', name: '小艺语音大模型' }]
    renderDialog(undefined)
    const trigger = screen.getAllByRole('combobox')[0]
    await user.click(trigger)
    await user.click(await screen.findByRole('option', { name: '小艺语音大模型' }))
    expect(trigger).toHaveTextContent('小艺语音大模型')
    expect(trigger).not.toHaveTextContent('voice_llm')
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

describe('取消 / 关闭后重开不残留（INT-1777 复测 P2-1）', () => {
  it('编辑态：改名称后取消 → 重开回填已保存值，直接保存不会写入被取消的输入', async () => {
    renderReopenable(API_FIXTURE)
    fireEvent.change(screen.getByLabelText('API 名称 *'), {
      target: { value: '不该保存的名字' },
    })
    cancelAndReopen()
    expect(screen.getByLabelText('API 名称 *')).toHaveValue('接线测试_API')

    fireEvent.click(screen.getByRole('button', { name: '保存' }))
    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1))
    expect(saveMock.mock.calls[0][0].name).toBe('接线测试_API')
  })

  it('新增态：改名称 / 最大并发后取消 → 重开为空值', () => {
    renderReopenable(undefined)
    fireEvent.change(screen.getByLabelText('API 名称 *'), {
      target: { value: '不该保存的名字' },
    })
    fireEvent.change(screen.getByLabelText('最大并发'), { target: { value: '42' } })
    cancelAndReopen()
    expect(screen.getByLabelText('API 名称 *')).toHaveValue('')
    expect(screen.getByLabelText('最大并发')).toHaveValue(5)
  })

  it('取消后重开，页签仍落基础页签', () => {
    renderReopenable(API_FIXTURE)
    openRequestTab()
    cancelAndReopen()
    expect(screen.getByRole('tab', { name: '基础' }).getAttribute('aria-selected')).toBe('true')
  })
})
