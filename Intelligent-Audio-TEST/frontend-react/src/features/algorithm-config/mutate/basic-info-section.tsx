/**
 * §6.2 基本信息分节（mutate sheet 首 Tab）。
 * 算法代码 · 显示名称 · 所属分组 · 排序 · 状态 Switch（开=上线 关=下线）· 描述。
 * 算法代码编辑/复制态 disabled（主键）；所属分组含「＋ 新建分组」哨兵项（inline 创建联动刷新）。
 */
import { useState } from 'react'
import type { UseFormReturn } from 'react-hook-form'

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
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { cn } from '@/lib/utils'
import type { AlgorithmGroup } from '@/domain/models/algorithmConfig'
import type {
  AlgorithmFormValues,
  MutateMode,
} from '@/features/algorithm-config/types'

const NEW_GROUP_SENTINEL = '__new_group__'

export function BasicInfoSection({
  form,
  groups,
  mode,
  onCreateGroup,
}: {
  form: UseFormReturn<AlgorithmFormValues>
  groups: AlgorithmGroup[]
  mode: MutateMode
  onCreateGroup: (name: string) => Promise<number>
}) {
  const { register, watch, setValue, formState } = form
  const groupId = watch('groupId')
  const status = watch('status')
  const [addingGroup, setAddingGroup] = useState(false)
  const [groupName, setGroupName] = useState('')
  const [groupPending, setGroupPending] = useState(false)

  const handleGroupSelect = (value: string | null) => {
    if (value === NEW_GROUP_SENTINEL) {
      setAddingGroup(true)
      return
    }
    setValue('groupId', value ?? '', { shouldDirty: true })
  }

  const handleCreateGroup = async () => {
    const name = groupName.trim()
    if (!name || groupPending) return
    setGroupPending(true)
    try {
      const id = await onCreateGroup(name)
      setValue('groupId', String(id), { shouldDirty: true })
      setAddingGroup(false)
      setGroupName('')
    } finally {
      setGroupPending(false)
    }
  }

  return (
    <div className='space-y-3'>
      <div className='grid gap-3 sm:grid-cols-2'>
        <div className='space-y-1.5'>
          <Label htmlFor='algo-type' required>算法代码</Label>
          <Input
            id='algo-type'
            placeholder='如：asr_v3'
            className='font-mono'
            disabled={mode !== 'create'}
            aria-invalid={Boolean(formState.errors.type)}
            {...register('type')}
          />
          {mode !== 'create' && (
            <p className='text-muted-foreground text-xs'>算法代码为主键，编辑/复制态不可修改</p>
          )}
          {formState.errors.type && (
            <p className='text-destructive text-xs'>{formState.errors.type.message}</p>
          )}
        </div>

        <div className='space-y-1.5'>
          <Label htmlFor='algo-name' required>显示名称</Label>
          <Input
            id='algo-name'
            placeholder='如：翻译'
            aria-invalid={Boolean(formState.errors.name)}
            {...register('name')}
          />
          {formState.errors.name && (
            <p className='text-destructive text-xs'>{formState.errors.name.message}</p>
          )}
        </div>
      </div>

      <div className='grid gap-3 sm:grid-cols-2'>
        <div className='space-y-1.5'>
          <Label required>所属分组</Label>
          <Select
            value={groupId}
            onValueChange={handleGroupSelect}
          >
            <SelectTrigger
              className={cn('w-full justify-between', !groupId && 'text-muted-foreground')}
              aria-invalid={Boolean(formState.errors.groupId)}
            >
              <SelectValue>
                {groupId
                  ? (groups.find((g) => String(g.id) === groupId)?.name ??
                    '请选择分组')
                  : '请选择分组'}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {groups.map((group) => (
                <SelectItem key={group.id} value={String(group.id)}>
                  {group.name}
                </SelectItem>
              ))}
              <SelectItem value={NEW_GROUP_SENTINEL}>＋ 新建分组</SelectItem>
            </SelectContent>
          </Select>
          {addingGroup && (
            <div className='flex items-center gap-2 pt-1'>
              <Input
                aria-label='新分组名称'
                placeholder='输入新分组名称'
                value={groupName}
                onChange={(e) => setGroupName(e.target.value)}
                className='h-7 text-xs'
              />
              <Button
                size='xs'
                type='button'
                disabled={!groupName.trim() || groupPending}
                onClick={handleCreateGroup}
              >
                {groupPending ? '创建中…' : '确定'}
              </Button>
              <Button
                size='xs'
                type='button'
                variant='ghost'
                disabled={groupPending}
                onClick={() => {
                  setAddingGroup(false)
                  setGroupName('')
                }}
              >
                取消
              </Button>
            </div>
          )}
          {formState.errors.groupId && (
            <p className='text-destructive text-xs'>{formState.errors.groupId.message}</p>
          )}
        </div>

        <div className='space-y-1.5'>
          <Label htmlFor='algo-order'>排序</Label>
          <Input
            id='algo-order'
            type='number'
            min={0}
            {...register('displayOrder', { valueAsNumber: true })}
          />
        </div>
      </div>

      <div className='flex items-center justify-between rounded-lg border border-border px-3 py-2'>
        <div>
          <Label htmlFor='algo-status' className='text-foreground'>
            {status === 'online' ? '上线' : '下线'}
          </Label>
          <p className='text-muted-foreground text-xs'>
            上线状态的算法可被测试任务与用例引用
          </p>
        </div>
        <Switch
          id='algo-status'
          checked={status === 'online'}
          onCheckedChange={(checked) =>
            setValue('status', checked ? 'online' : 'offline', { shouldDirty: true })
          }
        />
      </div>

      <div className='space-y-1.5'>
        <Label htmlFor='algo-desc'>描述</Label>
        <Textarea
          id='algo-desc'
          rows={3}
          placeholder='算法用途说明（可选）'
          {...register('description')}
        />
      </div>
    </div>
  )
}
