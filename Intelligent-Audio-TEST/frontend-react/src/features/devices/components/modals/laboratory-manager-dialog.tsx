/**
 * 实验室管理弹窗（16_设备域.md §6.26/INT-487；Dialog sm:max-w-3xl）。
 * 标题「实验室管理」+ 说明「管理物理实验室及其资源归属（设备/播放设备/用例），用于按实验室
 * 分组与测试资源过滤」；实验室列表（代码 mono/名称/所在位置「{building}·{floor}·{room_number}」/
 * 状态 StatusBadge（active=success 启用/inactive=neutral 停用/maintenance=warning 维护中）/
 * 资源统计 tabular「设备 {n} · 播放 {m} · 用例 {k}」/更新时间/操作[编辑·删除]）+
 * 新建实验室表单（名称（必填）/代码（必填）/所在楼栋/楼层/房间号/描述/状态）。
 * 数据契约按 doc/总架构/实验室扩展功能设计.md §5.1 设计；后端 /api/laboratories CRUD 未实现
 * （§11-24）——本弹窗为设计稿 mock 预览，入口在「更多操作」禁用 + Tooltip「实验室管理后端建设中」。
 */
import { MapPin, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { cn } from '@/lib/utils'
import type { Laboratory, LaboratoryStatus } from '@/domain/models/laboratory'
import { LABORATORY_STATUS_META } from '@/domain/models/laboratory'
import { useLaboratoryMutations } from '@/application/devices/use-devices'

export interface LaboratoryManagerDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  labs: Laboratory[]
}

const STATUS_OPTIONS: ReadonlyArray<{ value: LaboratoryStatus; label: string }> = [
  { value: 'active', label: '启用' },
  { value: 'inactive', label: '停用' },
  { value: 'maintenance', label: '维护中' },
]

export function LaboratoryManagerDialog(props: LaboratoryManagerDialogProps) {
  const { create, remove } = useLaboratoryMutations()
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [building, setBuilding] = useState('')
  const [floor, setFloor] = useState('')
  const [roomNumber, setRoomNumber] = useState('')
  const [description, setDescription] = useState('')
  const [status, setStatus] = useState<LaboratoryStatus>('active')
  const [deleteTarget, setDeleteTarget] = useState<Laboratory | null>(null)

  const handleCreate = async () => {
    if (!name.trim() || !code.trim()) {
      toast.error('请填写实验室名称与代码')
      return
    }
    try {
      await create.mutateAsync({
        name: name.trim(),
        code: code.trim(),
        building: building || null,
        floor: floor || null,
        roomNumber: roomNumber || null,
        description: description || null,
        status,
      })
      toast.success('实验室已创建')
      setName('')
      setCode('')
      setBuilding('')
      setFloor('')
      setRoomNumber('')
      setDescription('')
    } catch {
      toast.error('操作失败，请稍后重试')
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await remove.mutateAsync(deleteTarget.id)
      toast.success('实验室已删除')
      setDeleteTarget(null)
    } catch {
      toast.error('删除失败，请重试')
    }
  }

  return (
    <>
      <Dialog open={props.open} onOpenChange={props.onOpenChange}>
        <DialogContent className='sm:max-w-3xl'>
          <DialogHeader>
            <DialogTitle>实验室管理</DialogTitle>
            <DialogDescription>
              管理物理实验室及其资源归属（设备/播放设备/用例），用于按实验室分组与测试资源过滤。
            </DialogDescription>
          </DialogHeader>

          <div className='flex flex-col gap-3'>
            {/* 新建实验室表单（§6.26） */}
            <div className='bg-card/50 grid grid-cols-3 items-end gap-2.5 rounded-lg border p-3'>
              <div className='flex flex-col gap-1'>
                <Label htmlFor='lab-name'>名称</Label>
                <Input id='lab-name' value={name} onChange={(e) => setName(e.target.value)} placeholder='如：声学实验室 A' className='h-8' />
              </div>
              <div className='flex flex-col gap-1'>
                <Label htmlFor='lab-code'>代码（唯一）</Label>
                <Input id='lab-code' value={code} onChange={(e) => setCode(e.target.value)} placeholder='LAB-A-01' className='h-8 font-mono' />
              </div>
              <div className='flex flex-col gap-1'>
                <Label htmlFor='lab-status'>状态</Label>
                <Select value={status} onValueChange={(value) => setStatus(value as LaboratoryStatus)}>
                  <SelectTrigger id='lab-status' size='sm' className='w-full'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {STATUS_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className='flex flex-col gap-1'>
                <Label htmlFor='lab-building'>所在楼栋</Label>
                <Input id='lab-building' value={building} onChange={(e) => setBuilding(e.target.value)} placeholder='研发中心东区' className='h-8' />
              </div>
              <div className='flex flex-col gap-1'>
                <Label htmlFor='lab-floor'>楼层</Label>
                <Input id='lab-floor' value={floor} onChange={(e) => setFloor(e.target.value)} placeholder='3 层' className='h-8' />
              </div>
              <div className='flex flex-col gap-1'>
                <Label htmlFor='lab-room'>房间号</Label>
                <Input id='lab-room' value={roomNumber} onChange={(e) => setRoomNumber(e.target.value)} placeholder='A301' className='h-8' />
              </div>
              <div className='col-span-3 flex flex-col gap-1'>
                <Label htmlFor='lab-desc'>描述</Label>
                <Input id='lab-desc' value={description} onChange={(e) => setDescription(e.target.value)} placeholder='选填' className='h-8' />
              </div>
              <div className='col-span-3 flex justify-end gap-2'>
                <Button variant='outline' size='sm' onClick={() => { setName(''); setCode(''); setBuilding(''); setFloor(''); setRoomNumber(''); setDescription('') }}>
                  取消
                </Button>
                <Button size='sm' className='gap-1' onClick={() => void handleCreate()}>
                  <Plus aria-hidden='true' className='size-3.5' />
                  新建实验室
                </Button>
              </div>
            </div>

            {/* 实验室列表（§6.26 DataTable） */}
            <div className='bg-card ring-foreground/10 overflow-hidden rounded-lg ring-1'>
              <div className='overflow-x-auto'>
                <table className='w-full min-w-[720px] text-xs'>
                  <thead>
                    <tr className='bg-[var(--table-header)]'>
                      <th className='px-2.5 py-1.5 text-left font-medium'>代码</th>
                      <th className='px-2.5 py-1.5 text-left font-medium'>名称</th>
                      <th className='px-2.5 py-1.5 text-left font-medium'>所在位置</th>
                      <th className='px-2.5 py-1.5 text-left font-medium'>状态</th>
                      <th className='px-2.5 py-1.5 text-right font-medium'>资源统计</th>
                      <th className='px-2.5 py-1.5 text-left font-medium'>更新时间</th>
                      <th className='w-14 px-2.5 py-1.5 text-right font-medium'>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {props.labs.length === 0 ? (
                      <tr>
                        <td colSpan={7} className='text-muted-foreground px-3 py-6 text-center'>
                          暂无实验室
                        </td>
                      </tr>
                    ) : (
                      props.labs.map((lab) => {
                        const statusMeta = LABORATORY_STATUS_META[lab.status]
                        const toneClass = {
                          success: 'text-success border-success/40 bg-success/10',
                          neutral: 'text-muted-foreground',
                          warning: 'text-warning border-warning/40 bg-warning/10',
                        }[statusMeta.tone]
                        return (
                          <tr key={lab.id} className='hover:bg-muted/40 border-border/50 border-b last:border-b-0'>
                            <td className='px-2.5 py-1.5 font-mono'>{lab.code}</td>
                            <td className='max-w-40 px-2.5 py-1.5'>
                              <span className='min-w-0 block truncate'>{lab.name}</span>
                              {lab.description && (
                                <span className='text-muted-foreground min-w-0 block truncate text-[11px]'>
                                  {lab.description}
                                </span>
                              )}
                            </td>
                            <td className='px-2.5 py-1.5'>
                              <span className='text-muted-foreground inline-flex items-center gap-1'>
                                <MapPin aria-hidden='true' className='size-3' />
                                {[lab.building, lab.floor, lab.roomNumber].filter(Boolean).join('·') || '—'}
                              </span>
                            </td>
                            <td className='px-2.5 py-1.5'>
                              <Badge variant='outline' className={cn('rounded-sm px-1 font-normal', toneClass)}>
                                {statusMeta.label}
                              </Badge>
                            </td>
                            <td className='px-2.5 py-1.5 text-right font-mono tabular-nums'>
                              设备 {lab.deviceCount} · 播放 {lab.playbackDeviceCount} · 用例 {lab.testCaseCount}
                            </td>
                            <td className='px-2.5 py-1.5 font-mono tabular-nums'>
                              {lab.updatedAt ? lab.updatedAt.replace('T', ' ').slice(0, 16) : '—'}
                            </td>
                            <td className='px-2.5 py-1.5 text-right'>
                              <Button
                                variant='ghost'
                                size='icon-sm'
                                className='size-6 text-destructive'
                                aria-label={`删除实验室 ${lab.name}`}
                                onClick={() => setDeleteTarget(lab)}
                              >
                                <Trash2 aria-hidden='true' className='size-3.5' />
                              </Button>
                            </td>
                          </tr>
                        )
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          <DialogFooter>
            <Button variant='outline' onClick={() => props.onOpenChange(false)}>
              关闭
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteTarget != null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title='删除实验室'
        desc={
          deleteTarget
            ? `删除实验室「${deleteTarget.name}」？该操作不可恢复（关联设备/用例将解除归属）。`
            : ''
        }
        destructive
        confirmText='删除'
        handleConfirm={() => void handleDelete()}
      />
    </>
  )
}
