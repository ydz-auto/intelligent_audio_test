/**
 * 用例编辑音频列表批量工具纯函数（domain/lib 层，11_用例域.md §5.1 音频列表工具栏）。
 * 四件排序/映射派生逻辑：
 * - interleaveByTags：标签交错——按所选标签顺序分段，命中该标签的音频入段（多标签音频每段各现一次，对齐 §3.6 多标签语义）；
 * - assignRoundRobin：设备交叉——按列表顺序将所选设备轮转分配；
 * - patchByTag：标签设备——命中指定标签的条目应用补丁；
 * - patchScope：批量设备/批量声压——按「全部/勾选」范围应用补丁。
 * 均为不可变纯函数，可单测；mock 态纯前端派生，不接后端。
 */

/** 批量应用范围（批量设备/批量声压的「全部音频/勾选音频」） */
export type BatchScope = 'all' | 'selected'

/**
 * 标签交错：按所选标签顺序分段输出。
 * 每个标签一段，命中该标签的条目按原列表顺序入段（同一多标签条目在每个命中段各现一次）；
 * 未命中任何所选标签的条目按原列表顺序追加到末尾（排序不改丢数据）。
 * tags 为空时返回原列表副本（不改序）。
 * clone 传入时为每段出现克隆新行身份（保留内容、分配新 id），保证多标签条目各段出现互不耦合
 * （界面可独立勾选/编辑/删除且 React key 不重复）；缺省时按原引用返回（纯排序视图）。
 */
export function interleaveByTags<T>(
  items: readonly T[],
  tagsOf: (item: T) => readonly string[],
  tags: readonly string[],
  clone?: (item: T) => T
): T[] {
  if (tags.length === 0) return [...items]
  const matched = new Set<number>()
  const out: T[] = []
  const emit = clone ?? ((item: T) => item)
  for (const tag of tags) {
    for (let i = 0; i < items.length; i++) {
      const item = items[i]
      if (tagsOf(item).includes(tag)) {
        out.push(emit(item))
        matched.add(i)
      }
    }
  }
  for (let i = 0; i < items.length; i++) {
    if (!matched.has(i)) out.push(items[i])
  }
  return out
}

/**
 * 设备交叉：按列表顺序将 values 轮转分配到每个条目（第 i 条取 values[i % values.length]）。
 * values 为空时返回原列表副本（不改条目）。
 */
export function assignRoundRobin<T>(
  items: readonly T[],
  values: readonly string[],
  patch: (item: T, value: string) => T
): T[] {
  if (values.length === 0) return [...items]
  return items.map((item, i) => patch(item, values[i % values.length]))
}

/**
 * 标签设备：命中指定标签的条目应用补丁（批量设置播放设备）。
 */
export function patchByTag<T>(
  items: readonly T[],
  tagsOf: (item: T) => readonly string[],
  tag: string,
  patch: (item: T) => T
): T[] {
  return items.map((item) => (tagsOf(item).includes(tag) ? patch(item) : item))
}

/**
 * 批量设置：按范围（全部/勾选）应用补丁（批量设备/批量声压共用）。
 */
export function patchScope<T>(
  items: readonly T[],
  scope: BatchScope,
  isSelected: (item: T) => boolean,
  patch: (item: T) => T
): T[] {
  return items.map((item) => (scope === 'all' || isSelected(item) ? patch(item) : item))
}
