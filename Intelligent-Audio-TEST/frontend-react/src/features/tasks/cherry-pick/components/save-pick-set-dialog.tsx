/**
 * 另存为挑选集弹窗（18_挑选合并交互重设计.md §4.3/§5.2，INT-600）。
 * 购物车抽屉与购物车步骤页脚共用（§4.3「另存挑选集」；预览步骤只读，不带「另存挑选集」）。
 * 名称输入 → saveAsPickSet → 成功 toast；打开时重置输入。
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { usePickCartStore } from '@/application/tasks/cherry-pick/use-pick-cart-store'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'

export function SavePickSetDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const saveAsPickSet = usePickCartStore((s) => s.saveAsPickSet)
  const [name, setName] = useState('')

  useEffect(() => {
    if (open) setName('')
  }, [open])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-sm'>
        <DialogHeader>
          <DialogTitle>另存为挑选集</DialogTitle>
          <DialogDescription>
            为当前购物车内容命名，之后可从「管理挑选集」恢复进购物车
          </DialogDescription>
        </DialogHeader>
        <Input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder='挑选集名称（例如：远场高置信度候选集）'
          maxLength={40}
        />
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            disabled={!name.trim()}
            onClick={async () => {
              const pick = await saveAsPickSet(name.trim())
              onOpenChange(false)
              toast.success(
                pick
                  ? `挑选集「${pick.name}」已保存（${pick.itemCount} 条）`
                  : '挑选集已保存'
              )
            }}
          >
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
