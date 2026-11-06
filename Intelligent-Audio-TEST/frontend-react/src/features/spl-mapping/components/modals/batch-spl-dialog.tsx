/**
 * 批量 SPL 配置（§6.22 BatchSPLModal 平移；Dialog sm:max-w-2xl）。
 * 批量目标（当前筛选/跨页全选映射集合）+ 公共参数（测量距离/测试频率/目标声压级/数字增益，
 * 应用到全部所选）+ 含已校准映射时提交前 ConfirmDialog「将对 {n} 个已校准映射执行配置变更，
 * 变更后校准将重置为未校准」+ 提交逐映射批量更新 + 结果 toast「批量配置完成：成功 {s} 失败 {f}」。
 * 权限 spl:update。
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { ConfirmDialog } from '@/components/confirm-dialog'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import type { SplMapping } from '@/domain/models/splMapping'
import { useSplMutations } from '@/application/spl/useSplMappings'

export type BatchSplDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  mappings: SplMapping[]
  count: number
}

export function BatchSplDialog(props: BatchSplDialogProps) {
  const { update } = useSplMutations()
  const [distance, setDistance] = useState('1.0')
  const [testFrequency, setTestFrequency] = useState('1000')
  const [targetSpl, setTargetSpl] = useState('65')
  const [digitalGain, setDigitalGain] = useState('0')
  const [pending, setPending] = useState(false)
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false)

  useEffect(() => {
    if (props.open) {
      setDistance('1.0')
      setTestFrequency('1000')
      setTargetSpl('65')
      setDigitalGain('0')
      setPending(false)
    }
  }, [props.open])

  if (!props.open) return null

  const calibratedCount = props.mappings.filter(
    (m) => m.calibrationStatus === 'calibrated'
  ).length

  const handleSubmit = async () => {
    if (props.mappings.length === 0) {
      toast.info('当前筛选无映射可配置')
      return
    }
    if (calibratedCount > 0) {
      setResetConfirmOpen(true)
      return
    }
    await applyBatch()
  }

  const applyBatch = async () => {
    setPending(true)
    try {
      let success = 0
      for (const mapping of props.mappings) {
        await update.mutateAsync({
          id: mapping.id,
          patch: {
            distance: Number(distance),
            testFrequency: Number(testFrequency),
            targetSpl: Number(targetSpl),
            digitalGain: Number(digitalGain),
            calibrationStatus: 'uncalibrated',
            calibrationData: null,
          },
        })
        success += 1
      }
      toast.success(`批量配置完成：成功 ${success} 失败 ${props.mappings.length - success}`)
      props.onOpenChange(false)
    } catch {
      toast.error('批量配置失败，请重试')
    } finally {
      setPending(false)
      setResetConfirmOpen(false)
    }
  }

  return (
    <>
      <Dialog open={props.open} onOpenChange={props.onOpenChange}>
        <DialogContent className='sm:max-w-2xl'>
          <DialogHeader>
            <DialogTitle>批量 SPL 配置</DialogTitle>
            <DialogDescription>
              对当前筛选的 {props.count} 个映射统一应用公共参数（含已校准映射时校准将重置）
            </DialogDescription>
          </DialogHeader>

          <div className='grid grid-cols-1 gap-3 sm:grid-cols-2'>
            <div className='space-y-2'>
              <Label>测量距离（米）</Label>
              <Input
                type='number'
                step='0.1'
                value={distance}
                onChange={(e) => setDistance(e.target.value)}
                aria-label='测量距离'
              />
            </div>
            <div className='space-y-2'>
              <Label>测试频率（Hz）</Label>
              <Input
                type='number'
                value={testFrequency}
                onChange={(e) => setTestFrequency(e.target.value)}
                aria-label='测试频率'
              />
            </div>
            <div className='space-y-2'>
              <Label>目标声压级（dB）</Label>
              <Input
                type='number'
                value={targetSpl}
                onChange={(e) => setTargetSpl(e.target.value)}
                aria-label='目标声压级'
              />
            </div>
            <div className='space-y-2'>
              <Label>数字增益（dB）</Label>
              <Input
                type='number'
                step='0.1'
                value={digitalGain}
                onChange={(e) => setDigitalGain(e.target.value)}
                aria-label='数字增益'
              />
            </div>
          </div>

          <div className='border-border/60 bg-muted/25 rounded-md border px-3 py-2 text-xs'>
            <span className='text-muted-foreground'>批量目标：</span>
            <span className='font-mono tabular-nums'>{props.count}</span>
            <span> 个映射（当前筛选</span>
            {calibratedCount > 0 && (
              <span>
                ，其中 <span className='font-mono tabular-nums'>{calibratedCount}</span> 个已校准
              </span>
            )}
            <span>）</span>
          </div>

          <DialogFooter>
            <Button variant='outline' size='sm' onClick={() => props.onOpenChange(false)}>
              取消
            </Button>
            <Button size='sm' onClick={handleSubmit} disabled={pending}>
              {pending ? '配置中...' : '确认配置'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={resetConfirmOpen}
        onOpenChange={setResetConfirmOpen}
        title='校准重置确认'
        desc={`将对 ${calibratedCount} 个已校准映射执行配置变更，变更后校准将重置为未校准`}
        confirmText='继续'
        handleConfirm={applyBatch}
      />
    </>
  )
}
