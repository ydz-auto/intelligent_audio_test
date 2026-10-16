/**
 * 任务创建入口弹窗（09_任务域.md §5.6，页头「+ 创建新任务」）。
 * 标题「创建新任务」；单入口卡「开始测试」（INT-486 2026-10-16 口径：开始测试不再分
 * E2E/API 模式，设备+API 混合执行，点击跳 /start-test 单流程）。
 */
import { Smartphone } from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'

export function TaskTypeDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const navigate = useNavigate()

  const go = (to: string) => {
    onOpenChange(false)
    void navigate({ to })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>创建新任务</DialogTitle>
          <DialogDescription>选择用例与设备/API，开始一次测试</DialogDescription>
        </DialogHeader>
        <div className='grid grid-cols-1 gap-4'>
          <button
            type='button'
            onClick={() => go('/start-test')}
            className='hover:shadow-lg group flex flex-col items-center gap-3 rounded-xl border bg-primary/10 p-6 text-primary transition-all'
          >
            <Smartphone aria-hidden='true' className='size-8' />
            <span className='text-sm font-medium'>开始测试</span>
            <span className='text-primary/70 text-xs'>设备 + API 混合执行 · 同流程完成测试与报告</span>
          </button>
        </div>
        <div className='flex justify-end'>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
