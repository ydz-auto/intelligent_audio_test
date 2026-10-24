/**
 * 用例批量弹窗群宿主（INT-1026 共享组件；/testcases 与 /start-test 双挂）。
 * 纯展示组件：消费 useCaseBatchActions 返回的弹窗状态，装配七件套批量弹窗
 * （用例专属参数/播放设备/声压/评估维度/调整分组/噪声/管理标签）+ 通用确认弹窗
 * （标签生成名称/用例参考更新）。数据 props 由各页 query 层提供（两页同源 queryKey，天然一致）。
 */
import { useMemo } from 'react'

import type { Dimension, EvaluationCategory } from '@/domain/models/evaluationDimension'
import type { TestCaseGroup } from '@/domain/models/testCaseGroup'
import type { TagItem } from '@/domain/models/testTag'
import type { BatchDialogState } from '@/application/testcases/use-case-batch-actions'
import type { CaseConfirmState } from '@/features/testcases/modals/case-confirms'
import { BatchAdjustGroupDialog } from '@/features/testcases/modals/batch-adjust-group-dialog'
import { BatchAlgoParamsDialog } from '@/features/testcases/modals/batch-algo-params-dialog'
import { BatchDeviceDialog } from '@/features/testcases/modals/batch-device-dialog'
import { BatchDimensionsDialog } from '@/features/testcases/modals/batch-dimensions-dialog'
import { BatchManageTagsDialog } from '@/features/testcases/modals/batch-manage-tags-dialog'
import { BatchNoiseDialog } from '@/features/testcases/modals/batch-noise-dialog'
import { BatchSplDialog } from '@/features/testcases/modals/batch-spl-dialog'
import { CaseConfirmDialog } from '@/features/testcases/modals/case-confirms'

export interface CaseBatchActionsHostProps {
  batchDialog: BatchDialogState | null
  setBatchDialog: (state: BatchDialogState | null) => void
  confirm: CaseConfirmState | null
  setConfirm: (state: CaseConfirmState | null) => void
  handleConfirm: (state: CaseConfirmState) => void
  groups: TestCaseGroup[]
  tags: TagItem[]
  /** 全量评估维度（含子维度；批量设置评估维度 DimensionPicker 主/子分组云用） */
  dimensions: Dimension[]
  /** 评估维度分类（DimensionPicker 分类分组组头；负责人 2026-10-19 口径） */
  categories?: EvaluationCategory[]
  algorithmType?: string | null
  testType?: string | null
  /**
   * 当前页已加载的用例（含真实轮次数 rounds；INT-1642 批量设置评估维度「指定轮次」、
   * INT-1731 专属参数/播放设备/声压/噪声四窗「轮次范围」均取选中用例的真实轮次——
   * 多选取最大轮次；未加载到的 id 沿用已加载最大值）
   */
  cases?: Array<{ id: string; rounds: number }>
}

/** 按选中用例真实轮次渲染「轮次范围」的批量窗（INT-1731：五窗同口径） */
const ROUND_SCOPED_KINDS = new Set<BatchDialogState['kind']>([
  'dimensions',
  'params',
  'device',
  'spl',
  'noise',
])

export function CaseBatchActionsHost({
  batchDialog,
  setBatchDialog,
  confirm,
  setConfirm,
  handleConfirm,
  groups,
  tags,
  dimensions,
  categories = [],
  algorithmType,
  testType,
  cases,
}: CaseBatchActionsHostProps) {
  /** 选中用例的真实最大轮次（轮次范围各窗用；未知 id 不计入，全部未知回落 1） */
  const selectedRoundCount = useMemo(() => {
    if (!batchDialog || !ROUND_SCOPED_KINDS.has(batchDialog.kind)) return 1
    const wanted = new Set(batchDialog.ids)
    const known = (cases ?? [])
      .filter((c) => wanted.has(c.id))
      .map((c) => c.rounds)
    return Math.max(1, ...known)
  }, [batchDialog, cases])

  return (
    <>
      {batchDialog?.kind === 'dimensions' && (
        <BatchDimensionsDialog
          open
          onOpenChange={(open) => !open && setBatchDialog(null)}
          count={batchDialog.count}
          ids={batchDialog.ids}
          dimensions={dimensions}
          categories={categories}
          algorithmType={algorithmType}
          testType={testType}
          roundCount={selectedRoundCount}
        />
      )}
      {batchDialog?.kind === 'group' && (
        <BatchAdjustGroupDialog
          open
          onOpenChange={(open) => !open && setBatchDialog(null)}
          count={batchDialog.count}
          ids={batchDialog.ids}
          groups={groups}
        />
      )}
      {batchDialog?.kind === 'tags' && (
        <BatchManageTagsDialog
          open
          onOpenChange={(open) => !open && setBatchDialog(null)}
          count={batchDialog.count}
          ids={batchDialog.ids}
          tags={tags}
        />
      )}
      {batchDialog?.kind === 'params' && (
        <BatchAlgoParamsDialog
          open
          onOpenChange={(open) => !open && setBatchDialog(null)}
          count={batchDialog.count}
          ids={batchDialog.ids}
          roundCount={selectedRoundCount}
        />
      )}
      {batchDialog?.kind === 'device' && (
        <BatchDeviceDialog
          open
          onOpenChange={(open) => !open && setBatchDialog(null)}
          count={batchDialog.count}
          ids={batchDialog.ids}
          roundCount={selectedRoundCount}
        />
      )}
      {batchDialog?.kind === 'spl' && (
        <BatchSplDialog
          open
          onOpenChange={(open) => !open && setBatchDialog(null)}
          count={batchDialog.count}
          ids={batchDialog.ids}
          roundCount={selectedRoundCount}
        />
      )}
      {batchDialog?.kind === 'noise' && (
        <BatchNoiseDialog
          open
          onOpenChange={(open) => !open && setBatchDialog(null)}
          count={batchDialog.count}
          ids={batchDialog.ids}
          roundCount={selectedRoundCount}
        />
      )}
      <CaseConfirmDialog
        open={confirm != null}
        onOpenChange={(open) => !open && setConfirm(null)}
        state={confirm}
        onConfirm={handleConfirm}
      />
    </>
  )
}
