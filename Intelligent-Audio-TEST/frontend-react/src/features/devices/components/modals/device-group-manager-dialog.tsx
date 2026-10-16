/**
 * 设备分组管理弹窗（16_设备域.md §6.3；Dialog sm:max-w-2xl）。
 * 顶部新建表单（分组名称（必填）/分组类型 select[测试设备组·播放设备组]/分组描述 + 创建/取消）；
 * 分组列表（嵌套分组：父级行 ChevronRight 展开子分组；节点行=分组名称/类型 Badge/设备数/
 * 操作[成员·删除]）；成员行内展开：成员标签（名称 + × 移出）+ 空态「暂无成员设备」+
 * 添加成员 select（仅 testDevices 可加——DeviceGroupMember 只关联被测设备表，§11-5；
 * 播放设备组类型整项禁用 + Tooltip「播放设备分组暂未实装」）。
 * 删除 ConfirmDialog destructive（含成员时走 cascade=true 口径文案）。
 */
import { ChevronDown, ChevronRight, Plus, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
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
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from '@/components/ui/tooltip'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { cn } from '@/lib/utils'
import type { DeviceGroup } from '@/domain/models/deviceGroup'
import { DEVICE_GROUP_TYPE_META } from '@/domain/models/deviceGroup'
import type { TestDevice } from '@/domain/models/testDevice'

export interface DeviceGroupManagerDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  groups: DeviceGroup[]
  testDevices: TestDevice[]
}

export function DeviceGroupManagerDialog(props: DeviceGroupManagerDialogProps) {
  const [expanded, setExpanded] = useState<Set<number>>(new Set([2]))
  const [groupType, setGroupType] = useState<'test' | 'playback'>('test')
  const [groupName, setGroupName] = useState('')
  const [groupDesc, setGroupDesc] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<DeviceGroup | null>(null)
  const [memberAdd, setMemberAdd] = useState<Record<number, string>>({})

  // mock 内存分组（页面内新建/删成员即时可见）；随 props.groups 查询加载后同步
  const [groups, setGroups] = useState<DeviceGroup[]>(props.groups)

  useEffect(() => {
    if (props.open) setGroups(props.groups)
  }, [props.groups, props.open])

  const toggleExpand = (id: number) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const deviceName = useMemo(
    () => (id: number) => props.testDevices.find((d) => d.id === id)?.name ?? `设备 #${id}`,
    [props.testDevices]
  )

  const handleCreate = () => {
    if (!groupName.trim()) {
      toast.error('请填写分组名称')
      return
    }
    setGroups((prev) => [
      {
        id: Math.max(0, ...prev.map((g) => g.id)) + 1,
        name: groupName.trim(),
        description: groupDesc || null,
        groupType,
        members: [],
        children: [],
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
      },
      ...prev,
    ])
    toast.success('分组已创建')
    setGroupName('')
    setGroupDesc('')
  }

  const addMember = (groupId: number, deviceId: number) => {
    setGroups((prev) =>
      prev.map((g) =>
        g.id === groupId ? { ...g, members: g.members.includes(deviceId) ? g.members : [...g.members, deviceId] } : g
      )
    )
  }

  const removeMember = (groupId: number, deviceId: number) => {
    setGroups((prev) =>
      prev.map((g) => (g.id === groupId ? { ...g, members: g.members.filter((id) => id !== deviceId) } : g))
    )
  }

  const handleDelete = () => {
    if (!deleteTarget) return
    setGroups((prev) => prev.filter((g) => g.id !== deleteTarget.id))
    toast.success('分组已删除')
    setDeleteTarget(null)
  }

  const renderGroup = (group: DeviceGroup, depth: number) => {
    const isExpanded = expanded.has(group.id)
    const typeMeta = DEVICE_GROUP_TYPE_META[group.groupType]
    const memberCount = group.members.length
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
          <Button
            variant='ghost'
            size='icon-sm'
            className='size-6 text-destructive'
            aria-label={`删除分组 ${group.name}`}
            onClick={() => setDeleteTarget(group)}
          >
            <Trash2 aria-hidden='true' className='size-3.5' />
          </Button>
        </div>

        {isExpanded && (
          <div className={cn('border-border/60 mt-0.5 flex flex-col gap-1 border-l pl-3', depth > 0 && 'ms-8')}>
            {/* 成员标签 */}
            {group.members.length === 0 ? (
              <p className='text-muted-foreground px-2 py-1 text-xs'>暂无成员设备</p>
            ) : (
              group.members.map((deviceId) => (
                <span key={deviceId} className='inline-flex w-fit items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs'>
                  {deviceName(deviceId)}
                  <button
                    type='button'
                    className='text-muted-foreground hover:text-destructive'
                    aria-label={`移出 ${deviceName(deviceId)}`}
                    onClick={() => removeMember(group.id, deviceId)}
                  >
                    ×
                  </button>
                </span>
              ))
            )}
            {/* 添加成员（仅测试设备组；播放设备组禁用 + Tooltip §11-5） */}
            {group.groupType === 'test' ? (
              <span className='flex items-center gap-1.5 py-0.5'>
                <Select
                  value={memberAdd[group.id] ?? ''}
                  onValueChange={(value) => {
                    const deviceId = Number(value)
                    if (deviceId) addMember(group.id, deviceId)
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
            {/* 顶部新建表单（§6.3） */}
            <div className='bg-card/50 grid grid-cols-2 items-end gap-2.5 rounded-lg border p-3'>
              <div className='flex flex-col gap-1'>
                <Label htmlFor='group-name'>分组名称</Label>
                <Input id='group-name' value={groupName} onChange={(e) => setGroupName(e.target.value)} placeholder='如：客厅场景组' className='h-8' />
              </div>
              <div className='flex flex-col gap-1'>
                <Label htmlFor='group-type'>分组类型</Label>
                <Select value={groupType} onValueChange={(value) => setGroupType(value as 'test' | 'playback')}>
                  <SelectTrigger id='group-type' size='sm' className='w-full'>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value='test'>测试设备组</SelectItem>
                    <SelectItem value='playback'>播放设备组</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className='col-span-2 flex flex-col gap-1'>
                <Label htmlFor='group-desc'>分组描述</Label>
                <Input id='group-desc' value={groupDesc} onChange={(e) => setGroupDesc(e.target.value)} placeholder='选填' className='h-8' />
              </div>
              <div className='col-span-2 flex justify-end gap-2'>
                <Button variant='outline' size='sm' onClick={() => { setGroupName(''); setGroupDesc('') }}>
                  取消
                </Button>
                <Button size='sm' onClick={handleCreate}>
                  创建
                </Button>
              </div>
            </div>

            {/* 分组列表（嵌套展开） */}
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
        handleConfirm={handleDelete}
      />
    </>
  )
}
