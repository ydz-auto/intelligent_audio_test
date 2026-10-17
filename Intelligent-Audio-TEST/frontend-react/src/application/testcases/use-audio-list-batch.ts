/**
 * 用例编辑音频列表批量工具（application 层，11_用例域.md §5.1 音频列表工具栏）。
 * 五件纯前端派生动作：标签交错 / 标签设备 / 批量设备 / 设备交叉 / 批量声压。
 * 均为不可变派生（返回新数组，不修改入参），底层复用 domain/lib/audio-batch-ops 纯函数；
 * mock 态不接后端，后续接线替换为 mutations。
 */
import { useMemo } from 'react'

import {
  assignRoundRobin,
  interleaveByTags,
  patchByTag,
  patchScope,
  type BatchScope,
} from '@/domain/lib/audio-batch-ops'

/** 批量动作的最小行结构（与界面 RoundAudioDraft 结构兼容） */
interface RoundAudioLike {
  id: string
  fileId: string
  deviceId: string
  spl: number
}

export interface AudioListBatchActions {
  /** 标签交错：按所选标签顺序分段排序（多标签音频每段各现一次，各次出现经 newId 克隆独立行身份） */
  tagInterleave: <T extends RoundAudioLike>(
    rows: readonly T[],
    tags: readonly string[],
    newId: () => string
  ) => T[]
  /** 标签设备：命中指定标签的音频批量设置播放设备 */
  tagDevice: <T extends RoundAudioLike>(rows: readonly T[], tag: string, deviceId: string) => T[]
  /** 批量设备：按范围（全部/勾选）批量设置播放设备 */
  batchDevice: <T extends RoundAudioLike>(
    rows: readonly T[],
    deviceId: string,
    scope: BatchScope,
    selectedIds: ReadonlySet<string>
  ) => T[]
  /** 设备交叉：多选设备按列表顺序轮转分配 */
  crossDevice: <T extends RoundAudioLike>(rows: readonly T[], deviceIds: readonly string[]) => T[]
  /** 批量声压：按范围（全部/勾选）批量设置声压级 */
  batchSpl: <T extends RoundAudioLike>(
    rows: readonly T[],
    spl: number,
    scope: BatchScope,
    selectedIds: ReadonlySet<string>
  ) => T[]
}

/**
 * 音频列表批量动作工厂（页面级 mock 标签源不变，actions 身份稳定）。
 */
export function useAudioListBatch(
  tagsByFile: ReadonlyMap<string, readonly string[]>
): AudioListBatchActions {
  return useMemo(() => {
    const tagsOf = (r: RoundAudioLike) => tagsByFile.get(r.fileId) ?? []
    return {
      tagInterleave: (rows, tags, newId) =>
        interleaveByTags(rows, tagsOf, tags, (r) => ({ ...r, id: newId() })),
      tagDevice: (rows, tag, deviceId) =>
        patchByTag(rows, tagsOf, tag, (r) => ({ ...r, deviceId })),
      batchDevice: (rows, deviceId, scope, selectedIds) =>
        patchScope(
          rows,
          scope,
          (r) => selectedIds.has(r.id),
          (r) => ({ ...r, deviceId })
        ),
      crossDevice: (rows, deviceIds) =>
        assignRoundRobin(rows, deviceIds, (r, deviceId) => ({ ...r, deviceId })),
      batchSpl: (rows, spl, scope, selectedIds) =>
        patchScope(
          rows,
          scope,
          (r) => selectedIds.has(r.id),
          (r) => ({ ...r, spl })
        ),
    }
  }, [tagsByFile])
}
