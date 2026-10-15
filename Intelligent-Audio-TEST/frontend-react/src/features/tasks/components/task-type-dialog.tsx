/**
 * 任务类型选择弹窗（09_任务域.md §5.6，页头「+ 创建新任务」）。
 * 标题「创建新任务」说明「请选择测试类型」；两张选项卡（grid-cols-2）：
 * 端到端测试（Smartphone，bg-primary/10 text-primary）/ API测试（ArrowLeftRight，bg-secondary/10 text-secondary）。
 * 点击跳对应创建页（创建流程归测试执行卡 INT-355，本卡只出选择弹窗）。
 */
import { ArrowLeftRight, Smartphone } from 'lucide-react'
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
          <DialogDescription>请选择测试类型</DialogDescription>
        </DialogHeader>
        <div className='grid grid-cols-2 gap-4'>
          <button
            type='button'
            onClick={() => go('/E2ETest')}
            className='hover:shadow-lg group flex flex-col items-center gap-3 rounded-xl border bg-primary/10 p-6 text-primary transition-all'
          >
            <Smartphone aria-hidden='true' className='size-8' />
            <span className='text-sm font-medium'>端到端测试</span>
            <span className='text-primary/70 text-xs'>真实设备 · 端到端链路验证</span>
          </button>
          <button
            type='button'
            onClick={() => go('/APITest')}
            className='hover:shadow-lg group flex flex-col items-center gap-3 rounded-xl border bg-secondary/10 p-6 text-secondary transition-all'
          >
            <ArrowLeftRight aria-hidden='true' className='size-8' />
            <span className='text-sm font-medium'>API 测试</span>
            <span className='text-secondary/70 text-xs'>HTTP 接口 · 通道稳定性验证</span>
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
