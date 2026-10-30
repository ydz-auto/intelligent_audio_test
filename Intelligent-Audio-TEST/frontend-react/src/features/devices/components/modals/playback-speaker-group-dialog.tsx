/**
 * 逻辑音箱管理弹窗（设备管理 → 更多操作 → 逻辑音箱）。
 * 一个逻辑音箱 = 一个物理位置（如「设备正面 0.5m」），组内每个实验室各挂一台实体播放设备；
 * 用例可直接关联逻辑音箱，执行时由后端按「执行实验室」换成该实验室的实体音箱，
 * 避免跨实验室并行时驱动别处的音箱。
 * 数据契约：GET/POST/PUT/DELETE /api/v1/playback-devices/speaker-groups 与
 * PUT/DELETE .../speaker-groups/{id}/items（api_gateway routes/playback_bp.py）。
 */
import { Pencil, Plus, Trash2, Unlink } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'

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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { ConfirmDialog } from '@/components/confirm-dialog'
import {
  useLaboratories,
  usePlaybackDevices,
  usePlaybackSpeakerGroupMutations,
  usePlaybackSpeakerGroups,
} from '@/application/devices/use-devices'
import type { PlaybackDevice } from '@/domain/models/playbackDevice'
import type { PlaybackSpeakerGroup } from '@/domain/models/playbackSpeakerGroup'
import { ApiError } from '@/infrastructure/api/api-error'
import { StaticDataTable } from '@/features/system-settings/components/static-data-table'

export interface PlaybackSpeakerGroupDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** 失败提示（后端业务文案经 ApiError.userMessage 直呈；删除类按返回值分流） */
const errorText = (error: unknown, fallback: string): string =>
  error instanceof ApiError ? error.userMessage : fallback

const deviceLabel = (device: PlaybackDevice): string =>
  `${device.name} (通道 ${device.channelIndex ?? '—'})`

export function PlaybackSpeakerGroupDialog(props: PlaybackSpeakerGroupDialogProps) {
  const groupsQuery = usePlaybackSpeakerGroups()
  const labsQuery = useLaboratories()
  const devicesQuery = usePlaybackDevices()
  const { create, update, remove, setItem, removeItem } = usePlaybackSpeakerGroupMutations()

  const groups = useMemo<PlaybackSpeakerGroup[]>(() => groupsQuery.data ?? [], [groupsQuery.data])
  const labs = useMemo(() => labsQuery.data ?? [], [labsQuery.data])
  const devices = useMemo(() => devicesQuery.data ?? [], [devicesQuery.data])

  const [editingId, setEditingId] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selectedGroupId, setSelectedGroupId] = useState<number | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<PlaybackSpeakerGroup | null>(null)

  useEffect(() => {
    if (!props.open) return
    setEditingId(null)
    setName('')
    setDescription('')
    setSelectedGroupId(null)
  }, [props.open])

  const selectedGroup =
    groups.find((group) => group.id === selectedGroupId) ?? groups[0] ?? null

  const startEdit = (group: PlaybackSpeakerGroup) => {
    setEditingId(group.id)
    setName(group.name)
    setDescription(group.description ?? '')
  }

  const resetForm = () => {
    setEditingId(null)
    setName('')
    setDescription('')
  }

  const handleSubmit = async () => {
    const trimmed = name.trim()
    if (!trimmed) {
      toast.error('请填写逻辑音箱名称')
      return
    }
    try {
      if (editingId != null) {
        await update.mutateAsync({
          id: editingId,
          input: { name: trimmed, description: description || null },
        })
        toast.success('逻辑音箱已更新')
      } else {
        await create.mutateAsync({ name: trimmed, description: description || null })
        toast.success('逻辑音箱已创建')
      }
      resetForm()
    } catch (error) {
      toast.error(errorText(error, '操作失败，请稍后重试'))
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      const result = await remove.mutateAsync(deleteTarget.id)
      if (result.success) {
        toast.success('逻辑音箱已删除')
        setDeleteTarget(null)
        if (selectedGroupId === deleteTarget.id) setSelectedGroupId(null)
      } else {
        toast.error(result.message ?? '删除失败，请重试')
      }
    } catch (error) {
      toast.error(errorText(error, '删除失败，请重试'))
    }
  }

  /** 组内该实验室的对应实体音箱 */
  const itemOfLab = (group: PlaybackSpeakerGroup, labId: number) =>
    group.items.find((item) => item.labId === labId) ?? null

  /** 参与映射的实验室：组内已配置的 + 该实验室名下有播放设备的（其余实验室无音箱可配） */
  const mappingLabs = useMemo(() => {
    if (!selectedGroup) return []
    const deviceLabIds = new Set(devices.map((device) => device.labId))
    const itemLabIds = new Set(selectedGroup.items.map((item) => item.labId))
    return labs.filter((lab) => itemLabIds.has(lab.id) || deviceLabIds.has(lab.id))
  }, [labs, devices, selectedGroup])

  const handleItemChange = async (labId: number, deviceId: number) => {
    if (!selectedGroup) return
    try {
      await setItem.mutateAsync({
        groupId: selectedGroup.id,
        input: { labId, playbackDeviceId: deviceId },
      })
      toast.success('对应设备已保存')
    } catch (error) {
      toast.error(errorText(error, '保存失败，请重试'))
    }
  }

  const handleItemClear = async (labId: number) => {
    if (!selectedGroup) return
    try {
      const result = await removeItem.mutateAsync({ groupId: selectedGroup.id, labId })
      if (result.success) toast.success('已移除该实验室的对应设备')
      else toast.error(result.message ?? '移除失败，请重试')
    } catch (error) {
      toast.error(errorText(error, '移除失败，请重试'))
    }
  }

  return (
    <>
      <Dialog open={props.open} onOpenChange={props.onOpenChange}>
        <DialogContent className='sm:max-w-4xl'>
          <DialogHeader>
            <DialogTitle>逻辑音箱</DialogTitle>
            <DialogDescription>
              一个逻辑音箱代表一个物理位置，组内为每个实验室绑定各自的实体音箱；用例关联逻辑音箱后，跨实验室执行时自动换成所在实验室的音箱。
            </DialogDescription>
          </DialogHeader>

          <div className='flex flex-col gap-3'>
            {/* 新建/编辑表单 */}
            <div className='bg-card/50 grid grid-cols-3 items-end gap-2.5 rounded-lg border p-3'>
              <div className='flex flex-col gap-1'>
                <Label htmlFor='speaker-group-name'>名称</Label>
                <Input
                  id='speaker-group-name'
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  placeholder='如：设备正面（0.5m+0°）'
                  className='h-8'
                />
              </div>
              <div className='flex flex-col gap-1'>
                <Label htmlFor='speaker-group-desc'>描述</Label>
                <Input
                  id='speaker-group-desc'
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                  placeholder='选填'
                  className='h-8'
                />
              </div>
              <div className='flex justify-end gap-2'>
                {editingId != null && (
                  <Button variant='ghost' size='sm' onClick={resetForm}>
                    取消编辑
                  </Button>
                )}
                <Button size='sm' className='gap-1' onClick={() => void handleSubmit()}>
                  <Plus aria-hidden='true' className='size-3.5' />
                  {editingId != null ? '保存修改' : '新建逻辑音箱'}
                </Button>
              </div>
            </div>

            {/* 逻辑音箱列表 */}
            <StaticDataTable
              columns={[
                {
                  key: 'name',
                  header: '名称',
                  className: 'max-w-48',
                  render: (group: PlaybackSpeakerGroup) => (
                    <>
                      <span className='min-w-0 block truncate font-medium'>{group.name}</span>
                      {group.description && (
                        <span className='text-muted-foreground min-w-0 block truncate text-[11px]'>
                          {group.description}
                        </span>
                      )}
                    </>
                  ),
                },
                {
                  key: 'labs',
                  header: '已绑定实验室',
                  className: 'text-right font-mono tabular-nums',
                  render: (group: PlaybackSpeakerGroup) => group.items.length,
                },
                {
                  key: 'updatedAt',
                  header: '更新时间',
                  className: 'font-mono tabular-nums',
                  render: (group: PlaybackSpeakerGroup) =>
                    group.updatedAt ? group.updatedAt.replace('T', ' ').slice(0, 16) : '—',
                },
              ]}
              rows={groups}
              rowKey={(group) => String(group.id)}
              emptyText={groupsQuery.isLoading ? '加载中…' : '暂无逻辑音箱'}
              minWidth='640px'
              actions={(group) => (
                <span className='flex items-center justify-end gap-1'>
                  <Button
                    variant='ghost'
                    size='sm'
                    className='h-6 px-1.5 text-xs'
                    aria-label={`查看逻辑音箱 ${group.name} 的实验室映射`}
                    onClick={() => setSelectedGroupId(group.id)}
                  >
                    实验室映射
                  </Button>
                  <Button
                    variant='ghost'
                    size='icon-sm'
                    className='size-6'
                    aria-label={`编辑逻辑音箱 ${group.name}`}
                    onClick={() => startEdit(group)}
                  >
                    <Pencil aria-hidden='true' className='size-3.5' />
                  </Button>
                  <Button
                    variant='ghost'
                    size='icon-sm'
                    className='text-destructive size-6'
                    aria-label={`删除逻辑音箱 ${group.name}`}
                    onClick={() => setDeleteTarget(group)}
                  >
                    <Trash2 aria-hidden='true' className='size-3.5' />
                  </Button>
                </span>
              )}
            />

            {/* 选中组的实验室映射 */}
            {selectedGroup && (
              <div className='rounded-lg border'>
                <div className='border-b px-3 py-2 text-sm font-medium'>
                  「{selectedGroup.name}」在各实验室对应的实体音箱
                </div>
                <div className='max-h-72 overflow-y-auto'>
                  {mappingLabs.length === 0 ? (
                    <p className='text-muted-foreground px-3 py-4 text-center text-sm'>
                      暂无可绑定的实验室（请先在「实验室管理」建实验室并为播放设备绑定实验室）
                    </p>
                  ) : (
                    mappingLabs.map((lab) => {
                      const item = itemOfLab(selectedGroup, lab.id)
                      const labDevices = devices.filter((device) => device.labId === lab.id)
                      return (
                        <div
                          key={lab.id}
                          className='flex items-center gap-2 border-b px-3 py-2 last:border-b-0'
                        >
                          <span className='min-w-0 flex-1 truncate text-sm'>
                            {lab.name}
                            <span className='text-muted-foreground ms-1 font-mono text-xs'>
                              {lab.code}
                            </span>
                          </span>
                          <Select
                            value={item ? String(item.playbackDeviceId) : ''}
                            onValueChange={(value) => {
                              if (value) void handleItemChange(lab.id, Number(value))
                            }}
                            items={labDevices.map((device) => ({
                              value: String(device.id),
                              label: deviceLabel(device),
                            }))}
                          >
                            <SelectTrigger size='sm' className='w-64'>
                              <SelectValue placeholder='未设置' />
                            </SelectTrigger>
                            <SelectContent>
                              {labDevices.map((device) => (
                                <SelectItem key={device.id} value={String(device.id)}>
                                  {deviceLabel(device)}
                                </SelectItem>
                              ))}
                            </SelectContent>
                          </Select>
                          <Button
                            variant='ghost'
                            size='icon-sm'
                            className='size-7'
                            aria-label={`移除 ${lab.name} 的对应设备`}
                            disabled={!item}
                            onClick={() => void handleItemClear(lab.id)}
                          >
                            <Unlink aria-hidden='true' className='size-3.5' />
                          </Button>
                        </div>
                      )
                    })
                  )}
                </div>
              </div>
            )}
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
        title='删除逻辑音箱'
        desc={
          deleteTarget
            ? `删除逻辑音箱「${deleteTarget.name}」？已关联该逻辑音箱的用例需重新指定播放设备。`
            : ''
        }
        destructive
        confirmText='删除'
        handleConfirm={() => void handleDelete()}
      />
    </>
  )
}
