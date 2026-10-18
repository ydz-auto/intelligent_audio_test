/**
 * 角色/权限目录 query + 角色 mutation（application 层，INT-729 接线后）：
 * GET /auth/roles（role:read，回 permissions 码列表 + is_system）、
 * GET /auth/permissions（permission:read，权限点目录只读）；
 * POST /auth/roles/{id}/permissions 全量替换；角色变更后 invalidate roles 缓存
 * 联动用户抽屉角色下拉。
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
    mutationFn: (input: { name: string; description: string; permissions: string[] }) =>
      createRole(input),
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

  const setPermissionsMutation = useMutation({
    mutationFn: (args: { roleId: string; permissions: string[] }) =>
      setRolePermissions(args.roleId, args.permissions),
    onSuccess: () => {
      toast.success('角色权限已更新')
      invalidateRoles()
    },
    onError: () => toast.error('角色保存失败'),
  })

  const deleteRoleMutation = useMutation({
    mutationFn: (roleId: string) => deleteRole(roleId),
    onSuccess: () => {
      toast.success('角色已删除')
      invalidateRoles()
    },
    onError: (error: unknown) => {
      const message =
        error instanceof Error && error.message
          ? error.message
          : '角色保存失败'
      toast.error(message)
    },
  })

  return {
    createRole: createRoleMutation,
    updateRole: updateRoleMutation,
    setPermissions: setPermissionsMutation,
    deleteRole: deleteRoleMutation,
  }
}

export type { PlatformRole }
