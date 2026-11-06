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
 * INT-864（承接 INT-832）：后端 device_groups 增加 parent_id——「移动」接真实端点
 * PUT /test-devices/device-groups/{id}/move（目标父分组选择器，根=移到顶层），
 * 分组树按后端 parent_id 建（列表接口扁平分页、children 由 adapter 建树），
 * 删除确认按 INT-832 决策 2 升级（含子分组数，cascade=true 软删整棵子树、设备保留）。
 * P3-15 返修：播放设备组类型创建整项禁用 + Tooltip「播放设备分组暂未实装」。
 */
import { ChevronDown, ChevronRight, Copy, Move, Pencil, Plus, Trash2 } from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import { useQueryClient } from '@tanstack/react-query'

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
import { fetchDeviceGroupDetail } from '@/infrastructure/api/devicesApi'
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

export function DeviceGroupManagerDialog(props: DeviceGroupManagerDialogProps) {
  const queryClient = useQueryClient()
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  /** P2-1：展开时按需拉取的分组详情成员（组 id → 真实 device_ids；列表 device_ids 恒空） */
  const [detailMembers, setDetailMembers] = useState<Record<string, number[]>>({})
  const [groupType, setGroupType] = useState<DeviceGroupType>('test')
  const [groupName, setGroupName] = useState('')
  const [groupDesc, setGroupDesc] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<DeviceGroup | null>(null)
  const [memberAdd, setMemberAdd] = useState<Record<string, string>>({})
  const [bulkAddTarget, setBulkAddTarget] = useState<DeviceGroup | null>(null)
  const [renameTarget, setRenameTarget] = useState<DeviceGroup | null>(null)
  const [renameValue, setRenameValue] = useState('')
  /** INT-864：移动分组目标（null=弹窗关闭；'__root__'=根/顶层，否则为目标父分组 id） */
  const [moveTarget, setMoveTarget] = useState<DeviceGroup | null>(null)
  const [moveParent, setMoveParent] = useState('')
  /** 成员批量移除勾选集（组 id → 勾选设备 id 集合） */
  const [removingMap, setRemovingMap] = useState<Record<string, Set<number>>>({})
  const { create, update, move, remove, addMembers, removeMembers } = useDeviceGroupMutations()
  const groups = props.groups

  /** P2-1：拉取分组详情真实成员（已拉取过不重复；失败回落到列表 device_ids） */
  const ensureMembers = async (group: DeviceGroup): Promise<number[]> => {
    if (detailMembers[group.id] != null) return detailMembers[group.id]
    try {
      const detail = await queryClient.fetchQuery({
        queryKey: ['devices', 'groups', group.id],
        queryFn: () => fetchDeviceGroupDetail(group.id),
      })
      setDetailMembers((prev) =>
        prev[group.id] != null ? prev : { ...prev, [group.id]: detail.members }
      )
      return detail.members
    } catch {
      // 详情拉取失败不阻塞展开：成员标签回落列表 device_ids（可能为空）
      setDetailMembers((prev) =>
        prev[group.id] != null ? prev : { ...prev, [group.id]: group.members }
      )
      return group.members
    }
  }

  /** P2-1：成员增删成功后清缓存并（展开中）重拉详情，保证标签与计数一致 */
  const refreshMembers = (groupId: string) => {
    setDetailMembers((prev) => {
      const next = { ...prev }
      delete next[groupId]
      return next
    })
    const group = groups.find((g) => g.id === groupId)
    if (group && expanded.has(groupId)) {
      // 展开中：直接重拉详情并回填（不经过 ensureMembers，避免读到旧 state 闭包）
      void queryClient
        .fetchQuery({
          queryKey: ['devices', 'groups', groupId],
          queryFn: () => fetchDeviceGroupDetail(groupId),
        })
        .then((detail) => setDetailMembers((prev) => ({ ...prev, [groupId]: detail.members })))
        .catch(() => {
          // 重拉失败：保持当前展示（计数以列表 device_count 为准）
        })
    }
  }

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
    const expanding = !expanded.has(id)
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
    // P2-1：展开时按需拉取详情真实成员（列表 device_ids 恒空）
    if (expanding) {
      const group = groups.find((g) => g.id === id)
      if (group) void ensureMembers(group)
    }
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
      refreshMembers(groupId)
    } catch (err) {
      toast.error(errMessage(err, '添加成员失败，请重试'))
    }
  }

  const removeMember = async (groupId: string, deviceId: number) => {
    try {
      await removeMembers.mutateAsync({ id: groupId, deviceIds: [deviceId] })
      toast.success('成员已移出')
      refreshMembers(groupId)
    } catch (err) {
      toast.error(errMessage(err, '移出成员失败，请重试'))
    }
  }

  const removeMembersBatch = async (groupId: string, deviceIds: number[]) => {
    try {
      await removeMembers.mutateAsync({ id: groupId, deviceIds })
      toast.success(`已移出 ${deviceIds.length} 台设备`)
      refreshMembers(groupId)
    } catch (err) {
      toast.error(errMessage(err, '移出成员失败，请重试'))
    }
  }

  const addMembersBatch = async (groupId: string, deviceIds: number[]) => {
    try {
      await addMembers.mutateAsync({ id: groupId, deviceIds })
      toast.success(`已加入 ${deviceIds.length} 台设备`)
      refreshMembers(groupId)
    } catch (err) {
      toast.error(errMessage(err, '添加成员失败，请重试'))
    }
  }

  /** 复制分组「{name}（副本）」+ 成员 + 描述（后端无 copy 端点 → 复用 create 带 device_ids，§6.3） */
  const copyGroup = async (group: DeviceGroup) => {
    // P2-1：复制成员走详情真实 device_ids（列表恒空）
    const members = await ensureMembers(group)
    try {
      await create.mutateAsync({
        name: `${group.name}（副本）`,
        description: group.description,
        groupType: group.groupType,
        deviceIds: members,
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

  /** INT-864：移动分组到目标父级/根（PUT /test-devices/device-groups/{id}/move；成功刷新分组树） */
  const handleMove = async () => {
    if (!moveTarget) return
    try {
      await move.mutateAsync({
        id: moveTarget.id,
        parentId: moveParent === '__root__' ? null : moveParent,
      })
      toast.success(`分组「${moveTarget.name}」已移动`)
      setMoveTarget(null)
    } catch (err) {
      toast.error(errMessage(err, '移动分组失败，请重试'))
    }
  }

  /** INT-864：移动目标候选 = 全部分组（扁平）去掉自身及后代（环检测前端拦截，与后端 400 一致） */
  const moveTargetOptions = useMemo(() => {
    if (!moveTarget) return []
    const excluded = new Set<string>()
    const collect = (group: DeviceGroup) => {
      excluded.add(group.id)
      group.children.forEach(collect)
    }
    collect(moveTarget)
    const options: { id: string; label: string }[] = []
    const walk = (group: DeviceGroup, depth: number) => {
      if (group.id !== moveTarget.id) options.push({ id: group.id, label: `${'　'.repeat(depth)}${group.name}` })
      group.children.forEach((child) => walk(child, depth + 1))
    }
    groups.forEach((group) => walk(group, 0))
    return options.filter((o) => !excluded.has(o.id))
  }, [groups, moveTarget])

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
    // P2-1：列表 device_count 为真实成员数；成员标签用详情 device_ids（展开时按需拉取）
    const memberCount = group.memberCount
    const effectiveMembers = detailMembers[group.id] ?? group.members
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
              <DropdownMenuItem
                onClick={() => {
                  setMoveTarget(group)
                  setMoveParent('__root__')
                }}
              >
                <Move aria-hidden='true' className='size-3.5' />
                移动
              </DropdownMenuItem>
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
            {/* 成员标签（可勾选批量移除）——列表 device_ids 恒空，以详情真实成员为准 */}
            {effectiveMembers.length === 0 ? (
              <p className='text-muted-foreground px-2 py-1 text-xs'>暂无成员设备</p>
            ) : (
              <>
                {effectiveMembers.map((deviceId) => (
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
                  items={props.testDevices.map((device) => ({
                    value: String(device.id),
                    label: `${device.name}（#${device.id}）`,
                  }))}
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
                        items={[
                          { value: 'test', label: '测试设备组' },
                          { value: 'playback', label: '播放设备组' },
                        ]}
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

            {/* 分组列表（INT-864：按后端 parent_id 建树；父级行展开子分组） */}
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

      {/* 移动分组（INT-864；目标父分组选择器，根 = 移到顶层） */}
      <Dialog open={moveTarget != null} onOpenChange={(open) => !open && setMoveTarget(null)}>
        <DialogContent className='sm:max-w-sm'>
          <DialogHeader>
            <DialogTitle>移动分组</DialogTitle>
            <DialogDescription>
              将分组「{moveTarget?.name ?? ''}」移动到目标父分组下，选「根/顶层」则移到根。
            </DialogDescription>
          </DialogHeader>
          <div className='flex flex-col gap-1.5'>
            <Label htmlFor='move-parent'>目标父分组</Label>
            <Select
              value={moveParent}
              onValueChange={(value) => setMoveParent(value ?? '__root__')}
              items={[
                { value: '__root__', label: '根/顶层' },
                ...moveTargetOptions.map((o) => ({ value: o.id, label: o.label })),
              ]}
            >
              <SelectTrigger id='move-parent' size='sm' className='w-full'>
                <SelectValue placeholder='选择目标父分组' />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value='__root__'>根/顶层</SelectItem>
                {moveTargetOptions.map((option) => (
                  <SelectItem key={option.id} value={option.id}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant='outline' onClick={() => setMoveTarget(null)}>
              取消
            </Button>
            <Button onClick={() => void handleMove()}>移动</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={deleteTarget != null}
        onOpenChange={(open) => !open && setDeleteTarget(null)}
        title='删除分组'
        desc={deleteTarget ? deleteGroupConfirmCopy(deleteTarget) : ''}
        destructive
        confirmText='删除'
        handleConfirm={() => void handleDelete()}
      />
    </>
  )
}

/** INT-864 决策 2：整棵子树的分组数（含全部后代，用于删除确认文案） */
function subtreeGroupCount(group: DeviceGroup): number {
  let count = 0
  for (const child of group.children) count += 1 + subtreeGroupCount(child)
  return count
}

/** 删除分组确认文案（INT-832 决策 2：含子分组时升级，cascade=true 软删整棵子树、设备保留） */
function deleteGroupConfirmCopy(group: DeviceGroup): string {
  const childCount = subtreeGroupCount(group)
  if (childCount > 0) {
    return `分组「${group.name}」包含 ${group.memberCount} 个设备与 ${childCount} 个子分组。删除分组会把设备移出分组、子分组一并删除（设备本身保留），确定删除吗？`
  }
  if (group.memberCount > 0) {
    return `分组「${group.name}」包含 ${group.memberCount} 个设备。删除分组会把设备移出分组（设备本身保留），确定删除吗？`
  }
  return `确定要删除分组「${group.name}」吗？`
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
