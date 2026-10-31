/**
 * INT-2203 / INT-2213：映射大表的窗口化渲染（仅渲染视口附近的组头/行/组尾）。
 *
 * 背景（实测，docker 15173 + 真实库 1193 条评估映射 / 328 维度分组）：
 * 分组视图一次性渲染 1849 个 <tr>、5973 个 Select 触发器、整页 6.2 万 DOM 节点。
 * 静置时页面里仍有壳层常驻的 Web Animations（ai-discount-core，2.4~7s 无限循环），
 * 每一帧的样式/绘制代价随文档节点数放大——实测静置 16s 出现 12 条 0.8~1.0s 长任务、
 * 滚动每轮 22~40 条 1s 长任务；运行时把 tbody 行裁到 60 行后（6.2 万 → 3.4 千节点）
 * 同一页面静置长任务为 0。故把大表改成窗口渲染：DOM 只保留视口 ± overscan。
 *
 * INT-2213：映射视图抽成 mapping-view 公共件后，算法编辑 Sheet 与设备「参数配置」
 * 弹窗的四张分组表共用本模块（`useGroupVirtualWindow` 负责摊平组头/行/组尾）。
 *
 * 判据与降级：
 * - 找不到可滚动祖先（jsdom / 非 Sheet 宿主）或表格尚未布局（高度为 0）→ 关闭窗口化、
 *   全量渲染（单元测试与嵌套用法行为不变）。
 * - 行高由实际渲染的首个组头/数据行/组尾测得，测不到时用估算值；窗口按累计高度计算，
 *   上下用占位 <tr> 补足高度，滚动条总高度与分组顺序保持不变。
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

export type VirtualKind = 'row' | 'header' | 'add'

export type VirtualItem = {
  /** 稳定 key（前缀区分组头/行/组尾） */
  key: string
  kind: VirtualKind
}

export type VirtualWindowState = {
  start: number
  /** 不含 */
  end: number
  topPad: number
  bottomPad: number
  /** false = 未启用窗口化（全量渲染） */
  active: boolean
}

/** 摊平后的一维条目：组头 / 数据行 / 组尾「添加映射」 */
export type GroupVirtualItem<T> = {
  key: string
  kind: VirtualKind
  /** 所属分组的 key（折叠态、组头计数、组尾添加都按它回查） */
  groupKey: string
  /** kind='row' 时的数据行 */
  row?: T
}

/** 首帧测量前的高度估算（数据行 = 13px 字号 + py-1.5 + sm Select） */
const ESTIMATED_HEIGHT: Record<VirtualKind, number> = { row: 41, header: 34, add: 31 }
/** 视口外多渲染的像素带，抵消测量误差与快速滚动 */
const OVERSCAN_PX = 800

const FULL_WINDOW: VirtualWindowState = {
  start: 0,
  end: Number.MAX_SAFE_INTEGER,
  topPad: 0,
  bottomPad: 0,
  active: false,
}

/** 最近的纵向可滚动祖先（Sheet 的 form.overflow-y-auto / 弹窗的 DialogContent） */
function findScrollParent(el: HTMLElement | null): HTMLElement | null {
  let node = el?.parentElement ?? null
  while (node) {
    const overflowY = getComputedStyle(node).overflowY
    if ((overflowY === 'auto' || overflowY === 'scroll') && node.scrollHeight > node.clientHeight) {
      return node
    }
    node = node.parentElement
  }
  return null
}

export function useVirtualWindow(
  items: VirtualItem[],
  enabled: boolean
): {
  tbodyRef: React.RefObject<HTMLTableSectionElement | null>
  window: VirtualWindowState
  /** 是否已按真实布局测量过一次（首帧前不知道窗口范围，消费方据此推迟大表批量拉取） */
  measured: boolean
} {
  const tbodyRef = useRef<HTMLTableSectionElement | null>(null)
  const heightsRef = useRef<Record<VirtualKind, number>>({ ...ESTIMATED_HEIGHT })
  const [win, setWin] = useState<VirtualWindowState>(FULL_WINDOW)
  const [measured, setMeasured] = useState(false)
  /** 切到分组视图的那一帧窗口还没测量：先让消费方按「未测量」处理，避免立刻全量拉取 */
  const [prevEnabled, setPrevEnabled] = useState(enabled)
  if (prevEnabled !== enabled) {
    setPrevEnabled(enabled)
    if (enabled) setMeasured(false)
  }
  const itemsRef = useRef(items)
  itemsRef.current = items

  const recompute = useCallback(() => {
    const tbody = tbodyRef.current
    const list = itemsRef.current
    setMeasured(!enabled || Boolean(tbody))
    if (!enabled || !tbody) {
      setWin((prev) => (prev.active || prev.end !== list.length ? FULL_WINDOW : prev))
      return
    }
    // 用已渲染的代表行校准真实行高（组头/数据行/组尾各一个）
    for (const kind of ['header', 'row', 'add'] as const) {
      const tr = tbody.querySelector(`tr[data-vkind="${kind}"]`) as HTMLElement | null
      const h = tr?.offsetHeight ?? 0
      if (h > 0) heightsRef.current[kind] = h
    }
    const scroller = findScrollParent(tbody)
    const table = tbody.closest('table')
    const scrollerHeight = scroller?.clientHeight ?? 0
    if (!scroller || !table || scrollerHeight <= 0) {
      setWin((prev) => (prev.active ? FULL_WINDOW : prev))
      return
    }

    const scRect = scroller.getBoundingClientRect()
    const tableRect = table.getBoundingClientRect()
    // 表格顶在滚动内容坐标里的位置（每次读取 rect，表格上方内容高度变化也能跟上）
    const tableTopInContent = tableRect.top - scRect.top + scroller.scrollTop
    const viewTop = scroller.scrollTop - tableTopInContent
    const viewBottom = viewTop + scrollerHeight
    const heights = heightsRef.current

    let acc = 0
    let start = 0
    let end = list.length
    let foundEnd = false
    for (let i = 0; i < list.length; i++) {
      const h = heights[list[i].kind]
      // 累计顶边 acc 已在窗口上沿之上、且整行在 overscan 带外 → 跳过
      if (acc + h < viewTop - OVERSCAN_PX) {
        start = i + 1
      } else if (acc > viewBottom + OVERSCAN_PX) {
        end = i
        foundEnd = true
        break
      }
      acc += h
    }
    if (!foundEnd) end = list.length

    let topPad = 0
    for (let i = 0; i < start; i++) topPad += heights[list[i].kind]
    let bottomPad = 0
    for (let i = end; i < list.length; i++) bottomPad += heights[list[i].kind]

    setWin((prev) =>
      prev.active &&
      prev.start === start &&
      prev.end === end &&
      prev.topPad === topPad &&
      prev.bottomPad === bottomPad
        ? prev
        : { start, end, topPad, bottomPad, active: true }
    )
  }, [enabled])

  const recomputeRef = useRef(recompute)
  recomputeRef.current = recompute

  // 列表/折叠态变化时重算
  useEffect(() => {
    recomputeRef.current()
  }, [items, enabled])

  // 滚动 / 容器尺寸变化时重算（rAF 合帧）
  useEffect(() => {
    const tbody = tbodyRef.current
    if (!tbody) return
    const scroller = findScrollParent(tbody)
    if (!scroller) return
    let raf = 0
    const onScroll = () => {
      if (raf) return
      raf = requestAnimationFrame(() => {
        raf = 0
        recomputeRef.current()
      })
    }
    scroller.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(onScroll) : null
    ro?.observe(scroller)
    return () => {
      scroller.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      ro?.disconnect()
      if (raf) cancelAnimationFrame(raf)
    }
  }, [enabled])

  return { tbodyRef, window: win, measured }
}

/**
 * 分组视图窗口化（组头 / 数据行 / 组尾摊平后交给 `useVirtualWindow`）。
 *
 * @param groups    `[分组 key, 行[]]`（顺序即渲染顺序）
 * @param collapsed 已折叠的分组 key（折叠组只渲染组头）
 * @param enabled   是否启用（视图为分组态时为 true）
 * @param showAdd   组尾「添加映射」是否渲染（只读弹窗不渲染，避免占位高度漂移）
 */
export function useGroupVirtualWindow<T extends { key: string }>(
  groups: ReadonlyArray<readonly [string, T[]]>,
  collapsed: ReadonlySet<string>,
  enabled: boolean,
  showAdd = true
): {
  tbodyRef: React.RefObject<HTMLTableSectionElement | null>
  window: VirtualWindowState
  items: GroupVirtualItem<T>[]
  visibleItems: GroupVirtualItem<T>[]
  countByKey: Map<string, number>
  measured: boolean
} {
  const items = useMemo(() => {
    if (!enabled) return []
    const out: GroupVirtualItem<T>[] = []
    for (const [key, groupRows] of groups) {
      out.push({ kind: 'header', key: `h:${key}`, groupKey: key })
      if (collapsed.has(key)) continue
      for (const row of groupRows) {
        out.push({ kind: 'row', key: `r:${row.key}`, groupKey: key, row })
      }
      if (showAdd) out.push({ kind: 'add', key: `a:${key}`, groupKey: key })
    }
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, groups, collapsed, showAdd])

  const virtualItems = useMemo<VirtualItem[]>(
    () => items.map((item) => ({ key: item.key, kind: item.kind })),
    [items]
  )
  const { tbodyRef, window: virtualWindow, measured } = useVirtualWindow(
    virtualItems,
    enabled && items.length > 0
  )
  const visibleItems = virtualWindow.active
    ? items.slice(virtualWindow.start, Math.min(virtualWindow.end, items.length))
    : items
  const countByKey = useMemo(
    () => new Map(groups.map(([key, groupRows]) => [key, groupRows.length])),
    [groups]
  )

  return { tbodyRef, window: virtualWindow, items, visibleItems, countByKey, measured }
}
