/**
 * 用户管理 query/mutations（application 层，INT-729 接线后）：
 * 列表 GET /auth/users（分页 ≤100 + status/keyword 下推、roleCodes 客户端
 * 二次过滤）；详情 GET /auth/users/{id}（overrides 附加权限回填编辑抽屉）；
 * 行操作分走 POST/PUT/DELETE；成功 toast + invalidate 联动（对齐 newAPI
 * users-provider triggerRefresh 模式）。
 */
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'

import {
  assignRole,
  createUser,
  deleteUser,
  getUserDetail,
  getUsers,
  grantPermissions,
  updateUser,
  USERS_QUERY_KEY,
  type UserListFilter,
} from '@/infrastructure/api/userApi'
import type { PlatformUser, PlatformUserStatus } from '@/domain/models/user'

export function useUsersQuery(filter: UserListFilter) {
  return useQuery({
    queryKey: [...USERS_QUERY_KEY, filter],
    queryFn: () => getUsers(filter),
    staleTime: 30_000,
  })
}

export function useUserDetailQuery(userId: string | null) {
  return useQuery({
    queryKey: ['iam', 'user-detail', userId],
    queryFn: () => getUserDetail(userId as string),
    enabled: !!userId,
    staleTime: 30_000,
  })
}

export type CreateUserInput = {
  username: string
  displayName?: string
  email: string
  password: string
  roleId?: number
  status: PlatformUserStatus
}

export function useUserMutations() {
  const queryClient = useQueryClient()

  const invalidateUsers = () =>
    void queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY })

  const createUserMutation = useMutation({
    mutationFn: (input: CreateUserInput) => createUser(input),
    onSuccess: () => {
      toast.success('用户已创建')
      invalidateUsers()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  const updateUserMutation = useMutation({
    mutationFn: (args: {
      userId: string
      patch: Partial<Pick<PlatformUser, 'displayName' | 'email' | 'status'>>
    }) => updateUser(args.userId, args.patch),
    onSuccess: () => {
      toast.success('用户已更新')
      invalidateUsers()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  const assignRoleMutation = useMutation({
    mutationFn: (args: { userId: string; roleCode: string }) =>
      assignRole(args.userId, args.roleCode),
    onSuccess: () => {
      toast.success('用户角色已更新')
      invalidateUsers()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  const grantPermissionsMutation = useMutation({
    mutationFn: (args: {
      userId: string
      permissions: string[]
      previousPermissions?: string[]
    }) => grantPermissions(args.userId, args.permissions, args.previousPermissions),
    onSuccess: () => {
      toast.success('附加权限已授予')
      invalidateUsers()
    },
    onError: () => toast.error('操作失败，请稍后重试'),
  })

  const deleteUserMutation = useMutation({
    mutationFn: (userId: string) => deleteUser(userId),
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
