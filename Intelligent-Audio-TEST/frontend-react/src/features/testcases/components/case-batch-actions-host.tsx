/**
 * 用例批量弹窗群宿主（INT-1026 共享组件；/testcases 与 /start-test 双挂）。
 * 纯展示组件：消费 useCaseBatchActions 返回的弹窗状态，装配七件套批量弹窗
 * （用例专属参数/播放设备/声压/评估维度/调整分组/噪声/管理标签）+ 通用确认弹窗
 * （标签生成名称/用例参考更新）。数据 props 由各页 query 层提供（两页同源 queryKey，天然一致）。
 */
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
}

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
}: CaseBatchActionsHostProps) {
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
        />
      )}
      {batchDialog?.kind === 'device' && (
        <BatchDeviceDialog
          open
          onOpenChange={(open) => !open && setBatchDialog(null)}
          count={batchDialog.count}
          ids={batchDialog.ids}
        />
      )}
      {batchDialog?.kind === 'spl' && (
        <BatchSplDialog
          open
          onOpenChange={(open) => !open && setBatchDialog(null)}
          count={batchDialog.count}
          ids={batchDialog.ids}
        />
      )}
      {batchDialog?.kind === 'noise' && (
        <BatchNoiseDialog
          open
          onOpenChange={(open) => !open && setBatchDialog(null)}
          count={batchDialog.count}
          ids={batchDialog.ids}
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
