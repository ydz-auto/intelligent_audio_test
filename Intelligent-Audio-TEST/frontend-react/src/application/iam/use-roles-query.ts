/**
 * 角色/权限目录 query + 角色 mutation（application 层，INT-347 §4.4.2）：
 * GET /roles（role:read，回 permissions 码列表 + is_system）、GET /permissions
 * （permission:read，权限点目录只读）；POST /roles/{id}/permissions 全量替换；
 * 角色变更后 invalidate roles 缓存联动用户抽屉角色下拉。
 * 接线 INT-651：全部走真实 API（roleApi.ts），mock 已移除。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { PlatformRole } from '@/domain/models/role'
import {
  createRole,
  deleteRole,
  getPermissionCatalog,
  getRoles,
  PERMISSION_CATALOG_QUERY_KEY,
  ROLES_QUERY_KEY,
  setRolePermissions,
  updateRole,
} from '@/infrastructure/api/roleApi'

export function useRolesQuery() {
  return useQuery({
    queryKey: [...ROLES_QUERY_KEY],
    queryFn: getRoles,
    staleTime: 30_000,
  })
}

export function usePermissionCatalogQuery() {
  return useQuery({
    queryKey: [...PERMISSION_CATALOG_QUERY_KEY],
    queryFn: getPermissionCatalog,
    staleTime: Infinity,
  })
}

export function useRoleMutations() {
  const queryClient = useQueryClient()

  const invalidateRoles = () =>
    void queryClient.invalidateQueries({ queryKey: ROLES_QUERY_KEY })

  const createRoleMutation = useMutation({
    mutationFn: createRole,
    onSuccess: () => {
      toast.success('角色已创建')
      invalidateRoles()
    },
    onError: () => toast.error('角色保存失败'),
  })

  const updateRoleMutation = useMutation({
    mutationFn: (args: { roleId: string; patch: { name?: string; description?: string } }) =>
      updateRole(args.roleId, args.patch),
    onSuccess: () => {
      toast.success('角色权限已更新')
      invalidateRoles()
    },
    onError: () => toast.error('角色保存失败'),
  })

  const setPermissions = useMutation({
    mutationFn: (args: { roleId: string; permissions: string[] }) =>
      setRolePermissions(args.roleId, args.permissions),
    onSuccess: () => {
      toast.success('角色权限已更新')
      invalidateRoles()
    },
    onError: () => toast.error('角色保存失败'),
  })

  const deleteRoleMutation = useMutation({
    mutationFn: deleteRole,
    onSuccess: () => {
      toast.success('角色已删除')
      invalidateRoles()
    },
    onError: (error: unknown) => {
      const message =
        error instanceof Error && error.message ? error.message : '角色保存失败'
      toast.error(message)
    },
  })

  return {
    createRole: createRoleMutation,
    updateRole: updateRoleMutation,
    setPermissions,
    deleteRole: deleteRoleMutation,
  }
}

export type { PlatformRole }
