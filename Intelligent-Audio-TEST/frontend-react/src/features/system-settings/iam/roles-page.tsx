/**
 * 角色权限管理分区（interfaces 层，INT-347 §4.4.2 母版 B 变体）：
 * 角色表 + 角色×权限串矩阵对话框（sm:max-w-[720px] 内部滚动）；
 * admin 特例矩阵禁用「超级管理员持有全部权限（通配），不可修改」；
 * 保存 = POST /roles/{id}/permissions 全量替换（确认提示）；
 * 系统角色删除按钮隐藏、被引用角色删除预检「该角色仍有用户归属，请先转移用户」。
 */
import { useEffect, useMemo, useState } from 'react'
import { KeyRound, Ellipsis } from 'lucide-react'

import { usePermissions } from '@/application/hooks/use-permissions'
import {
  usePermissionCatalogQuery,
  useRolesQuery,
  useRoleMutations,
} from '@/application/iam/use-roles-query'
import { useUsersQuery } from '@/application/iam/use-users-query'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Label } from '@/components/ui/label'
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
import { ConfirmDialog } from '@/components/confirm-dialog'
import { ErrorState } from '@/components/error-state'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import type { PlatformRole } from '@/domain/models/role'

import { PermissionMatrix, WILDCARD_PERMISSION } from '../components/permission-matrix'
import { SettingsSection } from '../components/settings-section'

export function RolesPage() {
  const { hasPermission } = usePermissions()
  const rolesQuery = useRolesQuery()
  const permissionCatalogQuery = usePermissionCatalogQuery()
  const mutations = useRoleMutations()
  // 用户数后端角色接口不返回（role_bp.py 无 user_count），按用户列表 role_name 统计
  const usersQuery = useUsersQuery({})

  const userCountByRole = useMemo(() => {
    const counts = new Map<string, number>()
    for (const user of usersQuery.data ?? []) {
      counts.set(user.roleCode, (counts.get(user.roleCode) ?? 0) + 1)
    }
    return counts
  }, [usersQuery.data])

  const canCreate = hasPermission('role:create')
  const canUpdate = hasPermission('role:update')
  const canDelete = hasPermission('role:delete')

  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogMode, setDialogMode] = useState<'create' | 'edit' | 'detail'>('create')
  const [dialogRole, setDialogRole] = useState<PlatformRole | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<PlatformRole | null>(null)

  const openCreate = () => {
    setDialogMode('create')
    setDialogRole(null)
    setDialogOpen(true)
  }
  const openRole = (role: PlatformRole, mode: 'edit' | 'detail') => {
    setDialogMode(mode === 'edit' ? 'edit' : 'detail')
    setDialogRole(role)
    setDialogOpen(true)
  }

  return (
    <SettingsSection
      title='角色权限管理'
      description='平台采用基于角色的权限控制（RBAC）：角色绑定权限串，用户归属角色'
    >
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <p className='text-muted-foreground text-sm'>
          角色权限变更后即时生效，用户归属角色决定其基线权限范围
        </p>
        {canCreate && (
          <Button size='sm' onClick={openCreate}>
            + 新建角色
          </Button>
        )}
      </div>

      {rolesQuery.isLoading ? (
        <div aria-busy='true' className='overflow-hidden rounded-lg border'>
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className='flex gap-4 border-b p-4 last:border-0'>
              <Skeleton className='h-5 w-40' />
              <Skeleton className='h-5 flex-1' />
              <Skeleton className='h-5 w-20' />
            </div>
          ))}
        </div>
      ) : rolesQuery.isError ? (
        <ErrorState
          title='加载失败'
          description='角色列表加载失败，请重试'
          onRetry={() => void rolesQuery.refetch()}
        />
      ) : (rolesQuery.data?.length ?? 0) === 0 ? (
        <Empty className='min-h-[200px] border-dashed'>
          <EmptyHeader>
            <EmptyMedia variant='icon'>
              <KeyRound className='size-4' />
            </EmptyMedia>
            <EmptyTitle>暂无自定义角色</EmptyTitle>
            <EmptyDescription>系统内置五角色常驻表内</EmptyDescription>
          </EmptyHeader>
          <EmptyContent />
        </Empty>
      ) : (
        <div className='overflow-hidden rounded-lg border'>
          <div className='overflow-x-auto'>
            <table className='w-full min-w-[720px] text-sm'>
              <thead>
                <tr className='text-muted-foreground border-b bg-muted/30'>
                  <th className='px-3 py-2.5 text-left font-medium'>角色名称</th>
                  <th className='px-3 py-2.5 text-left font-medium'>描述</th>
                  <th className='px-3 py-2.5 text-left font-medium'>类型</th>
                  <th className='px-3 py-2.5 text-left font-medium'>权限数</th>
                  <th className='px-3 py-2.5 text-left font-medium'>用户数</th>
                  <th className='w-12 px-3 py-2.5' />
                </tr>
              </thead>
              <tbody>
                {(rolesQuery.data ?? []).map((role) => {
                  const isAdmin = role.permissions.includes(WILDCARD_PERMISSION)
                  return (
                    <tr
                      key={role.id}
                      className='hover:bg-muted/30 border-b transition-colors last:border-0'
                    >
                      <td className='px-3 py-3'>
                        <div className='font-medium'>{role.name}</div>
                        <div className='text-muted-foreground font-mono text-xs'>
                          {role.code}
                        </div>
                      </td>
                      <td className='max-w-[280px] px-3 py-3'>
                        <span className='text-muted-foreground line-clamp-2 text-xs'>
                          {role.description}
                        </span>
                      </td>
                      <td className='px-3 py-3'>
                        <Badge variant={role.isSystem ? 'secondary' : 'outline'}>
                          {role.isSystem ? '系统内置' : '自定义'}
                        </Badge>
                      </td>
                      <td className='px-3 py-3'>
                        <span className='font-mono tabular-nums'>
                          {role.permissions.length}
                        </span>
                      </td>
                      <td className='px-3 py-3'>
                        <span className='font-mono tabular-nums'>
                          {userCountByRole.get(role.code) ?? 0}
                        </span>
                      </td>
                      <td className='px-3 py-3 text-right'>
                        <DropdownMenu modal={false}>
                          <DropdownMenuTrigger
                            render={
                              <Button
                                variant='ghost'
                                size='icon-sm'
                                aria-label={`角色操作：${role.name}`}
                              />
                            }
                          >
                            <Ellipsis className='size-4' />
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align='end' className='w-40'>
                            <DropdownMenuItem onClick={() => openRole(role, 'detail')}>
                              详情
                            </DropdownMenuItem>
                            {canUpdate && !isAdmin && (
                              <DropdownMenuItem onClick={() => openRole(role, 'edit')}>
                                编辑
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuSeparator />
                            {canDelete && !role.isSystem && (
                              <DropdownMenuItem
                                variant='destructive'
                                onClick={() => setDeleteTarget(role)}
                              >
                                删除
                              </DropdownMenuItem>
                            )}
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* 角色详情/编辑/新建 Dialog */}
      <RoleDialog
        open={dialogOpen}
        mode={dialogMode}
        role={dialogRole}
        permissionModules={permissionCatalogQuery.data ?? []}
        canUpdate={canUpdate}
        onOpenChange={setDialogOpen}
        isSaving={
          mutations.createRole.isPending ||
          mutations.updateRole.isPending ||
          mutations.setPermissions.isPending
        }
        onCreate={async (input) => {
          // 关窗时机下移：成功由 RoleDialog 关闭，失败保留弹窗与输入（toast 由 mutation 层弹出）
          await mutations.createRole.mutateAsync(input)
        }}
        onUpdate={async (roleId, patch) => {
          await mutations.updateRole.mutateAsync({ roleId, patch })
        }}
        onSetPermissions={async (roleId, permissions) => {
          await mutations.setPermissions.mutateAsync({ roleId, permissions })
        }}
      />

      {/* 删除确认 */}
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
        title='确认删除角色'
        desc={
          deleteTarget
            ? `删除后不可恢复；该角色仍有用户归属时需先转移用户。`
            : ''
        }
        destructive
        cancelBtnText='取消'
        confirmText='删除'
        isLoading={mutations.deleteRole.isPending}
        handleConfirm={() => {
          if (deleteTarget) mutations.deleteRole.mutate(deleteTarget.id)
          setDeleteTarget(null)
        }}
      />
    </SettingsSection>
  )
}

// ---------------------------------------------------------------------------
// 角色详情/编辑/新建对话框（sm:max-w-[720px]，矩阵内部滚动）
// ---------------------------------------------------------------------------

type RoleDialogProps = {
  open: boolean
  mode: 'create' | 'edit' | 'detail'
  role: PlatformRole | null
  permissionModules: Parameters<typeof PermissionMatrix>[0]['permissionModules']
  canUpdate: boolean
  onOpenChange: (open: boolean) => void
  /** 任一角色 mutation 进行中（提交按钮禁用，防重复提交） */
  isSaving: boolean
  onCreate: (input: {
    name: string
    description: string
    permissions: string[]
  }) => Promise<void>
  onUpdate: (roleId: string, patch: { name?: string; description?: string }) => Promise<void>
  onSetPermissions: (roleId: string, permissions: string[]) => Promise<void>
}

/** 表单字段（字段级错误的定位键，与 Input 的 id 后缀一致） */
type RoleDialogField = 'name'

type RoleDialogFieldErrors = Partial<Record<RoleDialogField, string>>

function RoleDialog(props: RoleDialogProps) {
  const isCreate = props.mode === 'create'
  const isAdmin = props.role?.permissions.includes(WILDCARD_PERMISSION) ?? false
  const readOnly = props.mode === 'detail' || (props.mode === 'edit' && !props.canUpdate) || isAdmin

  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [permissions, setPermissions] = useState<string[]>([])
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<RoleDialogFieldErrors>({})

  useEffect(() => {
    if (!props.open) return
    const target = props.role
    setName(target?.name ?? '')
    setDescription(target?.description ?? '')
    setPermissions(target?.permissions ?? [])
    setFieldErrors({})
  }, [props.open, props.role])

  const clearFieldError = (field: RoleDialogField) =>
    setFieldErrors((prev) => {
      if (!prev[field]) return prev
      const next = { ...prev }
      delete next[field]
      return next
    })

  /** 必填校验（§05 系统设置：zod 口径的前端拦截，中文红字 + aria-invalid） */
  const validate = (): RoleDialogFieldErrors => {
    const errors: RoleDialogFieldErrors = {}
    if (!name.trim()) errors.name = '请输入角色名称'
    return errors
  }

  const handleConfirmSave = async () => {
    setConfirmOpen(false)
    const target = props.role
    if (!target) return
    try {
      // 名称/描述有变更才更新基础信息，权限恒做全量替换
      if (name.trim() !== target.name || description !== target.description) {
        await props.onUpdate(target.id, { name: name.trim(), description })
      }
      await props.onSetPermissions(target.id, permissions)
      props.onOpenChange(false)
    } catch {
      // 任一提交失败：弹窗保持打开、输入与矩阵保留（toast 由 mutation 层弹出）
    }
  }

  const handleSaveClick = async () => {
    const errors = validate()
    setFieldErrors(errors)
    if (Object.keys(errors).length > 0) return
    if (isCreate) {
      try {
        await props.onCreate({ name: name.trim(), description, permissions })
        props.onOpenChange(false)
      } catch {
        // 失败保留弹窗与输入（toast 由 mutation 层弹出）
      }
      return
    }
    if (props.role) {
      // 全量替换权限矩阵需二次确认（role_bp.py 全量替换语义）
      setConfirmOpen(true)
    }
  }

  const title = isCreate ? '新建角色' : props.mode === 'detail' ? '角色详情' : '编辑角色'

  return (
    <>
      <Dialog open={props.open} onOpenChange={props.onOpenChange}>
        <DialogContent className='sm:max-w-[720px]'>
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            <DialogDescription>
              {isCreate
                ? '创建自定义角色并分配权限串'
                : `角色 ${props.role?.name ?? ''} 的权限配置`}
            </DialogDescription>
          </DialogHeader>
          <div className='max-h-[60vh] space-y-4 overflow-y-auto pr-1'>
            <div className='grid gap-3'>
              <div className='grid gap-1.5'>
                <Label htmlFor='role-name'>
                  角色名称 <span className='text-destructive'>*</span>
                </Label>
                <Input
                  id='role-name'
                  placeholder='输入角色名称'
                  disabled={!isCreate && !props.canUpdate}
                  value={name}
                  aria-invalid={Boolean(fieldErrors.name)}
                  aria-describedby={fieldErrors.name ? 'role-name-error' : undefined}
                  onChange={(event) => {
                    setName(event.target.value)
                    clearFieldError('name')
                  }}
                />
                {fieldErrors.name && (
                  <p id='role-name-error' className='text-destructive text-xs'>
                    {fieldErrors.name}
                  </p>
                )}
              </div>
              <div className='grid gap-1.5'>
                <Label htmlFor='role-description'>描述</Label>
                <Textarea
                  id='role-description'
                  rows={2}
                  placeholder='描述该角色的职责范围'
                  disabled={props.mode === 'detail' || (props.mode === 'edit' && !props.canUpdate)}
                  value={description}
                  onChange={(event) => setDescription(event.target.value)}
                />
              </div>
              {props.role?.isSystem && (
                <p className='text-muted-foreground rounded-lg bg-muted/40 px-3 py-2 text-xs'>
                  系统内置角色不可删除
                </p>
              )}
            </div>

            <PermissionMatrix
              value={permissions}
              onChange={setPermissions}
              disabled={readOnly}
              disabledReason={
                isAdmin
                  ? '超级管理员持有全部权限（通配），不可修改'
                  : readOnly
                    ? '当前无角色编辑权限，矩阵为只读态'
                    : undefined
              }
              permissionModules={props.permissionModules}
            />
          </div>
          <DialogFooter>
            <Button
              variant='outline'
              disabled={props.isSaving}
              onClick={() => props.onOpenChange(false)}
            >
              取消
            </Button>
            {!readOnly && (
              <Button onClick={() => void handleSaveClick()} disabled={props.isSaving}>
                {isCreate ? '创建' : '保存'}
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title='确认保存角色权限'
        desc='将全量替换该角色的权限配置，确认保存？'
        cancelBtnText='取消'
        confirmText='确认保存'
        handleConfirm={handleConfirmSave}
      />
    </>
  )
}
