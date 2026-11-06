/**
 * 用例编辑音频列表批量工具（application 层，11_用例域.md §5.1 音频列表工具栏）。
 * 五件纯前端派生动作：标签交错 / 标签设备 / 批量设备 / 设备交叉 / 批量声压。
 * 均为不可变派生（返回新数组，不修改入参），底层复用 domain/lib/audio-batch-ops 纯函数。
 * 标签源由调用方注入（真实音频库 tags 映射），不持 mock 数据。
 */
import { useMemo } from 'react'

import {
  assignRoundRobin,
  interleaveByTags,
  patchByTag,
  patchScope,
  type BatchScope,
} from '@/domain/lib/audio-batch-ops'

/** 批量动作的最小行结构（与界面 RoundAudioDraft 结构兼容；speakerGroupId 为逻辑音箱 id） */
export interface RoundAudioLike {
  id: string
  /** 老字段：实体播放设备 id（用例已不再直接选设备，保留以兼容回读） */
  deviceId: string
  /** 逻辑音箱组 id（用例唯一可选的播放目标） */
  speakerGroupId?: string
  spl: number
  /** 真实音频 id（标签源解析用；可选） */
  audioId?: number | string | null
  /** 行内标签（标签源解析 fallback；可选） */
  tags?: readonly string[]
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
 * 音频列表批量动作工厂（标签源由调用方注入 tagsOf，身份稳定）。
 */
export function useAudioListBatch(
  tagsOf: (row: RoundAudioLike) => readonly string[]
): AudioListBatchActions {
  return useMemo(() => {
    return {
      tagInterleave: (rows, tags, newId) =>
        interleaveByTags(rows, tagsOf, tags, (r) => ({ ...r, id: newId() })),
      tagDevice: (rows, tag, speakerGroupId) =>
        patchByTag(rows, tagsOf, tag, (r) => ({ ...r, speakerGroupId, deviceId: '' })),
      batchDevice: (rows, speakerGroupId, scope, selectedIds) =>
        patchScope(
          rows,
          scope,
          (r) => selectedIds.has(r.id),
          (r) => ({ ...r, speakerGroupId, deviceId: '' })
        ),
      crossDevice: (rows, speakerGroupIds) =>
        assignRoundRobin(rows, speakerGroupIds, (r, speakerGroupId) => ({
          ...r,
          speakerGroupId,
          deviceId: '',
        })),
      batchSpl: (rows, spl, scope, selectedIds) =>
        patchScope(
          rows,
          scope,
          (r) => selectedIds.has(r.id),
          (r) => ({ ...r, spl })
        ),
    }
  }, [tagsOf])
}
