/**
 * 用户管理分区（interfaces 层，INT-347 §4.4.1 母版 C DataTable）：
 * 搜索 + 状态/角色筛选 → DataTable（勾选/用户名/邮箱/角色/状态/附加权限数/注册时间/操作）
 * → 行操作（编辑/分配角色/附加权限/启停/删除，按钮级权限 + 自保护）→ Sheet 抽屉
 * （基本信息 / 角色与状态 / 附加权限 PermissionMatrix）→ 删除 ConfirmDialog。
 * 数据流：GET /users（分页 ≤100 + status/keyword/role_id 过滤）→ useUsersQuery；
 * 行操作走 user:update/assign_role/grant_permission/delete。
 */
import { useMemo, useState } from 'react'
import {
  Search,
  Users as UsersIcon,
  ChevronDown,
  Ellipsis,
} from 'lucide-react'
import { cn } from '@/lib/utils'

import { usePermissions } from '@/application/hooks/use-permissions'
import { useUsersQuery, useUserDetail, useUserMutations } from '@/application/iam/use-users-query'
import { useRolesQuery, usePermissionCatalogQuery } from '@/application/iam/use-roles-query'
import { useAuthStore } from '@/infrastructure/stores/auth-store'
import {
  USER_STATUS_META,
  type PlatformUser,
  type PlatformUserStatus,
} from '@/domain/models/user'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover'
import {
  Empty,
  EmptyContent,
  EmptyDescription,
  EmptyHeader,
  EmptyMedia,
  EmptyTitle,
} from '@/components/ui/empty'
import { ConfirmDialog } from '@/components/confirm-dialog'
import { StatusBadge } from '@/features/dashboard/components/ui/status-badge'

import { SettingsSection } from '../components/settings-section'
import { UserMutateDrawer } from './user-mutate-drawer'

const STATUS_VALUES: Array<PlatformUserStatus | 'all'> = [
  'all',
  'active',
  'disabled',
  'locked',
]

export function UsersPage() {
  const { hasPermission } = usePermissions()
  const currentUser = useAuthStore((state) => state.user)
  const rolesQuery = useRolesQuery()
  const permissionCatalogQuery = usePermissionCatalogQuery()
  const mutations = useUserMutations()

  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState<PlatformUserStatus | 'all'>('all')
  const [roleCodes, setRoleCodes] = useState<string[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [drawerMode, setDrawerMode] = useState<'create' | 'edit'>('create')
  const [drawerUser, setDrawerUser] = useState<PlatformUser | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<PlatformUser | null>(null)

  const filter = useMemo(
    () => ({ keyword, status, roleCodes }),
    [keyword, status, roleCodes]
  )
  const usersQuery = useUsersQuery(filter)
  // 编辑态拉取详情（列表响应不含 overrides，抽屉附加权限矩阵需详情端点回填）
  const detailQuery = useUserDetail(drawerMode === 'edit' ? drawerUser?.id ?? null : null)

  // 角色码 → role_id 解析（角色分配/新建用户走后端 role_id 契约，INT-651）
  const roleIdOf = (roleCode: string): number | undefined => {
    const role = rolesQuery.data?.find((item) => item.code === roleCode)
    return role ? Number(role.id) : undefined
  }

  const canCreate = hasPermission('user:create')
  const canUpdate = hasPermission('user:update')
  const canAssignRole = hasPermission('user:assign_role')
  const canGrant = hasPermission('user:grant_permission')
  const canDelete = hasPermission('user:delete')

  const toggleRow = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    )
  }
  const toggleAll = () => {
    const items = usersQuery.data ?? []
    setSelectedIds((prev) =>
      prev.length === items.length && items.every((i) => prev.includes(i.id))
        ? []
        : items.map((i) => i.id)
    )
  }

  const openCreate = () => {
    setDrawerMode('create')
    setDrawerUser(null)
    setDrawerOpen(true)
  }
  const openEdit = (user: PlatformUser) => {
    setDrawerMode('edit')
    setDrawerUser(user)
    setDrawerOpen(true)
  }
  const closeDrawer = () => {
    setDrawerOpen(false)
    setDrawerUser(null)
  }

  const handleRowAction = (
    user: PlatformUser,
    action: 'edit' | 'delete' | 'toggle-status'
  ) => {
    if (action === 'edit') openEdit(user)
    else if (action === 'delete') setDeleteTarget(user)
    else if (action === 'toggle-status') {
      const next = user.status === 'active' ? 'disabled' : 'active'
      mutations.updateUser.mutate({ userId: user.id, patch: { status: next } })
    }
  }

  return (
    <SettingsSection
      title='用户管理'
      description='管理平台用户账号、角色分配与附加权限'
    >
      {/* 工具行 */}
      <div className='flex flex-wrap items-center justify-between gap-2'>
        <div className='flex flex-wrap items-center gap-2'>
          <div className='relative'>
            <Search
              className='text-muted-foreground absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2'
              aria-hidden='true'
            />
            <Input
              placeholder='搜索用户名或邮箱'
              className='h-8 w-56 pl-8'
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
            />
          </div>
          <Select
            value={status}
            onValueChange={(value) =>
              setStatus(value as PlatformUserStatus | 'all')
            }
          >
            <SelectTrigger className='h-8 w-28'>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUS_VALUES.map((value) => (
                <SelectItem key={value} value={value}>
                  {value === 'all' ? '全部状态' : USER_STATUS_META[value].label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Popover>
            <PopoverTrigger
              render={
                <Button variant='outline' size='sm' className='h-8'>
                  角色
                  <ChevronDown className='size-3.5' aria-hidden='true' />
                </Button>
              }
            />
            <PopoverContent className='w-56'>
              <div className='grid gap-1'>
                {/* 角色筛选选项来自真实角色列表（含自定义角色，P3-3），不再固定 5 系统角色 */}
                {(rolesQuery.data ?? []).map((role) => {
                  const checked = roleCodes.includes(role.code)
                  return (
                    <label
                      key={role.code}
                      className='hover:bg-muted flex cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm'
                    >
                      <Checkbox
                        checked={checked}
                        onCheckedChange={() =>
                          setRoleCodes((prev) =>
                            checked
                              ? prev.filter((c) => c !== role.code)
                              : [...prev, role.code]
                          )
                        }
                      />
                      {role.name}
                    </label>
                  )
                })}
              </div>
            </PopoverContent>
          </Popover>
        </div>
        {canCreate && (
          <Button size='sm' onClick={openCreate}>
            + 新建用户
          </Button>
        )}
      </div>

      {/* 表格 */}
      {usersQuery.isLoading ? (
        <div aria-busy='true' className='overflow-hidden rounded-lg border'>
          {Array.from({ length: 5 }).map((_, index) => (
            <div key={index} className='flex gap-4 border-b p-4 last:border-0'>
              <Skeleton className='h-4 w-4' />
              <Skeleton className='h-5 w-40' />
              <Skeleton className='h-5 flex-1' />
              <Skeleton className='h-5 w-20' />
            </div>
          ))}
        </div>
      ) : (usersQuery.data?.length ?? 0) === 0 ? (
        <Empty className='min-h-[240px] border-dashed'>
          <EmptyHeader>
            <EmptyMedia variant='icon'>
              <UsersIcon className='size-4' />
            </EmptyMedia>
            <EmptyTitle>
              {keyword || status !== 'all' || roleCodes.length > 0
                ? '未找到匹配的用户'
                : '暂无用户'}
            </EmptyTitle>
            <EmptyDescription>
              {keyword || status !== 'all' || roleCodes.length > 0
                ? '换个关键词或清除筛选条件试试'
                : '点击「新建用户」创建平台账号'}
            </EmptyDescription>
          </EmptyHeader>
          <EmptyContent />
        </Empty>
      ) : (
        <div className='overflow-hidden rounded-lg border'>
          <div className='overflow-x-auto'>
            <table className='w-full min-w-[760px] text-sm'>
              <thead>
                <tr className='text-muted-foreground border-b bg-muted/30'>
                  <th className='w-11 px-3 py-2.5 text-left'>
                    <Checkbox
                      aria-label='全选'
                      checked={
                        (usersQuery.data ?? []).length > 0 &&
                        (usersQuery.data ?? []).every((i) =>
                          selectedIds.includes(i.id)
                        )
                      }
                      onCheckedChange={toggleAll}
                    />
                  </th>
                  <th className='px-3 py-2.5 text-left font-medium'>用户名</th>
                  <th className='px-3 py-2.5 text-left font-medium'>邮箱</th>
                  <th className='px-3 py-2.5 text-left font-medium'>角色</th>
                  <th className='px-3 py-2.5 text-left font-medium'>状态</th>
                  <th className='px-3 py-2.5 text-left font-medium'>附加权限数</th>
                  <th className='px-3 py-2.5 text-left font-medium'>注册时间</th>
                  <th className='w-12 px-3 py-2.5' />
                </tr>
              </thead>
              <tbody>
                {(usersQuery.data ?? []).map((user) => {
                  const isSelf = currentUser?.id === user.id
                  const roleBadgeVariant =
                    user.roleCode === 'admin'
                      ? 'default'
                      : user.roleCode === 'tester'
                        ? 'secondary'
                        : 'outline'
                  const statusVariant =
                    user.status === 'active'
                      ? 'success'
                      : user.status === 'disabled'
                        ? 'neutral'
                        : 'warning'
                  return (
                    <tr
                      key={user.id}
                      className={cn(
                        'hover:bg-muted/30 border-b transition-colors last:border-0',
                        selectedIds.includes(user.id) && 'bg-primary/5'
                      )}
                    >
                      <td className='px-3 py-3'>
                        <Checkbox
                          aria-label={`选择用户 ${user.username}`}
                          checked={selectedIds.includes(user.id)}
                          onCheckedChange={() => toggleRow(user.id)}
                        />
                      </td>
                      <td className='max-w-[200px] px-3 py-3'>
                        <div className='truncate font-medium'>{user.username}</div>
                        <div className='text-muted-foreground truncate text-xs'>
                          {user.displayName}
                        </div>
                      </td>
                      <td className='px-3 py-3'>
                        <span className='text-muted-foreground text-xs'>
                          {user.email}
                        </span>
                      </td>
                      <td className='px-3 py-3'>
                        <Badge variant={roleBadgeVariant}>{user.roleName}</Badge>
                      </td>
                      <td className='px-3 py-3'>
                        <StatusBadge
                          label={USER_STATUS_META[user.status].label}
                          variant={statusVariant}
                        />
                      </td>
                      <td className='px-3 py-3'>
                        <span className='font-mono tabular-nums'>
                          {user.extraPermissions.length}
                        </span>
                      </td>
                      <td className='px-3 py-3'>
                        <span className='text-muted-foreground font-mono text-xs tabular-nums'>
                          {user.createdAt.slice(0, 10)}
                        </span>
                      </td>
                      <td className='px-3 py-3 text-right'>
                        <DropdownMenu modal={false}>
                          <DropdownMenuTrigger
                            render={
                              <Button
                                variant='ghost'
                                size='icon-sm'
                                aria-label={`用户操作：${user.username}`}
                              />
                            }
                          >
                            <Ellipsis className='size-4' />
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align='end' className='w-44'>
                            {canUpdate && (
                              <DropdownMenuItem
                                onClick={() => handleRowAction(user, 'edit')}
                              >
                                编辑
                              </DropdownMenuItem>
                            )}
                            {canAssignRole && !isSelf && (
                              <DropdownMenuItem
                                onClick={() => openEdit(user)}
                              >
                                分配角色
                              </DropdownMenuItem>
                            )}
                            {canGrant && (
                              <DropdownMenuItem
                                onClick={() => openEdit(user)}
                              >
                                附加权限
                              </DropdownMenuItem>
                            )}
                            {canUpdate && (
                              <DropdownMenuItem
                                onClick={() => handleRowAction(user, 'toggle-status')}
                              >
                                {user.status === 'active' ? '停用' : '启用'}
                              </DropdownMenuItem>
                            )}
                            <DropdownMenuSeparator />
                            {canDelete && !isSelf && (
                              <DropdownMenuItem
                                variant='destructive'
                                onClick={() => handleRowAction(user, 'delete')}
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

      {/* 新建/编辑抽屉 */}
      <UserMutateDrawer
        open={drawerOpen}
        mode={drawerMode}
        user={drawerMode === 'edit' ? (detailQuery.data ?? drawerUser) : drawerUser}
        roles={rolesQuery.data ?? []}
        permissionModules={permissionCatalogQuery.data ?? []}
        onOpenChange={closeDrawer}
        onCreate={(input) => {
          mutations.createUser.mutate({ ...input, roleId: roleIdOf(input.roleCode) })
          closeDrawer()
        }}
        onUpdate={(userId, patch) => {
          mutations.updateUser.mutate({ userId, patch })
          closeDrawer()
        }}
        onAssignRole={(userId, roleCode) => {
          mutations.assignRole.mutate({ userId, roleId: roleIdOf(roleCode) ?? 0 })
          closeDrawer()
        }}
        onGrantPermissions={(userId, permissions) => {
          mutations.grantPermissions.mutate({ userId, permissions })
          closeDrawer()
        }}
      />

      {/* 删除确认 */}
      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null)
        }}
        title='确认删除用户'
        desc={
          deleteTarget
            ? `将永久删除用户 ${deleteTarget.username}，该操作不可恢复。`
            : ''
        }
        destructive
        cancelBtnText='取消'
        confirmText='删除'
        isLoading={mutations.deleteUser.isPending}
        handleConfirm={() => {
          if (deleteTarget) mutations.deleteUser.mutate(deleteTarget.id)
          setDeleteTarget(null)
        }}
      />
    </SettingsSection>
  )
}
