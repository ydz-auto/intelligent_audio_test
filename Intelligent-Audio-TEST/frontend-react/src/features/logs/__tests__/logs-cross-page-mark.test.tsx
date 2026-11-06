/**
 * 跨页勾选时批量标记入口按「已选集合」判定（INT-1945 返工）。
 * 回归：`markableSelectedCount` 曾由当前页 `rows` 推导，翻到全文件日志的一页后，
 * 已选中的历史库行不在 `rows` 里 → 计数变 0 → 浮条误报「所选为文件日志，不支持标记」
 * 并藏掉「标记颜色」入口，用户无法继续标记仍可标记的行。
 * 可标记性只由 id 决定（文件游标行 id ≥ 10^12 只读），与所在页无关。
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import type { LogItem, LogQuery } from '@/domain/models/log'
import { LogsPage } from '@/features/logs/index'

/** 夹具须在 vi.mock 工厂执行前就绪（工厂会被提升），故用 vi.hoisted */
const fixture = vi.hoisted(() => {
  const makeLog = (id: number, content: string) => ({
    id,
    time: '2026-10-25 10:00:00.000000',
    level: 'INFO',
    category: 'test',
    module: 'task',
    source: 'api_gateway',
    content,
    mark: null,
    deviceId: null,
    taskId: null,
    apiId: null,
    testCaseId: null,
    threadId: null,
    algorithmType: null,
  })
  // 历史 logs 表行（< 10^12，可标记）
  const legacyId = 6950062
  // 审计文件游标行（≥ 10^12，后端只读，PUT /logs/mark 恒 updated=0）
  const fileIds = [1792961330651870, 1792961330651871]
  return {
    legacyId,
    fileIds,
    page1: [makeLog(legacyId, '历史库日志-可标记')],
    page2: fileIds.map((id) => makeLog(id, `文件日志-${id}`)),
  }
})

vi.mock('@tanstack/react-router', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>()
  return {
    ...actual,
    // 页面仅用 Link 渲染「查看归档」入口，测试不需真实路由上下文
    Link: (props: { children?: React.ReactNode }) => <a href='#'>{props.children}</a>,
  }
})

vi.mock('@/application/hooks/use-permissions', () => ({
  usePermissions: () => ({
    user: { id: 1 },
    hasPermission: () => true,
    hasAnyPermission: () => true,
  }),
}))

vi.mock('@/application/hooks/use-global-algorithm', () => ({
  useGlobalAlgorithm: () => ({ algorithmId: null, setAlgorithmId: vi.fn() }),
}))

vi.mock('@/application/hooks/use-algorithm-options', () => ({
  useAlgorithmOptions: () => ({ options: [], isLoading: false, isError: false }),
}))

vi.mock('@/application/logs/useLogList', () => ({
  // 第 1 页 1 条历史库行；第 2 页 2 条文件日志（复现「翻页后 rows 不含已选行」）
  useLogListQuery: (query: LogQuery) => {
    const items = query.page === 1 ? fixture.page1 : fixture.page2
    return {
      data: { items, total: 40, page: query.page, perPage: 20, pages: 2 },
      isLoading: false,
      isError: false,
      isFetching: false,
      refetch: vi.fn(),
    }
  },
  useLogStatsQuery: () => ({ data: undefined, isLoading: true }),
}))

vi.mock('@/application/logs/useLogRealtime', () => ({
  useLogRealtime: () => ({
    enabled: false,
    setEnabled: vi.fn(),
    connection: 'idle',
    logRate: 0,
    logDelay: 0,
    config: { pollIntervalMs: 5000, autoScroll: true, notifyNewLogs: true },
    setConfig: vi.fn(),
    newLogs: [] as LogItem[],
    resetNewLogs: vi.fn(),
  }),
}))

vi.mock('@/application/logs/useLogMutations', async (importOriginal) => {
  const actual =
    await importOriginal<typeof import('@/application/logs/useLogMutations')>()
  return {
    ...actual,
    useLogMutations: () => ({
      mark: { mutate: vi.fn(), isPending: false },
      clear: { mutate: vi.fn(), isPending: false },
      exportLogs: { mutate: vi.fn(), isPending: false },
    }),
  }
})

describe('日志跨页勾选的批量标记入口（INT-1945）', () => {
  it('第 1 页选历史库行、翻到全文件日志页后仍给「标记颜色」', async () => {
    const user = userEvent.setup()
    render(<LogsPage />)

    expect(await screen.findByText('历史库日志-可标记')).not.toBeNull()
    await user.click(
      screen.getByRole('checkbox', { name: `选择日志 ${fixture.legacyId}` })
    )

    expect(screen.getByText('已选择 1 条日志')).not.toBeNull()
    expect(screen.getByRole('button', { name: '标记颜色' })).not.toBeNull()

    // 翻到第 2 页：界面上已无历史库行，但选择里仍有可标记行
    await user.click(screen.getByRole('button', { name: '下一页' }))
    expect(await screen.findByText(`文件日志-${fixture.fileIds[0]}`)).not.toBeNull()

    expect(screen.getByText('已选择 1 条日志')).not.toBeNull()
    expect(screen.queryByText('所选为文件日志，不支持标记')).toBeNull()
    expect(screen.getByRole('button', { name: '标记颜色' })).not.toBeNull()
  })

  it('只选文件日志时不给入口、给不可标记说明（原修复不回归）', async () => {
    const user = userEvent.setup()
    render(<LogsPage />)

    await screen.findByText('历史库日志-可标记')
    await user.click(screen.getByRole('button', { name: '下一页' }))
    await screen.findByText(`文件日志-${fixture.fileIds[0]}`)

    await user.click(
      screen.getByRole('checkbox', { name: `选择日志 ${fixture.fileIds[0]}` })
    )

    expect(screen.getByText('已选择 1 条日志')).not.toBeNull()
    expect(screen.getByText('所选为文件日志，不支持标记')).not.toBeNull()
    expect(screen.queryByRole('button', { name: '标记颜色' })).toBeNull()
  })
})
