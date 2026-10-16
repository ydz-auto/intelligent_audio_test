/**
 * INT-500 代码审计返修回归：P2-1 数值排序 + P2-3 回收站 base 软删行覆盖。
 */
import { beforeEach, describe, expect, it } from 'vitest'

import { fetchReportList } from '@/infrastructure/api/reports-api'
import { useReportsUiStore } from '@/infrastructure/stores/reports-ui-store'

const resetStore = () =>
  useReportsUiStore.setState({
    favoriteIds: new Set(),
    unfavoritedIds: new Set(),
    deletedIds: new Set(),
    purgedIds: new Set(),
    restoredIds: new Set(),
  })

describe('INT-500 审计返修：报告列表排序与回收站覆盖', () => {
  beforeEach(resetStore)

  it('P2-1 total_cases 升序按数值排序（非字典序 0,120,384,48,54…）', async () => {
    const data = await fetchReportList({
      page: 1,
      per_page: 1000,
      sort_by: 'total_cases',
      order: 'asc',
      favorite: false,
      deleted: false,
    })
    const values = data.items.map((i) => i.summary.total_cases)
    expect(values).toEqual([...values].sort((a, b) => a - b))
    // 字典序错误反例：0 不应排在 120/384/48/54 之前
    expect(values.indexOf(0)).toBeLessThan(values.indexOf(48))
    expect(values.indexOf(48)).toBeLessThan(values.indexOf(120))
  })

  it('P2-1 pass_rate 降序首位为最大值', async () => {
    const data = await fetchReportList({
      page: 1,
      per_page: 1000,
      sort_by: 'pass_rate',
      order: 'desc',
      favorite: false,
      deleted: false,
    })
    const values = data.items.map((i) => i.summary.pass_rate)
    expect(Math.max(...values)).toBe(values[0])
  })

  it('P2-3 回收站展示 base 软删行（1180/1179）', async () => {
    const trash = await fetchReportList({
      page: 1,
      per_page: 1000,
      sort_by: 'created_at',
      order: 'desc',
      favorite: false,
      deleted: true,
    })
    const ids = trash.items.map((i) => i.id)
    expect(ids).toContain(1180)
    expect(ids).toContain(1179)
  })

  it('P2-3 restore 覆盖 mock 原值（1180 离开回收站、回到正常列表）', async () => {
    useReportsUiStore.getState().restore([1180])
    const trash = await fetchReportList({
      page: 1,
      per_page: 1000,
      sort_by: 'created_at',
      order: 'desc',
      favorite: false,
      deleted: true,
    })
    expect(trash.items.map((i) => i.id)).not.toContain(1180)
    const normal = await fetchReportList({
      page: 1,
      per_page: 1000,
      sort_by: 'created_at',
      order: 'desc',
      favorite: false,
      deleted: false,
    })
    expect(normal.items.map((i) => i.id)).toContain(1180)
  })

  it('P2-3 purge 后不再出现在回收站', async () => {
    useReportsUiStore.getState().purge([1180])
    const trash = await fetchReportList({
      page: 1,
      per_page: 1000,
      sort_by: 'created_at',
      order: 'desc',
      favorite: false,
      deleted: true,
    })
    expect(trash.items.map((i) => i.id)).not.toContain(1180)
  })
})
