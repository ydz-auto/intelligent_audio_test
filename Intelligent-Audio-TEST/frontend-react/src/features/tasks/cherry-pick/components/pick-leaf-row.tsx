/**
 * 结果行叶（18_挑选合并交互重设计.md §3.7.1 末级）。
 * 阶段 2 叶明细按需分页加载（candidates），叶行自带设备/API 名 + 结果类型 + 执行/评估状态；
 * 用例名只保留在用例卡（INT-2098），叶行不再重复显示；缺名由候选行缺省口径兜底
 * （INT-1824 §8.2.8：设备软删 → 「未知设备」，不裸显 UUID）。
 */
import type { PickTreeLeaf } from '@/domain/models/cherryPick'
import { resultTypeLabel } from '@/domain/lib/pick-candidate-tree'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'
import { formatPickDateTime } from '@/features/tasks/cherry-pick/constants'
import { getEvaluationStatusMeta } from '@/features/tasks/constants'

/** 设备/API 二选一：叶行名称（设备软删 → 「未知设备」） */
function leafDeviceName(leaf: PickTreeLeaf): string {
  if (leaf.deviceName) return leaf.deviceName
  if (leaf.apiName) return leaf.apiName
  return leaf.deviceId != null || leaf.apiId == null ? '未知设备' : '未知API'
}

/** 缺 result_type 展示为「结果类型待补充」（服务端缺值桶 `default`） */
function leafResultTypeLabel(leaf: PickTreeLeaf): string {
  return resultTypeLabel(leaf.resultType)
}

/** 叶行尾部信息（结果类型 + 执行/评估状态 + 时间）——独立叶行与「单结果上收父级行」共用 */
export function LeafTrailingMeta({
  leaf,
  hideResultType = false,
}: {
  leaf: PickTreeLeaf
  /** 树内：结果类型由上级 result_type 层已显示，不再重复 */
  hideResultType?: boolean
}) {
  const evalMeta = getEvaluationStatusMeta(leaf.evaluationStatus)
  return (
    <>
      {!hideResultType && (
        <Badge variant='outline' className='shrink-0 font-mono text-[10px]'>
          {leafResultTypeLabel(leaf)}
        </Badge>
      )}
      <StatusBadge
        label={
          leaf.executionStatus === 'completed'
            ? '已完成'
            : leaf.executionStatus === 'failed'
              ? '执行失败'
              : '已停止'
        }
        variant={
          leaf.executionStatus === 'completed'
            ? 'success'
            : leaf.executionStatus === 'failed'
              ? 'danger'
              : 'neutral'
        }
      />
      <StatusBadge label={evalMeta.label} variant={evalMeta.variant} pulse={evalMeta.pulse} />
      <span className='text-muted-foreground shrink-0 font-mono text-[10px] whitespace-nowrap tabular-nums'>
        {formatPickDateTime(leaf.createdAt)}
      </span>
    </>
  )
}

export function LeafRow({
  leaf,
  selected,
  onToggle,
  showLeafTask,
  hideDevice,
  hideResultType,
}: {
  leaf: PickTreeLeaf
  selected: boolean
  onToggle: (leaf: PickTreeLeaf) => void
  /** §3.8.3 三视图叶行携带来源任务名消歧（设备/结果类型/用例视图内树） */
  showLeafTask?: boolean
  /** 树内叶行：设备/API 名由上级「设备/API」层已显示，叶行不再重复 */
  hideDevice?: boolean
  /** 树内叶行：结果类型由上级「result_type」层已显示，叶行不再重复 */
  hideResultType?: boolean
}) {
  return (
    <div
      data-testid={`pick-leaf-${leaf.resultId}`}
      className='hover:bg-muted/40 flex min-w-0 items-center gap-2 rounded-md px-2 py-1 text-[13px] transition-colors'
    >
      <Checkbox
        checked={selected}
        onCheckedChange={() => onToggle(leaf)}
        aria-label={`结果 ${leaf.resultId}`}
      />
      {showLeafTask && (
        <span
          className='text-muted-foreground/60 max-w-28 shrink-0 truncate font-mono text-[10px] tabular-nums'
          title={`来源任务：${leaf.taskName}`}
        >
          {leaf.taskName}
        </span>
      )}
      {/* INT-2098：叶行不重复显示用例名（用例卡已展示），设备/API 名升为主列；
          树内（hideDevice）该信息归上级「设备/API」层，叶行留空占位不重复 */}
      {hideDevice ? (
        <span className='flex-1' />
      ) : (
        <span className='min-w-0 flex-1 truncate font-medium'>{leafDeviceName(leaf)}</span>
      )}
      <LeafTrailingMeta leaf={leaf} hideResultType={hideResultType} />
      {leaf.added && (
        <span className='text-muted-foreground/70 shrink-0 text-xs' title='已在购物车'>
          已加购
        </span>
      )}
    </div>
  )
}
