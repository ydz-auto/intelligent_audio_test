/**
 * 实验室管理弹窗（16_设备域.md §6.26/INT-487；Dialog sm:max-w-3xl）。
 * 标题「实验室管理」+ 说明「管理物理实验室及其资源归属（设备/播放设备/用例），用于按实验室
 * 分组与测试资源过滤」；实验室列表（代码 mono/名称/所在位置「{building}·{floor}·{room_number}」/
 * 状态 StatusBadge（active=success 启用/inactive=neutral 停用/maintenance=warning 维护中）/
 * 资源统计 tabular「设备 {n} · 播放 {m} · 用例 {k}」/更新时间/操作[编辑·删除]）+
 * 新建实验室表单（名称（必填）/代码（必填）/所在楼栋/楼层/房间号/描述/状态）。
 * 数据契约 INT-655：GET/POST/PUT/DELETE /api/v1/laboratories 真实端点（laboratory_bp.py），
 * 入口在「更多操作 → 实验室管理」可用；集合由 useLaboratories 查询 + 增删改后失效重拉。
 */
import { MapPin, Pencil, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
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
import { ApiError } from '@/infrastructure/api/api-error'
import { StaticDataTable } from '@/features/system-settings/components/static-data-table'
import { cn } from '@/lib/utils'
import { formatDateTime } from '@/lib/date-time'
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
  const { create, remove, update } = useLaboratoryMutations()
  const [editing, setEditing] = useState<Laboratory | null>(null)
  const [name, setName] = useState('')
  const [code, setCode] = useState('')
  const [building, setBuilding] = useState('')
  const [floor, setFloor] = useState('')
  const [roomNumber, setRoomNumber] = useState('')
  const [description, setDescription] = useState('')
  const [status, setStatus] = useState<LaboratoryStatus>('active')
  const [deleteTarget, setDeleteTarget] = useState<Laboratory | null>(null)

  const resetForm = () => {
    setEditing(null)
    setName('')
    setCode('')
    setBuilding('')
    setFloor('')
    setRoomNumber('')
    setDescription('')
    setStatus('active')
  }

  // 每次打开重置表单
  useEffect(() => {
    if (props.open) resetForm()
  }, [props.open])

  /** P3-21 返修：编辑实验室（§6.26 列表操作 [编辑·删除]） */
  const startEdit = (lab: Laboratory) => {
    setEditing(lab)
    setName(lab.name)
    setCode(lab.code)
    setBuilding(lab.building ?? '')
    setFloor(lab.floor ?? '')
    setRoomNumber(lab.roomNumber ?? '')
    setDescription(lab.description ?? '')
    setStatus(lab.status)
  }

  const handleSubmit = async () => {
    if (!name.trim() || !code.trim()) {
      toast.error('请填写实验室名称与代码')
      return
    }
    try {
      if (editing) {
        await update.mutateAsync({
          id: editing.id,
          patch: {
            name: name.trim(),
            code: code.trim(),
            building: building || null,
            floor: floor || null,
            roomNumber: roomNumber || null,
            description: description || null,
            status,
          },
        })
        toast.success('实验室已更新')
      } else {
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
      }
      resetForm()
    } catch (error) {
      // 后端业务文案（code 冲突 409 等）经 ApiError.userMessage 直呈
      toast.error(error instanceof ApiError ? error.userMessage : '操作失败，请稍后重试')
    }
  }

  /** P2-A 返修：deleteLaboratory 把 404/409/403 等非 2xx 收敛为 success:false 而不抛异常，
   *  必须按返回值分流，不能无条件提示「已删除」（与同页设备删除同口径）。 */
  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      const result = await remove.mutateAsync(deleteTarget.id)
      if (result.success) {
        toast.success('实验室已删除')
        setDeleteTarget(null)
      } else {
        toast.error(result.message ?? '删除失败，请重试')
      }
    } catch (error) {
      toast.error(error instanceof ApiError ? error.userMessage : '删除失败，请重试')
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
                <Select
                  value={status}
                  items={[...STATUS_OPTIONS]}
                  onValueChange={(value) => setStatus(value as LaboratoryStatus)}
                >
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
                {editing ? (
                  <Button variant='ghost' size='sm' onClick={resetForm}>
                    取消编辑
                  </Button>
                ) : (
                  <Button variant='outline' size='sm' onClick={resetForm}>
                    取消
                  </Button>
                )}
                <Button size='sm' className='gap-1' onClick={() => void handleSubmit()}>
                  <Plus aria-hidden='true' className='size-3.5' />
                  {editing ? '保存修改' : '新建实验室'}
                </Button>
              </div>
            </div>

            {/* 实验室列表（§6.26 DataTable；P3-27 返修：复用 StaticDataTable） */}
            <StaticDataTable
              columns={[
                {
                  key: 'code',
                  header: '代码',
                  className: 'font-mono',
                  render: (lab: Laboratory) => lab.code,
                },
                {
                  key: 'name',
                  header: '名称',
                  className: 'max-w-40',
                  render: (lab: Laboratory) => (
                    <>
                      <span className='min-w-0 block truncate'>{lab.name}</span>
                      {lab.description && (
                        <span className='text-muted-foreground min-w-0 block truncate text-[11px]'>
                          {lab.description}
                        </span>
                      )}
                    </>
                  ),
                },
                {
                  key: 'location',
                  header: '所在位置',
                  render: (lab: Laboratory) => (
                    <span className='text-muted-foreground inline-flex items-center gap-1'>
                      <MapPin aria-hidden='true' className='size-3' />
                      {[lab.building, lab.floor, lab.roomNumber].filter(Boolean).join('·') || '—'}
                    </span>
                  ),
                },
                {
                  key: 'status',
                  header: '状态',
                  render: (lab: Laboratory) => {
                    const statusMeta = LABORATORY_STATUS_META[lab.status]
                    const toneClass = {
                      success: 'text-success border-success/40 bg-success/10',
                      neutral: 'text-muted-foreground',
                      warning: 'text-warning border-warning/40 bg-warning/10',
                    }[statusMeta.tone]
                    return (
                      <Badge variant='outline' className={cn('rounded-sm px-1 font-normal', toneClass)}>
                        {statusMeta.label}
                      </Badge>
                    )
                  },
                },
                {
                  key: 'resources',
                  header: '资源统计',
                  className: 'text-right font-mono tabular-nums',
                  render: (lab: Laboratory) =>
                    `设备 ${lab.deviceCount} · 播放 ${lab.playbackDeviceCount} · 用例 ${lab.testCaseCount}`,
                },
                {
                  key: 'updatedAt',
                  header: '更新时间',
                  className: 'font-mono tabular-nums',
                  render: (lab: Laboratory) =>
                    formatDateTime(lab.updatedAt),
                },
              ]}
              rows={props.labs}
              rowKey={(lab) => String(lab.id)}
              emptyText='暂无实验室'
              minWidth='720px'
              actions={(lab) => (
                <span className='flex items-center justify-end gap-1'>
                  <Button
                    variant='ghost'
                    size='icon-sm'
                    className='size-6'
                    aria-label={`编辑实验室 ${lab.name}`}
                    onClick={() => startEdit(lab)}
                  >
                    <Pencil aria-hidden='true' className='size-3.5' />
                  </Button>
                  <Button
                    variant='ghost'
                    size='icon-sm'
                    className='size-6 text-destructive'
                    aria-label={`删除实验室 ${lab.name}`}
                    onClick={() => setDeleteTarget(lab)}
                  >
                    <Trash2 aria-hidden='true' className='size-3.5' />
                  </Button>
                </span>
              )}
            />
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
