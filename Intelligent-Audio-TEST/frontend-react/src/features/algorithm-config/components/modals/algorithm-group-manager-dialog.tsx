/**
 * 算法分组管理弹窗（§7.1；Dialog sm:max-w-2xl + StaticDataTable + 小表单 Dialog + 删除 ConfirmDialog）。
 * 权限：algorithm:group_manage 读写、algorithm:read 只读查看。
 * 分组含算法时删除拦截提示（cascade 语义「删除分组不会删除算法」）。
 */
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'

import {
  useAlgorithmGroupMutations,
} from '@/application/algorithm-config/useAlgorithmDefinitions'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'
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
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import type { AlgorithmGroup } from '@/domain/models/algorithmConfig'

export type AlgorithmGroupManagerDialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  groups: AlgorithmGroup[]
  canManage: boolean
}

type GroupFormState = {
  open: boolean
  group: AlgorithmGroup | null
}

type GroupDeleteState = AlgorithmGroup | null

export function AlgorithmGroupManagerDialog(props: AlgorithmGroupManagerDialogProps) {
  const { create, update, remove } = useAlgorithmGroupMutations()
  const [form, setForm] = useState<GroupFormState>({ open: false, group: null })
  const [deleteState, setDeleteState] = useState<GroupDeleteState>(null)
  const [pending, setPending] = useState(false)

  const nextOrder = useMemo(
    () => (props.groups.length > 0
      ? Math.max(...props.groups.map((g) => g.displayOrder)) + 1
      : 1),
    [props.groups]
  )

  const handleSubmit = async (name: string, description: string, icon: string, displayOrder: number) => {
    setPending(true)
    try {
      if (form.group) {
        await update.mutateAsync({ id: form.group.id, input: { name, description, icon, displayOrder } })
        toast.success('分组已更新')
      } else {
        await create.mutateAsync({ name, description, icon, displayOrder })
        toast.success('分组已创建')
      }
      setForm({ open: false, group: null })
    } catch {
      toast.error('保存失败，请重试')
    } finally {
      setPending(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteState) return
    setPending(true)
    try {
      const result = await remove.mutateAsync(deleteState.id)
      if (result.success) {
        toast.success('分组已删除')
        setDeleteState(null)
      } else {
        toast.error(result.message ?? '删除失败，请重试')
        setDeleteState(null)
      }
    } catch {
      toast.error('删除失败，请重试')
    } finally {
      setPending(false)
    }
  }

  return (
    <>
      <Dialog open={props.open} onOpenChange={props.onOpenChange}>
        <DialogContent className='sm:max-w-2xl'>
          <DialogHeader>
            <DialogTitle>算法分组管理</DialogTitle>
            <DialogDescription>
              管理算法分组，算法分组用于算法列表筛选与编辑时归属选择
            </DialogDescription>
          </DialogHeader>

          <div className='flex items-center justify-between gap-2'>
            <p className='text-muted-foreground text-sm'>
              共 {props.groups.length} 个分组
            </p>
            {props.canManage && (
              <Button size='sm' onClick={() => setForm({ open: true, group: null })}>
                <Plus aria-hidden='true' />
                新建分组
              </Button>
            )}
          </div>

          <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
            <div className='overflow-x-auto'>
              <table className='w-full min-w-0 text-[13px]'>
                <thead>
                  <tr className='bg-[var(--table-header)] text-xs'>
                    <th className='px-3 py-2 text-left font-medium'>分组名称</th>
                    <th className='px-3 py-2 text-left font-medium'>描述</th>
                    <th className='px-3 py-2 text-right font-medium'>排序</th>
                    <th className='px-3 py-2 text-right font-medium'>算法数</th>
                    {props.canManage && (
                      <th className='w-20 px-3 py-2 text-right font-medium'>操作</th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {props.groups.length === 0 ? (
                    <tr>
                      <td
                        colSpan={props.canManage ? 5 : 4}
                        className='text-muted-foreground px-3 py-6 text-center'
                      >
                        暂无分组
                      </td>
                    </tr>
                  ) : (
                    props.groups.map((group) => (
                      <tr key={group.id} className='border-border/50 border-b last:border-b-0'>
                        <td className='px-3 py-2 font-medium'>{group.name}</td>
                        <td className='text-muted-foreground max-w-64 truncate px-3 py-2' title={group.description ?? ''}>
                          {group.description ?? '—'}
                        </td>
                        <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                          {group.displayOrder}
                        </td>
                        <td className='px-3 py-2 text-right font-mono text-xs tabular-nums'>
                          {group.algorithmCount}
                        </td>
                        {props.canManage && (
                          <td className='px-3 py-2'>
                            <div className='flex items-center justify-end gap-0.5'>
                              <Button
                                variant='ghost'
                                size='icon-sm'
                                aria-label={`编辑分组 ${group.name}`}
                                onClick={() => setForm({ open: true, group })}
                              >
                                <Pencil aria-hidden='true' className='size-3.5' />
                              </Button>
                              <Button
                                variant='ghost'
                                size='icon-sm'
                                className='text-destructive'
                                aria-label={`删除分组 ${group.name}`}
                                onClick={() => setDeleteState(group)}
                              >
                                <Trash2 aria-hidden='true' className='size-3.5' />
                              </Button>
                            </div>
                          </td>
                        )}
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </DialogContent>
      </Dialog>

      {/* 新建/编辑分组小表单（§7.1：名称/描述/图标/排序） */}
      <GroupFormDialog
        open={form.open}
        group={form.group}
        nextOrder={nextOrder}
        pending={pending}
        onOpenChange={(open) => setForm({ open, group: open ? form.group : null })}
        onSubmit={handleSubmit}
      />

      {/* 删除分组确认（含算法时 cascade 语义提示） */}
      <AlertDialog open={deleteState != null} onOpenChange={(open) => !open && setDeleteState(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除分组</AlertDialogTitle>
            <AlertDialogDescription>
              {deleteState != null && deleteState.algorithmCount > 0
                ? `分组「${deleteState.name}」包含 ${deleteState.algorithmCount} 个算法。删除分组不会删除算法（算法将变为未分组），确定删除吗？`
                : `确定删除分组「${deleteState?.name}」吗？此操作不可恢复。`}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={pending}>取消</AlertDialogCancel>
            <AlertDialogAction variant='destructive' disabled={pending} onClick={handleDelete}>
              {pending ? '删除中…' : '删除'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  )
}

function GroupFormDialog({
  open,
  group,
  nextOrder,
  pending,
  onOpenChange,
  onSubmit,
}: {
  open: boolean
  group: AlgorithmGroup | null
  nextOrder: number
  pending: boolean
  onOpenChange: (open: boolean) => void
  onSubmit: (name: string, description: string, icon: string, displayOrder: number) => void
}) {
  const [name, setName] = useState(group?.name ?? '')
  const [description, setDescription] = useState(group?.description ?? '')
  const [icon, setIcon] = useState(group?.icon ?? '')
  const [displayOrder, setDisplayOrder] = useState(String(group?.displayOrder ?? nextOrder))

  // 弹窗切换时重置表单（新建 nextOrder / 编辑 group 值）
  const [prevOpen, setPrevOpen] = useState(false)
  if (open !== prevOpen) {
    setPrevOpen(open)
    if (open) {
      setName(group?.name ?? '')
      setDescription(group?.description ?? '')
      setIcon(group?.icon ?? '')
      setDisplayOrder(String(group?.displayOrder ?? nextOrder))
    }
  }

  const invalid = name.trim() === ''

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-xl'>
        <DialogHeader>
          <DialogTitle>{group ? '编辑分组' : '新建分组'}</DialogTitle>
          <DialogDescription>
            {group ? '更新该算法分组的配置' : '创建新的算法分组，用于算法归属分类'}
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (invalid) return
            onSubmit(name.trim(), description.trim(), icon.trim(), Number(displayOrder) || 0)
          }}
          className='space-y-3'
        >
          <div className='grid gap-3 sm:grid-cols-2'>
            <div className='space-y-1.5'>
              <Label htmlFor='group-name' required>分组名称</Label>
              <Input
                id='group-name'
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder='如：语音识别'
                aria-invalid={invalid}
              />
            </div>
            <div className='space-y-1.5'>
              <Label htmlFor='group-order'>排序</Label>
              <Input
                id='group-order'
                type='number'
                min={0}
                value={displayOrder}
                onChange={(e) => setDisplayOrder(e.target.value)}
              />
            </div>
          </div>
          <div className='space-y-1.5'>
            <Label htmlFor='group-icon'>图标</Label>
            <Input
              id='group-icon'
              value={icon}
              onChange={(e) => setIcon(e.target.value)}
              placeholder='图标标识（可选）'
            />
          </div>
          <div className='space-y-1.5'>
            <Label htmlFor='group-desc'>描述</Label>
            <Textarea
              id='group-desc'
              rows={3}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder='分组用途说明（可选）'
            />
          </div>
          <DialogFooter>
            <Button variant='outline' type='button' onClick={() => onOpenChange(false)}>
              取消
            </Button>
            <Button type='submit' disabled={invalid || pending}>
              {pending ? '保存中…' : '保存'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
