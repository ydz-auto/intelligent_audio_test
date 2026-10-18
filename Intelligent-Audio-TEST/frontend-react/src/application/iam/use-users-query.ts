/**
 * 用户管理 query/mutations（application 层，接线 INT-651）：
 * 列表 GET /auth/users（分页 ≤100 + status/keyword/role_id 过滤，INT-347 §4.4.1）；
 * 详情 GET /auth/users/{id}（overrides → 抽屉附加权限回填）；
 * 行操作分走 PUT/POST/DELETE；成功 toast + invalidate 联动（对齐 newAPI
 * users-provider triggerRefresh 模式）。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import type { PlatformUser } from '@/domain/models/user'
import {
  assignRole,
  createUser,
  deleteUser,
  getUser,
  getUsers,
  grantPermissions,
  updateUser,
  USERS_QUERY_KEY,
  type UserListFilter,
} from '@/infrastructure/api/userApi'

export function useUsersQuery(filter: UserListFilter) {
  return useQuery({
    queryKey: [...USERS_QUERY_KEY, filter],
    queryFn: () => getUsers(filter),
    staleTime: 30_000,
  })
}

/** 用户详情（抽屉编辑回填附加权限；列表响应不含 overrides，需详情端点） */
export function useUserDetail(userId: string | null) {
  return useQuery({
    queryKey: [...USERS_QUERY_KEY, 'detail', userId],
    queryFn: () => (userId ? getUser(userId) : Promise.resolve(null)),
    enabled: !!userId,
  })
}

export function useUserMutations() {
  const queryClient = useQueryClient()

  const invalidateUsers = () =>
    void queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY })

  const createUserMutation = useMutation({
    mutationFn: createUser,
    onSuccess: () => {
      toast.success('用户已创建')
      invalidateUsers()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  const updateUserMutation = useMutation({
    mutationFn: (args: {
      userId: string
      patch: Partial<
        Pick<
          PlatformUser,
          'displayName' | 'email' | 'status' | 'roleCode' | 'roleName'
        >
      >
    }) => updateUser(args.userId, args.patch),
    onSuccess: () => {
      toast.success('用户已更新')
      invalidateUsers()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  const assignRoleMutation = useMutation({
    mutationFn: (args: { userId: string; roleId: number }) =>
      assignRole(args.userId, args.roleId),
    onSuccess: () => {
      toast.success('用户角色已更新')
      invalidateUsers()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  const grantPermissionsMutation = useMutation({
    mutationFn: (args: { userId: string; permissions: string[] }) =>
      grantPermissions(args.userId, args.permissions),
    onSuccess: () => {
      toast.success('附加权限已授予')
      invalidateUsers()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  const deleteUserMutation = useMutation({
    mutationFn: deleteUser,
    onSuccess: () => {
      toast.success('用户已删除')
      invalidateUsers()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  return {
    createUser: createUserMutation,
    updateUser: updateUserMutation,
    assignRole: assignRoleMutation,
    grantPermissions: grantPermissionsMutation,
    deleteUser: deleteUserMutation,
  }
}
