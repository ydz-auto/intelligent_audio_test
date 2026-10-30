/**
 * 参数策略管理对话框（features/algorithm-config/param-profiles；T4.3）。
 *
 * 列表（GET /algorithm/param-profiles）+ 新建 / 编辑（POST / PUT）
 * + 克隆（POST /{id}/clone）+ 删除二次确认（DELETE /{id}，软删除）。
 * 权限：读 = algorithm:read；写 = algorithm:param_manage（canManage 控制动作可用）。
 */
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import {
  useParamProfileList,
  useParamProfileMutations,
} from '@/application/algorithm-config/useParamProfiles'
import { useTestAlgorithmOptions } from '@/application/test-execution/useTestAlgorithmOptions'
import {
  PARAM_PROFILE_SCOPE_LABEL,
  PARAM_PROFILE_STATUS_LABEL,
  type ParamProfile,
} from '@/domain/models/paramProfile'
import { ApiError } from '@/infrastructure/api/api-error'
import { Badge } from '@/components/ui/badge'
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
import { Spinner } from '@/components/ui/spinner'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Textarea } from '@/components/ui/textarea'
import { ParamProfileFormDialog } from '@/features/algorithm-config/param-profiles/param-profile-form-dialog'

const ALL_ALGORITHMS = '__all__'

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.userMessage
  return error instanceof Error && error.message ? error.message : '操作失败，请重试'
}

export interface ParamProfileManagerDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** `algorithm:param_manage` */
  canManage: boolean
  /** 页头当前全局算法（作为默认过滤条件） */
  defaultAlgorithmType: string
}

export function ParamProfileManagerDialog({
  open,
  onOpenChange,
  canManage,
  defaultAlgorithmType,
}: ParamProfileManagerDialogProps) {
  const algorithmsQuery = useTestAlgorithmOptions()
  const [algorithmFilter, setAlgorithmFilter] = useState(defaultAlgorithmType || ALL_ALGORITHMS)
  const [formState, setFormState] = useState<{
    open: boolean
    mode: 'create' | 'edit'
    profileId: number | null
  }>({ open: false, mode: 'create', profileId: null })
  const [cloneTarget, setCloneTarget] = useState<ParamProfile | null>(null)
  const [cloneName, setCloneName] = useState('')
  const [cloneDescription, setCloneDescription] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<ParamProfile | null>(null)

  const { profiles, isLoading, isError } = useParamProfileList(
    algorithmFilter === ALL_ALGORITHMS ? null : algorithmFilter,
    open
  )
  const { clone, remove } = useParamProfileMutations()

  useEffect(() => {
    if (open) setAlgorithmFilter(defaultAlgorithmType || ALL_ALGORITHMS)
  }, [open, defaultAlgorithmType])

  const algorithmOptions = [
    { value: ALL_ALGORITHMS, label: '全部算法' },
    ...(algorithmsQuery.data ?? []).map((item) => ({ value: item.id, label: item.name })),
  ]

  const openCreate = () => {
    setFormState({
      open: true,
      mode: 'create',
      profileId: null,
    })
  }

  const openEdit = (profile: ParamProfile) => {
    setFormState({ open: true, mode: 'edit', profileId: profile.id })
  }

  const openClone = (profile: ParamProfile) => {
    setCloneTarget(profile)
    setCloneName(`${profile.name} 副本`)
    setCloneDescription(profile.description ?? '')
  }

  const submitClone = async () => {
    if (!cloneTarget) return
    const name = cloneName.trim()
    if (!name) {
      toast.error('请填写策略名称')
      return
    }
    try {
      await clone.mutateAsync({
        profileId: cloneTarget.id,
        input: { name, description: cloneDescription.trim() || null },
      })
      toast.success('参数策略已克隆')
      setCloneTarget(null)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  const submitDelete = async () => {
    if (!deleteTarget) return
    try {
      const deleted = await remove.mutateAsync(deleteTarget.id)
      if (deleted) toast.success('参数策略已删除')
      else toast.error('策略不存在或已删除')
      setDeleteTarget(null)
    } catch (error) {
      toast.error(errorMessage(error))
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className='max-h-[85vh] overflow-y-auto sm:max-w-5xl'>
          <DialogHeader>
            <DialogTitle>参数策略</DialogTitle>
            <DialogDescription>
              可复用参数策略：多个 API 实例可绑定同一策略，实例覆盖优先于策略。
            </DialogDescription>
          </DialogHeader>

          <div className='flex flex-wrap items-center justify-between gap-2'>
            <div className='flex items-center gap-2'>
              <Label className='text-xs whitespace-nowrap'>算法类型</Label>
              <Select
                value={algorithmFilter}
                items={algorithmOptions}
                onValueChange={(value) => setAlgorithmFilter(value ?? ALL_ALGORITHMS)}
              >
                <SelectTrigger size='sm' className='w-48 justify-between'>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {algorithmOptions.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              type='button'
              size='sm'
              className='gap-1'
              disabled={!canManage}
              onClick={openCreate}
            >
              <Plus aria-hidden='true' className='size-3.5' />
              新建策略
            </Button>
          </div>

          {isLoading ? (
            <div className='text-muted-foreground flex items-center justify-center gap-2 py-12 text-xs'>
              <Spinner className='size-4' />
              正在读取参数策略…
            </div>
          ) : isError ? (
            <p className='text-destructive py-8 text-center text-xs'>
              参数策略读取失败（可能需要 algorithm:read 权限）。
            </p>
          ) : profiles.length === 0 ? (
            <p className='text-muted-foreground border-border/60 rounded-lg border border-dashed py-8 text-center text-xs'>
              当前筛选下没有参数策略{canManage ? '，可点击「新建策略」创建。' : '。'}
            </p>
          ) : (
            <div className='border-border/60 overflow-x-auto rounded-lg border'>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>名称</TableHead>
                    <TableHead>算法类型</TableHead>
                    <TableHead>作用域</TableHead>
                    <TableHead>状态</TableHead>
                    <TableHead>字段</TableHead>
                    <TableHead>映射</TableHead>
                    <TableHead className='w-40'>操作</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {profiles.map((profile) => (
                    <TableRow key={profile.id}>
                      <TableCell>
                        <p className='text-sm font-medium'>{profile.name}</p>
                        {profile.description && (
                          <p className='text-muted-foreground text-xs'>{profile.description}</p>
                        )}
                      </TableCell>
                      <TableCell className='font-mono text-xs'>{profile.algorithmType}</TableCell>
                      <TableCell>
                        <Badge variant='secondary'>
                          {PARAM_PROFILE_SCOPE_LABEL[profile.scope]}
                        </Badge>
                      </TableCell>
                      <TableCell className='text-xs'>
                        {PARAM_PROFILE_STATUS_LABEL[profile.status]}
                      </TableCell>
                      <TableCell className='text-xs tabular-nums'>
                        {profile.params.length}
                      </TableCell>
                      <TableCell className='text-xs tabular-nums'>
                        {profile.mappings.length}
                      </TableCell>
                      <TableCell>
                        <div className='flex items-center gap-1'>
                          <Button
                            type='button'
                            variant='ghost'
                            size='sm'
                            className='h-7 gap-1 px-2 text-xs'
                            disabled={!canManage}
                            onClick={() => openEdit(profile)}
                          >
                            <Pencil aria-hidden='true' className='size-3.5' />
                            编辑
                          </Button>
                          <Button
                            type='button'
                            variant='ghost'
                            size='sm'
                            className='h-7 px-2 text-xs'
                            disabled={!canManage}
                            onClick={() => openClone(profile)}
                          >
                            克隆
                          </Button>
                          <Button
                            type='button'
                            variant='ghost'
                            size='sm'
                            className='text-destructive h-7 px-2 text-xs'
                            disabled={!canManage}
                            onClick={() => setDeleteTarget(profile)}
                          >
                            <Trash2 aria-hidden='true' className='size-3.5' />
                            删除
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          <DialogFooter>
            <Button type='button' variant='outline' onClick={() => onOpenChange(false)}>
              关闭
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ParamProfileFormDialog
        open={formState.open}
        onOpenChange={(next) => setFormState((prev) => ({ ...prev, open: next }))}
        mode={formState.mode}
        profileId={formState.profileId}
        defaultAlgorithmType={
          algorithmFilter === ALL_ALGORITHMS ? defaultAlgorithmType : algorithmFilter
        }
      />

      {/* 克隆：新名称 + 描述 */}
      <Dialog open={cloneTarget != null} onOpenChange={(next) => !next && setCloneTarget(null)}>
        <DialogContent className='sm:max-w-md'>
          <DialogHeader>
            <DialogTitle>克隆参数策略</DialogTitle>
            <DialogDescription>
              复制「{cloneTarget?.name ?? ''}」的字段与映射，生成新策略。
            </DialogDescription>
          </DialogHeader>
          <div className='space-y-3'>
            <div className='space-y-1.5'>
              <Label htmlFor='clone-profile-name'>策略名称 *</Label>
              <Input
                id='clone-profile-name'
                maxLength={100}
                value={cloneName}
                onChange={(e) => setCloneName(e.target.value)}
              />
            </div>
            <div className='space-y-1.5'>
              <Label htmlFor='clone-profile-description'>描述</Label>
              <Textarea
                id='clone-profile-description'
                rows={2}
                value={cloneDescription}
                onChange={(e) => setCloneDescription(e.target.value)}
              />
            </div>
          </div>
          <DialogFooter>
            <Button type='button' variant='outline' onClick={() => setCloneTarget(null)}>
              取消
            </Button>
            <Button type='button' disabled={clone.isPending} onClick={submitClone}>
              {clone.isPending ? '克隆中…' : '克隆'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 删除二次确认（软删除；绑定的 API 回落为未绑定） */}
      <Dialog open={deleteTarget != null} onOpenChange={(next) => !next && setDeleteTarget(null)}>
        <DialogContent className='sm:max-w-md'>
          <DialogHeader>
            <DialogTitle>删除参数策略</DialogTitle>
            <DialogDescription>
              确认删除「{deleteTarget?.name ?? ''}」？绑定该策略的 API 将回落为未绑定（实例覆盖行保留）。
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type='button' variant='outline' onClick={() => setDeleteTarget(null)}>
              取消
            </Button>
            <Button
              type='button'
              variant='destructive'
              disabled={remove.isPending}
              onClick={submitDelete}
            >
              {remove.isPending ? '删除中…' : '确认删除'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
