/**
 * 批量设置逻辑音箱弹窗（11_用例域.md §5.3.2，Dialog sm:max-w-lg）。
 * 用例只关联逻辑音箱：下拉只列逻辑音箱（GET /playback-devices/speaker-groups），
 * 提交走 POST /testcases/batch（update_playback_devices）：
 * playback_devices.speakerGroupId + targets + round_mode/round_numbers（逐轮为 round_values）。
 * 执行时由后端按「执行实验室」解析成该实验室的实体音箱。
 */
import { useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Spinner } from '@/components/ui/spinner'
import { usePlaybackSpeakerGroups } from '@/application/devices/use-devices'
import {
  batchTestcaseAction,
  type TestcaseBatchPayload,
  type TestcaseRoundMode,
} from '@/infrastructure/api/testcases-batch-api'
import {
  applyLayerToTargets,
  ApplyLayerField,
  createRoundScope,
  existingRounds,
  RoundScopeThreeField,
  usePerRoundValue,
  type ApplyLayerId,
} from '@/features/testcases/modals/batch-shared'

export function BatchDeviceDialog({
  open,
  onOpenChange,
  count,
  ids,
  roundCount,
  unknownRoundCount = 0,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  count: number
  ids: string[]
  /** 选中用例实际轮次数（config.rounds 派生；0=空态——INT-1731/INT-1506） */
  roundCount: number
  /** 选中用例中轮次未知（列表尚未加载）的条数 */
  unknownRoundCount?: number
}) {
  const totalRounds = Math.max(1, roundCount)
  const [submitting, setSubmitting] = useState(false)
  const [scope, setScope] = useState(() => createRoundScope(roundCount))
  const [layers, setLayers] = useState<ApplyLayerId[]>([])
  const {
    current: speakerGroupId,
    setCurrent: setSpeakerGroupId,
    perRound,
  } = usePerRoundValue('', scope)

  const groupsQuery = usePlaybackSpeakerGroups()
  const speakerGroups = groupsQuery.data ?? []

  // 声明式 items：闭合态从 items 取 label，否则 base-ui 回退显示原始组 id（INT-1686）
  const groupItems = speakerGroups.map((group) => ({
    value: String(group.id),
    label: `[逻辑音箱] ${group.name}`,
  }))

  const handleSubmit = async () => {
    const targets = applyLayerToTargets(layers)
    let payload: TestcaseBatchPayload
    if (scope.mode === 'per_round') {
      // 逐轮设置：round_values = {轮次号: {speakerGroupId, targets}}，仅含用户实际编辑过的真实轮次
      const roundValues: Record<string, unknown> = {}
      for (const [roundKey, roundGroupId] of Object.entries(perRound)) {
        const round = Number(roundKey)
        if (!Number.isInteger(round) || round < 1 || round > totalRounds) continue
        if (roundGroupId === '') continue
        const numeric = Number(roundGroupId)
        if (Number.isNaN(numeric)) continue
        roundValues[roundKey] = { speakerGroupId: numeric, targets }
      }
      if (Object.keys(roundValues).length === 0) {
        toast.error('请至少为一个轮次选择逻辑音箱')
        return
      }
      payload = { roundMode: 'per_round', roundNumbers: [], roundValues }
    } else {
      if (!speakerGroupId) return
      const roundNumbers =
        scope.mode === 'specific' ? existingRounds(scope.specificRounds, totalRounds) : undefined
      // 指定轮次未勾选任何真实轮次：不提交（后端对不存在/空轮次静默回成功——INT-1731）
      if (roundNumbers && roundNumbers.length === 0) {
        toast.error('请至少选择一个轮次')
        return
      }
      payload = {
        playbackDevices: { speakerGroupId: Number(speakerGroupId) },
        targets,
        roundMode: scope.mode as TestcaseRoundMode,
        roundNumbers,
      }
    }
    setSubmitting(true)
    try {
      await batchTestcaseAction('update_playback_devices', ids, payload)
      toast.success(`批量操作执行成功（更新 ${count} 个）`)
      onOpenChange(false)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : '批量设置逻辑音箱失败')
    } finally {
      setSubmitting(false)
    }
  }

  /** 逐轮模式：任一编辑过的轮次选了逻辑音箱即可提交 */
  const canSubmit =
    scope.mode === 'per_round'
      ? Object.values(perRound).some((v) => v !== '')
      : Boolean(speakerGroupId)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>批量设置逻辑音箱</DialogTitle>
          <DialogDescription>
            您勾选了 {count} 个用例，将统一关联同一个逻辑音箱（执行时按实验室换成本实验室实体音箱）
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-4'>
          <div className='space-y-1.5'>
            <span className='text-sm font-medium'>
              {scope.mode === 'per_round' ? `第 ${scope.activeRound} 轮逻辑音箱 *` : '逻辑音箱 *'}
            </span>
            <Select
              value={speakerGroupId}
              onValueChange={(v) => setSpeakerGroupId(v ?? '')}
              disabled={speakerGroups.length === 0}
              items={groupItems}
            >
              <SelectTrigger size='sm' className='h-8 w-full'>
                <SelectValue placeholder='请选择逻辑音箱' />
              </SelectTrigger>
              <SelectContent>
                {groupItems.map((item) => (
                  <SelectItem key={item.value} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {groupsQuery.isLoading ? (
              <p className='text-muted-foreground/70 inline-flex items-center gap-1.5 pt-1 text-xs'>
                <Spinner className='size-3.5' />
                正在加载逻辑音箱...
              </p>
            ) : speakerGroups.length === 0 ? (
              <p className='text-muted-foreground/70 pt-1 text-xs'>
                暂无可用的逻辑音箱（请先在设备管理 → 逻辑音箱中配置）
              </p>
            ) : null}
          </div>

          <RoundScopeThreeField
            name='batch-device-round'
            value={scope}
            onChange={setScope}
            roundCount={roundCount}
            unknownRoundCount={unknownRoundCount}
          />
          <ApplyLayerField
            value={layers}
            onChange={setLayers}
            hint='可多选；留空时默认应用到目标人音频'
          />
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)} disabled={submitting}>
            取消
          </Button>
          <Button onClick={() => void handleSubmit()} disabled={submitting || !canSubmit}>
            {submitting && <Spinner className='size-3.5' />}
            确定
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
