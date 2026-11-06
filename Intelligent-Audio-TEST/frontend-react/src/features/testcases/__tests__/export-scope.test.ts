/**
 * 「按当前筛选导出」范围解析（INT-1642 代码审计 P2 返工）。
 * 原实现 index.tsx 内联走 POST /testcases/ids：后端 fetch_case_ids 不认 favorite，
 * 「只看收藏」下导出的是全库（静默）。现收藏/未分组走列表端点逐页翻完，其余走 /ids。
 * 必测三条：收藏态、回收站态、未分组态。
 */
import { describe, expect, it, vi } from 'vitest'

import {
  buildExportListQuery,
  resolveExportIds,
  type ExportScopeDeps,
} from '@/features/testcases/lib/export-scope'
import { UNGROUPED_GROUP_ID } from '@/features/testcases/constants'
import type { TestCaseListItem } from '@/domain/models/testCase'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'

function makeDeps(over: Partial<ExportScopeDeps> = {}): ExportScopeDeps {
  return {
    fetchAllIds: vi.fn().mockResolvedValue(['tc-fav-1']),
    fetchIdsByFilter: vi.fn().mockResolvedValue(['tc-ids-1']),
    groups: [],
    loadedItems: [],
    ...over,
  }
}

const group = { id: 'g-1', name: '枪声组' } as TestCaseGroup
const caseRow = (id: string, groupId: string | null) =>
  ({ id, groupId }) as TestCaseListItem

describe('buildExportListQuery 筛选态 → 列表查询', () => {
  it('搜索词 trim；空串不下发（避免后端把空串当条件）', () => {
    expect(buildExportListQuery({ search: '  JS172  ' }).search).toBe('JS172')
    expect(buildExportListQuery({ search: '   ' }).search).toBeUndefined()
  })

  it('收藏 / 回收站 / 分组 / 标签 / 维度 / 算法原样映射', () => {
    expect(
      buildExportListQuery({
        favorite: true,
        groupId: UNGROUPED_GROUP_ID,
        tag: '枪声',
        dimensionId: 3,
        algorithmType: 'algo-x',
      })
    ).toMatchObject({
      favorite: true,
      groupId: UNGROUPED_GROUP_ID,
      tag: '枪声',
      dimensionId: 3,
      algorithmType: 'algo-x',
    })
  })
})

describe('resolveExportIds 收藏态（P2 返工核心）', () => {
  it('走列表端点逐页翻完，且查询带 favorite=true（不再走不认收藏的 /ids）', async () => {
    const deps = makeDeps({ fetchAllIds: vi.fn().mockResolvedValue(['tc-fav-1', 'tc-fav-2']) })

    const ids = await resolveExportIds({ favorite: true }, deps)

    expect(deps.fetchAllIds).toHaveBeenCalledTimes(1)
    expect(deps.fetchAllIds).toHaveBeenCalledWith(
      expect.objectContaining({ favorite: true })
    )
    expect(deps.fetchIdsByFilter).not.toHaveBeenCalled()
    expect(ids).toEqual(['tc-fav-1', 'tc-fav-2'])
  })

  it('收藏 + 其它筛选：搜索 / 标签 / 维度 / 算法一并交给列表端点', async () => {
    const deps = makeDeps()

    await resolveExportIds(
      {
        favorite: true,
        search: 'JS172',
        tag: '枪声',
        dimensionId: 2,
        algorithmType: 'algo-x',
      },
      deps
    )

    expect(deps.fetchAllIds).toHaveBeenCalledWith(
      expect.objectContaining({
        favorite: true,
        search: 'JS172',
        tag: '枪声',
        dimensionId: 2,
        algorithmType: 'algo-x',
      })
    )
  })
})

describe('resolveExportIds 回收站态', () => {
  it('仍走 POST /testcases/ids（only_deleted），不触发列表全量扫描', async () => {
    const deps = makeDeps({ fetchIdsByFilter: vi.fn().mockResolvedValue(['tc-trash-1']) })

    const ids = await resolveExportIds({ trash: true }, deps)

    expect(deps.fetchAllIds).not.toHaveBeenCalled()
    expect(deps.fetchIdsByFilter).toHaveBeenCalledWith(
      expect.objectContaining({ trash: true })
    )
    expect(ids).toEqual(['tc-trash-1'])
  })
})

describe('resolveExportIds 未分组态', () => {
  it('未分组哨兵走列表口径（不带 group_id 拉全量、按 groupId=null 过滤），不退化成已加载行', async () => {
    const deps = makeDeps({ fetchAllIds: vi.fn().mockResolvedValue(['tc-u-1']) })

    const ids = await resolveExportIds({ groupId: UNGROUPED_GROUP_ID }, deps)

    expect(deps.fetchAllIds).toHaveBeenCalledWith(
      expect.objectContaining({ groupId: UNGROUPED_GROUP_ID })
    )
    expect(deps.fetchIdsByFilter).not.toHaveBeenCalled()
    expect(ids).toEqual(['tc-u-1'])
  })
})

describe('resolveExportIds 其余筛选（/ids 契约：只认分组名）', () => {
  it('分组 id 映射为分组名后传给 /ids', async () => {
    const deps = makeDeps({ groups: [group] })

    await resolveExportIds({ groupId: 'g-1', search: ' JS172 ' }, deps)

    expect(deps.fetchAllIds).not.toHaveBeenCalled()
    expect(deps.fetchIdsByFilter).toHaveBeenCalledWith(
      expect.objectContaining({ group: '枪声组', search: 'JS172' })
    )
  })

  it('分组表未就绪：以已加载的该分组行兜底，不退化成全库', async () => {
    const deps = makeDeps({
      groups: [],
      loadedItems: [caseRow('tc-a', 'g-2'), caseRow('tc-b', null)],
    })

    const ids = await resolveExportIds({ groupId: 'g-2' }, deps)

    expect(ids).toEqual(['tc-a'])
    expect(deps.fetchIdsByFilter).not.toHaveBeenCalled()
    expect(deps.fetchAllIds).not.toHaveBeenCalled()
  })

  it('取数失败向上抛（由导出弹窗 toast 透出），不静默返回空集', async () => {
    const deps = makeDeps({
      fetchAllIds: vi.fn().mockRejectedValue(new Error('列表请求失败')),
    })
    await expect(resolveExportIds({ favorite: true }, deps)).rejects.toThrow(
      '列表请求失败'
    )
  })
})
