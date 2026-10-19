/**
 * 设备分组管理弹窗（16_设备域.md §6.3；Dialog sm:max-w-2xl）。
 * 顶部新建表单（分组名称/分组类型 select[测试设备组·播放设备组]/分组描述 + 创建/取消）；
 * 分组列表（父级行展开子分组；节点行=分组名称/类型 Badge/设备数/
 * 操作[成员·复制·重命名·移动·删除]）；成员行内展开：成员标签（名称 + × 移出 + 勾选批量移除）+
 * 空态「暂无成员设备」+ 批量添加成员（多选设备 Dialog）+ 添加成员 select（仅 testDevices 可加——
 * DeviceGroupMember 只关联被测设备表，§11-5）。
 * INT-721 接线：全部增删改/成员操作走 device_bp /test-devices/device-groups 真实端点
 * （create/update/delete?cascade=true/add-devices/remove-devices），经 useDeviceGroupMutations
 * invalidate ['devices','groups'] 刷新列表（不再本地持有一份可漂移的分组状态）。
 * 嵌套分组/「移动」后端 device_group 无 parent_id 字段（§11-5 嵌套为前端 UI 稿）→ 待 FEAT，
 * 移动入口禁用 + Tooltip；children 恒空，树渲染保留为嵌套落地后的兼容。
 * P3-15 返修：播放设备组类型创建整项禁用 + Tooltip「播放设备分组暂未实装」。
 */
import { ChevronDown, ChevronRight, Copy, Move, Pencil, Plus, Trash2 } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { cn } from '@/lib/utils'
import type { DeviceGroup, DeviceGroupType } from '@/domain/models/deviceGroup'
import { DEVICE_GROUP_TYPE_META } from '@/domain/models/deviceGroup'
import type { TestDevice } from '@/domain/models/testDevice'
import { useDeviceGroupMutations } from '@/application/devices/use-devices'
import { ApiError } from '@/infrastructure/api/api-error'

export interface DeviceGroupManagerDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  groups: DeviceGroup[]
  testDevices: TestDevice[]
}

/** 批量添加成员弹窗（§6.3：多选设备批量加入） */
function BulkAddMembersDialog({
  open,
  devices,
  onClose,
  onConfirm,
}: {
  open: boolean
  devices: TestDevice[]
  onClose: () => void
  onConfirm: (deviceIds: number[]) => void
}) {
  const [selected, setSelected] = useState<Set<number>>(new Set())
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>批量添加成员</DialogTitle>
          <DialogDescription>勾选设备批量加入当前分组（仅测试设备可加，§11-5）。</DialogDescription>
        </DialogHeader>
        <div className='max-h-72 overflow-y-auto'>
          {devices.length === 0 ? (
            <p className='text-muted-foreground py-6 text-center text-sm'>暂无可用测试设备</p>
          ) : (
            <div className='flex flex-col gap-1'>
              {devices.map((device) => (
                <label key={device.id} className='hover:bg-muted/40 flex items-center gap-2 rounded-md px-2 py-1.5 text-sm'>
                  <Checkbox
                    checked={selected.has(device.id)}
                    onCheckedChange={(checked) =>
                      setSelected((prev) => {
                        const next = new Set(prev)
                        if (checked) next.add(device.id)
                        else next.delete(device.id)
                        return next
                      })
                    }
                  />
                  <span className='min-w-0 flex-1 truncate'>{device.name}</span>
                  <span className='text-muted-foreground font-mono text-xs'>#{device.id}</span>
                </label>
              ))}
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={onClose}>
            取消
          </Button>
          <Button
            disabled={selected.size === 0}
            onClick={() => {
              onConfirm([...selected])
              setSelected(new Set())
            }}
          >
            加入 {selected.size} 台设备
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** 移动分组入口（后端 device_group 无 parent_id，嵌套待 FEAT） */
function MoveDisabledMenuItem() {
  return (
    <Tooltip>
      <TooltipTrigger render={<DropdownMenuItem disabled className='gap-2' />}>
        <Move aria-hidden='true' className='size-3.5' />
        移动
      </TooltipTrigger>
      <TooltipContent>后端暂不支持分组嵌套（移动/子分组待 FEAT）</TooltipContent>
    </Tooltip>
  )
}

export function DeviceGroupManagerDialog(props: DeviceGroupManagerDialogProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [groupType, setGroupType] = useState<DeviceGroupType>('test')
  const [groupName, setGroupName] = useState('')
  const [groupDesc, setGroupDesc] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<DeviceGroup | null>(null)
  const [memberAdd, setMemberAdd] = useState<Record<string, string>>({})
  const [bulkAddTarget, setBulkAddTarget] = useState<DeviceGroup | null>(null)
  const [renameTarget, setRenameTarget] = useState<DeviceGroup | null>(null)
  const [renameValue, setRenameValue] = useState('')
  /** 成员批量移除勾选集（组 id → 勾选设备 id 集合） */
  const [removingMap, setRemovingMap] = useState<Record<string, Set<number>>>({})
  const { create, update, remove, addMembers, removeMembers } = useDeviceGroupMutations()
  const groups = props.groups

  const toggleRemoving = (groupId: string, deviceId: number) => {
    setRemovingMap((prev) => {
      const current = new Set(prev[groupId] ?? [])
      if (current.has(deviceId)) current.delete(deviceId)
      else current.add(deviceId)
      return { ...prev, [groupId]: current }
    })
  }

  const deviceName = (id: number) =>
    props.testDevices.find((d) => d.id === id)?.name ?? `设备 #${id}`

  const toggleExpand = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const errMessage = (err: unknown, fallback: string) =>
    err instanceof ApiError ? err.userMessage : fallback

  const handleCreate = async () => {
    if (!groupName.trim()) {
      toast.error('请填写分组名称')
      return
    }
    try {
      await create.mutateAsync({
        name: groupName.trim(),
        description: groupDesc || null,
        groupType,
        deviceIds: [],
      })
      toast.success('分组已创建')
      setGroupName('')
      setGroupDesc('')
    } catch (err) {
      toast.error(errMessage(err, '分组创建失败，请重试'))
    }
  }

  const addMember = async (groupId: string, deviceId: number) => {
    try {
      await addMembers.mutateAsync({ id: groupId, deviceIds: [deviceId] })
      toast.success('成员已添加')
    } catch (err) {
      toast.error(errMessage(err, '添加成员失败，请重试'))
    }
  }

  const removeMember = async (groupId: string, deviceId: number) => {
    try {
      await removeMembers.mutateAsync({ id: groupId, deviceIds: [deviceId] })
      toast.success('成员已移出')
    } catch (err) {
      toast.error(errMessage(err, '移出成员失败，请重试'))
    }
  }

  const removeMembersBatch = async (groupId: string, deviceIds: number[]) => {
    try {
      await removeMembers.mutateAsync({ id: groupId, deviceIds })
      toast.success(`已移出 ${deviceIds.length} 台设备`)
    } catch (err) {
      toast.error(errMessage(err, '移出成员失败，请重试'))
    }
  }

  const addMembersBatch = async (groupId: string, deviceIds: number[]) => {
    try {
      await addMembers.mutateAsync({ id: groupId, deviceIds })
      toast.success(`已加入 ${deviceIds.length} 台设备`)
    } catch (err) {
      toast.error(errMessage(err, '添加成员失败，请重试'))
    }
  }

  /** 复制分组「{name}（副本）」+ 成员 + 描述（后端无 copy 端点 → 复用 create 带 device_ids，§6.3） */
  const copyGroup = async (group: DeviceGroup) => {
    try {
      await create.mutateAsync({
        name: `${group.name}（副本）`,
        description: group.description,
        groupType: group.groupType,
        deviceIds: group.members,
      })
      toast.success(`已复制分组「${group.name}」`)
    } catch (err) {
      toast.error(errMessage(err, '复制分组失败，请重试'))
    }
  }

  const renameGroup = async () => {
    if (!renameTarget) return
    if (!renameValue.trim()) {
      toast.error('请填写分组名称')
      return
    }
    try {
      await update.mutateAsync({
        id: renameTarget.id,
        patch: { name: renameValue.trim(), description: renameTarget.description },
      })
      toast.success('分组已重命名')
      setRenameTarget(null)
    } catch (err) {
      toast.error(errMessage(err, '重命名失败，请重试'))
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      // cascade=true：删除分组会把设备移出分组（设备本身保留），与确认文案一致
      await remove.mutateAsync(deleteTarget.id)
      toast.success('分组已删除')
      setDeleteTarget(null)
    } catch (err) {
      toast.error(errMessage(err, '删除失败，请重试'))
    }
  }

  const renderGroup = (group: DeviceGroup, depth: number) => {
    const isExpanded = expanded.has(group.id)
    const typeMeta = DEVICE_GROUP_TYPE_META[group.groupType]
    const memberCount = group.members.length
    const removing = removingMap[group.id] ?? new Set<number>()
    return (
      <div key={group.id} className='flex flex-col'>
        <div
          className={cn(
            'hover:bg-muted/40 flex items-center gap-2 rounded-md px-2 py-1.5',
            depth > 0 && 'ms-4'
          )}
        >
          <button
            type='button'
            className='flex min-w-0 flex-1 items-center gap-1.5 text-start'
            onClick={() => toggleExpand(group.id)}
            aria-expanded={isExpanded}
          >
            {isExpanded ? (
              <ChevronDown aria-hidden='true' className='text-muted-foreground size-3.5 shrink-0' />
            ) : (
              <ChevronRight aria-hidden='true' className='text-muted-foreground size-3.5 shrink-0' />
            )}
            <span className='min-w-0 flex-1 truncate text-sm'>{group.name}</span>
          </button>
          <Badge variant='outline' className='rounded-sm px-1 font-normal'>
            {typeMeta.label}
          </Badge>
          <span className='text-muted-foreground w-10 text-right text-xs tabular-nums'>
            {memberCount} 台
          </span>
          {/* 分组操作（复制/重命名/移动/删除） */}
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <Button variant='ghost' size='icon-sm' className='size-6' aria-label={`分组操作 ${group.name}`} />
              }
            >
              <MoreDots />
            </DropdownMenuTrigger>
            <DropdownMenuContent align='end' className='w-40'>
              <DropdownMenuItem onClick={() => void copyGroup(group)}>
                <Copy aria-hidden='true' className='size-3.5' />
                复制
              </DropdownMenuItem>
              <DropdownMenuItem
                onClick={() => {
                  setRenameTarget(group)
                  setRenameValue(group.name)
                }}
              >
                <Pencil aria-hidden='true' className='size-3.5' />
                重命名
              </DropdownMenuItem>
              <MoveDisabledMenuItem />
              <DropdownMenuSeparator />
              <DropdownMenuItem
                variant='destructive'
                onClick={() => setDeleteTarget(group)}
              >
                <Trash2 aria-hidden='true' className='size-3.5' />
                删除
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {isExpanded && (
          <div className={cn('border-border/60 mt-0.5 flex flex-col gap-1 border-l pl-3', depth > 0 && 'ms-8')}>
            {/* 成员标签（可勾选批量移除） */}
            {group.members.length === 0 ? (
              <p className='text-muted-foreground px-2 py-1 text-xs'>暂无成员设备</p>
            ) : (
              <>
                {group.members.map((deviceId) => (
                  <span
                    key={deviceId}
                    className='inline-flex w-fit items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs'
                  >
                    <Checkbox
                      checked={removing.has(deviceId)}
                      onCheckedChange={() => toggleRemoving(group.id, deviceId)}
                      aria-label={`勾选 ${deviceName(deviceId)}`}
                    />
                    {deviceName(deviceId)}
                    <button
                      type='button'
                      className='text-muted-foreground hover:text-destructive'
                      aria-label={`移出 ${deviceName(deviceId)}`}
                      onClick={() => void removeMember(group.id, deviceId)}
                    >
                      ×
                    </button>
                  </span>
                ))}
                {removing.size > 0 && (
                  <Button
                    variant='ghost'
                    size='sm'
                    className='h-6 w-fit px-1.5 text-xs text-destructive'
                    onClick={() => {
                      void removeMembersBatch(group.id, [...removing])
                      setRemovingMap((prev) => ({ ...prev, [group.id]: new Set() }))
                    }}
                  >
                    批量移除 {removing.size} 台
                  </Button>
                )}
              </>
            )}
            {/* 批量添加成员 + 单个添加（仅测试设备组；播放设备组禁用 + Tooltip §11-5） */}
            {group.groupType === 'test' ? (
              <span className='flex items-center gap-1.5 py-0.5'>
                <Select
                  value={memberAdd[group.id] ?? ''}
                  onValueChange={(value) => {
                    const deviceId = Number(value)
                    if (deviceId) void addMember(group.id, deviceId)
                    setMemberAdd((prev) => ({ ...prev, [group.id]: '' }))
                  }}
                >
                  <SelectTrigger size='sm' className='w-44'>
                    <SelectValue placeholder='添加成员设备' />
                  </SelectTrigger>
                  <SelectContent>
                    {props.testDevices.map((device) => (
                      <SelectItem key={device.id} value={String(device.id)}>
                        {device.name}（#{device.id}）
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button variant='ghost' size='icon-sm' className='size-6' aria-label='添加成员'>
                  <Plus aria-hidden='true' className='size-3.5' />
                </Button>
                <Button
                  variant='outline'
                  size='sm'
                  className='h-7 gap-1 text-xs'
                  onClick={() => setBulkAddTarget(group)}
                >
                  批量添加成员
                </Button>
              </span>
            ) : (
              <Tooltip>
                <TooltipTrigger render={<span className='py-0.5 text-xs opacity-50' />}>
                  播放设备组成员暂未实装
                </TooltipTrigger>
                <TooltipContent>播放设备分组暂未实装</TooltipContent>
              </Tooltip>
            )}
          </div>
        )}

        {group.children.map((child) => renderGroup(child, depth + 1))}
      </div>
    )
  }

  return (
    <>
      <Dialog open={props.open} onOpenChange={props.onOpenChange}>
        <DialogContent className='sm:max-w-2xl'>
          <DialogHeader>
            <DialogTitle>设备分组管理</DialogTitle>
            <DialogDescription>按场景组织测试设备，便于批量操作与筛选。</DialogDescription>
          </DialogHeader>

          <div className='flex flex-col gap-3'>
            {/* 顶部新建表单（§6.3；P3-15 播放设备组类型禁用） */}
            <div className='bg-card/50 grid grid-cols-2 items-end gap-2.5 rounded-lg border p-3'>
              <div className='flex flex-col gap-1'>
                <Label htmlFor='group-name'>分组名称</Label>
                <Input id='group-name' value={groupName} onChange={(e) => setGroupName(e.target.value)} placeholder='如：客厅场景组' className='h-8' />
              </div>
              <div className='flex flex-col gap-1'>
                <Label htmlFor='group-type'>分组类型</Label>
                <Tooltip>
                  <TooltipTrigger
                    render={
                      <Select
                        value={groupType}
                        onValueChange={(value) => setGroupType(value as DeviceGroupType)}
                      >
                        <SelectTrigger id='group-type' size='sm' className='w-full'>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value='test'>测试设备组</SelectItem>
                          <SelectItem value='playback' disabled>
                            播放设备组
                          </SelectItem>
                        </SelectContent>
                      </Select>
                    }
                  />
                  <TooltipContent>播放设备分组暂未实装</TooltipContent>
                </Tooltip>
              </div>
              <div className='col-span-2 flex flex-col gap-1'>
                <Label htmlFor='group-desc'>分组描述</Label>
                <Input id='group-desc' value={groupDesc} onChange={(e) => setGroupDesc(e.target.value)} placeholder='选填' className='h-8' />
              </div>
              <div className='col-span-2 flex justify-end gap-2'>
                <Button variant='outline' size='sm' onClick={() => { setGroupName(''); setGroupDesc('') }}>
                  取消
                </Button>
                <Button size='sm' onClick={() => void handleCreate()}>
                  创建
                </Button>
              </div>
            </div>

            {/* 分组列表（嵌套展开；后端扁平、children 恒空，树渲染为嵌套落地兼容） */}
            <div className='bg-card ring-foreground/10 max-h-80 overflow-y-auto rounded-lg ring-1 p-1'>
              {groups.length === 0 ? (
                <p className='text-muted-foreground px-3 py-8 text-center text-sm'>暂无分组</p>
              ) : (
                groups.map((group) => renderGroup(group, 0))
              )}
            </div>
          </div>

          <DialogFooter>
            <Button variant='outline' onClick={() => props.onOpenChange(false)}>
              关闭
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 批量添加成员（§6.3） */}
      {bulkAddTarget && (
        <BulkAddMembersDialog
          open
          devices={props.testDevices}
          onClose={() => setBulkAddTarget(null)}
          onConfirm={(deviceIds) => {
            void addMembersBatch(bulkAddTarget.id, deviceIds)
            setBulkAddTarget(null)
          }}
        />
      )}

      {/* 重命名（§6.3） */}
      <Dialog open={renameTarget != null} onOpenChange={(open) => !open && setRenameTarget(null)}>
        <DialogContent className='sm:max-w-sm'>
          <DialogHeader>
            <DialogTitle>重命名分组</DialogTitle>
            <DialogDescription>修改分组名称，保存后即时生效。</DialogDescription>
          </DialogHeader>
          <Input
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            placeholder='分组名称'
            className='h-8'
          />
          <DialogFooter>
            <Button variant='outline' onClick={() => setRenameTarget(null)}>
              取消
            </Button>
            <Button onClick={() => void renameGroup()}>保存</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteTarget != null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title='删除分组'
        desc={
          deleteTarget
            ? deleteTarget.members.length > 0
              ? `分组「${deleteTarget.name}」包含 ${deleteTarget.members.length} 个设备。删除分组会把设备移出分组（设备本身保留），确定删除吗？`
              : `确定要删除分组「${deleteTarget.name}」吗？`
            : ''
        }
        destructive
        confirmText='删除'
        handleConfirm={() => void handleDelete()}
      />
    </>
  )
}

/** 分组行更多操作三点图标 */
function MoreDots() {
  return (
    <span className='flex items-center gap-0.5' aria-hidden='true'>
      <span className='size-0.5 rounded-full bg-current' />
      <span className='size-0.5 rounded-full bg-current' />
      <span className='size-0.5 rounded-full bg-current' />
    </span>
  )
}
